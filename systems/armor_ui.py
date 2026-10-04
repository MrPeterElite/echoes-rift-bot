import json
import secrets
import time
from vkbottle import Keyboard, Text, KeyboardButtonColor
import database as db
from systems.armor import list_armor, armor_action, repair_cost


def register_armor_handlers(bot):
    pending = {}

    async def context(message):
        character = await db.get_character_by_user(message.from_id)
        if not character or character[10]!='approved':
            await message.answer('Нужна одобренная квента.')
            return None
        if message.peer_id!=message.from_id:
            location = await db.get_location_by_peer(message.peer_id)
            current = await db.get_character_location(character[0])
            if not location or not current or location[0]!=current[0]:
                await message.answer('Откройте броню в ЛС или своей RP-локации.')
                return None
        return character

    @bot.on.message(text=['/бронежилеты','🛡 Моя броня'])
    async def armor_list(message):
        character = await context(message)
        if not character:return
        items = await list_armor(character[0])
        lines = ['🛡 МОЯ БРОНЯ']
        for item in items:
            lines.append(f"#{item['id']} · {item['name']} · {item['durability']}/{item['max_durability']}"+(' · НАДЕТ' if item['equipped'] else ''))
        if not items:lines.append('Бронежилетов нет. Купить можно в магазине → Броня.')
        else:lines.append('\n/бронежилет ID — действия с жилетом\n/передатьброню ID_жилета ID_персонажа')
        await message.answer('\n'.join(lines))

    @bot.on.message(text='/бронежилет <armor_id>')
    async def armor_card(message, armor_id=None):
        character = await context(message)
        if not character:return
        try:armor_id=int(armor_id)
        except (TypeError,ValueError):
            await message.answer('Укажите ID бронежилета из /бронежилеты.');return
        item = next((a for a in await list_armor(character[0]) if a['id']==armor_id),None)
        if not item:
            await message.answer('Бронежилет не найден.');return
        kb = (Keyboard(inline=True).add(Text(f'🛡 Надеть #{armor_id}'),color=KeyboardButtonColor.PRIMARY)
              .row().add(Text(f'🔧 Ремонт #{armor_id}'),color=KeyboardButtonColor.POSITIVE)
              .row().add(Text('Снять бронежилет'),color=KeyboardButtonColor.SECONDARY))
        cost = repair_cost(item['durability'],item['max_durability'],item['price'])
        await message.answer(f"🛡 {item['name']} · #{armor_id}\nПрочность: {item['durability']}/{item['max_durability']}\n"
                             f"{'Надет' if item['equipped'] else 'В инвентаре'}\nРемонт: {cost} CR",keyboard=kb.get_json())

    async def act(message, action, armor_id=None, target_id=None, expected=None):
        character = await context(message)
        if not character:return
        result = await armor_action(message.from_id,character[0],action,armor_id,target_id,expected)
        if result['status']=='confirm':
            token = secrets.token_hex(6)
            pending[message.from_id] = (token,message.peer_id,character[0],armor_id,int(time.time())+60,result['quote'])
            kb = (Keyboard(inline=True).add(Text('✅ Оплатить ремонт',payload={'armor_repair':token}),color=KeyboardButtonColor.POSITIVE)
                  .row().add(Text('❌ Отменить ремонт'),color=KeyboardButtonColor.SECONDARY))
            await message.answer(result['text']+'\nПодтверждение действует минуту.',keyboard=kb.get_json())
        else:
            await message.answer(result['text'])

    @bot.on.message(text=['/надетьброню <armor_id>','🛡 Надеть #<armor_id>'])
    async def equip_armor(message, armor_id=None):
        try:armor_id=int(armor_id)
        except (TypeError,ValueError):
            await message.answer('Укажите ID бронежилета.');return
        pending.pop(message.from_id,None)
        await act(message,'equip',armor_id)

    @bot.on.message(text=['/снятьброню','Снять бронежилет'])
    async def unequip_armor(message):
        pending.pop(message.from_id,None)
        await act(message,'unequip')

    @bot.on.message(text=['/ремонтброни <armor_id>','🔧 Ремонт #<armor_id>'])
    async def repair_armor(message, armor_id=None):
        try:armor_id=int(armor_id)
        except (TypeError,ValueError):
            await message.answer('Укажите ID бронежилета.');return
        pending.pop(message.from_id,None)
        await act(message,'repair',armor_id)

    @bot.on.message(text='✅ Оплатить ремонт')
    async def confirm_armor_repair(message):
        try:
            payload = getattr(message,'payload',None) or {}
            if isinstance(payload,str):payload=json.loads(payload)
            token = payload.get('armor_repair') if isinstance(payload,dict) else None
        except (ValueError,TypeError):token=None
        request=pending.get(message.from_id)
        if not request or request[0]!=token or request[1]!=message.peer_id:
            await message.answer('Подтверждение не найдено. Откройте ремонт заново.');return
        pending.pop(message.from_id,None)
        character=await db.get_character_by_user(message.from_id)
        if request[4]<=int(time.time()) or not character or character[0]!=request[2]:
            await message.answer('Подтверждение устарело. Откройте ремонт заново.');return
        await act(message,'repair',request[3],expected=request[5])

    @bot.on.message(text=['❌ Отменить ремонт','/отменаремонта'])
    async def cancel_armor_repair(message):
        pending.pop(message.from_id,None)
        await message.answer('Ремонт отменён. Деньги не списаны.')

    @bot.on.message(text='/передатьброню <armor_id> <target_id>')
    async def transfer_armor(message, armor_id=None,target_id=None):
        try:armor_id,target_id=int(armor_id),int(target_id)
        except (TypeError,ValueError):
            await message.answer('/передатьброню ID_жилета ID_персонажа');return
        pending.pop(message.from_id,None)
        await act(message,'transfer',armor_id,target_id)
