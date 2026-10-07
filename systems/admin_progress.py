"""Admin XP and faction edits, committed together with their audit record."""
import json
import time
import database as db

XP_ACTIONS = {'➕ Выдать XP': 'xp_add', '➖ Списать XP': 'xp_subtract', '🧾 Установить XP': 'xp_set'}
FACTIONS = {
    '🛡 Директория': '🛡️ ЗЕМНАЯ ДИРЕКТОРИЯ',
    '⚙ HELIOS Dynamics': '⚙️ HELIOS DYNAMICS',
    '🕯 Орден Завесы': '🕯️ ОРДЕН ЗАВЕСЫ',
    '🔥 Культ': '🔥 КУЛЬТ ПЕПЕЛЬНОГО ОТКРОВЕНИЯ',
    '🚫 Убрать фракцию': '🚫 Без фракции',
}
MAX_XP = 2**63 - 1


async def change_progress(admin_id, cid, action, value, now):
    if action in XP_ACTIONS.values():
        if type(value) is not int or not 0 <= value <= MAX_XP or (action != 'xp_set' and value == 0):
            return False, 'invalid'
    elif action != 'faction_set' or value not in FACTIONS.values():
        return False, 'invalid'
    async with db._transaction() as conn:
        cur = await conn.execute('SELECT role FROM bot_admins WHERE vk_user_id=? AND active=1', (admin_id,))
        role = await cur.fetchone()
        if not role or role[0] not in ('admin', 'senior', 'owner'):
            return False, 'forbidden'
        cur = await conn.execute('SELECT user_id, faction, faction_rank, faction_rank_level FROM characters WHERE id=?', (cid,))
        character = await cur.fetchone()
        if not character:
            return False, 'not_found'
        uid = character[0]
        if action == 'faction_set':
            if character[1] == value:
                return False, 'unchanged'
            await conn.execute('UPDATE characters SET faction=?, faction_rank=NULL, faction_rank_level=0 WHERE id=?', (value, cid))
            details = {'before': character[1], 'after': value, 'previous_rank': character[2], 'previous_rank_level': character[3]}
        else:
            await conn.execute('INSERT OR IGNORE INTO users(user_id, balance) VALUES (?, 1500)', (uid,))
            cur = await conn.execute('SELECT xp FROM users WHERE user_id=?', (uid,))
            old = (await cur.fetchone())[0] or 0
            new = value if action == 'xp_set' else old + (value if action == 'xp_add' else -value)
            if new < 0:
                return False, 'not_enough'
            if new > MAX_XP:
                return False, 'overflow'
            await conn.execute('UPDATE users SET xp=? WHERE user_id=?', (new, uid))
            details = {'before': old, 'after': new, 'amount': value}
        await conn.execute('INSERT INTO admin_audit_log(admin_vk_id,action,target_vk_id,target_character_id,details,created_at) VALUES (?,?,?,?,?,?)',
                           (admin_id, action, uid, cid, json.dumps(details, ensure_ascii=False), now))
        return True, details['after']


def install_progress(bot, deps, sessions, require_admin, show_player):
    Keyboard, Text = deps['Keyboard'], deps['Text']
    def keyboard(labels):
        kb = Keyboard(one_time=False)
        for i, label in enumerate([*labels, '⬅️ К игроку']):
            if i: kb.row()
            kb.add(Text(label))
        return kb.get_json()

    async def selected(message):
        if not await require_admin(message, 'admin'):
            return None
        cid = sessions.get(message.from_id, {}).get('character_id')
        c = await db.get_character_by_id(cid or 0)
        if not c:
            await message.answer('Сначала выберите игрока через «👤 Управление игроком».')
        return c

    @bot.on.message(text='⭐ Опыт игрока')
    async def experience_menu(message):
        c = await selected(message)
        if not c: return
        sessions[message.from_id] = {'mode': 'player', 'character_id': c[0]}
        user = await db.get_user(c[1])
        await message.answer(f'⭐ {c[2]} — {user[2] if user else 0} XP\nВыберите действие.', keyboard=keyboard(XP_ACTIONS))

    @bot.on.message(text=list(XP_ACTIONS))
    async def experience_start(message):
        c = await selected(message)
        if not c: return
        action = next((v for k, v in XP_ACTIONS.items() if normalize(k) == normalize(message.text)), None)
        if not action: return
        sessions[message.from_id] = {'mode': action, 'character_id': c[0]}
        prompt = 'Введите новый общий опыт (целое число от 0).' if action == 'xp_set' else 'Введите количество XP целым положительным числом.'
        await message.answer(f'👤 #{c[0]} — {c[2]}\n{prompt}', keyboard=keyboard([]))

    @bot.on.message(text='🔄 Изменить фракцию')
    async def faction_start(message):
        c = await selected(message)
        if not c: return
        sessions[message.from_id] = {'mode': 'faction_set', 'character_id': c[0]}
        await message.answer(f'👤 #{c[0]} — {c[2]}\nТекущая фракция: {c[5]}\nВыберите новую. Старый фракционный ранг будет сброшен.', keyboard=keyboard(FACTIONS))

    async def apply(message, action, value):
        c = await selected(message)
        if not c: return
        ok, result = await change_progress(message.from_id, c[0], action, value, int(time.time()))
        if not ok:
            messages = {'not_enough': 'У игрока недостаточно XP. Опыт не изменён.', 'unchanged': 'Эта фракция уже назначена. Ранг сохранён.',
                        'forbidden': 'Недостаточно административных прав.', 'not_found': 'Персонаж уже удалён.',
                        'overflow': 'Слишком большое значение XP.', 'invalid': 'Введите допустимое целое число. Для выдачи и списания — больше нуля.'}
            await message.answer(messages[result]); return
        text = f'✅ Опыт персонажа #{c[0]}: {result} XP.' if action != 'faction_set' else f'✅ Фракция персонажа #{c[0]}: {result}.\nРанг сброшен; назначить его можно в разделе «Фракция игрока».'
        await message.answer(text)
        await show_player(message, c[0])

    @bot.on.message(text=list(FACTIONS))
    async def faction_apply(message):
        if message.peer_id != deps['ADMIN_CHAT_ID']: return
        if sessions.get(message.from_id, {}).get('mode') != 'faction_set':
            await message.answer('Сначала выберите игрока и нажмите «Изменить фракцию».'); return
        value = next((v for k, v in FACTIONS.items() if normalize(k) == normalize(message.text)), None)
        if value: await apply(message, 'faction_set', value)

    def normalize(text):
        text = (text or '').strip().replace('\ufe0f', '')
        if text.startswith('[club') and ']' in text: text = text.split(']', 1)[1].strip()
        return ' '.join(text.split())

    buttons = {normalize('⭐ Опыт игрока'): experience_menu, normalize('🔄 Изменить фракцию'): faction_start}
    buttons.update({normalize(k): experience_start for k in XP_ACTIONS})
    buttons.update({normalize(k): faction_apply for k in FACTIONS})

    async def handle(message):
        if message.peer_id != deps['ADMIN_CHAT_ID']: return False
        handler = buttons.get(normalize(message.text))
        if handler:
            await handler(message); return True
        session = sessions.get(message.from_id, {})
        if session.get('mode') not in XP_ACTIONS.values(): return False
        text = (message.text or '').strip()
        try: amount = int(text)
        except ValueError:
            if await require_admin(message, 'admin'): await message.answer('Введите целое число XP или нажмите «К игроку».')
            return True
        await apply(message, session['mode'], amount)
        return True
    return handle
