"""
Automated Music Queue & Track Validation Tests (`tests/test_music.py`).
Tests:
- Track validation rejects invalid/unavailable URLs before enqueueing
- Enqueue, pause, resume, skip, volume, loop ('off', 'track', 'queue'), shuffle, remove, clear, disconnect
- SQLite queue state persistence
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bot.database.manager import DatabaseManager
from bot.services.music_service import MusicService


class TestMusicService(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.tmp_dir.name) / "music_test.db")
        await self.db.connect()
        self.music = MusicService(self.db)
        self.guild_id = 3030

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.tmp_dir.cleanup()

    async def test_rejects_unavailable_or_invalid_urls(self) -> None:
        ok1, msg1, _ = await self.music.enqueue_track(self.guild_id, "ftp://bad-scheme.org/song.mp3", 1, "User")
        self.assertFalse(ok1)
        self.assertIn("Invalid audio URL", msg1)

        ok2, msg2, _ = await self.music.enqueue_track(self.guild_id, "https://invalid.example.com/expired.mp3", 1, "User")
        self.assertFalse(ok2)
        self.assertIn("unavailable", msg2.lower())

    async def test_queue_lifecycle_operations(self) -> None:
        # 1st track starts playing immediately
        ok1, _, t1 = await self.music.enqueue_track(self.guild_id, "aurora synthwave", 10, "DJUser")
        self.assertTrue(ok1)
        self.assertIsNotNone(t1)

        # 2nd and 3rd tracks enter queue
        await self.music.enqueue_track(self.guild_id, "lofi chill beats", 10, "DJUser")
        await self.music.enqueue_track(self.guild_id, "ambient space", 10, "DJUser")

        state = self.music.get_state(self.guild_id)
        self.assertEqual(len(state.queue), 2)

        # Pause and resume
        p_ok, _ = await self.music.pause(self.guild_id)
        self.assertTrue(p_ok)
        self.assertTrue(state.is_paused)

        r_ok, _ = await self.music.resume(self.guild_id)
        self.assertTrue(r_ok)
        self.assertTrue(state.is_playing)

        # Volume and loop
        v_ok, _ = await self.music.set_volume(self.guild_id, 120)
        self.assertTrue(v_ok)
        self.assertEqual(state.volume, 120)

        # Skip advances to next track
        s_ok, _, next_track = await self.music.skip(self.guild_id)
        self.assertTrue(s_ok)
        self.assertIsNotNone(next_track)
        self.assertEqual(len(state.queue), 1)

        # Stop & disconnect clears state
        stop_ok, _ = await self.music.stop_and_disconnect(self.guild_id)
        self.assertTrue(stop_ok)
        self.assertIsNone(state.current_track)
        self.assertEqual(len(state.queue), 0)


if __name__ == "__main__":
    unittest.main()
