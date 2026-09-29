# -*- coding: utf-8 -*-
"""SQLite storage backend.

Mirrors the public interface of :class:`utils.postgres.AsyncPostgresDB` so the
bot can run without a PostgreSQL server (handy for small single-instance
deployments). Enable it with ``[database] driver = "sqlite"`` in
``conf_dir/.secrets.toml``.
"""

import asyncio
import os
from contextlib import asynccontextmanager

import aiosqlite
from loguru import logger

BOOLEAN_SETTING_FIELDS = {
    "vote_to_join",
    "pin_msg",
    "clean_pinned_message",
    "anonymous_vote",
    "advanced_vote",
}

ALLOWED_SETTING_FIELDS = {
    "vote_to_join",
    "vote_time",
    "pin_msg",
    "clean_pinned_message",
    "anonymous_vote",
    "advanced_vote",
    "language",
    "mini_voters",
}

SELECT_SETTING = """
    SELECT group_id, vote_to_join, vote_time, pin_msg, clean_pinned_message,
           anonymous_vote, advanced_vote, language, mini_voters
    FROM setting
    WHERE group_id = ?
"""


def _row_to_dict(row: aiosqlite.Row) -> dict:
    return {key: row[key] for key in row.keys()}


class AsyncSQLiteDB:
    DEFAULT_GROUP_SETTINGS = {
        "vote_to_join": True,
        "vote_time": 600,
        "pin_msg": False,
        "clean_pinned_message": False,
        "anonymous_vote": True,
        "advanced_vote": False,
        "language": "en_US",
        "mini_voters": 3,
    }

    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None
        # SQLite handles one writer at a time; serialize access explicitly.
        self._lock = asyncio.Lock()

    async def connect(self):
        try:
            directory = os.path.dirname(os.path.abspath(self.path))
            if directory:
                os.makedirs(directory, exist_ok=True)
            self.conn = await aiosqlite.connect(self.path)
            self.conn.row_factory = aiosqlite.Row
            await self.conn.execute("PRAGMA journal_mode=WAL")
            await self.conn.execute("PRAGMA foreign_keys=ON")
            await self.conn.commit()
            logger.success(f"Successfully connected to SQLite database at {self.path}")
            await self.ensure_tables_exist()
        except Exception as e:
            logger.error(f"Failed to connect to SQLite database: {str(e)}")
            raise

    async def close(self):
        try:
            if self.conn is not None:
                await self.conn.close()
                self.conn = None
                logger.info("SQLite database connection closed successfully")
        except Exception as e:
            logger.error(f"Error closing SQLite database: {str(e)}")
            raise

    @asynccontextmanager
    async def _acquire(self):
        if self.conn is None:
            raise RuntimeError("SQLite connection is not established")
        async with self._lock:
            yield self.conn

    async def ensure_tables_exist(self):
        try:
            async with self._acquire() as connection:
                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS setting (
                        group_id INTEGER PRIMARY KEY,
                        vote_to_join INTEGER NOT NULL DEFAULT 1,
                        vote_time INTEGER NOT NULL DEFAULT 600
                            CHECK (vote_time BETWEEN 30 AND 604800),
                        pin_msg INTEGER NOT NULL DEFAULT 0,
                        clean_pinned_message INTEGER NOT NULL DEFAULT 0,
                        anonymous_vote INTEGER NOT NULL DEFAULT 1,
                        advanced_vote INTEGER NOT NULL DEFAULT 0,
                        language TEXT NOT NULL DEFAULT 'en_US',
                        mini_voters INTEGER NOT NULL DEFAULT 3
                            CHECK (mini_voters BETWEEN 1 AND 500)
                    )
                """)
                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS join_request (
                        uuid TEXT PRIMARY KEY,
                        group_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        request_time TEXT NOT NULL,
                        waiting INTEGER NOT NULL,
                        result INTEGER NULL,
                        admin INTEGER NULL,
                        yes_votes INTEGER NULL,
                        no_votes INTEGER NULL
                    )
                """)
                await connection.commit()
            logger.success("Database tables checked and created if needed")
        except Exception as e:
            logger.error(f"Error ensuring tables exist: {str(e)}")
            raise

    def _settings_from_row(self, row: aiosqlite.Row) -> dict:
        settings = _row_to_dict(row)
        for field in BOOLEAN_SETTING_FIELDS:
            settings[field] = bool(settings[field])
        return settings

    async def get_group_settings(self, group_id: int) -> dict:
        try:
            async with self._acquire() as connection:
                cursor = await connection.execute(SELECT_SETTING, (group_id,))
                row = await cursor.fetchone()
                await cursor.close()

                if row:
                    return self._settings_from_row(row)

                defaults = self.DEFAULT_GROUP_SETTINGS
                await connection.execute(
                    """
                    INSERT OR IGNORE INTO setting (
                        group_id, vote_to_join, vote_time, pin_msg,
                        clean_pinned_message, anonymous_vote, advanced_vote,
                        language, mini_voters
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        group_id,
                        int(defaults["vote_to_join"]),
                        defaults["vote_time"],
                        int(defaults["pin_msg"]),
                        int(defaults["clean_pinned_message"]),
                        int(defaults["anonymous_vote"]),
                        int(defaults["advanced_vote"]),
                        defaults["language"],
                        defaults["mini_voters"],
                    ),
                )
                await connection.commit()

                cursor = await connection.execute(SELECT_SETTING, (group_id,))
                row = await cursor.fetchone()
                await cursor.close()
                return self._settings_from_row(row)
        except Exception as e:
            logger.error(
                f"Error getting/creating group settings for {group_id}: {str(e)}"
            )
            raise

    async def create_join_request(self, uuid: str, group_id: int, user_id: int) -> None:
        try:
            async with self._acquire() as connection:
                await connection.execute(
                    """
                    INSERT INTO join_request (
                        uuid, group_id, user_id, request_time, waiting, result, admin
                    ) VALUES (?, ?, ?, CURRENT_TIMESTAMP, 1, NULL, NULL)
                    """,
                    (str(uuid), group_id, user_id),
                )
                await connection.commit()
        except Exception as e:
            logger.error(f"Error creating join_request for uuid={uuid}: {str(e)}")
            raise

    async def update_join_request(
        self,
        uuid: str,
        result: bool,
        admin: int | None = None,
        yes_votes: int | None = None,
        no_votes: int | None = None,
    ) -> bool:
        try:
            async with self._acquire() as connection:
                if yes_votes is None and no_votes is None:
                    cursor = await connection.execute(
                        """
                        UPDATE join_request
                        SET result = ?, admin = ?, waiting = 0
                        WHERE uuid = ?
                        """,
                        (int(result), admin, str(uuid)),
                    )
                else:
                    cursor = await connection.execute(
                        """
                        UPDATE join_request
                        SET result = ?, admin = ?, waiting = 0,
                            yes_votes = COALESCE(?, yes_votes),
                            no_votes = COALESCE(?, no_votes)
                        WHERE uuid = ?
                        """,
                        (int(result), admin, yes_votes, no_votes, str(uuid)),
                    )
                await connection.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating join_request for uuid={uuid}: {str(e)}")
            raise

    async def has_waiting_join_request(self, group_id: int, user_id: int) -> bool:
        try:
            async with self._acquire() as connection:
                cursor = await connection.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM join_request
                        WHERE group_id = ? AND user_id = ? AND waiting = 1
                    )
                    """,
                    (group_id, user_id),
                )
                row = await cursor.fetchone()
                await cursor.close()
                return bool(row[0])
        except Exception as e:
            logger.error(
                f"Error checking waiting join_request for group_id={group_id}, user_id={user_id}: {str(e)}"
            )
            raise

    async def get_join_request_waiting_by_uuid(self, uuid: str) -> bool | None:
        try:
            async with self._acquire() as connection:
                cursor = await connection.execute(
                    """
                    SELECT waiting
                    FROM join_request
                    WHERE uuid = ?
                    """,
                    (str(uuid),),
                )
                row = await cursor.fetchone()
                await cursor.close()
                if row is None:
                    return None
                return bool(row[0])
        except Exception as e:
            logger.error(f"Error querying waiting status for uuid={uuid}: {str(e)}")
            raise

    async def get_join_request_status_by_uuid(self, uuid: str) -> dict | None:
        try:
            async with self._acquire() as connection:
                cursor = await connection.execute(
                    """
                    SELECT uuid, group_id, user_id, waiting, result
                    FROM join_request
                    WHERE uuid = ?
                    """,
                    (str(uuid),),
                )
                row = await cursor.fetchone()
                await cursor.close()
                if row is None:
                    return None
                status = _row_to_dict(row)
                status["waiting"] = bool(status["waiting"])
                if status["result"] is not None:
                    status["result"] = bool(status["result"])
                return status
        except Exception as e:
            logger.error(
                f"Error querying join request status for uuid={uuid}: {str(e)}"
            )
            raise

    async def update_group_setting(self, group_id: int, item: str, value) -> bool:
        if item not in ALLOWED_SETTING_FIELDS:
            raise ValueError(f"Unsupported setting field: {item}")

        try:
            await self.get_group_settings(group_id)
            if item in BOOLEAN_SETTING_FIELDS:
                value = int(bool(value))

            async with self._acquire() as connection:
                cursor = await connection.execute(
                    f"UPDATE setting SET {item} = ? WHERE group_id = ?",
                    (value, group_id),
                )
                await connection.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(
                f"Error updating group setting for group_id={group_id}, item={item}: {str(e)}"
            )
            raise
