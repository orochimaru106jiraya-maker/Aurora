"""
Activity-Based Auto Roles Cog (`/activity`) for Cosmic ki baddie.

Supports 4 real-time activity streams:
1. Spotify Listening (`ActivityType.listening` / Spotify presence) — Assigns role while listening, removes when ended.
2. Gaming (`ActivityType.playing`) — Assigns default gaming role and game-specific roles, removes when game closes.
3. Voice Chat (`on_voice_state_update`) — Assigns voice role (or channel-specific role) on join, removes on leave.
4. Text Chat (`on_message`) — Tracks messages with anti-spam cooldowns and assigns milestone threshold roles.

Implements all 8 required `/activity` slash commands:
- `/activity setup`
- `/activity config`
- `/activity spotify`
- `/activity gaming`
- `/activity voice`
- `/activity chat`
- `/activity roles`
- `/activity disable`

Discord Gateway Intent Note:
- Spotify and Gaming presence detection requires `Intents.presences = True` and `Intents.members = True` enabled in the
  Discord Developer Portal (Bot -> Privileged Gateway Intents).
- Mobile/Invisible users or users with 'Display current activity as a status message' disabled in Discord Privacy Settings
  will not emit `on_presence_update` payloads.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from bot.core.discord_compat import app_commands, commands, discord
from bot.database.models import PermissionLevel
from bot.utils.checks import require_permission_level
from bot.utils.validators import validate_assignable_role

if TYPE_CHECKING:
    from bot.core.bot import CosmicBot


class ActivityRolesCog(commands.Cog):
    """Automatic role assignment based on Spotify, Gaming, Voice, and Text Chat activity."""

    activity_group = app_commands.Group(
        name="activity",
        description="Configure automatic roles for Spotify, Gaming, Voice Chat, and Text Chat milestones.",
    )

    def __init__(self, bot: "CosmicBot") -> None:
        self.bot = bot
        self._chat_cooldowns: Dict[Tuple[int, int], float] = {}

    async def _ensure_activity_config(self, guild_id: int) -> Dict[str, Any]:
        row = await self.bot.db.fetch_one("SELECT * FROM activity_role_configs WHERE guild_id = ?;", (guild_id,))
        if row:
            return row
        await self.bot.db.execute(
            "INSERT INTO activity_role_configs (guild_id, enabled) VALUES (?, 1) ON CONFLICT(guild_id) DO NOTHING;",
            (guild_id,),
        )
        row = await self.bot.db.fetch_one("SELECT * FROM activity_role_configs WHERE guild_id = ?;", (guild_id,))
        return row or {}

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        guild = getattr(after, "guild", None)
        if guild is None or getattr(after, "bot", False):
            return
        cfg = await self._ensure_activity_config(int(guild.id))
        if not bool(cfg.get("enabled", 1)):
            return

        activities = getattr(after, "activities", []) or []

        # 1. Spotify Activity Detection
        spotify_role_id = cfg.get("spotify_role_id")
        if spotify_role_id:
            s_role = guild.get_role(int(spotify_role_id))
            if s_role and validate_assignable_role(s_role, guild)[0]:
                is_spotify = any(
                    getattr(a, "name", "").lower() == "spotify"
                    or getattr(a, "type", None) == discord.ActivityType.listening
                    for a in activities
                )
                has_role = any(int(r.id) == int(spotify_role_id) for r in getattr(after, "roles", []))
                if is_spotify and not has_role:
                    await after.add_roles(s_role, reason="Spotify listening activity started")
                elif not is_spotify and has_role:
                    await after.remove_roles(s_role, reason="Spotify listening activity ended")

        # 2. Gaming Activity Detection
        gaming_role_id = cfg.get("gaming_default_role_id")
        gaming_map: Dict[str, int] = json.loads(cfg.get("gaming_map_json") or "{}")
        playing_names = [
            getattr(a, "name", "").lower()
            for a in activities
            if getattr(a, "type", None) == discord.ActivityType.playing
        ]
        if gaming_role_id:
            g_role = guild.get_role(int(gaming_role_id))
            if g_role and validate_assignable_role(g_role, guild)[0]:
                has_g_role = any(int(r.id) == int(gaming_role_id) for r in getattr(after, "roles", []))
                if playing_names and not has_g_role:
                    await after.add_roles(g_role, reason="Gaming activity started")
                elif not playing_names and has_g_role:
                    await after.remove_roles(g_role, reason="Gaming activity ended")

        for game_key, mapped_rid in gaming_map.items():
            specific_role = guild.get_role(int(mapped_rid))
            if specific_role and validate_assignable_role(specific_role, guild)[0]:
                is_playing_this = any(game_key.lower() in gname for gname in playing_names)
                has_spec = any(int(r.id) == int(mapped_rid) for r in getattr(after, "roles", []))
                if is_playing_this and not has_spec:
                    await after.add_roles(specific_role, reason=f"Playing {game_key}")
                elif not is_playing_this and has_spec:
                    await after.remove_roles(specific_role, reason=f"Stopped playing {game_key}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: Any, after: Any) -> None:
        guild = getattr(member, "guild", None)
        if guild is None or getattr(member, "bot", False):
            return
        cfg = await self._ensure_activity_config(int(guild.id))
        if not bool(cfg.get("enabled", 1)):
            return

        voice_role_id = cfg.get("voice_default_role_id")
        if voice_role_id:
            v_role = guild.get_role(int(voice_role_id))
            if v_role and validate_assignable_role(v_role, guild)[0]:
                in_voice = getattr(after, "channel", None) is not None
                has_v_role = any(int(r.id) == int(voice_role_id) for r in getattr(member, "roles", []))
                if in_voice and not has_v_role:
                    await member.add_roles(v_role, reason="Joined voice chat")
                elif not in_voice and has_v_role:
                    await member.remove_roles(v_role, reason="Left voice chat")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        guild = getattr(message, "guild", None)
        author = getattr(message, "author", None)
        if guild is None or author is None or getattr(author, "bot", False):
            return
        cfg = await self._ensure_activity_config(int(guild.id))
        if not bool(cfg.get("enabled", 1)):
            return

        cooldown = int(cfg.get("chat_cooldown_seconds") or 30)
        now = time.monotonic()
        cd_key = (int(guild.id), int(author.id))
        if now - self._chat_cooldowns.get(cd_key, 0.0) < cooldown:
            return
        self._chat_cooldowns[cd_key] = now

        await self.bot.db.execute(
            """
            INSERT INTO activity_user_stats (guild_id, user_id, message_count, last_message_at)
            VALUES (?, ?, 1, datetime('now'))
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                message_count = message_count + 1,
                last_message_at = datetime('now');
            """,
            (int(guild.id), int(author.id)),
        )
        stat = await self.bot.db.fetch_one(
            "SELECT message_count FROM activity_user_stats WHERE guild_id = ? AND user_id = ?;",
            (int(guild.id), int(author.id)),
        )
        msg_count = int((stat or {}).get("message_count", 1))
        thresholds = json.loads(cfg.get("chat_thresholds_json") or "[]")
        for item in thresholds:
            if msg_count >= int(item.get("messages", 100)):
                role = guild.get_role(int(item["role_id"]))
                if role and validate_assignable_role(role, guild)[0]:
                    if all(int(r.id) != int(role.id) for r in getattr(author, "roles", [])):
                        await author.add_roles(role, reason=f"Reached {msg_count} chat messages milestone")

    @activity_group.command(name="setup", description="Initialize Activity Auto-Roles and view Gateway Intent requirements.")
    @require_permission_level(PermissionLevel.ADMIN, module_name="activity_roles")
    async def activity_setup(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        cfg = await self._ensure_activity_config(int(interaction.guild.id))
        embed = discord.Embed(
            title="Activity-Based Auto Roles — Setup & Intent Guide",
            description=(
                "Configure automatic roles for **Spotify**, **Gaming**, **Voice Chat**, and **Text Chat**.\n\n"
                "**Discord Presence & Gateway Intent Notes:**\n"
                "• Ensure `PRESENCE INTENT` and `SERVER MEMBERS INTENT` are toggled **ON** in the Discord Developer Portal.\n"
                "• Users who set their status to *Invisible* or disable activity sharing in Discord Privacy Settings do not broadcast presence updates."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Module Status", value="Enabled" if cfg.get("enabled", 1) else "Disabled", inline=True)
        embed.add_field(name="Chat Cooldown", value=f"`{cfg.get('chat_cooldown_seconds', 30)}s`", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @activity_group.command(name="config", description="Configure anti-spam cooldown for text chat activity tracking.")
    @app_commands.describe(chat_cooldown_seconds="Seconds between counted messages per user (anti-spam)")
    @require_permission_level(PermissionLevel.ADMIN, module_name="activity_roles")
    async def activity_config(self, interaction: discord.Interaction, chat_cooldown_seconds: int = 30) -> None:
        if interaction.guild is None:
            return
        await self._ensure_activity_config(int(interaction.guild.id))
        clean_cd = max(5, min(600, int(chat_cooldown_seconds)))
        await self.bot.db.execute(
            "UPDATE activity_role_configs SET chat_cooldown_seconds = ?, enabled = 1 WHERE guild_id = ?;",
            (clean_cd, int(interaction.guild.id)),
        )
        await interaction.response.send_message(
            f"Updated text activity anti-spam cooldown to **{clean_cd}s**.",
            ephemeral=True,
        )

    @activity_group.command(name="spotify", description="Set the role automatically assigned while a member is listening to Spotify.")
    @app_commands.describe(role="Role to assign during Spotify playback")
    @require_permission_level(PermissionLevel.ADMIN, module_name="activity_roles")
    async def activity_spotify(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if interaction.guild is None:
            return
        ok, msg = validate_assignable_role(role, interaction.guild)
        if not ok:
            await interaction.response.send_message(msg, ephemeral=True)
            return
        await self._ensure_activity_config(int(interaction.guild.id))
        await self.bot.db.execute(
            "UPDATE activity_role_configs SET spotify_role_id = ? WHERE guild_id = ?;",
            (int(role.id), int(interaction.guild.id)),
        )
        await interaction.response.send_message(f"Configured Spotify listening auto-role: {role.mention}.", ephemeral=True)

    @activity_group.command(name="gaming", description="Set the default gaming role or a game-specific role.")
    @app_commands.describe(role="Role to assign when gaming", game_name="Optional specific game name (leave blank for all games)")
    @require_permission_level(PermissionLevel.ADMIN, module_name="activity_roles")
    async def activity_gaming(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        game_name: Optional[str] = None,
    ) -> None:
        if interaction.guild is None:
            return
        ok, msg = validate_assignable_role(role, interaction.guild)
        if not ok:
            await interaction.response.send_message(msg, ephemeral=True)
            return
        cfg = await self._ensure_activity_config(int(interaction.guild.id))
        if game_name and game_name.strip():
            gmap = json.loads(cfg.get("gaming_map_json") or "{}")
            gmap[game_name.strip().lower()] = int(role.id)
            await self.bot.db.execute(
                "UPDATE activity_role_configs SET gaming_map_json = ? WHERE guild_id = ?;",
                (json.dumps(gmap), int(interaction.guild.id)),
            )
            await interaction.response.send_message(
                f"Configured game-specific role {role.mention} for **{game_name.strip()}**.",
                ephemeral=True,
            )
        else:
            await self.bot.db.execute(
                "UPDATE activity_role_configs SET gaming_default_role_id = ? WHERE guild_id = ?;",
                (int(role.id), int(interaction.guild.id)),
            )
            await interaction.response.send_message(f"Configured default gaming role: {role.mention}.", ephemeral=True)

    @activity_group.command(name="voice", description="Set the role assigned while a member is connected to a voice channel.")
    @app_commands.describe(role="Role to assign while in voice chat")
    @require_permission_level(PermissionLevel.ADMIN, module_name="activity_roles")
    async def activity_voice(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if interaction.guild is None:
            return
        ok, msg = validate_assignable_role(role, interaction.guild)
        if not ok:
            await interaction.response.send_message(msg, ephemeral=True)
            return
        await self._ensure_activity_config(int(interaction.guild.id))
        await self.bot.db.execute(
            "UPDATE activity_role_configs SET voice_default_role_id = ? WHERE guild_id = ?;",
            (int(role.id), int(interaction.guild.id)),
        )
        await interaction.response.send_message(f"Configured voice chat activity role: {role.mention}.", ephemeral=True)

    @activity_group.command(name="chat", description="Add a message threshold milestone role for active text chatters.")
    @app_commands.describe(messages="Message count required", role="Role to award when threshold is reached")
    @require_permission_level(PermissionLevel.ADMIN, module_name="activity_roles")
    async def activity_chat(self, interaction: discord.Interaction, messages: int, role: discord.Role) -> None:
        if interaction.guild is None:
            return
        ok, msg = validate_assignable_role(role, interaction.guild)
        if not ok:
            await interaction.response.send_message(msg, ephemeral=True)
            return
        cfg = await self._ensure_activity_config(int(interaction.guild.id))
        thresholds = json.loads(cfg.get("chat_thresholds_json") or "[]")
        thresholds.append({"messages": max(1, int(messages)), "role_id": int(role.id)})
        await self.bot.db.execute(
            "UPDATE activity_role_configs SET chat_thresholds_json = ? WHERE guild_id = ?;",
            (json.dumps(thresholds), int(interaction.guild.id)),
        )
        await interaction.response.send_message(
            f"Added chat milestone: **{messages} messages** → {role.mention}.",
            ephemeral=True,
        )

    @activity_group.command(name="roles", description="View all configured Spotify, Gaming, Voice, and Chat activity roles.")
    async def activity_roles_view(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        cfg = await self._ensure_activity_config(int(interaction.guild.id))
        embed = discord.Embed(
            title=f"Activity Auto-Roles — {interaction.guild.name}",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Spotify Role",
            value=f"<@&{cfg['spotify_role_id']}>" if cfg.get("spotify_role_id") else "`Not Configured`",
            inline=True,
        )
        embed.add_field(
            name="Default Gaming Role",
            value=f"<@&{cfg['gaming_default_role_id']}>" if cfg.get("gaming_default_role_id") else "`Not Configured`",
            inline=True,
        )
        embed.add_field(
            name="Voice Chat Role",
            value=f"<@&{cfg['voice_default_role_id']}>" if cfg.get("voice_default_role_id") else "`Not Configured`",
            inline=True,
        )
        thresholds = json.loads(cfg.get("chat_thresholds_json") or "[]")
        t_lines = [f"• **{t['messages']} msgs** → <@&{t['role_id']}>" for t in thresholds] or ["No chat milestones set."]
        embed.add_field(name="Text Chat Milestones", value="\n".join(t_lines), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @activity_group.command(name="disable", description="Disable all Activity-Based Auto Roles in this server.")
    @require_permission_level(PermissionLevel.ADMIN, module_name="activity_roles")
    async def activity_disable(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        await self._ensure_activity_config(int(interaction.guild.id))
        await self.bot.db.execute(
            "UPDATE activity_role_configs SET enabled = 0 WHERE guild_id = ?;",
            (int(interaction.guild.id),),
        )
        await interaction.response.send_message("Disabled Activity-Based Auto Roles for this server.", ephemeral=True)


async def setup(bot: "CosmicBot") -> None:
    await bot.add_cog(ActivityRolesCog(bot))
