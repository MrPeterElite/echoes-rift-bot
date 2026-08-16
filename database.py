import aiosqlite


async def connect():
    return await aiosqlite.connect("database.db")


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
    db = await connect()

    cursor = await db.execute(
        "SELECT * FROM users WHERE user_id = ?",
        (user_id,)
    )
    user = await cursor.fetchone()

    if not user:
        await db.execute(
            "INSERT INTO users (user_id, balance) VALUES (?, ?)",
            (user_id, 1500)
        )

    await db.commit()
    await db.close()


async def get_user(user_id):
    db = await connect()

    cursor = await db.execute(
        "SELECT * FROM users WHERE user_id = ?",
        (user_id,)
    )
    user = await cursor.fetchone()

    await db.close()
    return user


async def reset_user(user_id):
    db = await connect()

    await db.execute("DELETE FROM characters WHERE user_id = ?", (user_id,))
    await db.execute(
        "UPDATE users SET balance = 1500, xp = 0, level = 1 WHERE user_id = ?",
        (user_id,)
    )

    await db.commit()
    await db.close()


async def create_character(data):
    db = await connect()

    cursor = await db.execute("""
    INSERT INTO characters (
        user_id, name, age, gender, faction,
        biology, personality, history, arts, status
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["user_id"],
        data["name"],
        data["age"],
        data["gender"],
        data["faction"],
        data["biology"],
        data["personality"],
        data["history"],
        ",".join(data["arts"]),
        "pending"
    ))

    character_id = cursor.lastrowid

    await db.commit()
    await db.close()

    return character_id


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

    for column_name, column_type in columns:
        try:
            await db.execute(
                f"ALTER TABLE characters ADD COLUMN {column_name} {column_type}"
            )
        except Exception:
            pass

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
    for column_name, column_type in columns:
        try:
            await db.execute(
                f"ALTER TABLE characters ADD COLUMN {column_name} {column_type}"
            )
        except Exception:
            pass
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
        last_payment_time INTEGER DEFAULT 0
    )
    """)

    await db.commit()
    await db.close()


async def get_housing(character_id):
    db = await connect()

    cursor = await db.execute(
        "SELECT * FROM housing WHERE character_id = ?",
        (character_id,)
    )
    housing = await cursor.fetchone()

    await db.close()
    return housing


async def assign_housing(character_id, housing_class, sector):
    weekly_rent = HOUSING_PRICES.get(housing_class, 0)

    db = await connect()

    await db.execute("""
        INSERT OR REPLACE INTO housing (
            character_id, housing_class, sector, weekly_rent, last_payment_time
        )
        VALUES (
            ?,
            ?,
            ?,
            ?,
            COALESCE(
                (SELECT last_payment_time FROM housing WHERE character_id = ?),
                0
            )
        )
    """, (character_id, housing_class, sector, weekly_rent, character_id))

    await db.commit()
    await db.close()


async def remove_housing(character_id):
    db = await connect()

    await db.execute(
        "DELETE FROM housing WHERE character_id = ?",
        (character_id,)
    )

    await db.commit()
    await db.close()


async def update_housing_sector(character_id, sector):
    db = await connect()

    await db.execute(
        "UPDATE housing SET sector = ? WHERE character_id = ?",
        (sector, character_id)
    )

    await db.commit()
    await db.close()


async def update_housing_class(character_id, housing_class):
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
    db = await connect()

    await db.execute(
        "UPDATE housing SET last_payment_time = ? WHERE character_id = ?",
        (timestamp, character_id)
    )

    await db.commit()
    await db.close()


async def subtract_balance(user_id, amount):
    db = await connect()

    await db.execute(
        "UPDATE users SET balance = balance - ? WHERE user_id = ?",
        (amount, user_id)
    )

    await db.commit()
    await db.close()



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
        report_time INTEGER DEFAULT 0
    )
    """)
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

async def create_weekly_quest(character_id, title, description, credits, xp, assigned_at):
    db = await connect()
    cursor = await db.execute("""
        INSERT INTO weekly_quests (
            character_id, title, description, credits, xp, status, assigned_at
        )
        VALUES (?, ?, ?, ?, ?, 'active', ?)
    """, (character_id, title, description, credits, xp, assigned_at))
    quest_id = cursor.lastrowid
    await db.commit()
    await db.close()
    return quest_id

async def submit_quest_report(quest_id, report_text, report_attachment, report_time):
    db = await connect()
    await db.execute("""
        UPDATE weekly_quests
        SET status = 'review',
            report_text = ?,
            report_attachment = ?,
            report_time = ?
        WHERE id = ?
    """, (report_text, report_attachment, report_time, quest_id))
    await db.commit()
    await db.close()

async def get_quest_by_id(quest_id):
    db = await connect()
    cursor = await db.execute("SELECT * FROM weekly_quests WHERE id = ?", (quest_id,))
    row = await cursor.fetchone()
    await db.close()
    return row

async def update_quest_status(quest_id, status):
    db = await connect()
    await db.execute("UPDATE weekly_quests SET status = ? WHERE id = ?", (status, quest_id))
    await db.commit()
    await db.close()

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
            INSERT OR REPLACE INTO locations (code, name, peer_id, invite_link)
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
    db = await connect()

    cursor = await db.execute(
        "SELECT balance FROM users WHERE user_id = ?",
        (from_user_id,)
    )
    sender = await cursor.fetchone()

    if not sender:
        await db.close()
        return False, "sender_not_found"

    if sender[0] < amount:
        await db.close()
        return False, "not_enough_money"

    cursor = await db.execute(
        "SELECT balance FROM users WHERE user_id = ?",
        (to_user_id,)
    )
    receiver = await cursor.fetchone()

    if not receiver:
        await db.close()
        return False, "receiver_not_found"

    await db.execute(
        "UPDATE users SET balance = balance - ? WHERE user_id = ?",
        (amount, from_user_id)
    )

    await db.execute(
        "UPDATE users SET balance = balance + ? WHERE user_id = ?",
        (amount, to_user_id)
    )

    await db.commit()
    await db.close()

    return True, "ok"


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
    await ensure_inventory_tables()
    db = await connect()

    cursor = await db.execute("""
        SELECT id, quantity
        FROM inventory
        WHERE character_id = ?
        AND lower(item_name) = lower(?)
        AND quantity > 0
        ORDER BY id DESC
        LIMIT 1
    """, (character_id, item_name))

    row = await cursor.fetchone()

    if not row:
        await db.close()
        return False, "not_found"

    item_id, current_quantity = row

    if current_quantity < quantity:
        await db.close()
        return False, "not_enough"

    new_quantity = current_quantity - quantity

    if new_quantity <= 0:
        await db.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
    else:
        await db.execute(
            "UPDATE inventory SET quantity = ? WHERE id = ?",
            (new_quantity, item_id)
        )

    await db.commit()
    await db.close()
    return True, "ok"


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
    item = await find_inventory_item(from_character_id, item_name)

    if not item:
        return False, "not_found"

    item_id, category, real_item_name, current_quantity = item

    if current_quantity < quantity:
        return False, "not_enough"

    ok, reason = await remove_inventory_item(from_character_id, real_item_name, quantity)

    if not ok:
        return False, reason

    await add_inventory_item(to_character_id, category, real_item_name, quantity)
    return True, "ok"



async def update_character_arts(character_id, arts):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE characters SET arts = ? WHERE id = ?",
            (arts, character_id),
        )
        await db.commit()
