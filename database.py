import os
import shutil
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from dotenv import load_dotenv


_PROJECT_ROOT = Path(__file__).resolve().parent
_SEED_DB_PATH = _PROJECT_ROOT / "database.db"
load_dotenv(_PROJECT_ROOT / ".env")


def _resolve_database_path():
    configured = os.getenv("DATABASE_PATH") or os.getenv("DB_PATH")
    if configured:
        path = Path(configured)
    elif os.getenv("DATA_DIR"):
        path = Path(os.environ["DATA_DIR"]) / "database.db"
    elif Path("/app/data").is_dir():
        # Bothost сохраняет /app/data между обновлениями контейнера.
        path = Path("/app/data/database.db")
    else:
        # Обычный локальный запуск Windows/Linux.
        path = _SEED_DB_PATH

    path.parent.mkdir(parents=True, exist_ok=True)

    # При первом запуске на хостинге переносим существующую базу проекта
    # в постоянное хранилище. Последующие деплои её не перезаписывают.
    try:
        same_file = path.resolve() == _SEED_DB_PATH.resolve()
    except OSError:
        same_file = False
    if not same_file and not path.exists() and _SEED_DB_PATH.exists():
        shutil.copy2(_SEED_DB_PATH, path)
        print(f"[database] Начальная база скопирована в {path}")

    return str(path)


DB_NAME = _resolve_database_path()


async def connect():
    return await aiosqlite.connect(DB_NAME, timeout=30)


async def create_tables():
    db = await connect()

    await db.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance INTEGER DEFAULT 1500,
        xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1
    )
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS characters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        age TEXT,
        gender TEXT,
        faction TEXT,
        biology TEXT,
        personality TEXT,
        history TEXT,
        arts TEXT,
        status TEXT DEFAULT 'pending'
    )
    """)

    await db.commit()
    await db.close()


async def create_user(user_id):
    async with _transaction() as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 1500)", (user_id,))



async def get_user(user_id):
    db = await connect()

    cursor = await db.execute(
        "SELECT * FROM users WHERE user_id = ?",
        (user_id,)
    )
    user = await cursor.fetchone()

    await db.close()
    return user


async def reset_user(user_id, expected_character_id=None):
    """Delete confirmed character state and restore the requested starting balance."""
    async with _transaction() as db:
        cursor = await db.execute("SELECT id FROM characters WHERE user_id = ? ORDER BY id DESC", (user_id,))
        ids = [row[0] for row in await cursor.fetchall()]
        if expected_character_id is not None and (not ids or ids[0] != expected_character_id):
            return False
        for cid in ids:
            await _delete_character_state(db, cid)
        await db.execute("DELETE FROM character_drafts WHERE user_id = ?", (user_id,))
        await db.execute("UPDATE users SET balance = 1500, xp = 0, level = 1 WHERE user_id = ?", (user_id,))
        return True



async def create_character(data):
    async with _transaction() as db:
        cursor = await db.execute("SELECT id FROM characters WHERE user_id = ? ORDER BY id DESC LIMIT 1", (data["user_id"],))
        existing = await cursor.fetchone()
        if existing:
            return existing[0]
        await db.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 1500)", (data["user_id"],))
        cursor = await db.execute("""INSERT INTO characters
            (user_id, name, age, gender, faction, biology, personality, history, arts, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
            tuple(data[k] for k in ('user_id','name','age','gender','faction','biology','personality','history')) + (','.join(data['arts']),))
        await db.execute("DELETE FROM character_drafts WHERE user_id = ?", (data['user_id'],))
        return cursor.lastrowid



async def get_character_by_user(user_id):
    db = await connect()

    cursor = await db.execute(
        "SELECT * FROM characters WHERE user_id = ? ORDER BY id DESC LIMIT 1",
        (user_id,)
    )
    character = await cursor.fetchone()

    await db.close()
    return character


async def get_character_by_id(character_id):
    db = await connect()

    cursor = await db.execute(
        "SELECT * FROM characters WHERE id = ?",
        (character_id,)
    )
    character = await cursor.fetchone()

    await db.close()
    return character


async def update_character_status(character_id, status):
    db = await connect()

    await db.execute(
        "UPDATE characters SET status = ? WHERE id = ?",
        (status, character_id)
    )

    await db.commit()
    await db.close()


async def get_approved_characters():
    db = await connect()

    cursor = await db.execute(
        "SELECT * FROM characters WHERE status = 'approved' ORDER BY id DESC LIMIT 20"
    )
    characters = await cursor.fetchall()

    await db.close()
    return characters
async def ensure_career_columns():
    db = await connect()

    columns = [
        ("department", "TEXT"),
        ("job_title", "TEXT"),
        ("job_level", "INTEGER DEFAULT 0"),
        ("last_salary_time", "INTEGER DEFAULT 0")
    ]

    cursor = await db.execute("PRAGMA table_info(characters)")
    existing = {row[1] for row in await cursor.fetchall()}
    for column_name, column_type in columns:
        if column_name not in existing:
            await db.execute(f"ALTER TABLE characters ADD COLUMN {column_name} {column_type}")
    await db.commit()
    await db.close()


async def update_character_job(character_id, department, job_title, job_level):
    db = await connect()

    await db.execute("""
        UPDATE characters
        SET department = ?, job_title = ?, job_level = ?
        WHERE id = ?
    """, (department, job_title, job_level, character_id))

    await db.commit()
    await db.close()


async def update_last_salary(character_id, timestamp):
    db = await connect()

    await db.execute(
        "UPDATE characters SET last_salary_time = ? WHERE id = ?",
        (timestamp, character_id)
    )

    await db.commit()
    await db.close()


async def add_balance(user_id, amount):
    db = await connect()

    await db.execute(
        "UPDATE users SET balance = balance + ? WHERE user_id = ?",
        (amount, user_id)
    )

    await db.commit()
    await db.close()

async def ensure_faction_rank_columns():
    db = await connect()
    columns = [
        ("faction_rank", "TEXT"),
        ("faction_rank_level", "INTEGER DEFAULT 0")
    ]
    cursor = await db.execute("PRAGMA table_info(characters)")
    existing = {row[1] for row in await cursor.fetchall()}
    for column_name, column_type in columns:
        if column_name not in existing:
            await db.execute(f"ALTER TABLE characters ADD COLUMN {column_name} {column_type}")
    await db.commit()
    await db.close()


async def update_faction_rank(character_id, faction_rank, faction_rank_level):
    db = await connect()
    await db.execute("""
        UPDATE characters
        SET faction_rank = ?, faction_rank_level = ?
        WHERE id = ?
    """, (faction_rank, faction_rank_level, character_id))
    await db.commit()
    await db.close()


HOUSING_PRICES = {
    "V": 125,
    "IV": 350,
    "III": 900,
    "II": 1500,
    "I": 0
}


