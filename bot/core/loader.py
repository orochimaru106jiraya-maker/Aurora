"""
Cog Extension Loader for Cosmic ki baddie.
Never silently ignores failed Cog loading — records detailed diagnostics for every extension.
"""

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from bot.core.bot import CosmicBot

logger = logging.getLogger("cosmic.core.loader")

REQUIRED_COGS: List[str] = [
    "bot.cogs.setup_wizard",
    "bot.cogs.permissions",
    "bot.cogs.tickets",
    "bot.cogs.moderation",
    "bot.cogs.jtc",
    "bot.cogs.activity_roles",
    "bot.cogs.reaction_roles",
    "bot.cogs.ai_assistant",
    "bot.cogs.music",
    "bot.cogs.embeds",
    "bot.cogs.auto_responder",
    "bot.cogs.administration",
]


@dataclass
class LoaderReport:
    loaded_extensions: List[str] = field(default_factory=list)
    failed_extensions: Dict[str, str] = field(default_factory=dict)

    @property
    def all_succeeded(self) -> bool:
        return len(self.failed_extensions) == 0 and len(self.loaded_extensions) == len(REQUIRED_COGS)


class CogLoader:
    """Manages deterministic loading and diagnostics for all 12 bot Cogs."""

    def __init__(self, bot: "CosmicBot") -> None:
        self.bot = bot
        self.report = LoaderReport()

    async def load_all_cogs(self) -> LoaderReport:
        self.report = LoaderReport()
        for ext in REQUIRED_COGS:
            try:
                await self.bot.load_extension(ext)
                self.report.loaded_extensions.append(ext)
                logger.info("Successfully loaded extension: %s", ext)
            except Exception as exc:
                tb = traceback.format_exc()
                self.report.failed_extensions[ext] = f"{type(exc).__name__}: {exc}"
                logger.error("Failed to load extension %s: %s\n%s", ext, exc, tb)

        if self.report.failed_extensions:
            logger.critical(
                "Cog loading completed with %d failures: %s",
                len(self.report.failed_extensions),
                list(self.report.failed_extensions.keys()),
            )
        else:
            logger.info("All %d Cogs loaded cleanly.", len(self.report.loaded_extensions))

        return self.report
