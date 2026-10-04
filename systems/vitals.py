"""Persistent health and atomic consumables. Scene markers do not resolve combat."""
import uuid
from systems.weapon_stats import weapon_stats

import database as db
from systems.item_effects import FOOD_DURATION, FOOD_CAP, BASIC_HEAL_LIMIT


async def ensure_health_tables():
    async with db._transaction() as conn:
        await conn.execute('''CREATE TABLE IF NOT EXISTS character_health (
            character_id INTEGER PRIMARY KEY,
            hp INTEGER NOT NULL DEFAULT 100 CHECK(hp >= 0 AND hp <= max_hp),
            max_hp INTEGER NOT NULL DEFAULT 100 CHECK(max_hp > 0),
            armor INTEGER NOT NULL DEFAULT 0 CHECK(armor >= 0 AND armor <= max_armor),
            max_armor INTEGER NOT NULL DEFAULT 0 CHECK(max_armor >= 0),
            food_hp INTEGER NOT NULL DEFAULT 0 CHECK(food_hp BETWEEN 0 AND 30),
            food_max INTEGER NOT NULL DEFAULT 0 CHECK(food_max BETWEEN 0 AND 30),
            food_expires INTEGER NOT NULL DEFAULT 0,
            basic_healed INTEGER NOT NULL DEFAULT 0 CHECK(basic_healed BETWEEN 0 AND 20),
            scene_key TEXT NOT NULL DEFAULT '',
            medkit_used INTEGER NOT NULL DEFAULT 0 CHECK(medkit_used IN (0,1))
        )''')
        await conn.execute('INSERT OR IGNORE INTO character_health(character_id) SELECT id FROM characters')


async def _state(conn, cid, now):
    await conn.execute('INSERT OR IGNORE INTO character_health(character_id) SELECT id FROM characters WHERE id=?', (cid,))
    await conn.execute("UPDATE character_health SET food_hp=0, food_max=0, food_expires=0 WHERE character_id=? AND scene_key='' AND food_expires<=?", (cid, now))
    cursor = await conn.execute('SELECT name,durability,max_durability FROM armor_instances WHERE character_id=? AND equipped=1',(cid,))
    equipped = await cursor.fetchone()
    if equipped:
        await conn.execute('UPDATE character_health SET armor=?,max_armor=? WHERE character_id=?',(equipped[1],equipped[2],cid))
    cursor = await conn.execute('SELECT * FROM character_health WHERE character_id=?', (cid,))
    row = await cursor.fetchone()
    if not row:
        return None
    result = dict(zip([c[0] for c in cursor.description], row))
    result['armor_name'] = equipped[0] if equipped else 'не экипирована'
    cursor = await conn.execute('SELECT name,weapon_type,item_code FROM weapon_instances WHERE character_id=? AND equipped=1',(cid,))
    weapon = await cursor.fetchone()
    result['weapon_name'] = weapon[0] if weapon else 'не выбрано'
    result['weapon_type'] = weapon[1] if weapon else ''
    result['weapon_damage'] = weapon_stats(weapon[2]).get('damage',0) if weapon else 0
    return result


async def get_health(cid, now):
    # Public reads also refresh an expired duel marker. duels.py itself uses
    # _state directly while holding its transaction, so this does not recurse.
    from systems import duels
    await duels.refresh_character_scene(cid, now)
    async with db._transaction() as conn:
        return await _state(conn, cid, now)


async def use_health_item(uid, cid, item, now, expected=None):
    """Quote partial/replacement use, then revalidate the exact quote on confirmation."""
    from systems import duels
    await duels.refresh_character_scene(cid, now)
    effect = item.get('effect', {})
    async with db._transaction() as conn:
        cursor = await conn.execute("SELECT 1 FROM characters WHERE id=? AND user_id=? AND status='approved'", (cid, uid))
        if not await cursor.fetchone():
            return {'status':'invalid_character'}
        state = await _state(conn, cid, now)
        if state['scene_key'].startswith('duel:'):
            return {'status':'duel_only'}
        if state['hp'] == 0:
            return {'status':'incapacitated'}
        kind = effect.get('type')
        amount = effect.get('amount', 0)
        if kind not in ('food_hp', 'heal') or not isinstance(amount, int) or amount <= 0:
            return {'status':'invalid_effect'}
        if kind == 'food_hp':
            if state['scene_key']:
                return {'status':'in_combat'}
            if amount > FOOD_CAP:
                return {'status':'invalid_effect'}
            if state['food_hp'] >= amount:
                return {'status':'not_stronger'}
            gain = amount - state['food_hp']
            needs_confirmation = state['food_hp'] > 0
        else:
            group = effect.get('group')
            if group not in ('basic', 'medkit'):
                return {'status':'invalid_effect'}
            if state['hp'] == state['max_hp']:
                return {'status':'full_hp'}
            if group == 'medkit' and state['scene_key'] and state['medkit_used']:
                return {'status':'limit'}
            remaining = BASIC_HEAL_LIMIT - state['basic_healed'] if group == 'basic' else amount
            gain = min(amount, state['max_hp'] - state['hp'], remaining)
            if gain <= 0:
                return {'status':'limit'}
            needs_confirmation = gain < amount
        # Expiry is fixed in the state; wall clock is deliberately not part of the quote.
        quote = (cid, item['code'], kind, amount, gain, tuple(state.items()))
        if (needs_confirmation and expected != quote) or (expected is not None and expected != quote):
            return {'status':'confirm', 'quote':quote, 'gain':gain, 'target':amount if kind=='food_hp' else state['hp']+gain}
        ok, reason = await db._take_item(conn, cid, item['name'], 1)
        if not ok:
            return {'status':'missing_item'}
        if kind == 'food_hp':
            await conn.execute('UPDATE character_health SET food_hp=?, food_max=?, food_expires=? WHERE character_id=?', (amount, amount, now+FOOD_DURATION, cid))
        else:
            new_hp = state['hp'] + gain
            basic = state['basic_healed'] + gain if group=='basic' else state['basic_healed']
            if new_hp == state['max_hp'] and not state['scene_key']:
                basic = 0
            medkit = 1 if group=='medkit' and state['scene_key'] else state['medkit_used']
            await conn.execute('UPDATE character_health SET hp=?, basic_healed=?, medkit_used=? WHERE character_id=?', (new_hp, basic, medkit, cid))
        return {'status':'ok', 'gain':gain, 'before':state, 'after':await _state(conn,cid,now)}