async def ensure_housing_tables():
    db = await connect()

    await db.execute("""
    CREATE TABLE IF NOT EXISTS housing (
        character_id INTEGER PRIMARY KEY,
        housing_class TEXT,
        sector TEXT,
        weekly_rent INTEGER DEFAULT 0,
        last_payment_time INTEGER DEFAULT 0,
        description TEXT DEFAULT '',
        visibility TEXT DEFAULT 'public'
    )
    """)

    # Мягкая миграция для уже существующих баз проекта.
    cursor = await db.execute("PRAGMA table_info(housing)")
    columns = {row[1] for row in await cursor.fetchall()}
    if "description" not in columns:
        await db.execute("ALTER TABLE housing ADD COLUMN description TEXT DEFAULT ''")
    if "visibility" not in columns:
        await db.execute("ALTER TABLE housing ADD COLUMN visibility TEXT DEFAULT 'public'")

    await db.execute("""
    CREATE TABLE IF NOT EXISTS housing_interiors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        character_id INTEGER NOT NULL,
        set_code TEXT NOT NULL,
        item_name TEXT NOT NULL,
        installed_at INTEGER DEFAULT 0
    )
    """)

    await db.execute("""
    CREATE INDEX IF NOT EXISTS idx_housing_interiors_character
    ON housing_interiors(character_id)
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS housing_interior_slots (
        interior_id INTEGER NOT NULL,
        character_id INTEGER NOT NULL,
        slot TEXT NOT NULL,
        UNIQUE(character_id, slot)
    )
    """)

    await db.execute("""
    CREATE INDEX IF NOT EXISTS idx_housing_interior_slots_interior
    ON housing_interior_slots(interior_id)
    """)

    await db.commit()
    await db.close()


async def get_housing(character_id):
    await ensure_housing_tables()
    db = await connect()

    cursor = await db.execute(
        "SELECT * FROM housing WHERE character_id = ?",
        (character_id,)
    )
    housing = await cursor.fetchone()

    await db.close()
    return housing


async def assign_housing(character_id, housing_class, sector):
    await ensure_housing_tables()
    weekly_rent = HOUSING_PRICES.get(housing_class, 0)

    db = await connect()

    # UPDATE + INSERT вместо INSERT OR REPLACE: так новые поля Кают 2.0
    # (описание/публичность) не сбрасываются при повторной выдаче жилья.
    cursor = await db.execute(
        "SELECT character_id FROM housing WHERE character_id = ?",
        (character_id,)
    )
    exists = await cursor.fetchone()

    if exists:
        await db.execute("""
            UPDATE housing
            SET housing_class = ?, sector = ?, weekly_rent = ?
            WHERE character_id = ?
        """, (housing_class, sector, weekly_rent, character_id))
    else:
        await db.execute("""
            INSERT INTO housing (
                character_id, housing_class, sector, weekly_rent,
                last_payment_time, description, visibility
            )
            VALUES (?, ?, ?, ?, 0, '', 'public')
        """, (character_id, housing_class, sector, weekly_rent))

    await db.commit()
    await db.close()


async def remove_housing(character_id):
    """Изъять жильё и безопасно вернуть установленные комплекты в инвентарь."""
    await ensure_housing_tables()
    await ensure_inventory_tables()
    db = await connect()

    try:
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute("""
            SELECT item_name
            FROM housing_interiors
            WHERE character_id = ?
        """, (character_id,))
        rows = await cursor.fetchall()

        for (item_name,) in rows:
            await db.execute("""
                INSERT INTO inventory (character_id, category, item_name, quantity)
                VALUES (?, 'furniture', ?, 1)
                ON CONFLICT(character_id, category, item_name)
                DO UPDATE SET quantity = quantity + 1
            """, (character_id, item_name))

        await db.execute(
            "DELETE FROM housing_interior_slots WHERE character_id = ?",
            (character_id,)
        )
        await db.execute(
            "DELETE FROM housing_interiors WHERE character_id = ?",
            (character_id,)
        )
        await db.execute(
            "DELETE FROM housing WHERE character_id = ?",
            (character_id,)
        )
        await db.commit()
        return len(rows)
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


async def update_housing_sector(character_id, sector):
    await ensure_housing_tables()
    db = await connect()

    await db.execute(
        "UPDATE housing SET sector = ? WHERE character_id = ?",
        (sector, character_id)
    )

    await db.commit()
    await db.close()


async def update_housing_class(character_id, housing_class):
    await ensure_housing_tables()
    weekly_rent = HOUSING_PRICES.get(housing_class, 0)

    db = await connect()

    await db.execute("""
        UPDATE housing
        SET housing_class = ?, weekly_rent = ?
        WHERE character_id = ?
    """, (housing_class, weekly_rent, character_id))

    await db.commit()
    await db.close()


async def update_housing_payment(character_id, timestamp):
    await ensure_housing_tables()
    db = await connect()

    await db.execute(
        "UPDATE housing SET last_payment_time = ? WHERE character_id = ?",
        (timestamp, character_id)
    )

    await db.commit()
    await db.close()


async def get_housing_interiors(character_id):
    await ensure_housing_tables()
    db = await connect()
    cursor = await db.execute("""
        SELECT id, set_code, item_name, installed_at
        FROM housing_interiors
        WHERE character_id = ?
        ORDER BY installed_at, id
    """, (character_id,))
    rows = await cursor.fetchall()
    await db.close()
    return rows


async def install_housing_interior(character_id, set_code, item_name, timestamp, slots, max_slots):
    """Атомарно перенести комплект из инвентаря и занять его интерьерные слоты."""
    await ensure_housing_tables()
    await ensure_inventory_tables()
    slots = list(dict.fromkeys(slots or []))
    if not slots:
        return False, "invalid_slots"

    db = await connect()

    try:
        # BEGIN IMMEDIATE сериализует конкурирующие установки в SQLite:
        # две одновременные команды не смогут занять один слот или превысить лимит.
        await db.execute("BEGIN IMMEDIATE")

        cursor = await db.execute("""
            SELECT COUNT(*)
            FROM housing_interior_slots
            WHERE character_id = ?
        """, (character_id,))
        used_slots = (await cursor.fetchone())[0]
        if used_slots + len(slots) > max_slots:
            await db.rollback()
            return False, "capacity"

        placeholders = ",".join("?" for _ in slots)
        cursor = await db.execute(
            f"""
            SELECT slot
            FROM housing_interior_slots
            WHERE character_id = ? AND slot IN ({placeholders})
            LIMIT 1
            """,
            (character_id, *slots)
        )
        if await cursor.fetchone():
            await db.rollback()
            return False, "slot_conflict"

        cursor = await db.execute("""
            SELECT id, quantity
            FROM inventory
            WHERE character_id = ?
              AND category = 'furniture'
              AND lower(item_name) = lower(?)
              AND quantity > 0
            LIMIT 1
        """, (character_id, item_name))
        row = await cursor.fetchone()
        if not row:
            await db.rollback()
            return False, "not_found"

        item_id, quantity = row
        cursor = await db.execute("""
            INSERT INTO housing_interiors (character_id, set_code, item_name, installed_at)
            VALUES (?, ?, ?, ?)
        """, (character_id, set_code, item_name, timestamp))
        interior_id = cursor.lastrowid

        for slot in slots:
            await db.execute("""
                INSERT INTO housing_interior_slots (interior_id, character_id, slot)
                VALUES (?, ?, ?)
            """, (interior_id, character_id, slot))

        if quantity == 1:
            await db.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
        else:
            await db.execute(
                "UPDATE inventory SET quantity = quantity - 1 WHERE id = ?",
                (item_id,)
            )

        await db.commit()
        return True, "ok"
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


