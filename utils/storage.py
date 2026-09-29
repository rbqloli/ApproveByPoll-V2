# -*- coding: utf-8 -*-
"""Storage backend selection.

``BotDatabase`` resolves to a PostgreSQL or SQLite implementation based on
``[database] driver`` in ``conf_dir/.secrets.toml`` (default: ``postgres``).
"""

from loguru import logger

from app_conf import settings


def build_database():
    driver = str(settings.get("database.driver", "postgres")).strip().lower()

    if driver in {"sqlite", "sqlite3"}:
        from utils.sqlite_db import AsyncSQLiteDB

        path = str(settings.get("database.path", "data/approvebypoll.db"))
        logger.info(f"🗄️ 使用 SQLite 存储后端: {path}")
        return AsyncSQLiteDB(path)

    from utils.postgres import AsyncPostgresDB

    logger.info("🗄️ 使用 PostgreSQL 存储后端")
    return AsyncPostgresDB()


BotDatabase = build_database()
