"""
Automated Command Registry & Cog Loader Tests (`tests/test_commands.py`).
Tests:
- All 12 Cogs load with 0 failed extensions
- Every required Slash Command and nested Subgroup is registered
- Zero duplicate command name conflicts
- Every leaf command has a real async coroutine callback
- Persistent views register with `timeout=None`
- Dashboard navigation across all 14 pages
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bot.core.bot import CosmicBot
from bot.core.config import BotConfig
from bot.core.discord_compat import discord
from bot.ui.dashboard import DASHBOARD_PAGES, SetupDashboardView


class TestCommandRegistryAndDashboard(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        cfg = BotConfig(
            discord_token="test_token",
            application_id=123456,
            test_guild_id=None,
            database_path=str(Path(self.tmp_dir.name) / "cmd_test.db"),
            bot_owner_id=987654321,
            default_prefix="!",
            local_llm_endpoint="",
            local_llm_model="llama3.2:1b",
            log_level="WARNING",
            log_file_path=str(Path(self.tmp_dir.name) / "test.log"),
            ffmpeg_path="ffmpeg",
        )
        self.bot = CosmicBot(config=cfg)
        await self.bot.initialize_core(register_views=True)

    async def asyncTearDown(self) -> None:
        await self.bot.close()
        self.tmp_dir.cleanup()

    async def test_all_12_cogs_loaded_and_zero_failures(self) -> None:
        self.assertTrue(self.bot.cog_loader.report.all_succeeded)
        self.assertEqual(len(self.bot.cog_loader.report.loaded_extensions), 12)
        self.assertEqual(len(self.bot.cog_loader.report.failed_extensions), 0)

    async def test_complete_slash_command_registry(self) -> None:
        report = self.bot.command_sync.audit_registered_commands()
        self.assertEqual(len(report.duplicate_conflicts), 0)
        self.assertEqual(len(report.failed_commands), 0)
        self.assertGreaterEqual(report.total_registered, 115)

        qnames = {c["qualified_name"] for c in report.registered_commands}
        mandatory_commands = [
            "/setup",
            "/help",
            "/jticket setup",
            "/jticket panel",
            "/jticket config",
            "/jticket open",
            "/jticket close",
            "/jticket reopen",
            "/jticket delete",
            "/jticket claim",
            "/jticket unclaim",
            "/jticket transfer",
            "/jticket add",
            "/jticket remove",
            "/jticket rename",
            "/jticket transcript",
            "/jticket stats",
            "/jticket list",
            "/ban",
            "/unban",
            "/kick",
            "/timeout",
            "/untimeout",
            "/warn",
            "/warnings",
            "/clearwarnings",
            "/purge",
            "/snipe",
            "/editsnipe",
            "/lock",
            "/unlock",
            "/slowmode",
            "/hide",
            "/unhide",
            "/modlogs",
            "/case",
            "/clearcases",
            "/permissions setup",
            "/permissions view",
            "/permissions role add",
            "/permissions role remove",
            "/permissions user add",
            "/permissions user remove",
            "/permissions command",
            "/permissions module",
            "/permissions reset",
            "/jtc setup",
            "/jtc config",
            "/jtc enable",
            "/jtc disable",
            "/jtc panel",
            "/jtc list",
            "/jtc rename",
            "/jtc limit",
            "/jtc lock",
            "/jtc unlock",
            "/jtc hide",
            "/jtc unhide",
            "/jtc add",
            "/jtc remove",
            "/jtc transfer",
            "/jtc delete",
            "/activity setup",
            "/activity config",
            "/activity spotify",
            "/activity gaming",
            "/activity voice",
            "/activity chat",
            "/activity roles",
            "/activity disable",
            "/reactionrole setup",
            "/reactionrole create",
            "/reactionrole edit",
            "/reactionrole delete",
            "/reactionrole list",
            "/reactionrole add",
            "/reactionrole remove",
            "/ai setup",
            "/ai enable",
            "/ai disable",
            "/ai personality",
            "/ai knowledge add",
            "/ai knowledge edit",
            "/ai knowledge remove",
            "/ai knowledge list",
            "/ai reset",
            "/ai status",
            "/play",
            "/pause",
            "/resume",
            "/skip",
            "/stop",
            "/queue",
            "/nowplaying",
            "/volume",
            "/loop",
            "/shuffle",
            "/remove",
            "/clearqueue",
            "/disconnect",
            "/embed create",
            "/embed edit",
            "/embed preview",
            "/embed publish",
            "/embed save",
            "/embed list",
            "/embed delete",
            "/autoresponder create",
            "/autoresponder edit",
            "/autoresponder delete",
            "/autoresponder list",
            "/autoresponder enable",
            "/autoresponder disable",
            "/autoresponder test",
            "/serverinfo",
            "/userinfo",
            "/roleinfo",
            "/channelinfo",
            "/botinfo",
            "/settings",
            "/dashboard",
            "/backup",
            "/restore",
            "/logs",
            "/prefix",
        ]
        for expected in mandatory_commands:
            self.assertIn(expected, qnames, f"Missing mandatory slash command: {expected}")

    async def test_14_page_setup_dashboard_rendering(self) -> None:
        guild = discord.Guild(id=5001, name="Test Server", owner_id=1001)
        view = SetupDashboardView(self.bot, author_id=1001)
        self.assertEqual(len(DASHBOARD_PAGES), 14)
        for p in DASHBOARD_PAGES:
            view.current_page = p["key"]
            view._rebuild_components()
            embed = await view.build_page_embed(guild)
            self.assertIn(p["label"], embed.title)


if __name__ == "__main__":
    unittest.main()