async def remove_housing_interior(character_id, interior_id):
    """Атомарно снять комплект и вернуть его в обычный инвентарь."""
    await ensure_housing_tables()
    await ensure_inventory_tables()
    db = await connect()

    try:
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute("""
            SELECT item_name
            FROM housing_interiors
            WHERE id = ? AND character_id = ?
        """, (interior_id, character_id))
        row = await cursor.fetchone()
        if not row:
            await db.rollback()
            return False, "not_found", None

        item_name = row[0]
        await db.execute(
            "DELETE FROM housing_interior_slots WHERE interior_id = ? AND character_id = ?",
            (interior_id, character_id)
        )
        await db.execute(
            "DELETE FROM housing_interiors WHERE id = ? AND character_id = ?",
            (interior_id, character_id)
        )
        await db.execute("""
            INSERT INTO inventory (character_id, category, item_name, quantity)
            VALUES (?, 'furniture', ?, 1)
            ON CONFLICT(character_id, category, item_name)
            DO UPDATE SET quantity = quantity + 1
        """, (character_id, item_name))
        await db.commit()
        return True, "ok", item_name
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


async def update_housing_description(character_id, description):
    await ensure_housing_tables()
    db = await connect()
    await db.execute(
        "UPDATE housing SET description = ? WHERE character_id = ?",
        (description, character_id)
    )
    await db.commit()
    await db.close()


async def update_housing_visibility(character_id, visibility):
    await ensure_housing_tables()
    if visibility not in {"public", "private"}:
        raise ValueError("Unsupported housing visibility")
    db = await connect()
    await db.execute(
        "UPDATE housing SET visibility = ? WHERE character_id = ?",
        (visibility, character_id)
    )
    await db.commit()
    await db.close()


async def subtract_balance(user_id, amount):
    if not isinstance(amount, int) or amount <= 0:
        return False
    async with _transaction() as db:
        return await _debit(db, user_id, amount)




async def ensure_quest_tables():
    db = await connect()
    await db.execute("""
    CREATE TABLE IF NOT EXISTS weekly_quests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        character_id INTEGER,
        title TEXT,
        description TEXT,
        credits INTEGER DEFAULT 0,
        xp INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active',
        assigned_at INTEGER DEFAULT 0,
        report_text TEXT,
        report_attachment TEXT,
        report_time INTEGER DEFAULT 0,
        location TEXT DEFAULT '',
        difficulty TEXT DEFAULT '',
        report_requirements TEXT DEFAULT ''
    )
    """)
    cursor = await db.execute("PRAGMA table_info(weekly_quests)")
    columns = {row[1] for row in await cursor.fetchall()}
    migrations = {
        "location": "TEXT DEFAULT ''",
        "difficulty": "TEXT DEFAULT ''",
        "report_requirements": "TEXT DEFAULT ''",
    }
    for column, column_type in migrations.items():
        if column not in columns:
            await db.execute(f"ALTER TABLE weekly_quests ADD COLUMN {column} {column_type}")
    await db.commit()
    await db.close()

async def get_current_quest(character_id):
    db = await connect()
    cursor = await db.execute("""
        SELECT * FROM weekly_quests
        WHERE character_id = ?
        AND status IN ('active', 'review', 'rejected')
        ORDER BY id DESC
        LIMIT 1
    """, (character_id,))
    row = await cursor.fetchone()
    await db.close()
    return row

async def get_last_quest(character_id):
    db = await connect()
    cursor = await db.execute("""
        SELECT * FROM weekly_quests
        WHERE character_id = ?
        ORDER BY assigned_at DESC, id DESC
        LIMIT 1
    """, (character_id,))
    row = await cursor.fetchone()
    await db.close()
    return row

async def create_weekly_quest(
    character_id, title, description, credits, xp, assigned_at,
    location="", difficulty="", report_requirements=""
):
    async with _transaction() as db:
        cursor = await db.execute("SELECT id, status, assigned_at FROM weekly_quests WHERE character_id = ? ORDER BY id DESC LIMIT 1", (character_id,))
        last = await cursor.fetchone()
        if last and (last[1] in ('active', 'review', 'rejected') or assigned_at - (last[2] or 0) < 7 * 86400):
            return last[0]
        cursor = await db.execute("""
            INSERT INTO weekly_quests (
                character_id, title, description, credits, xp, status, assigned_at,
                location, difficulty, report_requirements
            )
            VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
        """, (
            character_id, title, description, credits, xp, assigned_at,
            location, difficulty, report_requirements
        ))
        return cursor.lastrowid


async def submit_quest_report(quest_id, report_text, report_attachment, report_time):
    async with _transaction() as db:
        cursor = await db.execute("""UPDATE weekly_quests SET status = 'review', report_text = ?,
            report_attachment = ?, report_time = ? WHERE id = ? AND status IN ('active', 'rejected')""",
            (report_text, report_attachment, report_time, quest_id))
        return cursor.rowcount == 1


async def get_quest_by_id(quest_id):
    db = await connect()
    cursor = await db.execute("SELECT * FROM weekly_quests WHERE id = ?", (quest_id,))
    row = await cursor.fetchone()
    await db.close()
    return row

async def update_quest_status(quest_id, status):
    # Completion and rewards must only pass through complete_quest_with_rewards.
    if status != 'rejected':
        return False
    async with _transaction() as db:
        cursor = await db.execute("UPDATE weekly_quests SET status = 'rejected' WHERE id = ? AND status = 'review'", (quest_id,))
        return cursor.rowcount == 1


async def add_xp(user_id, amount):
    db = await connect()
    await db.execute("UPDATE users SET xp = xp + ? WHERE user_id = ?", (amount, user_id))
    await db.commit()
    await db.close()


