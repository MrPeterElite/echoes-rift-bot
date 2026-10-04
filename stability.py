"""Startup migration and backups. No VK connection is needed to run this module."""
from contextlib import closing
import asyncio
import sqlite3
import time
from pathlib import Path

import database as db

from systems.vitals import ensure_health_tables

from systems.armor import ensure_armor_tables

VERSION = "armor-1"


def backup_before_migration():
    source = Path(db.DB_NAME)
    if not source.exists():
        return None
    with closing(sqlite3.connect(source)) as conn:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone()
        if exists and conn.execute("SELECT 1 FROM schema_migrations WHERE version=?", (VERSION,)).fetchone():
            return None
        folder = source.parent / "backups"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"database-before-{VERSION}-{time.time_ns()}.db"
        with closing(sqlite3.connect(target)) as backup:
            conn.backup(backup)
            if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Database backup integrity check failed; migration stopped")
    return target


async def initialize_database():
    backup = await asyncio.to_thread(backup_before_migration)
    if backup:
        print(f"[database] Migration backup: {backup}")
    for migration in (
        db.create_tables, db.ensure_career_columns, db.ensure_faction_rank_columns,
        db.ensure_quest_tables, db.ensure_housing_tables, db.ensure_location_tables,
        db.ensure_inventory_tables, db.ensure_core_update_tables, db.ensure_stability_tables, ensure_health_tables, ensure_armor_tables,
    ):
        await migration()
    async with db._transaction() as connection:
        await connection.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)", (VERSION,))


if __name__ == "__main__":
    asyncio.run(initialize_database())
