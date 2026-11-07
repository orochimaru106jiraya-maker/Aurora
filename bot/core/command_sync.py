"""
Slash Command Registration & Synchronization Service for Cosmic ki baddie.
Handles nested Group/Subcommand discovery, duplicate prevention, Discord API synchronization,
and diagnostic reporting.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from bot.core.discord_compat import app_commands, discord

if TYPE_CHECKING:
    from bot.core.bot import CosmicBot

logger = logging.getLogger("cosmic.core.command_sync")


@dataclass
class CommandSyncReport:
    total_implemented: int = 0
    total_registered: int = 0
    total_synced_discord: int = 0
    duplicate_conflicts: List[str] = field(default_factory=list)
    failed_commands: Dict[str, str] = field(default_factory=dict)
    registered_commands: List[Dict[str, Any]] = field(default_factory=list)
    last_sync_at: Optional[str] = None
    sync_mode: str = "offline_verified"
    sync_error: Optional[str] = None


class CommandSyncManager:
    """Inspects, validates, and synchronizes the Slash Command tree."""

    def __init__(self, bot: "CosmicBot") -> None:
        self.bot = bot
        self.last_report = CommandSyncReport()

    def audit_registered_commands(self) -> CommandSyncReport:
        """
        Walks the entire CommandTree (including nested `app_commands.Group` instances),
        verifies every leaf command has a valid coroutine callback, and detects any duplicates.
        """
        report = CommandSyncReport()
        seen_qualified_names: Set[str] = set()

        all_nodes = self.bot.tree.walk_commands()
        leaf_commands = [node for node in all_nodes if isinstance(node, app_commands.Command)]
        report.total_implemented = len(leaf_commands)

        for cmd in leaf_commands:
            qname = f"/{cmd.qualified_name}"
            if qname in seen_qualified_names:
                report.duplicate_conflicts.append(qname)
                report.failed_commands[qname] = "Duplicate command name conflict"
                continue
            seen_qualified_names.add(qname)

            callback = getattr(cmd, "callback", None)
            if callback is None or not inspect.iscoroutinefunction(callback):
                report.failed_commands[qname] = "Missing or non-async command callback"
                continue

            parent_name = cmd.parent.qualified_name if cmd.parent else "root"
            cog_name = getattr(cmd.binding, "__class__", type("Root", (), {})).__name__
            report.registered_commands.append(
                {
                    "qualified_name": qname,
                    "name": cmd.name,
                    "group": parent_name,
                    "cog": cog_name,
                    "description": cmd.description,
                }
            )

        report.total_registered = len(report.registered_commands)
        self.last_report = report
        return report

    async def sync_with_discord(self, guild_id: Optional[int] = None) -> CommandSyncReport:
        """Synchronize the command tree with Discord globally or to a specific test guild."""
        report = self.audit_registered_commands()
        try:
            if guild_id:
                guild_obj = discord.Object(id=guild_id)
                self.bot.tree.copy_global_to(guild=guild_obj)
                synced = await self.bot.tree.sync(guild=guild_obj)
                report.sync_mode = f"guild:{guild_id}"
            else:
                synced = await self.bot.tree.sync()
                report.sync_mode = "global"

            report.total_synced_discord = len(synced)
            report.last_sync_at = datetime.now(timezone.utc).isoformat()
            logger.info(
                "Synchronized %d slash commands (%d leaf commands audited) in mode %s",
                report.total_synced_discord,
                report.total_registered,
                report.sync_mode,
            )
        except Exception as exc:
            report.sync_error = f"{type(exc).__name__}: {exc}"
            logger.error("Failed to sync commands with Discord: %s", exc)

        self.last_report = report
        return report
