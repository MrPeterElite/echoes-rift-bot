"""Persistent owned weapons and one active weapon per character."""
import time
import database as db
from systems import duels
from systems.weapon_stats import weapon_stats


async def ensure_weapon_tables():
    async with db._transaction() as conn:
        await conn.execute('''CREATE TABLE IF NOT EXISTS weapon_instances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL,
            item_code TEXT NOT NULL,
            name TEXT NOT NULL,
            weapon_type TEXT NOT NULL,
            equipped INTEGER NOT NULL DEFAULT 0 CHECK(equipped IN (0,1))
        )''')
        await conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS one_equipped_weapon ON weapon_instances(character_id) WHERE equipped=1')


async def list_weapons(cid):
    conn=await db.connect()
    try:
        cursor=await conn.execute('SELECT * FROM weapon_instances WHERE character_id=? ORDER BY id',(cid,))
        rows = [dict(zip([c[0] for c in cursor.description],row)) for row in await cursor.fetchall()]
        return [dict(weapon_stats(row['item_code']), **row) for row in rows]
    finally:
        await conn.close()


async def weapon_action(uid,cid,action,weapon_id=None,target_id=None):
    await duels.refresh_character_scene(cid, int(time.time()))
    if action == 'transfer' and target_id:
        await duels.refresh_character_scene(target_id, int(time.time()))
    async with db._transaction() as conn:
        cursor=await conn.execute("SELECT 1 FROM characters WHERE id=? AND user_id=? AND status='approved'",(cid,uid))
        if not await cursor.fetchone():return {'status':'error','text':'Нужна ваша одобренная квента.'}
        cursor=await conn.execute('SELECT scene_key FROM character_health WHERE character_id=?',(cid,))
        state=await cursor.fetchone()
        if state and state[0]:return {'status':'error','text':'Выбор, снятие и передача оружия доступны только вне боя.'}
        if action=='unequip':
            await conn.execute('UPDATE weapon_instances SET equipped=0 WHERE character_id=?',(cid,))
            return {'status':'ok','text':'Оружие убрано. Оно осталось у персонажа.'}
        cursor=await conn.execute('SELECT name,equipped FROM weapon_instances WHERE id=? AND character_id=?',(weapon_id,cid))
        item=await cursor.fetchone()
        if not item:return {'status':'error','text':'Это оружие не принадлежит вашему персонажу.'}
        if action=='equip':
            await conn.execute('UPDATE weapon_instances SET equipped=0 WHERE character_id=?',(cid,))
            await conn.execute('UPDATE weapon_instances SET equipped=1 WHERE id=?',(weapon_id,))
            return {'status':'ok','text':f'Выбрано оружие: {item[0]}.'}
        if action=='transfer':
            if item[1] or target_id==cid:return {'status':'error','text':'Сначала уберите оружие и выберите другого получателя.'}
            cursor=await conn.execute("SELECT c.id,COALESCE(h.scene_key,'') FROM characters c LEFT JOIN character_health h ON h.character_id=c.id WHERE c.id=? AND c.status='approved'",(target_id,))
            target=await cursor.fetchone()
            if not target or target[1]:return {'status':'error','text':'Получатель должен быть одобрен и находиться вне боя.'}
            await conn.execute('UPDATE weapon_instances SET character_id=? WHERE id=?',(target_id,weapon_id))
            return {'status':'ok','text':'Оружие передано.'}
        return {'status':'error','text':'Неизвестное действие.'}