LOCATIONS_SEED = {
    "холл": ("🏛 Холл станции", 2000000011, "https://vk.me/join/6voM0CIsS94uS8cABJeXJCsoJ4TDseg3unI="),
    "медблок": ("🚑 Медблок станции", 2000000010, "https://vk.me/join/e0iTTNNi4uWIbvmIDzo/5ls7QaH_0o_j2LY="),
    "инженерия": ("⚙️ Инженерный отдел станции", 2000000009, "https://vk.me/join/TatJwu5OYLBd350t_TI2uNhkSN_DTwyMaXI="),
    "казармы": ("🛡 Казармы отдела безопасности", 2000000008, "https://vk.me/join/EDmKUG3044W6/qYh3WJV8PvTp64wXmCRpAo="),
    "храм": ("🔥 Храм Пепла станции", 2000000007, "https://vk.me/join/EKScfHooS_pB0AwrMvUAbhLX7uXi9GT5v04="),
    "жилые": ("🏠 Жилые блоки", 2000000006, "https://vk.me/join/eFjz7mle/HbQHOMTla4QC1ACyhdiLScqI/g="),
    "корабль": ("🚀 Корабль", 2000000005, "https://vk.me/join/rJ8qgyHZhLcslNAzrvJN92wuxl5_0m/HoZQ="),
    "колония": ("🏙 Колония на спутнике", 2000000004, "https://vk.me/join/Pnj3J_I_ib4ALHLpCzHDvXRrLWOrZQMD0AA="),
    "наука": ("🔬 Научный отдел", 2000000003, "https://vk.me/join/ET9P3Lzi4IbsaVVLjg8IIplhGLKiY5sxKw8="),
    "поверхность": ("🌍 Поверхность на колонии", 2000000002, "https://vk.me/join/khlMZbeEFWj69A8cIorqgTfhdO00fxDQZ2M="),
}


async def ensure_location_tables():
    db = await connect()
    await db.execute("""
    CREATE TABLE IF NOT EXISTS locations (
        code TEXT PRIMARY KEY,
        name TEXT,
        peer_id INTEGER UNIQUE,
        invite_link TEXT
    )
    """)
    await db.execute("""
    CREATE TABLE IF NOT EXISTS character_locations (
        character_id INTEGER PRIMARY KEY,
        location_code TEXT DEFAULT 'холл'
    )
    """)
    for code, data in LOCATIONS_SEED.items():
        name, peer_id, invite_link = data
        await db.execute("""
            INSERT OR IGNORE INTO locations (code, name, peer_id, invite_link)
            VALUES (?, ?, ?, ?)
        """, (code, name, peer_id, invite_link))
    await db.commit()
    await db.close()


async def get_all_locations():
    await ensure_location_tables()
    db = await connect()
    cursor = await db.execute("SELECT code, name, peer_id, invite_link FROM locations ORDER BY code")
    rows = await cursor.fetchall()
    await db.close()
    return rows


async def get_location_by_code(code):
    await ensure_location_tables()
    db = await connect()
    cursor = await db.execute("SELECT code, name, peer_id, invite_link FROM locations WHERE code = ?", (code,))
    row = await cursor.fetchone()
    await db.close()
    return row


async def get_location_by_peer(peer_id):
    await ensure_location_tables()
    db = await connect()
    cursor = await db.execute("SELECT code, name, peer_id, invite_link FROM locations WHERE peer_id = ?", (peer_id,))
    row = await cursor.fetchone()
    await db.close()
    return row


async def get_character_location(character_id):
    await ensure_location_tables()
    db = await connect()
    cursor = await db.execute("""
        SELECT l.code, l.name, l.peer_id, l.invite_link
        FROM character_locations cl
        JOIN locations l ON l.code = cl.location_code
        WHERE cl.character_id = ?
    """, (character_id,))
    row = await cursor.fetchone()
    if not row:
        await db.execute("INSERT OR REPLACE INTO character_locations (character_id, location_code) VALUES (?, 'холл')", (character_id,))
        await db.commit()
        cursor = await db.execute("SELECT code, name, peer_id, invite_link FROM locations WHERE code = 'холл'")
        row = await cursor.fetchone()
    await db.close()
    return row


async def set_character_location(character_id, location_code):
    await ensure_location_tables()
    db = await connect()
    await db.execute("INSERT OR REPLACE INTO character_locations (character_id, location_code) VALUES (?, ?)", (character_id, location_code))
    await db.commit()
    await db.close()


async def transfer_balance(from_user_id, to_user_id, amount):
    """Атомарный перевод CR между VK-пользователями."""
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return False, "invalid_amount"
    if amount <= 0:
        return False, "invalid_amount"
    if int(from_user_id) == int(to_user_id):
        return False, "same_user"

    db = await connect()
    try:
        await db.execute("BEGIN IMMEDIATE")

        cursor = await db.execute(
            "SELECT balance FROM users WHERE user_id = ?",
            (from_user_id,)
        )
        sender = await cursor.fetchone()
        if not sender:
            await db.rollback()
            return False, "sender_not_found"

        cursor = await db.execute(
            "SELECT balance FROM users WHERE user_id = ?",
            (to_user_id,)
        )
        receiver = await cursor.fetchone()
        if not receiver:
            await db.rollback()
            return False, "receiver_not_found"

        # Условное списание защищает от ухода баланса в минус даже при конкурирующих запросах.
        cursor = await db.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
            (amount, from_user_id, amount)
        )
        if cursor.rowcount != 1:
            await db.rollback()
            return False, "not_enough_money"

        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, to_user_id)
        )
        await db.commit()
        return True, "ok"
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


async def get_top_richest(limit=10):
    db = await connect()

    cursor = await db.execute("""
        SELECT
            users.user_id,
            users.balance,
            characters.id,
            characters.name
        FROM users
        LEFT JOIN characters ON characters.user_id = users.user_id
        WHERE characters.status = 'approved'
        ORDER BY users.balance DESC
        LIMIT ?
    """, (limit,))

    rows = await cursor.fetchall()
    await db.close()
    return rows


async def get_character_user_id(character_id):
    db = await connect()

    cursor = await db.execute(
        "SELECT user_id FROM characters WHERE id = ?",
        (character_id,)
    )
    row = await cursor.fetchone()

    await db.close()
    return row[0] if row else None


async def set_balance(user_id, amount):
    db = await connect()

    await db.execute(
        "UPDATE users SET balance = ? WHERE user_id = ?",
        (amount, user_id)
    )

    await db.commit()
    await db.close()


async def get_characters_in_location(location_code):
    await ensure_location_tables()
    db = await connect()

    cursor = await db.execute("""
        SELECT
            characters.id,
            characters.name,
            characters.faction,
            characters.department,
            characters.job_title
        FROM character_locations
        JOIN characters ON characters.id = character_locations.character_id
        WHERE character_locations.location_code = ?
        AND characters.status = 'approved'
        ORDER BY characters.name
    """, (location_code,))

    rows = await cursor.fetchall()
    await db.close()
    return rows


