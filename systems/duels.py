"""Transactional, persistent two-player duels. No VK calls inside transactions."""
import json
import secrets
from pathlib import Path
import database as db
from systems.vitals import _state

INVITE_TTL=300
TURN_TTL=600

async def one(conn,sql,args=()):
    cur=await conn.execute(sql,args);row=await cur.fetchone()
    return dict(zip([c[0] for c in cur.description],row)) if row else None

async def ensure_duel_tables():
    async with db._transaction() as conn:
        await conn.execute('''CREATE TABLE IF NOT EXISTS duels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,peer INTEGER NOT NULL,
            a INTEGER NOT NULL,b INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'invite',
            actor INTEGER,phase TEXT NOT NULL DEFAULT 'turn',revision INTEGER NOT NULL DEFAULT 0,
            expires INTEGER NOT NULL,damage_a INTEGER,damage_b INTEGER,draw_by INTEGER,
            result TEXT NOT NULL DEFAULT '')''')
        await conn.execute('CREATE TABLE IF NOT EXISTS duel_members(character_id INTEGER PRIMARY KEY,duel_id INTEGER NOT NULL)')

async def finish(conn,d,text):
    await conn.execute("UPDATE duels SET status='done',revision=revision+1,result=? WHERE id=?",(text,d['id']))
    await conn.execute('DELETE FROM duel_members WHERE duel_id=?',(d['id'],))
    await conn.execute("UPDATE character_health SET scene_key='',food_hp=0,food_max=0,food_expires=0,medkit_used=0,basic_healed=CASE WHEN hp=max_hp THEN 0 ELSE basic_healed END WHERE scene_key=?",(f"duel:{d['id']}",))

async def expire(conn,now):
    cur=await conn.execute("SELECT * FROM duels WHERE status!='done' AND expires<=?",(now,))
    rows=[dict(zip([c[0] for c in cur.description],r)) for r in await cur.fetchall()]
    for d in rows:await finish(conn,d,'Время ожидания истекло. Дуэль закрыта без победителя; полученный урон сохранён.')

async def present(conn,cid,peer):
    return await one(conn,"SELECT c.id,c.user_id,c.name FROM characters c LEFT JOIN character_locations cl ON cl.character_id=c.id JOIN locations l ON l.code=COALESCE(cl.location_code,'холл') WHERE c.id=? AND c.status='approved' AND l.peer_id=?",(cid,peer))

async def view(conn,d):
    d=dict(d)
    for key in ('a','b'):
        c=await one(conn,'SELECT name,user_id FROM characters WHERE id=?',(d[key],))
        d['name_'+key]=c['name'] if c else 'Удалённый персонаж'
    return d

async def panel(uid,peer,now):
    async with db._transaction() as conn:
        await expire(conn,now)
        c=await one(conn,"SELECT id FROM characters WHERE user_id=? AND status='approved' ORDER BY id DESC LIMIT 1",(uid,))
        if not c or not await present(conn,c['id'],peer):return {'text':'Откройте /дуель в своей RP-локации с одобренным персонажем.'}
        d=await one(conn,'SELECT d.* FROM duels d JOIN duel_members m ON m.duel_id=d.id WHERE m.character_id=?',(c['id'],))
        if d:return {'duel':await view(conn,d),'cid':c['id']}
        cur=await conn.execute("SELECT c.id,c.name FROM characters c LEFT JOIN character_locations cl ON cl.character_id=c.id JOIN locations l ON l.code=COALESCE(cl.location_code,'холл') LEFT JOIN duel_members m ON m.character_id=c.id LEFT JOIN character_health h ON h.character_id=c.id WHERE c.status='approved' AND c.id!=? AND l.peer_id=? AND m.character_id IS NULL AND COALESCE(h.scene_key,'')='' AND COALESCE(h.hp,100)>0 ORDER BY c.id",(c['id'],peer))
        return {'cid':c['id'],'targets':await cur.fetchall()}

