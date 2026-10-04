import json
import time
from vkbottle import Keyboard, Text, KeyboardButtonColor
from systems import duels
from systems.vitals import get_health
import database as db


def register_duel_handlers(bot):
    async def show(message,result):
        text=result.get('text','')
        kb=Keyboard(inline=True)
        d=result.get('duel')
        def button(label,action):
            kb.add(Text(label,payload={'duel':d['id'],'rev':d['revision'],'action':action}),color=KeyboardButtonColor.PRIMARY).row()
        if d:
            text+=f"\n⚔️ ДУЭЛЬ #{d['id']}\n{d['name_a']} (#{d['a']}) — {d['name_b']} (#{d['b']})\n"
            if d['status']=='invite':
                text+='Приглашённый игрок должен принять вызов в течение 5 минут.'
                button('✅ Принять бой','accept');button('❌ Отказаться','decline');button('Отменить вызов','cancel')
            else:
                for key in ('a','b'):
                    s=await get_health(d[key],int(time.time()))
                    text+=f"#{d[key]}: ❤️ {s['hp']}/100 · 🍽 {s['food_hp']} · 🛡 {s['armor']}/{s['max_armor']} · 🔫 {s['weapon_name']} (урон {d['damage_'+key]})\n"
                if d['phase']=='turn':
                    text+=f"Ход #{d['actor']}: атака или лечение."
                    button('⚔️ Атаковать','attack');button('💊 Лечение','medmenu')
                else:
                    defender=d['b'] if d['actor']==d['a'] else d['a']
                    text+=f'Защищается #{defender}. Блок −40% урона; уклонение — шанс 40%.'
                    button('🛡 Блок','block');button('💨 Уклонение','dodge')
                button('🤝 Завершить по согласию','draw')
                button('🏳 Сдаться','surrender_menu')
                if d['draw_by']:text+=f"\n#{d['draw_by']} предлагает закончить бой. Кнопка согласия завершит бой для соперника."
                text+='\nОжидание действия — 10 минут. /дуель восстанавливает панель.'
        elif 'targets' in result:
            targets=result['targets'];page=result.get('page',0)
            page=max(0,min(page,max(0,(len(targets)-1)//4)))
            text='⚔️ Выберите соперника. Бой начнётся только после его согласия.\n'+('Сейчас нет доступных соперников в этой локации.' if not targets else '')
            for cid,name in targets[page*4:page*4+4]:
                kb.add(Text(f'Вызвать #{cid}',payload={'duel_target':cid,'owner':message.from_id}),color=KeyboardButtonColor.PRIMARY).row()
                text+=f'#{cid} — {name}\n'
            if page:
                kb.add(Text('Предыдущие соперники',payload={'duel_page':page-1,'owner':message.from_id})).row()
            if (page+1)*4<len(targets):
                kb.add(Text('Следующие соперники',payload={'duel_page':page+1,'owner':message.from_id})).row()
        # Remove the empty final row before serializing VK's inline keyboard.
        data=json.loads(kb.get_json());data['buttons']=[row for row in data['buttons'] if row]
        await message.answer(text or 'Откройте /дуель.',**({'keyboard':json.dumps(data,ensure_ascii=False)} if data['buttons'] else {}))

    @bot.on.message(text='/дуель')
    async def duel_panel(message):await show(message,await duels.panel(message.from_id,message.peer_id,int(time.time())))

    @bot.on.message(text=['Вызвать #<target>','Предыдущие соперники','Следующие соперники','✅ Принять бой','❌ Отказаться','Отменить вызов','⚔️ Атаковать','🛡 Блок','💨 Уклонение','💊 Лечение','🤝 Завершить по согласию','🏳 Сдаться','Подтвердить сдачу','Лечить: <label>'])
    async def duel_button(message,**kwargs):
        try:
            payload=getattr(message,'payload',None) or {}
            if isinstance(payload,str):payload=json.loads(payload)
            if not isinstance(payload,dict):raise ValueError
            if 'owner' in payload and payload['owner']!=message.from_id:raise ValueError
            now=int(time.time())
            if 'duel_target' in payload or 'duel_page' in payload:
                if payload.get('owner')!=message.from_id:raise ValueError
                if 'duel_target' in payload:result=await duels.invite(message.from_id,message.peer_id,int(payload['duel_target']),now)
                else:
                    result=await duels.panel(message.from_id,message.peer_id,now);result['page']=int(payload['duel_page'])
                await show(message,result);return
            did,rev,action=int(payload['duel']),int(payload['rev']),payload['action']
        except (ValueError,TypeError,KeyError):
            await message.answer('Нажмите актуальную кнопку из /дуель.');return
        if action in ('medmenu','surrender_menu'):
            result=await duels.panel(message.from_id,message.peer_id,now);d=result.get('duel');cid=result.get('cid')
            if not d or d['id']!=did or d['revision']!=rev or d['peer']!=message.peer_id or d['status']!='active':
                await message.answer('Панель устарела. Откройте /дуель.');return
            kb=Keyboard(inline=True)
            if action=='surrender_menu':
                kb.add(Text('Подтвердить сдачу',payload={'duel':did,'rev':rev,'action':'surrender','owner':message.from_id}))
                await message.answer('Сдаться и признать победу соперника? HP и износ сохранятся.',keyboard=kb.get_json());return
            if d['actor']!=cid or d['phase']!='turn':
                await message.answer('Лечение доступно вместо атаки в свой ход.');return
            from systems.inventory import find_catalog_item
            s=await get_health(cid,now);count=0
            for _,name,quantity in await db.get_inventory(cid):
                item=find_catalog_item(name);effect=(item or {}).get('effect',{})
                if effect.get('type')!='heal' or quantity<1:continue
                gain=min(effect['amount'],100-s['hp'],20-s['basic_healed'] if effect['group']=='basic' else (0 if s['medkit_used'] else effect['amount']))
                if gain<=0:continue
                if count:kb.row()
                kb.add(Text(f'Лечить: +{gain} HP · ' + {'bandage':'Бинт','hemostatic':'Гемостатик','field_medkit':'Медкомплект'}.get(item['code'],'Предмет'),payload={'duel':did,'rev':rev,'action':'heal:'+item['code']}));count+=1
            await message.answer('Нажатие потратит один предмет и ваш ход. /дуель — вернуться.' if count else 'Доступного лечения нет: проверьте HP, лимиты и инвентарь.',**({'keyboard':kb.get_json()} if count else {}));return
        await show(message,await duels.act(message.from_id,message.peer_id,did,rev,action,now))

