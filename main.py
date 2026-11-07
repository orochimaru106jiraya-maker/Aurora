#!/usr/bin/env python3
"""
Cosmic ki baddie (Project Aurora) — Advanced Multifunctional Discord Management Bot
Entry point for Railway deployment and local execution.

Features:
- Modular Cog architecture with 12 specialized Cogs
- SQLite + aiosqlite centralized database manager with versioned migrations
- Server-side RBAC permission engine with hierarchy & owner protection
- Persistent UI Views surviving restarts (Tickets, Reaction Roles, JTC, Setup Wizard)
- Built-in CLI flags for static verification and command registry auditing
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from bot.core.config import BotConfig, setup_logging
from bot.core.bot import CosmicBot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cosmic ki baddie (Aurora) — Advanced Discord Server Management Platform"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Initialize database, run migrations, load all Cogs, and verify command registry without connecting to Discord Gateway.",
    )
    parser.add_argument(
        "--export-registry",
        type=str,
        default="",
        help="Export JSON report of all registered slash commands and health diagnostics to a file.",
    )
    return parser.parse_args()


async def run_verification_mode(config: BotConfig, export_path: str = "") -> int:
    """Boots the database, runs migrations, loads all Cogs, and verifies command registration."""
    logger = logging.getLogger("cosmic.main")
    logger.info("Starting Cosmic ki baddie in verification mode (--verify-only)...")

    bot = CosmicBot(config=config)
    try:
        await bot.initialize_core(register_views=False)
        report = await bot.health_monitor.generate_full_diagnostic_report()

        if export_path:
            import json
            out = Path(export_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, indent=2), encoding="utf-8")
            logger.info("Exported diagnostic report to %s", out)

        logger.info(
            "Verification complete: %d commands registered across %d Cogs (%d failed extensions).",
            report["commands"]["total_registered"],
            len(report["extensions"]["loaded"]),
            len(report["extensions"]["failed"]),
        )
        await bot.close()
        return 0 if not report["extensions"]["failed"] else 1
    except Exception as exc:
        logger.exception("Verification mode failed: %s", exc)
        await bot.close()
        return 1


async def main() -> int:
    args = parse_args()
    config = BotConfig.from_env()
    setup_logging(config)
    logger = logging.getLogger("cosmic.main")

    if args.verify_only or args.export_registry:
        return await run_verification_mode(config, args.export_registry)

    if not config.discord_token or config.discord_token == "your_discord_bot_token_here":
        logger.critical(
            "DISCORD_BOT_TOKEN is missing or set to placeholder. "
            "Configure DISCORD_BOT_TOKEN in your environment variables or Railway Variables panel. "
            "Run `python3 main.py --verify-only` to run offline diagnostics."
        )
        return 1

    bot = CosmicBot(config=config)
    try:
        async with bot:
            logger.info("Starting Cosmic ki baddie Discord Gateway connection...")
            await bot.start(config.discord_token, reconnect=True)
    except KeyboardInterrupt:
        logger.info("Received shutdown signal. Closing Cosmic ki baddie cleanly...")
    except Exception as exc:
        logger.critical("Fatal runtime exception in main loop: %s", exc, exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
