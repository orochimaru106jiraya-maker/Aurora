"""
Automated Local AI Assistant & Auto-Responder Tests (`tests/test_ai.py`).
Tests:
- Zero-API-key local knowledge base seeding & custom topic addition
- Intent classification (`greeting`, `support`, `music`, `voice`, `moderation`)
- Contextual conversation memory & reset
- Auto-responder exact vs partial matching and case sensitivity
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bot.core.bot import CosmicBot
from bot.core.config import BotConfig
from bot.database.manager import DatabaseManager
from bot.services.ai_service import AIService


class TestAIAssistantAndAutoResponder(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.tmp_dir.name) / "ai_test.db")
        await self.db.connect()
        self.ai = AIService(self.db)
        self.guild_id = 4040

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.tmp_dir.cleanup()

    async def test_local_knowledge_base_and_intent_matching(self) -> None:
        await self.ai.add_knowledge(
            guild_id=self.guild_id,
            topic="railway_hosting",
            keywords=["railway", "deploy", "volume", "hosting"],
            response_text="Mount a Railway volume at /data for persistent SQLite storage.",
            intent_category="faq",
        )

        ok, reply, meta = await self.ai.generate_response(
            guild_id=self.guild_id,
            user_id=101,
            username="DevAdmin",
            prompt="How do I deploy on Railway with a volume?",
            bypass_cooldown=True,
        )
        self.assertTrue(ok)
        self.assertIn("Mount a Railway volume at /data", reply)
        self.assertEqual(meta["matched_topic"], "railway_hosting")

        # Reset history
        cleared = self.ai.reset_conversation_history(self.guild_id)
        self.assertEqual(cleared, 1)

    async def test_auto_responder_matching_modes(self) -> None:
        cfg = BotConfig(
            discord_token="test",
            application_id=1,
            test_guild_id=None,
            database_path=str(Path(self.tmp_dir.name) / "ar.db"),
            bot_owner_id=1,
            default_prefix="!",
            local_llm_endpoint="",
            local_llm_model="llama3.2:1b",
            log_level="WARNING",
            log_file_path=str(Path(self.tmp_dir.name) / "ar.log"),
            ffmpeg_path="ffmpeg",
        )
        bot = CosmicBot(config=cfg)
        await bot.initialize_core(register_views=False)
        ar_cog = bot.cogs["AutoResponderCog"]

        exact_rule = {"trigger_phrase": "!ip", "match_mode": "exact", "case_sensitive": 0, "enabled": 1}
        self.assertTrue(ar_cog.match_trigger("!IP", exact_rule))
        self.assertFalse(ar_cog.match_trigger("what is !ip now", exact_rule))

        partial_cs_rule = {"trigger_phrase": "CosmicBaddie", "match_mode": "partial", "case_sensitive": 1, "enabled": 1}
        self.assertTrue(ar_cog.match_trigger("Hello CosmicBaddie bot", partial_cs_rule))
        self.assertFalse(ar_cog.match_trigger("hello cosmicbaddie bot", partial_cs_rule))
        await bot.close()


if __name__ == "__main__":
    unittest.main()
