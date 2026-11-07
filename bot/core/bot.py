"""
CosmicBot — Primary Bot Subclass for Cosmic ki baddie (Project Aurora).
Wires together:
- DatabaseManager (`self.db`)
- PermissionService (`self.permission_service`)
- LoggingService (`self.logging_service`)
- TicketService (`self.ticket_service`)
- JTCService (`self.jtc_service`)
- AIService (`self.ai_service`)
- MusicService (`self.music_service`)
- CogLoader (`self.cog_loader`)
- CommandSyncManager (`self.command_sync`)
- HealthMonitor (`self.health_monitor`)
- Persistent UI Views (`register_all_persistent_views`)
"""

from __future__ import annotations

import logging
from typing import Optional

from bot.core.command_sync import CommandSyncManager
from bot.core.config import BotConfig
from bot.core.discord_compat import commands, discord
from bot.core.error_handler import register_error_handlers
from bot.core.health import HealthMonitor
from bot.core.loader import CogLoader
from bot.database.manager import DatabaseManager
from bot.services.ai_service import AIService
from bot.services.jtc_service import JTCService
from bot.services.logging_service import LoggingService
from bot.services.music_service import MusicService
from bot.services.permission_service import PermissionService
from bot.services.ticket_service import TicketService
from bot.ui.persistent_views import register_all_persistent_views

logger = logging.getLogger("cosmic.core.bot")


class CosmicBot(commands.Bot):
    """Production Discord bot instance for Cosmic ki baddie."""

    def __init__(self, config: Optional[BotConfig] = None) -> None:
        self.config = config or BotConfig.from_env()
        intents = discord.Intents.all()
        super().__init__(
            command_prefix=self.config.default_prefix,
            intents=intents,
            application_id=self.config.application_id,
        )

        # Core Services & Database Layer
        self.db = DatabaseManager(self.config.database_path)
        self.permission_service = PermissionService(self.db, bot_owner_id=self.config.bot_owner_id)
        self.logging_service = LoggingService(self.db)
        self.ticket_service = TicketService(self.db)
        self.jtc_service = JTCService(self.db)
        self.ai_service = AIService(
            self.db,
            local_llm_endpoint=self.config.local_llm_endpoint,
            local_llm_model=self.config.local_llm_model,
        )
        self.music_service = MusicService(self.db, ffmpeg_path=self.config.ffmpeg_path)

        # Lifecycle & Diagnostics Managers
        self.cog_loader = CogLoader(self)
        self.command_sync = CommandSyncManager(self)
        self.health_monitor = HealthMonitor(self)
        self._core_initialized = False

        register_error_handlers(self)

    async def initialize_core(self, register_views: bool = True) -> None:
        """Connect SQLite, run migrations, load all 12 Cogs, and register persistent UI views."""
        if self._core_initialized:
            return
        await self.db.connect()
        await self.cog_loader.load_all_cogs()
        if register_views:
            count = register_all_persistent_views(self)
            logger.info("Registered %d persistent UI views.", count)
        self.command_sync.audit_registered_commands()
        self._core_initialized = True

    async def setup_hook(self) -> None:
        """Executed automatically by discord.py before connecting to the Gateway."""
        await self.initialize_core(register_views=True)
        await self.command_sync.sync_with_discord(guild_id=self.config.test_guild_id)

    async def on_ready(self) -> None:
        logger.info(
            "Cosmic ki baddie is online as %s (ID: %s) across %d guild(s).",
            getattr(self.user, "name", "Cosmic ki baddie"),
            getattr(self.user, "id", "N/A"),
            len(self.guilds),
        )
        cleaned = await self.jtc_service.recover_after_restart(self)
        if cleaned:
            logger.info("Recovered and cleaned up %d empty JTC voice channels on startup.", cleaned)

    async def close(self) -> None:
        await self.db.close()
        await super().close()
