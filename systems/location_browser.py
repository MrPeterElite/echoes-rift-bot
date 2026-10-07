import json
import time
from vkbottle import Keyboard,Text,OpenLink,KeyboardButtonColor
import database as db
from systems.navigation import HOME

def register_location_browser(bot):
    async def character(message):
        if message.peer_id!=message.from_id:
            await message.answer('Выбор локации кнопками доступен в ЛС бота.');return None
        c=await db.get_character_by_user(message.from_id)
        if not c or c[10]!='approved':
            await message.answer('Для перемещения нужен одобренный персонаж.');return None
        return c

    async def show(message,page=0):
        c=await character(message)
        if not c:return
        locations=await db.get_all_locations();current=await db.get_character_location(c[0])
        page=max(0,min(page,max(0,(len(locations)-1)//5)))
        kb=Keyboard(one_time=False)
        lines=['🗺 ЛОКАЦИИ',f"Вы сейчас: {current[1] if current else 'не определено'}",'Выберите место, затем нажмите «Перейти сюда».']
        for index,(code,name,_,_) in enumerate(locations[page*5:page*5+5]):
            if index:kb.row()
            kb.add(Text('📍 '+name[:34],payload={'location_pick':code,'owner':message.from_id,'cid':c[0]}))
        if locations:kb.row()
        if page:kb.add(Text('◀ Локации',payload={'location_page':page-1,'owner':message.from_id}))
        if (page+1)*5<len(locations):kb.add(Text('Локации ▶',payload={'location_page':page+1,'owner':message.from_id}))
        if page or (page+1)*5<len(locations):kb.row()
        kb.add(Text('📍 Где я')).add(Text(HOME),color=KeyboardButtonColor.SECONDARY)
        lines.append(f'Страница {page+1}/{max(1,(len(locations)+4)//5)}')
        await message.answer('\n'.join(lines),keyboard=kb.get_json())

    async def card(message,c,code,moved=False):
        target=await db.get_location_by_code(code)
        if not target:
            await message.answer('Локация больше недоступна. Откройте список заново.');return
        current=await db.get_character_location(c[0]);here=bool(current and current[0]==code)
        kb=Keyboard(one_time=False)
        if not here:
            kb.add(Text('🚶 Перейти сюда',payload={'location_move':code,'owner':message.from_id,'cid':c[0]}),color=KeyboardButtonColor.POSITIVE).row()
        if here and target[3] and target[3].startswith('https://'):
            kb.add(OpenLink(target[3],'Открыть беседу')).row()
        kb.add(Text('🗺 Локации')).add(Text(HOME),color=KeyboardButtonColor.SECONDARY)
        text=('✅ Вы перешли в локацию' if moved else '📍 Вы находитесь здесь' if here else '📍 Выбранная локация')+f': {target[1]}.'
        text+='\nТеперь можно открыть её беседу и продолжить RP.' if here else '\nПереход изменит местоположение вашего персонажа.'
        await message.answer(text,keyboard=kb.get_json())

    @bot.on.message(text=['🗺 Локации','◀ Локации','Локации ▶'])
    async def location_menu(message):
        if message.text=='🗺 Локации':await show(message);return
        try:
            payload=message.payload
            if isinstance(payload,str):payload=json.loads(payload)
            if payload['owner']!=message.from_id:raise ValueError
            page=int(payload['location_page'])
        except (AttributeError,ValueError,TypeError,KeyError):
            await message.answer('Откройте «🗺 Локации» заново.');return
        await show(message,page)

    @bot.on.message(text=['📍 <name>','🚶 Перейти сюда'])
    async def location_choose(message,**kwargs):
        if message.text=='📍 Где я':
            c=await character(message)
            if c:
                current=await db.get_character_location(c[0]);await card(message,c,current[0])
            return
        c=await character(message)
        if not c:return
        try:
            payload=message.payload
            if isinstance(payload,str):payload=json.loads(payload)
            if payload['owner']!=message.from_id or payload['cid']!=c[0]:raise ValueError
            code=payload.get('location_move') or payload['location_pick']
            if not isinstance(code,str):raise ValueError
        except (AttributeError,ValueError,TypeError,KeyError):
            await message.answer('Кнопка устарела. Откройте «🗺 Локации» заново.');return
        if 'location_move' in payload:
            ok,reason=await db.move_character_if_idle(message.from_id,c[0],code,int(time.time()))
            if not ok:
                await message.answer('⛔ Нельзя покинуть локацию во время активной дуэли или сцены.' if reason=='in_combat' else 'Не удалось перейти: проверьте персонажа и выбранную локацию.');return
            await card(message,c,code,moved=True)
        else:await card(message,c,code)
    return show
