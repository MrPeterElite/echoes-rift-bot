"""One owner-bound, revisioned inventory panel per RP peer and player."""
import asyncio
import json
import secrets
import time
import database as db
from systems.vitals import get_health, use_health_item
from systems.armor import list_armor, armor_action
from systems.weapons import list_weapons, weapon_action
from systems.item_effects import describe_effect
from systems.duel_callbacks import CallbackMessage

CATEGORIES = {'food': '🍽 Еда и напитки', 'medicine': '💊 Медикаменты', 'weapons': '🔫 Оружие', 'armor': '🛡 Броня', 'other': '📦 Остальное'}
ERRORS = {'duel_only': 'В дуэли лечитесь через /дуель — это расходует ход.', 'in_combat': 'Еду нельзя использовать в боевой сцене.',
          'full_hp': 'Здоровье полное. Предмет не потрачен.', 'limit': 'Лимит лечения исчерпан.',
          'incapacitated': 'При 0 HP обычное лечение недоступно.', 'not_stronger': 'Уже действует такой же или больший запас еды.',
          'missing_item': 'Предмета уже нет.', 'invalid_character': 'Нужен одобренный персонаж.', 'invalid_effect': 'У предмета нет доступного игрового эффекта.'}
_locks = {}

async def ensure_tables():
    async with db._transaction() as conn:
        await conn.execute('''CREATE TABLE IF NOT EXISTS bot_inventory_panels(
            peer INTEGER NOT NULL, uid INTEGER NOT NULL, cid INTEGER NOT NULL,
            cmid INTEGER NOT NULL, token TEXT NOT NULL, data TEXT NOT NULL,
            PRIMARY KEY(peer,uid))''')

async def load(peer, uid):
    conn = await db.connect()
    try:
        cur = await conn.execute('SELECT cid,cmid,token,data FROM bot_inventory_panels WHERE peer=? AND uid=?', (peer,uid))
        r = await cur.fetchone()
        return dict(cid=r[0], cmid=r[1], token=r[2], data=json.loads(r[3])) if r else None
    finally: await conn.close()

async def allowed(message):
    c = await db.get_character_by_user(message.from_id)
    if not c or c[10] != 'approved': return None, 'Сначала создайте персонажа и дождитесь одобрения.'
    if await db.get_active_mute(message.from_id, int(time.time())): return None, 'Действует ограничение доступа.'
    location = await db.get_location_by_peer(message.peer_id)
    current = await db.get_character_location(c[0])
    if not location or not current or location[0] != current[0]: return None, 'Откройте инвентарь в своей текущей RP-локации или в ЛС.'
    return c, None

async def entries(cid, category):
    if category == 'armor': return await list_armor(cid)
    if category == 'weapons': return await list_weapons(cid)
    return [dict(name=n, quantity=q, category=k) for k,n,q in await db.get_inventory(cid)
            if (k == category if category != 'other' else k not in ('food','medicine')) and q > 0]

def as_tuple(value):
    return tuple(as_tuple(v) for v in value) if isinstance(value, (list,tuple)) else value