async def ensure_inventory_tables():
    db = await connect()

    await db.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        character_id INTEGER,
        category TEXT,
        item_name TEXT,
        quantity INTEGER DEFAULT 0,
        UNIQUE(character_id, category, item_name)
    )
    """)

    await db.commit()
    await db.close()


async def get_inventory(character_id):
    await ensure_inventory_tables()
    db = await connect()

    cursor = await db.execute("""
        SELECT category, item_name, quantity
        FROM inventory
        WHERE character_id = ?
        AND quantity > 0
        ORDER BY category, item_name
    """, (character_id,))

    rows = await cursor.fetchall()
    await db.close()
    return rows


async def add_inventory_item(character_id, category, item_name, quantity):
    await ensure_inventory_tables()
    db = await connect()

    await db.execute("""
        INSERT INTO inventory (character_id, category, item_name, quantity)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(character_id, category, item_name)
        DO UPDATE SET quantity = quantity + excluded.quantity
    """, (character_id, category, item_name, quantity))

    await db.commit()
    await db.close()


async def remove_inventory_item(character_id, item_name, quantity):
    if not isinstance(quantity, int) or quantity <= 0:
        return False, 'invalid_quantity'
    async with _transaction() as db:
        return await _take_item(db, character_id, item_name, quantity)



async def find_inventory_item(character_id, item_name):
    await ensure_inventory_tables()
    db = await connect()

    cursor = await db.execute("""
        SELECT id, category, item_name, quantity
        FROM inventory
        WHERE character_id = ?
        AND lower(item_name) = lower(?)
        AND quantity > 0
        ORDER BY id DESC
        LIMIT 1
    """, (character_id, item_name))

    row = await cursor.fetchone()
    await db.close()
    return row


async def transfer_inventory_item(from_character_id, to_character_id, item_name, quantity):
    if not isinstance(quantity, int) or quantity <= 0:
        return False, 'invalid_quantity'
    if from_character_id == to_character_id:
        return False, 'same_character'
    async with _transaction() as db:
        cursor = await db.execute("SELECT id FROM characters WHERE id IN (?, ?) AND status = 'approved'", (from_character_id, to_character_id))
        if len(await cursor.fetchall()) != 2:
            return False, 'character_invalid'
        cursor = await db.execute("SELECT category, item_name FROM inventory WHERE character_id = ? AND lower(item_name) = lower(?) AND quantity > 0 ORDER BY id DESC LIMIT 1", (from_character_id, item_name))
        item = await cursor.fetchone()
        if not item:
            return False, 'not_found'
        ok, reason = await _take_item(db, from_character_id, item[1], quantity)
        if not ok:
            return False, reason
        await _put_item(db, to_character_id, item[0], item[1], quantity)
        return True, 'ok'




async def update_character_arts(character_id, arts):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE characters SET arts = ? WHERE id = ?",
            (arts, character_id),
        )
        await db.commit()


# ============================================================
# CORE / UX UPDATE: administration, punishments, promos, suggestions
# ============================================================

async def ensure_core_update_tables():
    await ensure_inventory_tables()
    db = await connect()

    await db.execute("""
    CREATE TABLE IF NOT EXISTS bot_admins (
        vk_user_id INTEGER PRIMARY KEY,
        role TEXT NOT NULL,
        active INTEGER DEFAULT 1,
        added_by INTEGER,
        created_at INTEGER DEFAULT 0
    )
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS admin_audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_vk_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        target_vk_id INTEGER,
        target_character_id INTEGER,
        details TEXT DEFAULT '',
        created_at INTEGER DEFAULT 0
    )
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS punishments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vk_user_id INTEGER NOT NULL,
        character_id INTEGER,
        type TEXT NOT NULL,
        reason TEXT NOT NULL,
        issued_by INTEGER NOT NULL,
        created_at INTEGER DEFAULT 0,
        expires_at INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1,
        revoked_by INTEGER,
        revoked_at INTEGER DEFAULT 0
    )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS idx_punishments_user ON punishments(vk_user_id, type, active)")

    await db.execute("""
    CREATE TABLE IF NOT EXISTS promo_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE COLLATE NOCASE,
        max_uses INTEGER DEFAULT 0,
        used_count INTEGER DEFAULT 0,
        expires_at INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1,
        created_by INTEGER NOT NULL,
        created_at INTEGER DEFAULT 0
    )
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS promo_rewards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        promo_code_id INTEGER NOT NULL,
        reward_type TEXT NOT NULL,
        reward_key TEXT DEFAULT '',
        item_name TEXT DEFAULT '',
        item_category TEXT DEFAULT '',
        amount INTEGER NOT NULL DEFAULT 1
    )
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS promo_redemptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        promo_code_id INTEGER NOT NULL,
        vk_user_id INTEGER NOT NULL,
        character_id INTEGER,
        redeemed_at INTEGER DEFAULT 0,
        UNIQUE(promo_code_id, vk_user_id)
    )
    """)

    await db.execute("""
    CREATE TABLE IF NOT EXISTS suggestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vk_user_id INTEGER NOT NULL,
        character_id INTEGER,
        text TEXT NOT NULL,
        attachment TEXT,
        status TEXT DEFAULT 'new',
        admin_response TEXT DEFAULT '',
        created_at INTEGER DEFAULT 0,
        reviewed_by INTEGER,
        reviewed_at INTEGER DEFAULT 0
    )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_status ON suggestions(status, created_at)")

    await db.commit()
    await db.close()


async def ensure_owner_admin(owner_vk_id, now=0):
    if not owner_vk_id:
        return
    await ensure_core_update_tables()
    db = await connect()
    await db.execute("""
        INSERT INTO bot_admins (vk_user_id, role, active, added_by, created_at)
        VALUES (?, 'owner', 1, ?, ?)
        ON CONFLICT(vk_user_id) DO UPDATE SET role='owner', active=1
    """, (int(owner_vk_id), int(owner_vk_id), int(now or 0)))
    await db.commit()
    await db.close()


async def get_bot_admin(vk_user_id):
    await ensure_core_update_tables()
    db = await connect()
    cursor = await db.execute(
        "SELECT vk_user_id, role, active, added_by, created_at FROM bot_admins WHERE vk_user_id = ?",
        (vk_user_id,)
    )
    row = await cursor.fetchone()
    await db.close()
    return row


async def list_bot_admins():
    await ensure_core_update_tables()
    db = await connect()
    cursor = await db.execute("""
        SELECT vk_user_id, role, active, added_by, created_at
        FROM bot_admins
        ORDER BY CASE role WHEN 'owner' THEN 4 WHEN 'senior' THEN 3 WHEN 'admin' THEN 2 ELSE 1 END DESC,
                 vk_user_id
    """)
    rows = await cursor.fetchall()
    await db.close()
    return rows


async def upsert_bot_admin(vk_user_id, role, added_by, created_at):
    if role not in {'owner', 'senior', 'admin', 'moderator'}:
        raise ValueError('invalid admin role')
    await ensure_core_update_tables()
    db = await connect()
    await db.execute("""
        INSERT INTO bot_admins (vk_user_id, role, active, added_by, created_at)
        VALUES (?, ?, 1, ?, ?)
        ON CONFLICT(vk_user_id) DO UPDATE SET role=excluded.role, active=1, added_by=excluded.added_by
    """, (vk_user_id, role, added_by, created_at))
    await db.commit()
    await db.close()


async def deactivate_bot_admin(vk_user_id):
    await ensure_core_update_tables()
    db = await connect()
    await db.execute("UPDATE bot_admins SET active = 0 WHERE vk_user_id = ? AND role != 'owner'", (vk_user_id,))
    await db.commit()
    await db.close()


async def log_admin_action(admin_vk_id, action, target_vk_id=None, target_character_id=None, details='', created_at=0):
    await ensure_core_update_tables()
    db = await connect()
    await db.execute("""
        INSERT INTO admin_audit_log (
            admin_vk_id, action, target_vk_id, target_character_id, details, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (admin_vk_id, action, target_vk_id, target_character_id, details or '', created_at))
    await db.commit()
    await db.close()


async def issue_mute(vk_user_id, character_id, reason, issued_by, created_at, expires_at):
    await ensure_core_update_tables()
    db = await connect()
    try:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute("""
            UPDATE punishments SET active = 0, revoked_by = ?, revoked_at = ?
            WHERE vk_user_id = ? AND type = 'mute' AND active = 1
        """, (issued_by, created_at, vk_user_id))
        cursor = await db.execute("""
            INSERT INTO punishments (
                vk_user_id, character_id, type, reason, issued_by,
                created_at, expires_at, active
            ) VALUES (?, ?, 'mute', ?, ?, ?, ?, 1)
        """, (vk_user_id, character_id, reason, issued_by, created_at, expires_at))
        punishment_id = cursor.lastrowid
        await db.commit()
        return punishment_id
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


async def get_active_mute(vk_user_id, now):
    # Таблицы гарантированно создаются при старте бота; эта функция вызывается
    # middleware на каждом входящем сообщении, поэтому здесь не запускаем миграции повторно.
    db = await connect()
    await db.execute("""
        UPDATE punishments SET active = 0
        WHERE vk_user_id = ? AND type = 'mute' AND active = 1
          AND expires_at > 0 AND expires_at <= ?
    """, (vk_user_id, now))
    cursor = await db.execute("""
        SELECT id, vk_user_id, character_id, reason, issued_by, created_at, expires_at
        FROM punishments
        WHERE vk_user_id = ? AND type = 'mute' AND active = 1
        ORDER BY id DESC LIMIT 1
    """, (vk_user_id,))
    row = await cursor.fetchone()
    await db.commit()
    await db.close()
    return row


async def revoke_mute(vk_user_id, revoked_by, revoked_at):
    await ensure_core_update_tables()
    db = await connect()
    cursor = await db.execute("""
        UPDATE punishments
        SET active = 0, revoked_by = ?, revoked_at = ?
        WHERE vk_user_id = ? AND type = 'mute' AND active = 1
    """, (revoked_by, revoked_at, vk_user_id))
    changed = cursor.rowcount
    await db.commit()
    await db.close()
    return changed > 0


async def delete_character_by_admin(character_id, reset_account=True):
    async with _transaction() as db:
        cursor = await db.execute("SELECT user_id, name FROM characters WHERE id = ?", (character_id,))
        row = await cursor.fetchone()
        if not row:
            return False, None, None
        await _delete_character_state(db, character_id)
        await db.execute("DELETE FROM character_drafts WHERE user_id = ?", (row[0],))
        if reset_account:
            await db.execute("UPDATE users SET balance = 1500, xp = 0, level = 1 WHERE user_id = ?", (row[0],))
        return True, row[0], row[1]



async def create_promo_code(code, max_uses, expires_at, created_by, created_at):
    await ensure_core_update_tables()
    db = await connect()
    try:
        cursor = await db.execute("""
            INSERT INTO promo_codes (code, max_uses, used_count, expires_at, active, created_by, created_at)
            VALUES (?, ?, 0, ?, 1, ?, ?)
        """, (code.strip().upper(), max(0, int(max_uses or 0)), int(expires_at or 0), created_by, created_at))
        promo_id = cursor.lastrowid
        await db.commit()
        return promo_id
    finally:
        await db.close()


async def add_promo_reward(promo_code_id, reward_type, amount, reward_key='', item_name='', item_category=''):
    if reward_type not in {'currency', 'item'}:
        raise ValueError('invalid reward type')
    if int(amount) <= 0:
        raise ValueError('amount must be positive')
    await ensure_core_update_tables()
    db = await connect()
    await db.execute("""
        INSERT INTO promo_rewards (
            promo_code_id, reward_type, reward_key, item_name, item_category, amount
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (promo_code_id, reward_type, reward_key or '', item_name or '', item_category or '', int(amount)))
    await db.commit()
    await db.close()


async def get_promo_by_code(code):
    await ensure_core_update_tables()
    db = await connect()
    cursor = await db.execute("""
        SELECT id, code, max_uses, used_count, expires_at, active, created_by, created_at
        FROM promo_codes WHERE code = ? COLLATE NOCASE
    """, (code.strip(),))
    row = await cursor.fetchone()
    await db.close()
    return row


async def get_promo_rewards(promo_id):
    await ensure_core_update_tables()
    db = await connect()
    cursor = await db.execute("""
        SELECT id, reward_type, reward_key, item_name, item_category, amount
        FROM promo_rewards WHERE promo_code_id = ? ORDER BY id
    """, (promo_id,))
    rows = await cursor.fetchall()
    await db.close()
    return rows


async def list_promo_codes(limit=25):
    await ensure_core_update_tables()
    db = await connect()
    cursor = await db.execute("""
        SELECT id, code, max_uses, used_count, expires_at, active, created_by, created_at
        FROM promo_codes ORDER BY id DESC LIMIT ?
    """, (limit,))
    rows = await cursor.fetchall()
    await db.close()
    return rows


async def set_promo_active(code, active):
    await ensure_core_update_tables()
    db = await connect()
    cursor = await db.execute(
        "UPDATE promo_codes SET active = ? WHERE code = ? COLLATE NOCASE",
        (1 if active else 0, code.strip())
    )
    changed = cursor.rowcount
    await db.commit()
    await db.close()
    return changed > 0


async def redeem_promo_code(code, vk_user_id, character_id, now):
    """Атомарно выдаёт ВСЕ награды. Один VK ID может активировать код один раз."""
    await ensure_core_update_tables()
    db = await connect()
    try:
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute("""
            SELECT id, code, max_uses, used_count, expires_at, active
            FROM promo_codes WHERE code = ? COLLATE NOCASE
        """, (code.strip(),))
        promo = await cursor.fetchone()
        if not promo:
            await db.rollback(); return False, 'not_found', []
        promo_id, normalized, max_uses, used_count, expires_at, active = promo
        if not active:
            await db.rollback(); return False, 'inactive', []
        if expires_at and expires_at <= now:
            await db.rollback(); return False, 'expired', []
        if max_uses and used_count >= max_uses:
            await db.rollback(); return False, 'limit', []
        cursor = await db.execute(
            "SELECT 1 FROM promo_redemptions WHERE promo_code_id = ? AND vk_user_id = ?",
            (promo_id, vk_user_id)
        )
        if await cursor.fetchone():
            await db.rollback(); return False, 'already_used', []

        # Награды предметами всегда привязаны к действующему одобренному персонажу
        # именно этого VK-пользователя. Это не даёт подменить character_id вручную.
        cursor = await db.execute("""
            SELECT 1 FROM characters
            WHERE id = ? AND user_id = ? AND status = 'approved'
        """, (character_id, vk_user_id))
        if not await cursor.fetchone():
            await db.rollback(); return False, 'character_invalid', []

        cursor = await db.execute("""
            SELECT reward_type, reward_key, item_name, item_category, amount
            FROM promo_rewards WHERE promo_code_id = ? ORDER BY id
        """, (promo_id,))
        rewards = await cursor.fetchall()
        if not rewards:
            await db.rollback(); return False, 'no_rewards', []

        cursor = await db.execute("SELECT 1 FROM users WHERE user_id = ?", (vk_user_id,))
        if not await cursor.fetchone():
            await db.execute(
                "INSERT INTO users (user_id, balance, xp, level) VALUES (?, 1500, 0, 1)",
                (vk_user_id,)
            )

        for reward_type, reward_key, item_name, item_category, amount in rewards:
            if reward_type == 'currency':
                await db.execute(
                    "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                    (amount, vk_user_id)
                )
            elif reward_type == 'item':
                await db.execute("""
                    INSERT INTO inventory (character_id, category, item_name, quantity)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(character_id, category, item_name)
                    DO UPDATE SET quantity = quantity + excluded.quantity
                """, (character_id, item_category, item_name, amount))

        await db.execute("""
            INSERT INTO promo_redemptions (promo_code_id, vk_user_id, character_id, redeemed_at)
            VALUES (?, ?, ?, ?)
        """, (promo_id, vk_user_id, character_id, now))
        await db.execute(
            "UPDATE promo_codes SET used_count = used_count + 1 WHERE id = ?",
            (promo_id,)
        )
        await db.commit()
        return True, normalized, rewards
    except aiosqlite.IntegrityError:
        await db.rollback()
        return False, 'already_used', []
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


async def create_suggestion(vk_user_id, character_id, text, attachment, created_at):
    await ensure_core_update_tables()
    db = await connect()
    cursor = await db.execute("""
        INSERT INTO suggestions (vk_user_id, character_id, text, attachment, status, created_at)
        VALUES (?, ?, ?, ?, 'new', ?)
    """, (vk_user_id, character_id, text, attachment, created_at))
    suggestion_id = cursor.lastrowid
    await db.commit()
    await db.close()
    return suggestion_id


async def get_last_suggestion_time(vk_user_id):
    await ensure_core_update_tables()
    db = await connect()
    cursor = await db.execute(
        "SELECT created_at FROM suggestions WHERE vk_user_id = ? ORDER BY id DESC LIMIT 1",
        (vk_user_id,)
    )
    row = await cursor.fetchone()
    await db.close()
    return row[0] if row else 0


async def get_suggestion(suggestion_id):
    await ensure_core_update_tables()
    db = await connect()
    cursor = await db.execute("SELECT * FROM suggestions WHERE id = ?", (suggestion_id,))
    row = await cursor.fetchone()
    await db.close()
    return row


async def list_suggestions(status='new', limit=20):
    await ensure_core_update_tables()
    db = await connect()
    if status:
        cursor = await db.execute(
            "SELECT * FROM suggestions WHERE status = ? ORDER BY id DESC LIMIT ?",
            (status, limit)
        )
    else:
        cursor = await db.execute("SELECT * FROM suggestions ORDER BY id DESC LIMIT ?", (limit,))
    rows = await cursor.fetchall()
    await db.close()
    return rows


async def update_suggestion_status(suggestion_id, status, reviewed_by, reviewed_at, admin_response=None):
    await ensure_core_update_tables()
    db = await connect()
    if admin_response is None:
        await db.execute("""
            UPDATE suggestions SET status = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?
        """, (status, reviewed_by, reviewed_at, suggestion_id))
    else:
        await db.execute("""
            UPDATE suggestions
            SET status = ?, reviewed_by = ?, reviewed_at = ?, admin_response = ?
            WHERE id = ?
        """, (status, reviewed_by, reviewed_at, admin_response, suggestion_id))
    await db.commit()
    await db.close()


async def get_pending_characters(limit=20):
    db = await connect()
    cursor = await db.execute(
        "SELECT * FROM characters WHERE status = 'pending' ORDER BY id ASC LIMIT ?", (limit,)
    )
    rows = await cursor.fetchall()
    await db.close()
    return rows


async def get_pending_quests(limit=20):
    await ensure_quest_tables()
    db = await connect()
    cursor = await db.execute("""
        SELECT * FROM weekly_quests WHERE status = 'review' ORDER BY report_time ASC, id ASC LIMIT ?
    """, (limit,))
    rows = await cursor.fetchall()
    await db.close()
    return rows


async def complete_quest_with_rewards(quest_id):
    """Атомарное принятие отчёта: статус + CR + XP выдаются ровно один раз."""
    db = await connect()
    try:
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute(
            "SELECT character_id, credits, xp, status FROM weekly_quests WHERE id = ?",
            (quest_id,)
        )
        quest = await cursor.fetchone()
        if not quest:
            await db.rollback(); return False, 'not_found', None
        character_id, credits, xp, status = quest
        if status != 'review':
            await db.rollback(); return False, 'wrong_status', None
        cursor = await db.execute("SELECT user_id FROM characters WHERE id = ?", (character_id,))
        row = await cursor.fetchone()
        if not row:
            await db.rollback(); return False, 'character_not_found', None
        user_id = row[0]
        cursor = await db.execute(
            "UPDATE weekly_quests SET status = 'completed' WHERE id = ? AND status = 'review'",
            (quest_id,)
        )
        if cursor.rowcount != 1:
            await db.rollback(); return False, 'already_processed', None
        await db.execute("UPDATE users SET balance = balance + ?, xp = xp + ? WHERE user_id = ?", (credits, xp, user_id))
        await db.commit()
        return True, 'ok', (character_id, user_id, credits, xp)
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()

# Shared transactional operations used by both buttons and text commands.
@asynccontextmanager
async def _transaction():
    db = await connect()
    try:
        await db.execute('BEGIN IMMEDIATE')
        yield db
        await db.commit()
    except BaseException:
        await db.rollback()
        raise
    finally:
        await db.close()


async def _debit(db, user_id, amount):
    cursor = await db.execute('UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?', (amount, user_id, amount))
    return cursor.rowcount == 1


async def _put_item(db, character_id, category, name, quantity):
    await db.execute('''INSERT INTO inventory(character_id, category, item_name, quantity) VALUES (?, ?, ?, ?)
        ON CONFLICT(character_id, category, item_name) DO UPDATE SET quantity = quantity + excluded.quantity''',
        (character_id, category, name, quantity))


async def _take_item(db, character_id, name, quantity):
    cursor = await db.execute('SELECT id, quantity FROM inventory WHERE character_id = ? AND lower(item_name) = lower(?) AND quantity > 0 ORDER BY id DESC LIMIT 1', (character_id, name))
    row = await cursor.fetchone()
    if not row:
        return False, 'not_found'
    if row[1] < quantity:
        return False, 'not_enough'
    await db.execute('UPDATE inventory SET quantity = quantity - ? WHERE id = ?', (quantity, row[0]))
    await db.execute('DELETE FROM inventory WHERE id = ? AND quantity = 0', (row[0],))
    return True, 'ok'


async def _delete_character_state(db, cid):
    for table in ('housing_interior_slots', 'housing_interiors', 'housing', 'inventory', 'weekly_quests', 'character_locations', 'character_health'):
        await db.execute(f'DELETE FROM {table} WHERE character_id = ?', (cid,))
    await db.execute('DELETE FROM characters WHERE id = ?', (cid,))


async def purchase_item(user_id, character_id, item, quantity):
    if not isinstance(quantity, int) or quantity <= 0:
        return False, 'invalid_quantity'
    price = item.get('price')
    if not isinstance(price, int) or price < 0 or price * quantity > 2**63 - 1:
        return False, 'invalid_price'
    if not item.get('purchasable', True):
        return False, 'unavailable'
    async with _transaction() as db:
        cursor = await db.execute("SELECT faction FROM characters WHERE id = ? AND user_id = ? AND status = 'approved'", (character_id, user_id))
        character = await cursor.fetchone()
        if not character:
            return False, 'character_invalid'
        if item.get('required_faction') and character[0] != item['required_faction']:
            return False, 'faction'
        if not await _debit(db, user_id, price * quantity):
            return False, 'not_enough_money'
        await _put_item(db, character_id, item['category'], item['name'], quantity)
        return True, 'ok'


async def claim_salary(user_id, now, interval, salary_by_level):
    async with _transaction() as db:
        cursor = await db.execute('SELECT id, status, department, job_title, job_level, last_salary_time FROM characters WHERE user_id = ? ORDER BY id DESC LIMIT 1', (user_id,))
        c = await cursor.fetchone()
        if not c or c[1] != 'approved' or not c[2] or not c[3] or not c[4]:
            return False, 'career_invalid', 0
        if now - (c[5] or 0) < interval:
            return False, 'cooldown', interval - (now - (c[5] or 0))
        amount = salary_by_level.get(c[4], 0)
        if amount <= 0:
            return False, 'career_invalid', 0
        cursor = await db.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
        if cursor.rowcount != 1:
            return False, 'user_missing', 0
        await db.execute('UPDATE characters SET last_salary_time = ? WHERE id = ?', (now, c[0]))
        return True, 'ok', amount


async def pay_rent(user_id, character_id, now, interval):
    async with _transaction() as db:
        cursor = await db.execute('SELECT h.weekly_rent, h.last_payment_time FROM housing h JOIN characters c ON c.id = h.character_id WHERE h.character_id = ? AND c.user_id = ?', (character_id, user_id))
        row = await cursor.fetchone()
        if not row:
            return False, 'housing_missing', 0
        rent, last = row[0], row[1] or 0
        if rent <= 0:
            return False, 'free', 0
        if last and now - last < interval:
            return False, 'cooldown', interval - (now - last)
        if not await _debit(db, user_id, rent):
            return False, 'not_enough_money', rent
        await db.execute('UPDATE housing SET last_payment_time = ? WHERE character_id = ?', (now, character_id))
        return True, 'ok', rent


async def ensure_stability_tables():
    async with _transaction() as db:
        await db.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY)')
        await db.execute('CREATE TABLE IF NOT EXISTS character_drafts(user_id INTEGER PRIMARY KEY, payload TEXT NOT NULL, updated_at INTEGER NOT NULL)')


async def save_character_draft(user_id, draft):
    async with _transaction() as db:
        cursor = await db.execute('SELECT 1 FROM characters WHERE user_id = ?', (user_id,))
        if await cursor.fetchone():
            return False
        await db.execute('INSERT INTO character_drafts(user_id, payload, updated_at) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at',
                         (user_id, json.dumps(draft, ensure_ascii=False), int(time.time())))
        return True


async def load_character_draft(user_id):
    db = await connect()
    try:
        cursor = await db.execute('SELECT payload FROM character_drafts WHERE user_id = ?', (user_id,))
        row = await cursor.fetchone()
        return json.loads(row[0]) if row else None
    finally:
        await db.close()


async def delete_character_draft(user_id):
    async with _transaction() as db:
        await db.execute('DELETE FROM character_drafts WHERE user_id = ?', (user_id,))

async def adjust_balance_by_admin(admin_id, character_id, mode, amount, now):
    if not isinstance(amount, int) or amount < 0 or amount > 2**63 - 1:
        return False, 'invalid_amount'
    if mode not in ('finance_add', 'finance_subtract', 'finance_set') or (mode != 'finance_set' and amount == 0):
        return False, 'invalid_amount'
    async with _transaction() as db:
        cursor = await db.execute("SELECT role FROM bot_admins WHERE vk_user_id = ? AND active = 1", (admin_id,))
        role = await cursor.fetchone()
        if not role or role[0] not in ('owner', 'senior', 'admin'):
            return False, 'forbidden'
        cursor = await db.execute('SELECT user_id FROM characters WHERE id = ?', (character_id,))
        character = await cursor.fetchone()
        if not character:
            return False, 'not_found'
        uid = character[0]
        await db.execute('INSERT OR IGNORE INTO users(user_id, balance) VALUES (?, 1500)', (uid,))
        if mode == 'finance_subtract':
            if not await _debit(db, uid, amount):
                return False, 'not_enough_money'
        elif mode == 'finance_add':
            cursor = await db.execute('UPDATE users SET balance = balance + ? WHERE user_id = ? AND balance <= ?', (amount, uid, 2**63 - 1 - amount))
            if cursor.rowcount != 1:
                return False, 'overflow'
        else:
            await db.execute('UPDATE users SET balance = ? WHERE user_id = ?', (amount, uid))
        await db.execute('INSERT INTO admin_audit_log(admin_vk_id, action, target_vk_id, target_character_id, details, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                         (admin_id, mode, uid, character_id, str(amount), now))
        return True, 'ok'
