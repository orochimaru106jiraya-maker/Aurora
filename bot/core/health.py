"""
Command & System Health Monitor for Cosmic ki baddie.
Reports:
- Total commands implemented
- Total commands registered
- Total commands synchronized
- Failed commands
- Missing permissions
- Failed extensions
- Database connection status
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from bot.core.bot import CosmicBot


class HealthMonitor:
    """Provides real-time health, command registry, and permission diagnostics."""

    def __init__(self, bot: "CosmicBot") -> None:
        self.bot = bot
        self.started_at = datetime.now(timezone.utc)

    async def generate_full_diagnostic_report(self, guild: Any = None) -> Dict[str, Any]:
        """Generate a complete health-check report for `/botinfo`, `/setup`, and CLI verification."""
        db_status = await self.bot.db.health_check()
        cmd_report = self.bot.command_sync.audit_registered_commands()
        loader_report = self.bot.cog_loader.report

        missing_permissions: List[str] = []
        if guild is not None and getattr(guild, "me", None) is not None:
            perms = guild.me.guild_permissions
            required_flags = [
                "manage_guild",
                "manage_roles",
                "manage_channels",
                "manage_messages",
                "kick_members",
                "ban_members",
                "moderate_members",
                "move_members",
                "connect",
                "speak",
                "view_channel",
                "send_messages",
                "embed_links",
                "attach_files",
            ]
            for flag in required_flags:
                if not getattr(perms, flag, False) and not getattr(perms, "administrator", False):
                    missing_permissions.append(flag)

        ffmpeg_available = shutil.which(self.bot.config.ffmpeg_path) is not None

        return {
            "bot_name": "Cosmic ki baddie",
            "project_codename": "Aurora",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": int((datetime.now(timezone.utc) - self.started_at).total_seconds()),
            "database": db_status,
            "commands": {
                "total_implemented": cmd_report.total_implemented,
                "total_registered": cmd_report.total_registered,
                "total_synchronized": cmd_report.total_synced_discord,
                "duplicate_conflicts": cmd_report.duplicate_conflicts,
                "failed_commands": cmd_report.failed_commands,
                "sync_mode": cmd_report.sync_mode,
                "registry": cmd_report.registered_commands,
            },
            "extensions": {
                "loaded": loader_report.loaded_extensions,
                "failed": loader_report.failed_extensions,
                "total_loaded": len(loader_report.loaded_extensions),
                "total_failed": len(loader_report.failed_extensions),
            },
            "permissions": {
                "missing_guild_permissions": missing_permissions,
                "status": "nominal" if not missing_permissions else "degraded",
            },
            "voice_and_media": {
                "ffmpeg_available": ffmpeg_available,
                "persistent_views_registered": len(getattr(self.bot, "persistent_views", [])),
            },
        }
