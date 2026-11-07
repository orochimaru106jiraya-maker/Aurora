"""
Join-to-Create (JTC) Temporary Voice Channel Cog (`/jtc`) for Cosmic ki baddie.

Implements all 16 required `/jtc` slash commands:
- `/jtc setup`
- `/jtc config`
- `/jtc enable`
- `/jtc disable`
- `/jtc panel`
- `/jtc list`
- `/jtc rename`
- `/jtc limit`
- `/jtc lock`
- `/jtc unlock`
- `/jtc hide`
- `/jtc unhide`
- `/jtc add`
- `/jtc remove`
- `/jtc transfer`
- `/jtc delete`
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from bot.core.discord_compat import app_commands, commands, discord
from bot.database.models import PermissionLevel
from bot.ui.persistent_views import PersistentJTCControlView
from bot.utils.checks import require_permission_level

if TYPE_CHECKING:
    from bot.core.bot import CosmicBot


class JTCCog(commands.Cog):
    """Join-to-Create temporary voice channel system and room control panel."""

    jtc_group = app_commands.Group(
        name="jtc",
        description="Manage Join-to-Create voice hubs and personal temporary voice rooms.",
    )

    def __init__(self, bot: "CosmicBot") -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: Any, after: Any) -> None:
        guild = getattr(member, "guild", None)
        if guild is None or getattr(member, "bot", False):
            return

        before_ch = getattr(before, "channel", None)
        after_ch = getattr(after, "channel", None)

        # If user joined a JTC trigger channel, spawn room
        if after_ch is not None and (before_ch is None or int(before_ch.id) != int(after_ch.id)):
            await self.bot.jtc_service.handle_user_join_trigger(guild, member, int(after_ch.id))

        # If user left a JTC active room, clean up if empty
        if before_ch is not None and (after_ch is None or int(before_ch.id) != int(after_ch.id)):
            await self.bot.jtc_service.cleanup_if_empty(guild, int(before_ch.id))

    async def _get_managed_voice_channel(self, interaction: discord.Interaction) -> Optional[discord.VoiceChannel]:
        if interaction.guild is None:
            return None
        voice_state = getattr(interaction.user, "voice", None)
        voice_ch = getattr(voice_state, "channel", None) if voice_state else None
        if voice_ch is None:
            # Check if user owns an active room in this guild
            owned = await self.bot.db.fetch_one(
                "SELECT channel_id FROM jtc_active_rooms WHERE guild_id = ? AND owner_id = ? LIMIT 1;",
                (int(interaction.guild.id), int(interaction.user.id)),
            )
            if owned:
                voice_ch = interaction.guild.get_channel(int(owned["channel_id"]))
        if voice_ch is None:
            await interaction.response.send_message(
                "You must be inside your Join-to-Create voice room to run this command.",
                ephemeral=True,
            )
            return None

        can_manage, reason = await self.bot.jtc_service.can_manage_room(
            interaction.guild,
            interaction.user,
            int(voice_ch.id),
            self.bot.permission_service,
        )
        if not can_manage:
            await interaction.response.send_message(reason, ephemeral=True)
            return None
        return voice_ch

    @jtc_group.command(name="setup", description="Set up a Join-to-Create trigger voice channel and optional category.")
    @app_commands.describe(
        trigger_channel="Designated voice channel users join to create their own room",
        category="Category where temporary voice rooms will be spawned",
        hub_name="Display name for this JTC hub",
    )
    @require_permission_level(PermissionLevel.ADMIN, module_name="jtc")
    async def jtc_setup(
        self,
        interaction: discord.Interaction,
        trigger_channel: discord.VoiceChannel,
        category: Optional[discord.CategoryChannel] = None,
        hub_name: str = "Main Voice Hub",
    ) -> None:
        if interaction.guild is None:
            return
        hub = await self.bot.jtc_service.create_or_update_hub(
            guild_id=int(interaction.guild.id),
            trigger_channel_id=int(trigger_channel.id),
            target_category_id=int(category.id) if category else None,
            hub_name=hub_name,
        )
        embed = discord.Embed(
            title=f"Join-to-Create Hub Configured — {hub_name}",
            description=(
                f"Trigger Channel: {trigger_channel.mention}\n"
                f"Category: {category.name if category else 'Server Default'}\n"
                f"Naming Format: `{hub.get('naming_format')}`"
            ),
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @jtc_group.command(name="config", description="Update naming format, default user limit, cooldown, and max rooms for a JTC hub.")
    @app_commands.describe(
        trigger_channel="The JTC trigger channel to configure",
        naming_format="Channel name template (e.g. {username}'s Room)",
        default_limit="Default user limit (0 = unlimited, 1-99)",
        cooldown_seconds="Creation cooldown per user in seconds",
        max_active_rooms="Maximum simultaneous temporary rooms in this server",
    )
    @require_permission_level(PermissionLevel.ADMIN, module_name="jtc")
    async def jtc_config(
        self,
        interaction: discord.Interaction,
        trigger_channel: discord.VoiceChannel,
        naming_format: str = "{username}'s Room",
        default_limit: int = 0,
        cooldown_seconds: int = 10,
        max_active_rooms: int = 25,
    ) -> None:
        if interaction.guild is None:
            return
        hub = await self.bot.jtc_service.create_or_update_hub(
            guild_id=int(interaction.guild.id),
            trigger_channel_id=int(trigger_channel.id),
            naming_format=naming_format,
            default_limit=max(0, min(99, default_limit)),
            cooldown_seconds=max(0, cooldown_seconds),
            max_active_rooms=max(1, max_active_rooms),
        )
        await interaction.response.send_message(
            f"Updated JTC hub on {trigger_channel.mention}: format=`{hub['naming_format']}`, limit=`{hub['default_limit']}`, max_rooms=`{hub['max_active_rooms']}`.",
            ephemeral=True,
        )

    @jtc_group.command(name="enable", description="Enable all Join-to-Create hubs in this server.")
    @require_permission_level(PermissionLevel.ADMIN, module_name="jtc")
    async def jtc_enable(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        await self.bot.db.execute("UPDATE jtc_configs SET enabled = 1 WHERE guild_id = ?;", (int(interaction.guild.id),))
        await interaction.response.send_message("Enabled Join-to-Create voice hubs for this server.", ephemeral=True)

    @jtc_group.command(name="disable", description="Disable all Join-to-Create hubs in this server.")
    @require_permission_level(PermissionLevel.ADMIN, module_name="jtc")
    async def jtc_disable(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        await self.bot.db.execute("UPDATE jtc_configs SET enabled = 0 WHERE guild_id = ?;", (int(interaction.guild.id),))
        await interaction.response.send_message("Disabled Join-to-Create voice hubs for this server.", ephemeral=True)

    @jtc_group.command(name="panel", description="Publish the interactive Join-to-Create Voice Room Control Panel.")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="jtc")
    async def jtc_panel(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Join-to-Create — Voice Room Control Panel",
            description=(
                "Manage your personal temporary voice room using the controls below.\n"
                "Only the room owner or server moderators can lock, hide, or modify a room."
            ),
            color=discord.Color.blurple(),
        )
        await interaction.channel.send(embed=embed, view=PersistentJTCControlView(self.bot))
        await interaction.response.send_message("Published JTC Voice Control Panel.", ephemeral=True)

    @jtc_group.command(name="list", description="List all configured JTC hubs and active temporary voice rooms.")
    async def jtc_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        hubs = await self.bot.jtc_service.get_guild_hubs(int(interaction.guild.id))
        rooms = await self.bot.jtc_service.get_active_rooms(int(interaction.guild.id))
        embed = discord.Embed(
            title=f"Join-to-Create Status — {interaction.guild.name}",
            color=discord.Color.blurple(),
        )
        hub_lines = [
            f"• **{h['hub_name']}**: Trigger <#{h['trigger_channel_id']}> · Format `{h['naming_format']}` · {'Enabled' if h['enabled'] else 'Disabled'}"
            for h in hubs
        ] or ["No JTC hubs configured yet. Run `/jtc setup`."]
        room_lines = [
            f"• <#{r['channel_id']}> · Owner: <@{r['owner_id']}> · Locked: `{bool(r['is_locked'])}`"
            for r in rooms
        ] or ["No active temporary rooms right now."]
        embed.add_field(name=f"Configured Hubs ({len(hubs)})", value="\n".join(hub_lines), inline=False)
        embed.add_field(name=f"Active Rooms ({len(rooms)})", value="\n".join(room_lines), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @jtc_group.command(name="rename", description="Rename your active Join-to-Create voice room.")
    @app_commands.describe(name="New name for your voice room")
    async def jtc_rename(self, interaction: discord.Interaction, name: str) -> None:
        vc = await self._get_managed_voice_channel(interaction)
        if vc is None:
            return
        clean = name.strip()[:95] or "Voice Room"
        await vc.edit(name=clean)
        await interaction.response.send_message(f"Renamed your voice room to **{clean}**.", ephemeral=True)

    @jtc_group.command(name="limit", description="Set the user limit (0-99) for your Join-to-Create voice room.")
    @app_commands.describe(limit="Maximum members allowed (0 for unlimited)")
    async def jtc_limit(self, interaction: discord.Interaction, limit: int) -> None:
        vc = await self._get_managed_voice_channel(interaction)
        if vc is None:
            return
        clean_lim = max(0, min(99, int(limit)))
        await vc.edit(user_limit=clean_lim)
        await self.bot.db.execute(
            "UPDATE jtc_active_rooms SET user_limit = ? WHERE channel_id = ?;",
            (clean_lim, int(vc.id)),
        )
        await interaction.response.send_message(f"Updated room user limit to **{clean_lim}**.", ephemeral=True)

    @jtc_group.command(name="lock", description="Lock your Join-to-Create voice room to prevent new users from connecting.")
    async def jtc_lock(self, interaction: discord.Interaction) -> None:
        vc = await self._get_managed_voice_channel(interaction)
        if vc is None or interaction.guild is None:
            return
        await vc.set_permissions(interaction.guild.default_role, connect=False)
        await self.bot.db.execute("UPDATE jtc_active_rooms SET is_locked = 1 WHERE channel_id = ?;", (int(vc.id),))
        await interaction.response.send_message(f"Locked {vc.mention}.", ephemeral=True)

    @jtc_group.command(name="unlock", description="Unlock your Join-to-Create voice room.")
    async def jtc_unlock(self, interaction: discord.Interaction) -> None:
        vc = await self._get_managed_voice_channel(interaction)
        if vc is None or interaction.guild is None:
            return
        await vc.set_permissions(interaction.guild.default_role, connect=True)
        await self.bot.db.execute("UPDATE jtc_active_rooms SET is_locked = 0 WHERE channel_id = ?;", (int(vc.id),))
        await interaction.response.send_message(f"Unlocked {vc.mention}.", ephemeral=True)

    @jtc_group.command(name="hide", description="Hide your Join-to-Create voice room from the channel list.")
    async def jtc_hide(self, interaction: discord.Interaction) -> None:
        vc = await self._get_managed_voice_channel(interaction)
        if vc is None or interaction.guild is None:
            return
        await vc.set_permissions(interaction.guild.default_role, view_channel=False)
        await self.bot.db.execute("UPDATE jtc_active_rooms SET is_hidden = 1 WHERE channel_id = ?;", (int(vc.id),))
        await interaction.response.send_message(f"Hidden {vc.mention}.", ephemeral=True)

    @jtc_group.command(name="unhide", description="Make your Join-to-Create voice room visible to the server.")
    async def jtc_unhide(self, interaction: discord.Interaction) -> None:
        vc = await self._get_managed_voice_channel(interaction)
        if vc is None or interaction.guild is None:
            return
        await vc.set_permissions(interaction.guild.default_role, view_channel=True)
        await self.bot.db.execute("UPDATE jtc_active_rooms SET is_hidden = 0 WHERE channel_id = ?;", (int(vc.id),))
        await interaction.response.send_message(f"Unhidden {vc.mention}.", ephemeral=True)

    @jtc_group.command(name="add", description="Permit a specific member to view and connect to your locked/hidden voice room.")
    @app_commands.describe(member="Member to permit into your room")
    async def jtc_add(self, interaction: discord.Interaction, member: discord.Member) -> None:
        vc = await self._get_managed_voice_channel(interaction)
        if vc is None:
            return
        await vc.set_permissions(member, view_channel=True, connect=True, speak=True)
        await interaction.response.send_message(f"Granted {member.mention} access to {vc.mention}.", ephemeral=True)

    @jtc_group.command(name="remove", description="Revoke a member's access to your voice room and disconnect them.")
    @app_commands.describe(member="Member to remove from your room")
    async def jtc_remove(self, interaction: discord.Interaction, member: discord.Member) -> None:
        vc = await self._get_managed_voice_channel(interaction)
        if vc is None:
            return
        await vc.set_permissions(member, connect=False)
        if member in getattr(vc, "members", []):
            await member.move_to(None, reason="Removed by JTC room owner")
        await interaction.response.send_message(f"Removed {member.mention} from {vc.mention}.", ephemeral=True)

    @jtc_group.command(name="transfer", description="Transfer ownership of your Join-to-Create room to another member.")
    @app_commands.describe(new_owner="Member who will become the new room owner")
    async def jtc_transfer(self, interaction: discord.Interaction, new_owner: discord.Member) -> None:
        vc = await self._get_managed_voice_channel(interaction)
        if vc is None:
            return
        await self.bot.db.execute(
            "UPDATE jtc_active_rooms SET owner_id = ? WHERE channel_id = ?;",
            (int(new_owner.id), int(vc.id)),
        )
        await vc.set_permissions(new_owner, view_channel=True, connect=True, manage_channels=True, move_members=True)
        await interaction.response.send_message(
            f"Transferred ownership of {vc.mention} to {new_owner.mention}."
        )

    @jtc_group.command(name="delete", description="Immediately delete your active Join-to-Create voice room.")
    async def jtc_delete(self, interaction: discord.Interaction) -> None:
        vc = await self._get_managed_voice_channel(interaction)
        if vc is None:
            return
        await self.bot.db.execute("DELETE FROM jtc_active_rooms WHERE channel_id = ?;", (int(vc.id),))
        await interaction.response.send_message(f"Deleting temporary room `{vc.name}`...", ephemeral=True)
        await vc.delete(reason=f"Deleted by room owner {interaction.user.name}")


async def setup(bot: "CosmicBot") -> None:
    await bot.add_cog(JTCCog(bot))
