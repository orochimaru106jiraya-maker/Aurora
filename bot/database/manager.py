"""
Centralized Database Manager for Cosmic ki baddie.
Provides dual compatibility:
- Uses `aiosqlite` when installed in the Python environment
- Seamlessly falls back to an asyncio-safe `sqlite3` executor wrapper when `aiosqlite` is not installed
- Never assumes a database connection object can be used as an async context manager directly after connection creation
- Supports transactions, migrations, JSON backups, and health diagnostics.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from bot.database.migrations import MIGRATIONS

logger = logging.getLogger("cosmic.database.manager")

try:
    import aiosqlite  # type: ignore
    HAS_AIOSQLITE = True
except ImportError:
    aiosqlite = None
    HAS_AIOSQLITE = False


class DatabaseManager:
    """
    Centralized asynchronous SQLite Database Manager.
    Handles connection lifecycle, concurrency serialization for writes,
    schema migrations, backups, and query execution.
    """

    def __init__(self, db_path: str | Path = "data/cosmic_baddie.db") -> None:
        self.db_path = Path(db_path)
        self._conn: Any = None
        self._sqlite_conn: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()
        self._connected = False
        self.driver_name = "aiosqlite" if HAS_AIOSQLITE else "sqlite3-async-adapter"

    @property
    def is_connected(self) -> bool:
        return self._connected and (self._conn is not None or self._sqlite_conn is not None)

    async def connect(self) -> None:
        """Open connection, enable WAL mode and foreign keys, and run migrations."""
        async with self._lock:
            if self._connected:
                return
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            if HAS_AIOSQLITE and aiosqlite is not None:
                # Explicitly await connect() and store the connection handle
                # (Never do `async with self._conn:` on an already-opened connection)
                self._conn = await aiosqlite.connect(str(self.db_path))
                self._conn.row_factory = aiosqlite.Row
                await self._conn.execute("PRAGMA journal_mode=WAL;")
                await self._conn.execute("PRAGMA foreign_keys=ON;")
                await self._conn.execute("PRAGMA synchronous=NORMAL;")
                await self._conn.commit()
            else:
                def _open_sync() -> sqlite3.Connection:
                    conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
                    conn.row_factory = sqlite3.Row
                    conn.execute("PRAGMA journal_mode=WAL;")
                    conn.execute("PRAGMA foreign_keys=ON;")
                    conn.execute("PRAGMA synchronous=NORMAL;")
                    conn.commit()
                    return conn

                self._sqlite_conn = await asyncio.to_thread(_open_sync)

            self._connected = True
            logger.info("Connected to SQLite database at %s via %s", self.db_path, self.driver_name)

        await self.run_migrations()

    async def close(self) -> None:
        """Close the active database connection cleanly."""
        async with self._lock:
            if not self._connected:
                return
            try:
                if HAS_AIOSQLITE and self._conn is not None:
                    await self._conn.close()
                    self._conn = None
                elif self._sqlite_conn is not None:
                    await asyncio.to_thread(self._sqlite_conn.close)
                    self._sqlite_conn = None
            finally:
                self._connected = False
                logger.info("Database connection closed (%s)", self.db_path)

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Execute a single DML statement and return lastrowid."""
        if not self._connected:
            await self.connect()
        async with self._lock:
            if HAS_AIOSQLITE and self._conn is not None:
                cursor = await self._conn.execute(sql, tuple(params))
                try:
                    last_id = cursor.lastrowid or 0
                finally:
                    await cursor.close()
                await self._conn.commit()
                return int(last_id)
            else:
                assert self._sqlite_conn is not None
                conn = self._sqlite_conn

                def _exec() -> int:
                    cur = conn.execute(sql, tuple(params))
                    try:
                        last_id = cur.lastrowid or 0
                    finally:
                        cur.close()
                    conn.commit()
                    return int(last_id)

                return await asyncio.to_thread(_exec)

    async def execute_many(self, statements: Sequence[Tuple[str, Sequence[Any]]]) -> None:
        """Execute multiple SQL statements atomically inside a transaction."""
        if not self._connected:
            await self.connect()
        async with self._lock:
            if HAS_AIOSQLITE and self._conn is not None:
                await self._conn.execute("BEGIN;")
                try:
                    for sql, params in statements:
                        cursor = await self._conn.execute(sql, tuple(params))
                        await cursor.close()
                    await self._conn.commit()
                except Exception:
                    await self._conn.rollback()
                    raise
            else:
                assert self._sqlite_conn is not None
                conn = self._sqlite_conn

                def _tx() -> None:
                    conn.execute("BEGIN;")
                    try:
                        for sql, params in statements:
                            cur = conn.execute(sql, tuple(params))
                            cur.close()
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        raise

                await asyncio.to_thread(_tx)

    async def fetch_one(self, sql: str, params: Sequence[Any] = ()) -> Optional[Dict[str, Any]]:
        """Fetch a single row as a dictionary or None."""
        if not self._connected:
            await self.connect()
        async with self._lock:
            if HAS_AIOSQLITE and self._conn is not None:
                cursor = await self._conn.execute(sql, tuple(params))
                try:
                    row = await cursor.fetchone()
                    return dict(row) if row is not None else None
                finally:
                    await cursor.close()
            else:
                assert self._sqlite_conn is not None
                conn = self._sqlite_conn

                def _fetch() -> Optional[Dict[str, Any]]:
                    cur = conn.execute(sql, tuple(params))
                    try:
                        row = cur.fetchone()
                        return dict(row) if row is not None else None
                    finally:
                        cur.close()

                return await asyncio.to_thread(_fetch)

    async def fetch_all(self, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        """Fetch all matching rows as a list of dictionaries."""
        if not self._connected:
            await self.connect()
        async with self._lock:
            if HAS_AIOSQLITE and self._conn is not None:
                cursor = await self._conn.execute(sql, tuple(params))
                try:
                    rows = await cursor.fetchall()
                    return [dict(r) for r in rows]
                finally:
                    await cursor.close()
            else:
                assert self._sqlite_conn is not None
                conn = self._sqlite_conn

                def _fetch_all() -> List[Dict[str, Any]]:
                    cur = conn.execute(sql, tuple(params))
                    try:
                        rows = cur.fetchall()
                        return [dict(r) for r in rows]
                    finally:
                        cur.close()

                return await asyncio.to_thread(_fetch_all)

    async def run_migrations(self) -> List[int]:
        """Apply all pending database migrations atomically."""
        await self.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        applied_rows = await self.fetch_all("SELECT version FROM schema_migrations ORDER BY version ASC;")
        applied_versions = {int(r["version"]) for r in applied_rows}
        newly_applied: List[int] = []

        for version, description, statements in MIGRATIONS:
            if version in applied_versions:
                continue
            tx_statements: List[Tuple[str, Sequence[Any]]] = [(stmt, ()) for stmt in statements]
            tx_statements.append(
                (
                    "INSERT INTO schema_migrations (version, description) VALUES (?, ?);",
                    (version, description),
                )
            )
            await self.execute_many(tx_statements)
            newly_applied.append(version)
            logger.info("Applied database migration v%d: %s", version, description)

        return newly_applied

    async def get_schema_version(self) -> int:
        row = await self.fetch_one("SELECT MAX(version) AS max_v FROM schema_migrations;")
        if not row or row.get("max_v") is None:
            return 0
        return int(row["max_v"])

    async def health_check(self) -> Dict[str, Any]:
        """Verify database connectivity, schema version, and table counts."""
        try:
            probe = await self.fetch_one("SELECT 1 AS ok;")
            version = await self.get_schema_version()
            tables = await self.fetch_all(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
            )
            return {
                "connected": bool(probe and probe.get("ok") == 1),
                "driver": self.driver_name,
                "db_path": str(self.db_path),
                "schema_version": version,
                "total_migrations": len(MIGRATIONS),
                "tables": [t["name"] for t in tables],
            }
        except Exception as exc:
            logger.exception("Database health check failed: %s", exc)
            return {
                "connected": False,
                "driver": self.driver_name,
                "db_path": str(self.db_path),
                "error": str(exc),
            }

    async def create_guild_backup(self, guild_id: int, created_by_id: int, label: str = "Manual Backup") -> Dict[str, Any]:
        """Export all guild-scoped configuration rows into a JSON snapshot stored in `server_backups`."""
        guild_cfg = await self.fetch_one("SELECT * FROM guild_configs WHERE guild_id = ?;", (guild_id,))
        ticket_cats = await self.fetch_all("SELECT * FROM ticket_categories WHERE guild_id = ?;", (guild_id,))
        rbac_roles = await self.fetch_all("SELECT * FROM rbac_role_mappings WHERE guild_id = ?;", (guild_id,))
        rbac_cmds = await self.fetch_all("SELECT * FROM rbac_command_rules WHERE guild_id = ?;", (guild_id,))
        jtc_cfgs = await self.fetch_all("SELECT * FROM jtc_configs WHERE guild_id = ?;", (guild_id,))
        auto_resps = await self.fetch_all("SELECT * FROM auto_responders WHERE guild_id = ?;", (guild_id,))
        embed_tpls = await self.fetch_all("SELECT * FROM embed_templates WHERE guild_id = ?;", (guild_id,))

        payload = {
            "guild_id": guild_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "guild_config": guild_cfg or {},
            "ticket_categories": ticket_cats,
            "rbac_role_mappings": rbac_roles,
            "rbac_command_rules": rbac_cmds,
            "jtc_configs": jtc_cfgs,
            "auto_responders": auto_resps,
            "embed_templates": embed_tpls,
        }
        backup_id = await self.execute(
            """
            INSERT INTO server_backups (guild_id, backup_label, payload_json, created_by_id)
            VALUES (?, ?, ?, ?);
            """,
            (guild_id, label, json.dumps(payload), created_by_id),
        )
        return {"backup_id": backup_id, "label": label, "payload": payload}

    async def restore_guild_backup(self, guild_id: int, backup_id: int) -> bool:
        """Restore a previously saved guild backup atomically."""
        row = await self.fetch_one(
            "SELECT * FROM server_backups WHERE backup_id = ? AND guild_id = ?;",
            (backup_id, guild_id),
        )
        if not row:
            return False

        payload = json.loads(row["payload_json"])
        cfg = payload.get("guild_config")
        statements: List[Tuple[str, Sequence[Any]]] = []

        if cfg:
            statements.append(
                (
                    """
                    INSERT INTO guild_configs (
                        guild_id, prefix, mod_log_channel_id, server_log_channel_id,
                        transcript_channel_id, snipe_limit, enabled_modules_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(guild_id) DO UPDATE SET
                        prefix = excluded.prefix,
                        mod_log_channel_id = excluded.mod_log_channel_id,
                        server_log_channel_id = excluded.server_log_channel_id,
                        transcript_channel_id = excluded.transcript_channel_id,
                        snipe_limit = excluded.snipe_limit,
                        enabled_modules_json = excluded.enabled_modules_json,
                        updated_at = datetime('now');
                    """,
                    (
                        guild_id,
                        cfg.get("prefix", "!"),
                        cfg.get("mod_log_channel_id"),
                        cfg.get("server_log_channel_id"),
                        cfg.get("transcript_channel_id"),
                        cfg.get("snipe_limit", 25),
                        cfg.get("enabled_modules_json", "{}"),
                    ),
                )
            )

        if statements:
            await self.execute_many(statements)
        return True