async def render(c, view, notice=''):
    from systems.health_ui import format_health
    from systems.inventory import find_catalog_item
    now = int(time.time())
    state = await get_health(c[0], now)
    text = f"🎒 {c[2]} · #{c[0]}\n❤️ {state['hp']}/{state['max_hp']} HP · 🍽 +{state['food_hp']} · 🛡 {state['armor']}/{state['max_armor']}\n🔫 {state['weapon_name']}\n"
    if notice: text += '\n' + notice + '\n'
    rows = []
    def button(label, **action): rows.append([(label, action)])
    screen = view.get('screen', 'home')
    if screen == 'state':
        text = format_health(c,state,now) + ('\n'+notice if notice else '')
    elif screen == 'list':
        category = view['category']; items = await entries(c[0], category)
        page = max(0,min(view.get('page',0),max(0,(len(items)-1)//5)))
        text += '\n' + CATEGORIES[category] + f' · страница {page+1}\n'
        for i,item in enumerate(items[page*5:page*5+5],start=page*5+1):
            extra = f" ×{item['quantity']}" if 'quantity' in item else (' · экипировано' if item['equipped'] else '')
            text += f"{i}. {item['name']}{extra}\n"
            button(f'{i}. '+item['name'][:30], screen='item', category=category, page=page, name=item['name'], item_id=item.get('id'))
        if not items: text += 'Здесь пока пусто.\n'
        nav = []
        if page: nav.append(('◀',dict(screen='list',category=category,page=page-1)))
        if (page+1)*5 < len(items): nav.append(('▶',dict(screen='list',category=category,page=page+1)))
        if nav: rows.append(nav)
    elif screen == 'item':
        category = view['category']
        item = next((x for x in await entries(c[0],category) if (x.get('id') == view.get('item_id') if category in ('armor','weapons') else x['name'] == view['name'])),None)
        if not item: text += '\nПредмета уже нет в инвентаре.'
        elif category in ('armor','weapons'):
            text += '\n'+item['name'] + (f"\nПрочность: {item['durability']}/{item['max_durability']}" if category == 'armor' else f"\nУрон: {item.get('damage',0)}")
            if state['scene_key']: text += '\nМенять экипировку можно только вне боя.'
            else: button('Снять' if item['equipped'] else 'Экипировать', **dict(view, op='unequip' if item['equipped'] else 'equip'))
        else:
            catalog = find_catalog_item(item['name'])
            text += f"\n{item['name']} ×{item['quantity']}\n"
            if catalog:
                text += catalog.get('description','') + '\n' + describe_effect(catalog)
                if state['scene_key']: text += '\nВ бою используйте действия в /дуель.'
                elif catalog.get('effect',{}).get('type') in ('heal','food_hp') or catalog.get('usable',False):
                    button('Использовать', **dict(view, op='preview'))
            else: text += 'Описание отсутствует.'
        if item and not state['scene_key']:
            transferable = category in ('armor','weapons') or (find_catalog_item(item['name']) or {}).get('transferable',True)
            if transferable:
                if item.get('equipped'): text += '\nДля передачи сначала снимите этот предмет.'
                else: button('🎁 Передать',screen='transfer_people',back=view)
        button('⬅ Назад', screen='list',category=category,page=view.get('page',0))
    elif screen.startswith('transfer_'):
        from systems.inventory_transfer import render_transfer
        details,transfer_rows=await render_transfer(c,view)
        text+=details; rows.extend(transfer_rows)
    elif screen == 'confirm':
        text += '\n'+view['details']+'\nБудет использована 1 единица. Подтверждение действует минуту.'
        if view['expires'] > now: button('✅ Подтвердить', **dict(view, op='use'))
        else: text += '\nПодтверждение истекло.'
        button('Отмена', **view['back'])
    if screen == 'home':
        for category,label in CATEGORIES.items(): button(label,screen='list',category=category,page=0)
    else: button('🎒 Категории',screen='home')
    if screen != 'state': button('❤️ Состояние',screen='state')
    button('Обновить',**dict(view,op='refresh'))
    button('Закрыть',op='close')
    return text,rows

async def publish(bot, message, c, view, notice='', callback=False):
    old = await load(message.peer_id,message.from_id)
    text,rows = await render(c,view,notice)
    token=secrets.token_hex(12); actions=[]; buttons=[]
    for row in rows:
        output=[]
        for label,action in row:
            index=len(actions); actions.append(action)
            payload={'inventory_ui':1,'uid':message.from_id,'token':token,'index':index}
            output.append({'action':{'type':'callback','label':label,'payload':json.dumps(payload)},'color':'secondary'})
        buttons.append(output)
    flat=[button for row in buttons for button in row]
    keyboard=json.dumps({'inline':True,'buttons':[flat[i:i+2] for i in range(0,len(flat),2)]},ensure_ascii=False)
    cmid=old['cmid'] if old else None
    if old:
        try:
            result=await bot.api.messages.edit(peer_id=message.peer_id,cmid=cmid,message=text[:4000],keyboard=keyboard)
            if result is False: raise RuntimeError('edit failed')
        except Exception:
            if callback:
                await message.notice('Не удалось обновить панель. Введите /инвентарь.'); return
            cmid=None
    if not cmid:
        result=await bot.api.messages.send(peer_ids=[message.peer_id],random_id=0,message=text[:4000],keyboard=keyboard)
        sent=result[0]
        cmid=sent.get('conversation_message_id') if isinstance(sent,dict) else getattr(sent,'conversation_message_id',None)
        if type(cmid) is not int or cmid <= 0: return
    async with db._transaction() as conn:
        await conn.execute('INSERT INTO bot_inventory_panels VALUES (?,?,?,?,?,?) ON CONFLICT(peer,uid) DO UPDATE SET cid=excluded.cid,cmid=excluded.cmid,token=excluded.token,data=excluded.data',
                           (message.peer_id,message.from_id,c[0],cmid,token,json.dumps({'view':view,'actions':actions},ensure_ascii=False)))
    if old and old['cmid'] != cmid:
        try: await bot.api.messages.delete(peer_id=message.peer_id,cmids=[old['cmid']],delete_for_all=True)
        except Exception: pass

async def open_panel(bot,message,screen='home'):
    await ensure_tables()
    async with _locks.setdefault((message.peer_id,message.from_id),asyncio.Lock()):
        c,error=await allowed(message)
        if error: await message.answer(error); return
        await publish(bot,message,c,{'screen':screen})

async def use_rp_item(c,item):
    async with db._transaction() as conn:
        cur=await conn.execute("SELECT 1 FROM characters WHERE id=? AND user_id=? AND status='approved'",(c[0],c[1]))
        if not await cur.fetchone(): return 'Персонаж изменился.'
        cur=await conn.execute('SELECT scene_key FROM character_health WHERE character_id=?',(c[0],))
        state=await cur.fetchone()
        if state and state[0]: return 'Использование через инвентарь доступно только вне боя.'
        cur=await conn.execute('SELECT quantity FROM inventory WHERE character_id=? AND item_name=?',(c[0],item['name']))
        row=await cur.fetchone()
        if not row or row[0] <= 0: return 'Предмета уже нет.'
        if item.get('consumable',True):
            ok,_=await db._take_item(conn,c[0],item['name'],1)
            if not ok: return 'Предмета уже нет.'
    return f"{c[2]} использует {item['name']}. Только RP: показатели не изменены."

async def perform(c, action, peer=None):
    from systems.inventory import find_catalog_item
    now=int(time.time()); op=action.get('op'); view={k:v for k,v in action.items() if k!='op'}
    if op=='transfer_commit':
        from systems.inventory_transfer import transfer
        return action['back'],await transfer(c[1],c[0],peer,action)
    if op in ('equip','unequip'):
        fn=armor_action if action['category']=='armor' else weapon_action
        result=await fn(c[1],c[0],op,action.get('item_id'))
        return view,result['text']
    if op not in ('preview','use'): return view,''
    back=action.get('back',view)
    item=find_catalog_item(back['name'])
    if not item: return back,'Описание предмета отсутствует.'
    if item.get('effect',{}).get('type') not in ('heal','food_hp') and not item.get('usable',False):
        return back,'Этот предмет нельзя использовать.'
    if op=='use' and action['expires']<=now: return back,'Подтверждение истекло. Выберите предмет заново.'
    if op=='use' and item.get('effect',{}).get('type') not in ('heal','food_hp'):
        return back,await use_rp_item(c,item)
    if item.get('effect',{}).get('type') in ('heal','food_hp'):
        result=await use_health_item(c[1],c[0],item,now,as_tuple(action['quote']) if action.get('quote') else None,preview=op=='preview')
        if result['status']=='confirm':
            details=f"{item['name']}: +{result['gain']} HP; {'запас от еды' if item['effect']['type']=='food_hp' else 'здоровье'} станет {result['target']}."
            return dict(screen='confirm',back=back,quote=result['quote'],expires=now+60,details=details),''
        if result['status']=='ok': return back,f"✅ Использован {item['name']}: +{result['gain']} HP."
        return back,ERRORS.get(result['status'],'Предмет не использован.')
    return dict(screen='confirm',back=back,expires=now+60,details=f"Использовать {item['name']}? Игровые показатели не изменятся."),''

async def handle_callback(bot,obj):
    message=CallbackMessage(bot,obj); payload=obj['payload']
    try:
        if payload.get('uid')!=message.from_id:
            await message.notice('Это инвентарь другого игрока. Откройте /инвентарь.'); return
        await ensure_tables()
        async with _locks.setdefault((message.peer_id,message.from_id),asyncio.Lock()):
            c,error=await allowed(message)
            if error: await message.notice(error); return
            row=await load(message.peer_id,message.from_id); index=payload.get('index')
            if not row or row['cid']!=c[0] or row['token']!=payload.get('token') or not row['token'] or type(index) is not int or not 0<=index<len(row['data']['actions']) or obj.get('conversation_message_id')!=row['cmid']:
                await message.notice('Панель устарела. Откройте /инвентарь.'); return
            async with db._transaction() as conn:
                cur=await conn.execute("UPDATE bot_inventory_panels SET token='' WHERE peer=? AND uid=? AND token=?",(message.peer_id,message.from_id,row['token']))
                if cur.rowcount!=1: await message.notice('Действие уже обработано.'); return
            action=row['data']['actions'][index]
            if action.get('op')=='close':
                try: await bot.api.messages.delete(peer_id=message.peer_id,cmids=[row['cmid']],delete_for_all=True)
                except Exception:
                    try: await bot.api.messages.edit(peer_id=message.peer_id,cmid=row['cmid'],message='Инвентарь закрыт.',keyboard=json.dumps({'inline':True,'buttons':[]}))
                    except Exception: await message.notice('Кнопки отключены; ВК не позволил убрать сообщение.'); return
                async with db._transaction() as conn:
                    await conn.execute('DELETE FROM bot_inventory_panels WHERE peer=? AND uid=?',(message.peer_id,message.from_id))
                return
            view,notice=await perform(c,action,message.peer_id)
            await publish(bot,message,c,view,notice,callback=True)
    finally: await message.acknowledge()
