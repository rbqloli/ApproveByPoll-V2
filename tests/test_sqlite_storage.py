import asyncio

import pytest

from utils.sqlite_db import AsyncSQLiteDB


def _run(coro_factory, tmp_path):
    async def scenario():
        db = AsyncSQLiteDB(str(tmp_path / "approvebypoll.db"))
        await db.connect()
        try:
            await coro_factory(db)
        finally:
            await db.close()

    asyncio.run(scenario())


def test_settings_defaults_and_update(tmp_path):
    async def scenario(db: AsyncSQLiteDB):
        settings = await db.get_group_settings(100)
        assert settings["vote_time"] == 600
        assert settings["vote_to_join"] is True
        assert settings["anonymous_vote"] is True
        assert settings["advanced_vote"] is False
        assert settings["mini_voters"] == 3

        await db.update_group_setting(100, "vote_time", 604800)
        await db.update_group_setting(100, "advanced_vote", True)
        await db.update_group_setting(100, "language", "zh_CN")

        settings = await db.get_group_settings(100)
        assert settings["vote_time"] == 604800
        assert settings["advanced_vote"] is True
        assert settings["language"] == "zh_CN"

    _run(scenario, tmp_path)


def test_vote_time_check_constraint(tmp_path):
    async def scenario(db: AsyncSQLiteDB):
        await db.get_group_settings(7)
        with pytest.raises(Exception):
            await db.update_group_setting(7, "vote_time", 10)

    _run(scenario, tmp_path)


def test_join_request_lifecycle(tmp_path):
    async def scenario(db: AsyncSQLiteDB):
        await db.create_join_request("uuid-1", group_id=1, user_id=2)
        assert await db.get_join_request_waiting_by_uuid("uuid-1") is True
        assert await db.get_join_request_waiting_by_uuid("missing") is None
        assert await db.has_waiting_join_request(1, 2) is True

        status = await db.get_join_request_status_by_uuid("uuid-1")
        assert status is not None
        assert status["waiting"] is True
        assert status["result"] is None

        updated = await db.update_join_request(
            "uuid-1", result=True, yes_votes=3, no_votes=1
        )
        assert updated is True
        assert await db.get_join_request_waiting_by_uuid("uuid-1") is False
        assert await db.has_waiting_join_request(1, 2) is False

        status = await db.get_join_request_status_by_uuid("uuid-1")
        assert status["waiting"] is False
        assert status["result"] is True

    _run(scenario, tmp_path)