async def invite(uid,peer,target,now):
    async with db._transaction() as conn:
        await expire(conn,now)
        c=await one(conn,"SELECT id FROM characters WHERE user_id=? AND status='approved' ORDER BY id DESC LIMIT 1",(uid,))
        if not c or c['id']==target:return {'text':'Выберите другого персонажа.'}
        for cid in (c['id'],target):
            if not await present(conn,cid,peer):return {'text':'Оба персонажа должны находиться в этой RP-локации.'}
            if await one(conn,'SELECT 1 FROM duel_members WHERE character_id=?',(cid,)):return {'text':'Один из игроков уже участвует в дуэли или ожидает ответа.'}
            s=await _state(conn,cid,now)
            if s['scene_key'] or s['hp']==0:return {'text':'Участник уже в сцене или имеет 0 HP.'}
        cur=await conn.execute('INSERT INTO duels(peer,a,b,expires) VALUES (?,?,?,?)',(peer,c['id'],target,now+INVITE_TTL))
        did=cur.lastrowid
        await conn.executemany('INSERT INTO duel_members VALUES (?,?)',[(cid,did) for cid in (c['id'],target)])
        return {'duel':await view(conn,await one(conn,'SELECT * FROM duels WHERE id=?',(did,)))}

async def act(uid,peer,did,revision,action,now):
    async with db._transaction() as conn:
        await expire(conn,now)
        d=await one(conn,'SELECT * FROM duels WHERE id=?',(did,))
        if not d or d['peer']!=peer:return {'text':'Панель не относится к этому чату.'}
        c=await one(conn,'SELECT id FROM characters WHERE user_id=? AND id IN (?,?)',(uid,d['a'],d['b']))
        if not c:return {'text':'Эти кнопки доступны только участникам дуэли.'}
        cid=c['id'];other=d['b'] if cid==d['a'] else d['a']
        if d['status']=='done':return {'text':d['result']}
        if revision!=d['revision']:return {'text':'Кнопка устарела. Откройте /дуель для актуальной панели.'}
        if not all([await present(conn,i,peer) for i in (d['a'],d['b'])]):
            await finish(conn,d,'Участник покинул локацию. Дуэль закрыта без победителя.')
            return {'text':'Участник покинул локацию. Дуэль закрыта; урон сохранён.'}
        text=''
        if d['status']=='invite':
            if action=='decline' and cid==d['b'] or action=='cancel' and cid==d['a']:
                await finish(conn,d,'Приглашение отклонено или отменено.');return {'text':'Приглашение закрыто.'}
            if action!='accept' or cid!=d['b']:return {'text':'Принять вызов может только приглашённый игрок.'}
            states=[await _state(conn,i,now) for i in (d['a'],d['b'])]
            if any(s['scene_key'] or s['hp']==0 for s in states):
                await finish(conn,d,'Участник больше не готов к бою.');return {'text':'Участник больше не готов к бою.'}
            for i in (d['a'],d['b']):await conn.execute('UPDATE character_health SET scene_key=?,medkit_used=0 WHERE character_id=?',(f'duel:{did}',i))
            await conn.execute("UPDATE duels SET status='active',actor=?,damage_a=?,damage_b=? WHERE id=?",(secrets.choice([d['a'],d['b']]),states[0]['weapon_damage'] or 8,states[1]['weapon_damage'] or 8,did))
            text='Вызов принят. Первый ход определён случайно. Без оружия урон 8.'
        elif action=='surrender':
            await finish(conn,d,f'Персонаж #{cid} сдался. Победитель: #{other}.');return {'text':f'🏳 Персонаж #{cid} сдался. Победитель: #{other}.'}
        elif action=='draw':
            if d['draw_by'] and d['draw_by']!=cid:
                await finish(conn,d,'Дуэль завершена по взаимному согласию.');return {'text':'🤝 Дуэль завершена по взаимному согласию.'}
            if d['draw_by']==cid:return {'text':'Предложение уже отправлено. Решение за соперником.'}
            await conn.execute('UPDATE duels SET draw_by=? WHERE id=?',(cid,did));text=f'#{cid} предлагает завершить бой. Соперник может принять или продолжить.'
        elif action=='attack':
            if d['phase']!='turn' or d['actor']!=cid:return {'text':'Сейчас не ваш ход атаки.'}
            await conn.execute("UPDATE duels SET phase='defend',draw_by=NULL WHERE id=?",(did,));text=f'⚔️ #{cid} атакует. #{other}, выберите блок или уклонение.'
        elif action in ('block','dodge'):
            if d['phase']!='defend' or d['actor']==cid:return {'text':'Сейчас вы не защищаетесь.'}
            hit=secrets.randbelow(100)<85
            avoided=action=='dodge' and secrets.randbelow(100)<40
            damage=d['damage_a'] if d['actor']==d['a'] else d['damage_b']
            damage=0 if not hit or avoided else (damage*3+4)//5 if action=='block' else damage
            s=await _state(conn,cid,now)
            armor=min(s['armor'],damage);food=min(s['food_hp'],damage-armor);hp=min(s['hp'],damage-armor-food)
            await conn.execute('UPDATE armor_instances SET durability=durability-? WHERE character_id=? AND equipped=1',(armor,cid))
            await conn.execute('UPDATE character_health SET armor=armor-?,food_hp=food_hp-?,hp=hp-? WHERE character_id=?',(armor,food,hp,cid))
            text=(f'💥 #{cid}: урон {damage} (броня −{armor}, еда −{food}, HP −{hp}).' if damage else f'💨 #{cid} избегает попадания.')
            if s['hp']-hp==0:
                await finish(conn,d,f'Победитель: #{other}. #{cid} выбывает при 0 HP, затем приходит в себя с 1 HP. Это не смерть персонажа.')
                await conn.execute('UPDATE character_health SET hp=1 WHERE character_id=?',(cid,))
                return {'text':text+f'\nПобедитель: #{other}. Дуэль окончена. Проигравший приходит в себя с 1 HP и может лечиться вне боя. Это не смерть персонажа.'}
            await conn.execute("UPDATE duels SET actor=?,phase='turn',draw_by=NULL WHERE id=?",(cid,did))
        elif action.startswith('heal:'):
            if d['phase']!='turn' or d['actor']!=cid:return {'text':'Лечение доступно только вместо атаки в свой ход.'}
            code=action.split(':',1)[1]
            catalog=json.loads((Path(__file__).resolve().parents[1]/'shop_items.json').read_text(encoding='utf-8'))
            item=next((i for i in catalog['medicine']['items'] if i['code']==code and i.get('effect',{}).get('type')=='heal'),None)
            if not item:return {'text':'Выберите лечебный предмет.'}
            s=await _state(conn,cid,now);effect=item['effect'];basic=effect['group']=='basic'
            gain=min(effect['amount'],s['max_hp']-s['hp'],20-s['basic_healed'] if basic else (0 if s['medkit_used'] else effect['amount']))
            if gain<=0:return {'text':'Здоровье полное или лимит лечения исчерпан. Ход не потрачен.'}
            ok,_=await db._take_item(conn,cid,item['name'],1)
            if not ok:return {'text':'Предмета нет в инвентаре. Ход не потрачен.'}
            await conn.execute('UPDATE character_health SET hp=hp+?,basic_healed=basic_healed+?,medkit_used=? WHERE character_id=?',(gain,gain if basic else 0,s['medkit_used'] if basic else 1,cid))
            await conn.execute("UPDATE duels SET actor=?,draw_by=NULL WHERE id=?",(other,did));text=f'🩹 #{cid} использует {item["name"]}: +{gain} HP. Ход переходит сопернику.'
        else:return {'text':'Недопустимое действие.'}
        # Asking for mutual termination cannot extend the turn indefinitely.
        deadline=d['expires'] if action=='draw' else now+TURN_TTL
        await conn.execute('UPDATE duels SET revision=revision+1,expires=? WHERE id=?',(deadline,did))
        return {'text':text,'duel':await view(conn,await one(conn,'SELECT * FROM duels WHERE id=?',(did,)))}
