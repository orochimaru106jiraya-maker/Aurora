"""
Automated Database Tests for Cosmic ki baddie (`tests/test_database.py`).
Tests:
- Database connection lifecycle (`connect`, `close`, `is_connected`)
- Versioned schema migrations (v1 through v6)
- Atomic transactions (`execute_many`) and rollback on error
- Guild configuration persistence, backups, and restoration
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bot.database.manager import DatabaseManager
from bot.database.migrations import MIGRATIONS


class TestDatabaseManager(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_cosmic.db"
        self.db = DatabaseManager(self.db_path)
        await self.db.connect()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.tmp_dir.cleanup()

    async def test_connection_and_migrations(self) -> None:
        self.assertTrue(self.db.is_connected)
        version = await self.db.get_schema_version()
        self.assertEqual(version, len(MIGRATIONS))

        health = await self.db.health_check()
        self.assertTrue(health["connected"])
        self.assertGreaterEqual(len(health["tables"]), 14)

    async def test_atomic_transaction_rollback_on_error(self) -> None:
        # Insert initial guild config
        await self.db.execute(
            "INSERT INTO guild_configs (guild_id, prefix) VALUES (?, ?);",
            (1001, "!"),
        )
        # Attempt a multi-statement transaction where the 2nd statement fails
        with self.assertRaises(Exception):
            await self.db.execute_many(
                [
                    ("UPDATE guild_configs SET prefix = ? WHERE guild_id = ?;", ("?", 1001)),
                    ("INSERT INTO non_existent_table (id) VALUES (1);", ()),
                ]
            )
        # Verify prefix remained '!' due to atomic rollback
        row = await self.db.fetch_one("SELECT prefix FROM guild_configs WHERE guild_id = ?;", (1001,))
        self.assertIsNotNone(row)
        self.assertEqual(row["prefix"], "!")

    async def test_backup_and_restore(self) -> None:
        await self.db.execute(
            "INSERT INTO guild_configs (guild_id, prefix, snipe_limit) VALUES (?, ?, ?);",
            (2002, "$", 40),
        )
        backup = await self.db.create_guild_backup(guild_id=2002, created_by_id=999, label="Pre-Change")
        self.assertGreater(backup["backup_id"], 0)

        # Mutate prefix
        await self.db.execute("UPDATE guild_configs SET prefix = '!' WHERE guild_id = 2002;")
        changed = await self.db.fetch_one("SELECT prefix FROM guild_configs WHERE guild_id = 2002;")
        self.assertEqual(changed["prefix"], "!")

        # Restore backup
        restored = await self.db.restore_guild_backup(2002, backup["backup_id"])
        self.assertTrue(restored)
        after = await self.db.fetch_one("SELECT prefix, snipe_limit FROM guild_configs WHERE guild_id = 2002;")
        self.assertEqual(after["prefix"], "$")
        self.assertEqual(after["snipe_limit"], 40)


if __name__ == "__main__":
    unittest.main()
