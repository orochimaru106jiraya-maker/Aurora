"""
Advanced Moderation Cog for Cosmic ki baddie.

Implements all 19 required moderation slash commands:
- `/ban`
- `/unban`
- `/kick`
- `/timeout`
- `/untimeout`
- `/warn`
- `/warnings`
- `/clearwarnings`
- `/purge`
- `/snipe`
- `/editsnipe`
- `/lock`
- `/unlock`
- `/slowmode`
- `/hide`
- `/unhide`
- `/modlogs`
- `/case`
- `/clearcases`

Enforces:
- Strict role hierarchy protection (`validate_role_hierarchy`)
- SQLite case management & configurable mod log channel
- Deleted and edited message listeners (`on_message_delete`, `on_message_edit`)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from bot.core.discord_compat import app_commands, commands, discord
from bot.core.error_handler import HierarchyViolationError
from bot.database.models import PermissionLevel
from bot.ui.confirmations import ConfirmationView
from bot.utils.checks import require_permission_level
from bot.utils.formatting import format_duration, parse_duration_seconds
from bot.utils.validators import validate_role_hierarchy

if TYPE_CHECKING:
    from bot.core.bot import CosmicBot


class ModerationCog(commands.Cog):
    """Comprehensive Server Moderation, Case Management, and Snipe Tracking."""

    def __init__(self, bot: "CosmicBot") -> None:
        self.bot = bot

    def _enforce_hierarchy(self, interaction: discord.Interaction, target: discord.Member) -> None:
        ok, msg = validate_role_hierarchy(
            actor=interaction.user,
            target=target,
            guild=interaction.guild,
            bot_owner_id=self.bot.config.bot_owner_id,
        )
        if not ok:
            raise HierarchyViolationError(msg)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if getattr(message, "guild", None) is None or getattr(getattr(message, "author", None), "bot", False):
            return
        attachments = [getattr(a, "url", "") for a in getattr(message, "attachments", []) if getattr(a, "url", "")]
        await self.bot.logging_service.record_snipe_event(
            guild_id=int(message.guild.id),
            channel_id=int(message.channel.id),
            author_id=int(message.author.id),
            author_name=getattr(message.author, "name", "User"),
            event_type="delete",
            old_content=getattr(message, "content", ""),
            attachment_urls=attachments,
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if getattr(before, "guild", None) is None or getattr(getattr(before, "author", None), "bot", False):
            return
        if getattr(before, "content", "") == getattr(after, "content", ""):
            return
        await self.bot.logging_service.record_snipe_event(
            guild_id=int(before.guild.id),
            channel_id=int(before.channel.id),
            author_id=int(before.author.id),
            author_name=getattr(before.author, "name", "User"),
            event_type="edit",
            old_content=getattr(before, "content", ""),
            new_content=getattr(after, "content", ""),
        )

    @app_commands.command(name="ban", description="Ban a member from the server with hierarchy protection and case logging.")
    @app_commands.describe(member="Member to ban", reason="Reason for the ban", delete_days="Days of messages to purge (0-7)")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="moderation")
    async def ban_command(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Violation of server rules",
        delete_days: int = 0,
    ) -> None:
        if interaction.guild is None:
            return
        self._enforce_hierarchy(interaction, member)
        clean_days = max(0, min(7, int(delete_days)))
        await member.ban(reason=f"By {interaction.user.name}: {reason}", delete_message_days=clean_days)
        case = await self.bot.logging_service.create_moderation_case(
            guild=interaction.guild,
            action_type="ban",
            target_user=member,
            moderator=interaction.user,
            reason=reason,
        )
        embed = discord.Embed(
            title=f"Case #{case['case_number']} — Member Banned",
            description=f"Target: {member.mention} (`{member.id}`)\nModerator: {interaction.user.mention}\nReason: {reason}",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="unban", description="Unban a user by their Discord User ID.")
    @app_commands.describe(user_id="Discord User ID to unban", reason="Reason for unbanning")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="moderation")
    async def unban_command(
        self,
        interaction: discord.Interaction,
        user_id: str,
        reason: str = "Appeal approved",
    ) -> None:
        if interaction.guild is None or not user_id.strip().isdigit():
            await interaction.response.send_message("Provide a valid numeric Discord User ID.", ephemeral=True)
            return
        uid = int(user_id.strip())
        target_obj = discord.Object(id=uid)
        await interaction.guild.unban(target_obj, reason=f"By {interaction.user.name}: {reason}")
        case = await self.bot.logging_service.create_moderation_case(
            guild=interaction.guild,
            action_type="unban",
            target_user=target_obj,
            moderator=interaction.user,
            reason=reason,
        )
        await interaction.response.send_message(f"Case `#{case['case_number']}`: Unbanned user `<@{uid}>` (`{uid}`).")

    @app_commands.command(name="kick", description="Kick a member from the server with hierarchy protection.")
    @app_commands.describe(member="Member to kick", reason="Reason for kicking")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="moderation")
    async def kick_command(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Kicked by moderator",
    ) -> None:
        if interaction.guild is None:
            return
        self._enforce_hierarchy(interaction, member)
        await member.kick(reason=f"By {interaction.user.name}: {reason}")
        case = await self.bot.logging_service.create_moderation_case(
            guild=interaction.guild,
            action_type="kick",
            target_user=member,
            moderator=interaction.user,
            reason=reason,
        )
        await interaction.response.send_message(
            f"Case `#{case['case_number']}`: Kicked {member.mention} (`{member.id}`). Reason: {reason}"
        )

    @app_commands.command(name="timeout", description="Timeout (mute) a member for a specified duration (e.g. 10m, 2h, 7d).")
    @app_commands.describe(member="Member to timeout", duration="Duration string (e.g. 15m, 1h, 3d)", reason="Reason for timeout")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="moderation")
    async def timeout_command(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: str = "10m",
        reason: str = "Timed out by moderator",
    ) -> None:
        if interaction.guild is None:
            return
        self._enforce_hierarchy(interaction, member)
        secs = parse_duration_seconds(duration)
        if not secs or secs > 28 * 86400:
            await interaction.response.send_message(
                "Invalid duration. Specify between `10s` and `28d` (e.g. `15m`, `2h`, `7d`).",
                ephemeral=True,
            )
            return
        until = datetime.now(timezone.utc) + timedelta(seconds=secs)
        await member.timeout(until, reason=f"By {interaction.user.name}: {reason}")
        case = await self.bot.logging_service.create_moderation_case(
            guild=interaction.guild,
            action_type="timeout",
            target_user=member,
            moderator=interaction.user,
            reason=reason,
            duration_seconds=secs,
        )
        await interaction.response.send_message(
            f"Case `#{case['case_number']}`: Timed out {member.mention} for **{format_duration(secs)}**. Reason: {reason}"
        )

    @app_commands.command(name="untimeout", description="Remove an active timeout from a member.")
    @app_commands.describe(member="Member to remove timeout from", reason="Reason for removing timeout")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="moderation")
    async def untimeout_command(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Timeout lifted early",
    ) -> None:
        if interaction.guild is None:
            return
        self._enforce_hierarchy(interaction, member)
        await member.timeout(None, reason=f"By {interaction.user.name}: {reason}")
        case = await self.bot.logging_service.create_moderation_case(
            guild=interaction.guild,
            action_type="untimeout",
            target_user=member,
            moderator=interaction.user,
            reason=reason,
        )
        await interaction.response.send_message(
            f"Case `#{case['case_number']}`: Removed timeout from {member.mention}."
        )

    @app_commands.command(name="warn", description="Issue a formal warning to a member and record it in SQLite.")
    @app_commands.describe(member="Member to warn", reason="Warning reason")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="moderation")
    async def warn_command(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
    ) -> None:
        if interaction.guild is None:
            return
        self._enforce_hierarchy(interaction, member)
        case = await self.bot.logging_service.create_moderation_case(
            guild=interaction.guild,
            action_type="warn",
            target_user=member,
            moderator=interaction.user,
            reason=reason,
        )
        await interaction.response.send_message(
            f"Case `#{case['case_number']}`: Warned {member.mention}. Reason: {reason}"
        )

    @app_commands.command(name="warnings", description="View all active warnings for a member.")
    @app_commands.describe(member="Member to inspect")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="moderation")
    async def warnings_command(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if interaction.guild is None:
            return
        rows = await self.bot.db.fetch_all(
            """
            SELECT * FROM moderation_cases
            WHERE guild_id = ? AND target_user_id = ? AND action_type = 'warn' AND active = 1
            ORDER BY case_number DESC;
            """,
            (int(interaction.guild.id), int(member.id)),
        )
        embed = discord.Embed(
            title=f"Active Warnings for {member.name} ({len(rows)})",
            color=discord.Color.gold(),
        )
        if not rows:
            embed.description = f"{member.mention} has no active warnings."
        else:
            embed.description = "\n".join(
                f"`Case #{r['case_number']}` · By <@{r['moderator_id']}> · {r['reason']} ({r['created_at']})"
                for r in rows[:20]
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="clearwarnings", description="Clear all active warnings for a member with confirmation.")
    @app_commands.describe(member="Member whose warnings will be cleared")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="moderation")
    async def clearwarnings_command(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if interaction.guild is None:
            return
        self._enforce_hierarchy(interaction, member)

        async def _do_clear(confirm_inter: discord.Interaction) -> None:
            await self.bot.db.execute(
                "UPDATE moderation_cases SET active = 0 WHERE guild_id = ? AND target_user_id = ? AND action_type = 'warn';",
                (int(interaction.guild.id), int(member.id)),
            )
            embed = discord.Embed(
                title="Warnings Cleared",
                description=f"All active warnings for {member.mention} have been cleared.",
                color=discord.Color.green(),
            )
            await confirm_inter.response.edit_message(embed=embed, view=None)

        view = ConfirmationView(author_id=int(interaction.user.id), on_confirm=_do_clear, confirm_label="Clear Warnings")
        prompt = discord.Embed(
            title="Confirm Clearing Warnings",
            description=f"Clear all active warnings for {member.mention}?",
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=prompt, view=view, ephemeral=True)

    @app_commands.command(name="purge", description="Bulk delete messages in the current channel (1-100, respecting Discord API limits).")
    @app_commands.describe(amount="Number of messages to delete (1-100)")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="moderation")
    async def purge_command(self, interaction: discord.Interaction, amount: int = 10) -> None:
        if interaction.guild is None:
            return
        if amount < 1 or amount > 100:
            await interaction.response.send_message(
                "Discord API limitation: Bulk message purge amount must be between **1** and **100**.",
                ephemeral=True,
            )
            return
        deleted = await interaction.channel.purge(limit=amount)
        await self.bot.logging_service.create_moderation_case(
            guild=interaction.guild,
            action_type="purge",
            target_user=interaction.user,
            moderator=interaction.user,
            reason=f"Purged {len(deleted)} messages in #{getattr(interaction.channel, 'name', 'channel')}",
        )
        await interaction.response.send_message(
            f"Purged **{len(deleted)}** message(s) in {interaction.channel.mention}.",
            ephemeral=True,
        )

    @app_commands.command(name="snipe", description="View recently deleted messages in this channel.")
    @app_commands.describe(index="Position in snipe history (1 = most recent)")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="moderation")
    async def snipe_command(self, interaction: discord.Interaction, index: int = 1) -> None:
        if interaction.guild is None:
            return
        rows = await self.bot.db.fetch_all(
            """
            SELECT * FROM snipe_messages
            WHERE guild_id = ? AND channel_id = ? AND event_type = 'delete'
            ORDER BY id DESC LIMIT 25;
            """,
            (int(interaction.guild.id), int(interaction.channel.id)),
        )
        idx = max(1, index) - 1
        if idx >= len(rows):
            await interaction.response.send_message("No deleted message found at that snipe index.", ephemeral=True)
            return
        rec = rows[idx]
        embed = discord.Embed(
            title=f"Sniped Deleted Message (#{index}/{len(rows)})",
            description=rec["old_content"],
            color=discord.Color.gold(),
        )
        embed.add_field(name="Author", value=f"<@{rec['author_id']}> ({rec['author_name']})", inline=True)
        embed.add_field(name="Deleted At", value=rec["created_at"], inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="editsnipe", description="View recently edited messages (before & after) in this channel.")
    @app_commands.describe(index="Position in edit snipe history (1 = most recent)")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="moderation")
    async def editsnipe_command(self, interaction: discord.Interaction, index: int = 1) -> None:
        if interaction.guild is None:
            return
        rows = await self.bot.db.fetch_all(
            """
            SELECT * FROM snipe_messages
            WHERE guild_id = ? AND channel_id = ? AND event_type = 'edit'
            ORDER BY id DESC LIMIT 25;
            """,
            (int(interaction.guild.id), int(interaction.channel.id)),
        )
        idx = max(1, index) - 1
        if idx >= len(rows):
            await interaction.response.send_message("No edited message found at that index.", ephemeral=True)
            return
        rec = rows[idx]
        embed = discord.Embed(
            title=f"Edit-Sniped Message (#{index}/{len(rows)})",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Author", value=f"<@{rec['author_id']}> ({rec['author_name']})", inline=False)
        embed.add_field(name="Before Edit", value=rec["old_content"][:1024], inline=False)
        embed.add_field(name="After Edit", value=(rec.get("new_content") or "")[:1024], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="lock", description="Lock a text channel so @everyone cannot send messages.")
    @app_commands.describe(channel="Channel to lock (defaults to current)", reason="Reason for locking")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="moderation")
    async def lock_command(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        reason: str = "Channel locked by moderator",
    ) -> None:
        if interaction.guild is None:
            return
        target_ch = channel or interaction.channel
        await target_ch.set_permissions(interaction.guild.default_role, send_messages=False, reason=reason)
        await interaction.response.send_message(f"Locked {target_ch.mention}. Reason: {reason}")

    @app_commands.command(name="unlock", description="Unlock a text channel so @everyone can send messages again.")
    @app_commands.describe(channel="Channel to unlock (defaults to current)", reason="Reason for unlocking")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="moderation")
    async def unlock_command(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        reason: str = "Channel unlocked by moderator",
    ) -> None:
        if interaction.guild is None:
            return
        target_ch = channel or interaction.channel
        await target_ch.set_permissions(interaction.guild.default_role, send_messages=True, reason=reason)
        await interaction.response.send_message(f"Unlocked {target_ch.mention}. Reason: {reason}")

    @app_commands.command(name="slowmode", description="Configure channel slowmode delay in seconds (0-21600).")
    @app_commands.describe(seconds="Slowmode delay in seconds (0 to disable, max 21600)")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="moderation")
    async def slowmode_command(self, interaction: discord.Interaction, seconds: int = 0) -> None:
        clean_sec = max(0, min(21600, int(seconds)))
        await interaction.channel.edit(slowmode_delay=clean_sec)
        await interaction.response.send_message(
            f"Set slowmode in {interaction.channel.mention} to **{clean_sec}s**."
        )

    @app_commands.command(name="hide", description="Hide a channel from @everyone.")
    @app_commands.describe(channel="Channel to hide (defaults to current)")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="moderation")
    async def hide_command(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if interaction.guild is None:
            return
        target_ch = channel or interaction.channel
        await target_ch.set_permissions(interaction.guild.default_role, view_channel=False)
        await interaction.response.send_message(f"Hidden {target_ch.mention} from `@everyone`.", ephemeral=True)

    @app_commands.command(name="unhide", description="Make a hidden channel visible to @everyone.")
    @app_commands.describe(channel="Channel to unhide (defaults to current)")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="moderation")
    async def unhide_command(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if interaction.guild is None:
            return
        target_ch = channel or interaction.channel
        await target_ch.set_permissions(interaction.guild.default_role, view_channel=True)
        await interaction.response.send_message(f"Unhidden {target_ch.mention} for `@everyone`.", ephemeral=True)

    @app_commands.command(name="modlogs", description="View moderation history for a specific user or the entire server.")
    @app_commands.describe(member="Optional member to filter moderation logs by")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="moderation")
    async def modlogs_command(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ) -> None:
        if interaction.guild is None:
            return
        if member is not None:
            rows = await self.bot.db.fetch_all(
                "SELECT * FROM moderation_cases WHERE guild_id = ? AND target_user_id = ? ORDER BY case_number DESC LIMIT 20;",
                (int(interaction.guild.id), int(member.id)),
            )
            title = f"Moderation Logs for {member.name}"
        else:
            rows = await self.bot.db.fetch_all(
                "SELECT * FROM moderation_cases WHERE guild_id = ? ORDER BY case_number DESC LIMIT 20;",
                (int(interaction.guild.id),),
            )
            title = f"Server Moderation Logs — {interaction.guild.name}"

        embed = discord.Embed(title=title, color=discord.Color.blurple())
        if not rows:
            embed.description = "No moderation cases recorded."
        else:
            embed.description = "\n".join(
                f"`#{r['case_number']}` [{r['action_type'].upper()}] Target: <@{r['target_user_id']}> · Mod: <@{r['moderator_id']}> · {r['reason']}"
                for r in rows
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="case", description="Inspect details of a specific moderation case number.")
    @app_commands.describe(case_number="Case number to inspect")
    @require_permission_level(PermissionLevel.MODERATOR, module_name="moderation")
    async def case_command(self, interaction: discord.Interaction, case_number: int) -> None:
        if interaction.guild is None:
            return
        row = await self.bot.db.fetch_one(
            "SELECT * FROM moderation_cases WHERE guild_id = ? AND case_number = ?;",
            (int(interaction.guild.id), int(case_number)),
        )
        if not row:
            await interaction.response.send_message(f"Moderation Case `#{case_number}` not found.", ephemeral=True)
            return
        embed = discord.Embed(
            title=f"Moderation Case #{row['case_number']} ({row['action_type'].upper()})",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Target User", value=f"<@{row['target_user_id']}> (`{row['target_user_id']}`)", inline=True)
        embed.add_field(name="Moderator", value=f"<@{row['moderator_id']}> (`{row['moderator_id']}`)", inline=True)
        embed.add_field(name="Status", value="Active" if row["active"] else "Cleared", inline=True)
        embed.add_field(name="Reason", value=row["reason"], inline=False)
        embed.set_footer(text=f"Created at {row['created_at']}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="clearcases", description="Clear all moderation cases for a user with confirmation.")
    @app_commands.describe(member="Member whose cases will be cleared")
    @require_permission_level(PermissionLevel.ADMIN, module_name="moderation")
    async def clearcases_command(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if interaction.guild is None:
            return

        async def _confirm_clear(confirm_inter: discord.Interaction) -> None:
            await self.bot.db.execute(
                "DELETE FROM moderation_cases WHERE guild_id = ? AND target_user_id = ?;",
                (int(interaction.guild.id), int(member.id)),
            )
            embed = discord.Embed(
                title="Moderation Cases Cleared",
                description=f"Cleared all moderation cases for {member.mention}.",
                color=discord.Color.green(),
            )
            await confirm_inter.response.edit_message(embed=embed, view=None)

        view = ConfirmationView(author_id=int(interaction.user.id), on_confirm=_confirm_clear, confirm_label="Delete Cases")
        prompt = discord.Embed(
            title="Confirm Clearing Cases",
            description=f"Permanently clear all moderation cases for {member.mention}?",
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=prompt, view=view, ephemeral=True)


async def setup(bot: "CosmicBot") -> None:
    await bot.add_cog(ModerationCog(bot))
