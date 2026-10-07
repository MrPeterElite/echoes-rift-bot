"""Button-based transfers with final transactional ownership and location checks."""
import time
import database as db
from systems import duels

async def recipients(cid):
    conn=await db.connect()
    try:
        cur=await conn.execute("""SELECT c.id,c.name FROM characters c
            JOIN character_locations l ON l.character_id=c.id
            JOIN character_locations me ON me.location_code=l.location_code
            WHERE me.character_id=? AND c.id!=? AND c.status='approved' ORDER BY c.id""",(cid,cid))
        return await cur.fetchall()
    finally: await conn.close()

async def transfer(uid,cid,peer,view):
    from systems.inventory import find_catalog_item
    if view['expires']<=int(time.time()): return 'Подтверждение истекло. Начните передачу заново.'
    target=view['target']; item=view['back']; category=item['category']; quantity=view['quantity']
    if type(quantity) is not int or quantity<=0 or target==cid: return 'Недопустимое количество или получатель.'
    await duels.refresh_character_scene(cid,int(time.time()))
    await duels.refresh_character_scene(target,int(time.time()))
    async with db._transaction() as conn:
        cur=await conn.execute("""SELECT c.id,c.user_id,c.name,COALESCE(h.scene_key,''),loc.peer_id
            FROM characters c LEFT JOIN character_health h ON h.character_id=c.id
            LEFT JOIN character_locations cl ON cl.character_id=c.id
            LEFT JOIN locations loc ON loc.code=cl.location_code
            WHERE c.id IN (?,?) AND c.status='approved'""",(cid,target))
        people={r[0]:r for r in await cur.fetchall()}
        if cid not in people or target not in people or people[cid][1]!=uid: return 'Персонаж отправителя или получателя изменился.'
        if any(p[4]!=peer for p in people.values()): return 'Оба персонажа должны находиться в этой RP-локации.'
        if any(p[3] for p in people.values()): return 'Передача доступна только когда оба персонажа вне боя.'
        if people[target][2]!=view['target_name']: return 'Имя получателя изменилось. Выберите его заново.'
        if category in ('armor','weapons'):
            table='armor_instances' if category=='armor' else 'weapon_instances'
            cur=await conn.execute(f'SELECT name,equipped FROM {table} WHERE id=? AND character_id=?',(item['item_id'],cid))
            row=await cur.fetchone()
            if not row: return 'Этот предмет уже не принадлежит вам.'
            if row[1]: return 'Сначала снимите броню или уберите оружие.'
            if quantity!=1: return 'Экипировка передаётся по одному экземпляру.'
            await conn.execute(f'UPDATE {table} SET character_id=? WHERE id=?',(target,item['item_id']))
            name=row[0]
        else:
            catalog=find_catalog_item(item['name'])
            if catalog and not catalog.get('transferable',True): return 'Этот предмет нельзя передавать.'
            cur=await conn.execute('SELECT id,category,item_name,quantity FROM inventory WHERE character_id=? AND item_name=?',(cid,item['name']))
            row=await cur.fetchone()
            if not row or row[3]<quantity: return 'Недостаточно предметов. Выберите количество заново.'
            await conn.execute('UPDATE inventory SET quantity=quantity-? WHERE id=?',(quantity,row[0]))
            await conn.execute('DELETE FROM inventory WHERE id=? AND quantity=0',(row[0],))
            await db._put_item(conn,target,row[1],row[2],quantity)
            name=row[2]
    return f"✅ Передано: {name} ×{quantity}\nПолучатель: {view['target_name']} · #{target}."

async def render_transfer(c,view):
    from systems.inventory_panel import entries
    rows=[]
    def button(label,**action): rows.append([(label,action)])
    back=view['back']; screen=view['screen']
    if screen=='transfer_people':
        people=await recipients(c[0]); page=max(0,min(view.get('recipient_page',0),max(0,(len(people)-1)//4)))
        text='\nКому передать '+back['name']+'?\nПерсонажи в вашей локации:\n'
        for cid,name in people[page*4:page*4+4]:
            text+=f'#{cid} — {name}\n'
            button(f'#{cid} {name}'[:40],screen='transfer_quantity',back=back,target=cid,target_name=name,quantity=1)
        if not people: text+='Других одобренных персонажей здесь нет.'
        if page: button('◀ Получатели',**dict(view,recipient_page=page-1))
        if (page+1)*4<len(people): button('Получатели ▶',**dict(view,recipient_page=page+1))
    else:
        item=next((x for x in await entries(c[0],back['category']) if (x.get('id')==back.get('item_id') if back['category'] in ('armor','weapons') else x['name']==back['name'])),None)
        maximum=item.get('quantity',1) if item else 0
        quantity=view['quantity']
        text=f"\nПередача: {back['name']}\nПолучатель: {view['target_name']} · #{view['target']}\nКоличество: {quantity} (доступно {maximum})\n"
        if screen=='transfer_quantity':
            if maximum:
                quantity=max(1,min(quantity,maximum)); view=dict(view,quantity=quantity)
                text=f"\nПередача: {back['name']}\nПолучатель: {view['target_name']} · #{view['target']}\nКоличество: {quantity} (доступно {maximum})\n"
                if maximum>1:
                    for label,n in [('−5',quantity-5),('−1',quantity-1),('+1',quantity+1),('+5',quantity+5),('Все',maximum)]:
                        n=max(1,min(n,maximum))
                        if n!=quantity: button(label,**dict(view,quantity=n))
                button('Далее',**dict(view,screen='transfer_confirm',expires=int(time.time())+60))
            else: text+='Предмета уже нет.'
            button('Другой получатель',screen='transfer_people',back=back)
        else:
            text+='Проверьте имя и количество. Подтверждение действует минуту.'
            if view['expires']>int(time.time()): button('✅ Передать',**dict(view,op='transfer_commit'))
            else: text+='\nПодтверждение истекло.'
            button('Изменить количество',**dict(view,screen='transfer_quantity'))
    button('Отмена',**back)
    return text,rows
