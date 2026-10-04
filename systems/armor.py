"""Individual armor instances; atomic equipment, repairs and transfers."""
import time
import database as db
from systems import duels


async def ensure_armor_tables():
    async with db._transaction() as conn:
        await conn.execute('''CREATE TABLE IF NOT EXISTS armor_instances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL,
            item_code TEXT NOT NULL,
            name TEXT NOT NULL,
            durability INTEGER NOT NULL CHECK(durability>=0 AND durability<=max_durability),
            max_durability INTEGER NOT NULL CHECK(max_durability>0),
            price INTEGER NOT NULL CHECK(price>0),
            equipped INTEGER NOT NULL DEFAULT 0 CHECK(equipped IN (0,1))
        )''')
        await conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS one_equipped_armor ON armor_instances(character_id) WHERE equipped=1')


def repair_cost(current, maximum, price):
    return (price*(maximum-current)+4*maximum-1)//(4*maximum)


async def list_armor(cid):
    conn = await db.connect()
    try:
        cursor = await conn.execute('SELECT * FROM armor_instances WHERE character_id=? ORDER BY id', (cid,))
        return [dict(zip([c[0] for c in cursor.description],row)) for row in await cursor.fetchall()]
    finally:
        await conn.close()


async def armor_action(uid, cid, action, armor_id=None, target_id=None, expected=None):
    await duels.refresh_character_scene(cid, int(time.time()))
    if action == 'transfer' and target_id:
        await duels.refresh_character_scene(target_id, int(time.time()))
    async with db._transaction() as conn:
        cursor = await conn.execute("SELECT 1 FROM characters WHERE id=? AND user_id=? AND status='approved'",(cid,uid))
        if not await cursor.fetchone():
            return {'status':'error','text':'Нужна ваша одобренная квента.'}
        await conn.execute('INSERT OR IGNORE INTO character_health(character_id) VALUES (?)',(cid,))
        cursor = await conn.execute('SELECT scene_key FROM character_health WHERE character_id=?',(cid,))
        if (await cursor.fetchone())[0]:
            return {'status':'error','text':'Менять, передавать и ремонтировать броню можно только вне боя.'}
        if action=='unequip':
            await conn.execute('UPDATE armor_instances SET equipped=0 WHERE character_id=?',(cid,))
            await conn.execute('UPDATE character_health SET armor=0,max_armor=0 WHERE character_id=?',(cid,))
            return {'status':'ok','text':'Бронежилет снят. Прочность сохранена.'}
        cursor = await conn.execute('SELECT * FROM armor_instances WHERE id=? AND character_id=?',(armor_id,cid))
        row = await cursor.fetchone()
        if not row:
            return {'status':'error','text':'Этот бронежилет не принадлежит вашему персонажу.'}
        item = dict(zip([c[0] for c in cursor.description],row))
        if action=='equip':
            await conn.execute('UPDATE armor_instances SET equipped=0 WHERE character_id=?',(cid,))
            await conn.execute('UPDATE armor_instances SET equipped=1 WHERE id=?',(armor_id,))
            await conn.execute('UPDATE character_health SET armor=?,max_armor=? WHERE character_id=?',(item['durability'],item['max_durability'],cid))
            return {'status':'ok','text':f"Надет: {item['name']} · {item['durability']}/{item['max_durability']}."}
        if action=='transfer':
            if item['equipped'] or target_id==cid:
                return {'status':'error','text':'Сначала снимите бронежилет и выберите другого получателя.'}
            cursor = await conn.execute("SELECT c.id, COALESCE(h.scene_key,'') FROM characters c LEFT JOIN character_health h ON h.character_id=c.id WHERE c.id=? AND c.status='approved'",(target_id,))
            target = await cursor.fetchone()
            if not target or target[1]:
                return {'status':'error','text':'Получатель должен быть одобрен и находиться вне боя.'}
            await conn.execute('UPDATE armor_instances SET character_id=? WHERE id=?',(target_id,armor_id))
            return {'status':'ok','text':'Бронежилет передан с текущей прочностью.'}
        if action=='repair':
            cost = repair_cost(item['durability'],item['max_durability'],item['price'])
            if not cost:
                return {'status':'error','text':'Бронежилет целый. Ремонт не нужен.'}
            quote = (armor_id,cid,item['durability'],item['max_durability'],cost)
            if expected != quote:
                return {'status':'confirm','quote':quote,'text':f"{item['name']}: ремонт {item['durability']} → {item['max_durability']} за {cost} CR?"}
            if not await db._debit(conn,uid,cost):
                return {'status':'error','text':'Недостаточно CR. Бронежилет не изменён.'}
            await conn.execute('UPDATE armor_instances SET durability=max_durability WHERE id=?',(armor_id,))
            if item['equipped']:
                await conn.execute('UPDATE character_health SET armor=?,max_armor=? WHERE character_id=?',(item['max_durability'],item['max_durability'],cid))
            return {'status':'ok','text':f"Бронежилет отремонтирован. Списано {cost} CR."}
        return {'status':'error','text':'Неизвестное действие.'}
