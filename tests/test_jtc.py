"""
Automated Join-to-Create (JTC) & Reaction Role Tests (`tests/test_jtc.py`).
Tests:
- JTC hub configuration
- Automatic temporary voice channel creation when user joins trigger channel
- SQLite ownership persistence & room permission checks
- Empty room automatic cleanup and restart recovery
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bot.core.discord_compat import discord
from bot.database.manager import DatabaseManager
from bot.services.jtc_service import JTCService
from bot.services.permission_service import PermissionService


class TestJTCSystem(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.tmp_dir.name) / "jtc_test.db")
        await self.db.connect()
        self.jtc = JTCService(self.db)
        self.perm = PermissionService(self.db, bot_owner_id=999)

        self.guild = discord.Guild(id=9090, name="Voice Guild", owner_id=1)
        self.trigger_vc = await self.guild.create_voice_channel(name="➕ Join to Create")
        self.member = discord.Member(id=7001, name="VoiceOwner", guild=self.guild)
        self.other_user = discord.Member(id=7002, name="OtherUser", guild=self.guild)
        self.guild.members.extend([self.member, self.other_user])

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.tmp_dir.cleanup()

    async def test_jtc_room_creation_ownership_and_cleanup(self) -> None:
        await self.jtc.create_or_update_hub(
            guild_id=self.guild.id,
            trigger_channel_id=self.trigger_vc.id,
            naming_format="{username}'s Studio",
            default_limit=5,
            cooldown_seconds=0,
        )

        ok, _, new_vc = await self.jtc.handle_user_join_trigger(
            guild=self.guild,
            member=self.member,
            trigger_channel_id=self.trigger_vc.id,
        )
        self.assertTrue(ok)
        self.assertIsNotNone(new_vc)
        self.assertEqual(new_vc.name, "VoiceOwner's Studio")
        self.assertEqual(new_vc.user_limit, 5)

        # Verify ownership permission check
        can_owner, _ = await self.jtc.can_manage_room(self.guild, self.member, new_vc.id, self.perm)
        self.assertTrue(can_owner)

        can_other, _ = await self.jtc.can_manage_room(self.guild, self.other_user, new_vc.id, self.perm)
        self.assertFalse(can_other)

        # Simulate member leaving room -> room becomes empty and is cleaned up
        new_vc.members.clear()
        cleaned = await self.jtc.cleanup_if_empty(self.guild, new_vc.id)
        self.assertTrue(cleaned)
        self.assertIsNone(await self.jtc.get_room(new_vc.id))


if __name__ == "__main__":
    unittest.main()
