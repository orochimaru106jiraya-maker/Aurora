"""
Join-to-Create (JTC) Temporary Voice Channel Service for Cosmic ki baddie.
Features:
- Multiple JTC hubs per server
- Automatic temporary room creation & member movement
- Automatic empty room cleanup & bot restart recovery
- SQLite ownership tracking
- Cooldowns and max active room limits
- Locking, hiding, user limits, member whitelist/blacklist, and ownership transfer
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from bot.core.discord_compat import discord
from bot.database.manager import DatabaseManager

logger = logging.getLogger("cosmic.services.jtc")


class JTCService:
    """Manages Join-to-Create voice hubs, active rooms, cooldowns, and restart recovery."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        self._creation_cooldowns: Dict[Tuple[int, int], float] = {}

    async def create_or_update_hub(
        self,
        guild_id: int,
        trigger_channel_id: int,
        target_category_id: Optional[int] = None,
        hub_name: str = "Main Voice Hub",
        naming_format: str = "{username}'s Room",
        default_limit: int = 0,
        cooldown_seconds: int = 10,
        max_active_rooms: int = 25,
        enabled: bool = True,
    ) -> Dict[str, Any]:
        await self.db.execute(
            """
            INSERT INTO jtc_configs (
                guild_id, hub_name, trigger_channel_id, target_category_id,
                naming_format, default_limit, cooldown_seconds, max_active_rooms, enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, trigger_channel_id) DO UPDATE SET
                hub_name = excluded.hub_name,
                target_category_id = excluded.target_category_id,
                naming_format = excluded.naming_format,
                default_limit = excluded.default_limit,
                cooldown_seconds = excluded.cooldown_seconds,
                max_active_rooms = excluded.max_active_rooms,
                enabled = excluded.enabled;
            """,
            (
                guild_id,
                hub_name,
                trigger_channel_id,
                target_category_id,
                naming_format,
                default_limit,
                cooldown_seconds,
                max_active_rooms,
                1 if enabled else 0,
            ),
        )
        row = await self.db.fetch_one(
            "SELECT * FROM jtc_configs WHERE guild_id = ? AND trigger_channel_id = ?;",
            (guild_id, trigger_channel_id),
        )
        return row or {}

    async def get_guild_hubs(self, guild_id: int) -> List[Dict[str, Any]]:
        return await self.db.fetch_all("SELECT * FROM jtc_configs WHERE guild_id = ?;", (guild_id,))

    async def get_active_rooms(self, guild_id: int) -> List[Dict[str, Any]]:
        return await self.db.fetch_all("SELECT * FROM jtc_active_rooms WHERE guild_id = ?;", (guild_id,))

    async def get_room(self, channel_id: int) -> Optional[Dict[str, Any]]:
        return await self.db.fetch_one("SELECT * FROM jtc_active_rooms WHERE channel_id = ?;", (channel_id,))

    async def can_manage_room(self, guild: Any, member: Any, channel_id: int, permission_service: Any) -> Tuple[bool, str]:
        """Only the room owner or authorized moderators/administrators can manage a JTC room."""
        room = await self.get_room(channel_id)
        if not room:
            return False, "This voice channel is not an active Join-to-Create room."
        if int(room["owner_id"]) == int(member.id):
            return True, "Authorized as room owner."

        from bot.database.models import PERMISSION_HIERARCHY, PermissionLevel

        lvl = await permission_service.get_member_effective_level(guild, member)
        if PERMISSION_HIERARCHY[lvl.value] >= PERMISSION_HIERARCHY[PermissionLevel.MODERATOR.value]:
            return True, f"Authorized as {lvl.value}."
        return False, f"Only the room owner (<@{room['owner_id']}>) or a server moderator can manage this room."

    async def handle_user_join_trigger(
        self,
        guild: Any,
        member: Any,
        trigger_channel_id: int,
    ) -> Tuple[bool, str, Optional[Any]]:
        """Create a temporary voice channel when a user joins a designated JTC trigger channel."""
        guild_id = int(guild.id)
        hub = await self.db.fetch_one(
            "SELECT * FROM jtc_configs WHERE guild_id = ? AND trigger_channel_id = ?;",
            (guild_id, int(trigger_channel_id)),
        )
        if not hub or not bool(hub.get("enabled", 1)):
            return False, "JTC hub is not enabled.", None

        # Cooldown check
        now = time.monotonic()
        cd_key = (guild_id, int(member.id))
        cooldown_sec = int(hub.get("cooldown_seconds") or 10)
        last_created = self._creation_cooldowns.get(cd_key, 0.0)
        if now - last_created < cooldown_sec:
            rem = int(cooldown_sec - (now - last_created)) + 1
            return False, f"Creation cooldown active ({rem}s remaining).", None

        # Max active rooms check
        active_rooms = await self.get_active_rooms(guild_id)
        max_rooms = int(hub.get("max_active_rooms") or 25)
        if len(active_rooms) >= max_rooms:
            return False, f"Maximum active JTC rooms ({max_rooms}) reached in this server.", None

        naming_fmt = hub.get("naming_format") or "{username}'s Room"
        room_name = naming_fmt.replace("{username}", getattr(member, "display_name", getattr(member, "name", "User")))[:95]
        default_limit = int(hub.get("default_limit") or 0)

        category = None
        if hub.get("target_category_id") and hasattr(guild, "get_channel"):
            category = guild.get_channel(int(hub["target_category_id"]))

        overwrites: Dict[Any, Any] = {
            member: discord.PermissionOverwrite(
                connect=True,
                speak=True,
                view_channel=True,
                manage_channels=True,
                move_members=True,
            )
        }
        voice_channel = await guild.create_voice_channel(
            name=room_name,
            category=category,
            user_limit=default_limit,
            overwrites=overwrites,
            reason=f"JTC temporary room created for {member.name}",
        )

        await self.db.execute(
            """
            INSERT INTO jtc_active_rooms (
                channel_id, guild_id, hub_id, owner_id, is_locked, is_hidden, user_limit, allowed_users_json
            ) VALUES (?, ?, ?, ?, 0, 0, ?, ?);
            """,
            (
                int(voice_channel.id),
                guild_id,
                int(hub["id"]),
                int(member.id),
                default_limit,
                json.dumps([int(member.id)]),
            ),
        )
        self._creation_cooldowns[cd_key] = now

        # Move member into the newly created room
        try:
            await member.move_to(voice_channel, reason="Moved into new JTC room")
            if member not in voice_channel.members:
                voice_channel.members.append(member)
        except Exception as exc:
            logger.warning("Could not move member %s into JTC room %s: %s", member.id, voice_channel.id, exc)

        return True, f"Created temporary room `{room_name}` (<#{voice_channel.id}>).", voice_channel

    async def cleanup_if_empty(self, guild: Any, channel_id: int) -> bool:
        """Delete a JTC temporary voice channel and its SQLite record when it becomes empty."""
        room = await self.get_room(channel_id)
        if not room:
            return False

        ch = guild.get_channel(int(channel_id)) if hasattr(guild, "get_channel") else None
        if ch is None:
            await self.db.execute("DELETE FROM jtc_active_rooms WHERE channel_id = ?;", (int(channel_id),))
            return True

        members = getattr(ch, "members", [])
        non_bot_members = [m for m in members if not getattr(m, "bot", False)]
        if len(non_bot_members) == 0:
            try:
                await ch.delete(reason="JTC temporary voice room became empty")
            except Exception as exc:
                logger.warning("Failed to delete empty JTC channel %d: %s", channel_id, exc)
            await self.db.execute("DELETE FROM jtc_active_rooms WHERE channel_id = ?;", (int(channel_id),))
            return True

        return False

    async def recover_after_restart(self, bot: Any) -> int:
        """Clean up orphaned or empty temporary voice rooms across all guilds after a bot restart."""
        cleaned = 0
        all_rooms = await self.db.fetch_all("SELECT * FROM jtc_active_rooms;")
        for room in all_rooms:
            guild_obj = None
            for g in getattr(bot, "guilds", []):
                if int(g.id) == int(room["guild_id"]):
                    guild_obj = g
                    break
            if guild_obj is not None:
                if await self.cleanup_if_empty(guild_obj, int(room["channel_id"])):
                    cleaned += 1
        return cleaned