async def admin_health_action(admin_id, action, ids, values, now):
    """Manual GM controls until a full combat engine exists; all changes are audited."""
    async with db._transaction() as conn:
        cursor = await conn.execute("SELECT 1 FROM bot_admins WHERE vk_user_id=? AND active=1 AND role IN ('owner','senior','admin')", (admin_id,))
        if not await cursor.fetchone():
            return False, 'Недостаточно прав.'
        states = []
        for cid in ids:
            state = await _state(conn,cid,now)
            if not state:
                return False, f'Персонаж #{cid} не найден.'
            states.append(state)
        if not states:
            return False, 'Укажите персонажей.'
        if any(s['scene_key'].startswith('duel:') for s in states):
            if action!='end':return False,'Для исправления состояния сначала завершите дуэль через /сценаконец.'
            from systems.duels import one, finish
            duel=await one(conn,'SELECT * FROM duels WHERE id=?',(int(states[0]['scene_key'].split(':')[1]),))
            if duel:await finish(conn,duel,'Дуэль завершена администрацией.')
        if action=='hp':
            hp = values[0]
            if not 0 <= hp <= states[0]['max_hp']:
                return False, 'HP должно быть от 0 до максимума.'
            s = states[0]
            basic = 0 if not s['scene_key'] and hp==s['max_hp'] else s['basic_healed']
            await conn.execute('UPDATE character_health SET hp=?,basic_healed=? WHERE character_id=?',(hp,basic,ids[0]))
        elif action=='armor':
            current, maximum = values
            if not 0 <= current <= maximum <= 10000:
                return False,'Нужно 0 ≤ броня ≤ максимум ≤ 10000.'
            cursor = await conn.execute('SELECT id,max_durability FROM armor_instances WHERE character_id=? AND equipped=1',(ids[0],))
            equipped = await cursor.fetchone()
            if equipped:
                if maximum != equipped[1]:
                    return False,'Максимальная прочность жилета неизменна.'
                await conn.execute('UPDATE armor_instances SET durability=? WHERE id=?',(current,equipped[0]))
            await conn.execute('UPDATE character_health SET armor=?,max_armor=? WHERE character_id=?',(current,maximum,ids[0]))
        elif action=='damage':
            amount = values[0]
            if not 0 < amount <= 1000000:
                return False,'Урон должен быть от 1 до 1000000.'
            s = states[0]
            absorbed = min(s['armor'],amount)
            food_loss = min(s['food_hp'], amount-absorbed)
            hp_loss = min(s['hp'], amount-absorbed-food_loss)
            await conn.execute('UPDATE armor_instances SET durability=? WHERE character_id=? AND equipped=1',(s['armor']-absorbed,ids[0]))
            await conn.execute('UPDATE character_health SET armor=?,food_hp=?,hp=? WHERE character_id=?',(s['armor']-absorbed,s['food_hp']-food_loss,s['hp']-hp_loss,ids[0]))
        elif action=='start':
            if any(s['scene_key'] or s['hp']==0 for s in states):
                return False,'Участник уже в сцене или имеет 0 HP.'
            key = uuid.uuid4().hex
            for cid in ids:
                await conn.execute('UPDATE character_health SET scene_key=?,medkit_used=0 WHERE character_id=?',(key,cid))
        elif action=='end':
            key = states[0]['scene_key']
            if not key:
                return False,'Персонаж не в боевой сцене.'
            await conn.execute("UPDATE character_health SET scene_key='', food_hp=0,food_max=0,food_expires=0,medkit_used=0,basic_healed=CASE WHEN hp=max_hp THEN 0 ELSE basic_healed END WHERE scene_key=?",(key,))
        else:
            return False,'Неизвестное действие.'
        await conn.execute('INSERT INTO admin_audit_log(admin_vk_id,action,target_character_id,details,created_at) VALUES (?,?,?,?,?)',
                           (admin_id,'health_'+action,ids[0],str((ids,values)),now))
        return True,'Состояние обновлено.'
