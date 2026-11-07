"""
Logging & Audit Service for Cosmic ki baddie.
Handles moderation cases, server audit logs, and deleted/edited message snipe tracking.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from bot.core.discord_compat import discord
from bot.database.manager import DatabaseManager
from bot.utils.formatting import format_duration, utc_now_iso

logger = logging.getLogger("cosmic.services.logging")


class LoggingService:
    """Manages guild configuration, moderation case numbers, audit embeds, and snipe history."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    async def ensure_guild_config(self, guild_id: int) -> Dict[str, Any]:
        row = await self.db.fetch_one("SELECT * FROM guild_configs WHERE guild_id = ?;", (guild_id,))
        if row:
            return row
        default_modules = {
            "moderation": True,
            "tickets": True,
            "permissions": True,
            "activity_roles": True,
            "reaction_roles": True,
            "jtc": True,
            "music": True,
            "ai_assistant": True,
            "auto_responder": True,
            "embeds": True,
            "administration": True,
        }
        await self.db.execute(
            """
            INSERT INTO guild_configs (guild_id, prefix, enabled_modules_json)
            VALUES (?, '!', ?)
            ON CONFLICT(guild_id) DO NOTHING;
            """,
            (guild_id, json.dumps(default_modules)),
        )
        row = await self.db.fetch_one("SELECT * FROM guild_configs WHERE guild_id = ?;", (guild_id,))
        return row or {"guild_id": guild_id, "prefix": "!", "enabled_modules_json": json.dumps(default_modules)}

    async def update_guild_config(self, guild_id: int, **updates: Any) -> Dict[str, Any]:
        await self.ensure_guild_config(guild_id)
        allowed_cols = {
            "prefix",
            "mod_log_channel_id",
            "server_log_channel_id",
            "transcript_channel_id",
            "snipe_limit",
            "enabled_modules_json",
        }
        set_clauses: List[str] = []
        params: List[Any] = []
        for col, val in updates.items():
            if col in allowed_cols:
                set_clauses.append(f"{col} = ?")
                params.append(val)
        if set_clauses:
            set_clauses.append("updated_at = datetime('now')")
            params.append(guild_id)
            sql = f"UPDATE guild_configs SET {', '.join(set_clauses)} WHERE guild_id = ?;"
            await self.db.execute(sql, params)
        return await self.ensure_guild_config(guild_id)

    async def create_moderation_case(
        self,
        guild: Any,
        action_type: str,
        target_user: Any,
        moderator: Any,
        reason: str,
        duration_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a numbered moderation case in SQLite and dispatch an embed to the configured mod log channel."""
        guild_id = int(guild.id)
        max_row = await self.db.fetch_one(
            "SELECT COALESCE(MAX(case_number), 0) AS max_case FROM moderation_cases WHERE guild_id = ?;",
            (guild_id,),
        )
        next_case = int((max_row or {}).get("max_case", 0)) + 1

        await self.db.execute(
            """
            INSERT INTO moderation_cases (
                guild_id, case_number, action_type, target_user_id,
                moderator_id, reason, duration_seconds, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1);
            """,
            (
                guild_id,
                next_case,
                action_type.lower(),
                int(target_user.id),
                int(moderator.id),
                reason,
                duration_seconds,
            ),
        )

        case_data = {
            "guild_id": guild_id,
            "case_number": next_case,
            "action_type": action_type.lower(),
            "target_user_id": int(target_user.id),
            "moderator_id": int(moderator.id),
            "reason": reason,
            "duration_seconds": duration_seconds,
            "created_at": utc_now_iso(),
        }

        # Dispatch to mod log channel if configured
        cfg = await self.ensure_guild_config(guild_id)
        mod_log_id = cfg.get("mod_log_channel_id")
        if mod_log_id and hasattr(guild, "get_channel"):
            channel = guild.get_channel(int(mod_log_id))
            if channel and hasattr(channel, "send"):
                embed = discord.Embed(
                    title=f"Moderation Case #{next_case} · {action_type.upper()}",
                    color=discord.Color.gold(),
                )
                embed.add_field(name="Target", value=f"<@{target_user.id}> (`{target_user.id}`)", inline=True)
                embed.add_field(name="Moderator", value=f"<@{moderator.id}> (`{moderator.id}`)", inline=True)
                embed.add_field(name="Duration", value=format_duration(duration_seconds), inline=True)
                embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
                embed.set_footer(text=f"Timestamp: {case_data['created_at']}")
                try:
                    await channel.send(embed=embed)
                except Exception as exc:
                    logger.warning("Failed to send mod log embed in guild %d: %s", guild_id, exc)

        return case_data

    async def record_snipe_event(
        self,
        guild_id: int,
        channel_id: int,
        author_id: int,
        author_name: str,
        event_type: str,
        old_content: str,
        new_content: Optional[str] = None,
        attachment_urls: Optional[List[str]] = None,
    ) -> None:
        """Store a deleted or edited message and prune older records exceeding the guild's snipe_limit."""
        cfg = await self.ensure_guild_config(guild_id)
        limit = int(cfg.get("snipe_limit") or 25)

        await self.db.execute(
            """
            INSERT INTO snipe_messages (
                guild_id, channel_id, author_id, author_name, event_type,
                old_content, new_content, attachment_urls_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                guild_id,
                channel_id,
                author_id,
                author_name,
                event_type,
                old_content or "[Attachment / Embed Only]",
                new_content,
                json.dumps(attachment_urls or []),
            ),
        )

        # Prune older records beyond snipe_limit per channel
        await self.db.execute(
            """
            DELETE FROM snipe_messages
            WHERE id NOT IN (
                SELECT id FROM snipe_messages
                WHERE guild_id = ? AND channel_id = ? AND event_type = ?
                ORDER BY id DESC LIMIT ?
            ) AND guild_id = ? AND channel_id = ? AND event_type = ?;
            """,
            (guild_id, channel_id, event_type, limit, guild_id, channel_id, event_type),
        )
