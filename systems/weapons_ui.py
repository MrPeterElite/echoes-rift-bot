from vkbottle import Keyboard, Text, KeyboardButtonColor
import database as db
from systems.weapons import list_weapons, weapon_action
from systems.weapon_stats import describe_weapon
from systems.media import stabilize_attachments


def register_weapon_handlers(bot):
    async def context(message):
        character=await db.get_character_by_user(message.from_id)
        if not character or character[10]!='approved':
            await message.answer('Нужен одобренный персонаж.');return None
        if message.peer_id!=message.from_id:
            location=await db.get_location_by_peer(message.peer_id)
            current=await db.get_character_location(character[0])
            if not location or not current or location[0]!=current[0]:
                await message.answer('Откройте оружие в ЛС или своей RP-локации.');return None
        return character

    @bot.on.message(text=['/оружие','🔫 Моё оружие'])
    async def weapon_list(message):
        character=await context(message)
        if not character:return
        items=await list_weapons(character[0])
        lines=['🔫 МОЁ ОРУЖИЕ']
        for item in items:
            lines.append(f"#{item['id']} · {item['name']} · {item['weapon_type']}"+(' · ВЫБРАНО' if item['equipped'] else ''))
        lines.append('\n/оружие ID — карточка и выбор\n/передатьоружие ID_оружия ID_персонажа' if items else 'Оружия нет. Магазин → Оружие.')
        await message.answer('\n'.join(lines))

    @bot.on.message(text='/оружие <weapon_id>')
    async def weapon_card(message,weapon_id=None):
        character=await context(message)
        if not character:return
        try:weapon_id=int(weapon_id)
        except (ValueError,TypeError):
            await message.answer('Укажите ID из /оружие.');return
        item=next((w for w in await list_weapons(character[0]) if w['id']==weapon_id),None)
        if not item:
            await message.answer('Оружие не найдено.');return
        kb=Keyboard(inline=True).add(Text(f'🔫 Выбрать #{weapon_id}'),color=KeyboardButtonColor.PRIMARY).row().add(Text('Убрать оружие'),color=KeyboardButtonColor.SECONDARY)
        kwargs = {'keyboard':kb.get_json()}
        if item.get('local_image'):
            attachment = await stabilize_attachments(bot,None,message.peer_id,item['local_image'])
            if attachment:kwargs['attachment']=attachment
        await message.answer(f"🔫 {item['name']} · #{weapon_id}\nТип: {item['weapon_type']}\n"+('Выбрано' if item['equipped'] else 'В инвентаре')+'\n'+describe_weapon(item),**kwargs)

    async def act(message,action,weapon_id=None,target_id=None):
        character=await context(message)
        if not character:return
        result=await weapon_action(message.from_id,character[0],action,weapon_id,target_id)
        await message.answer(result['text'])

    @bot.on.message(text=['/взятьоружие <weapon_id>','🔫 Выбрать #<weapon_id>'])
    async def equip_weapon(message,weapon_id=None):
        try:weapon_id=int(weapon_id)
        except (ValueError,TypeError):
            await message.answer('Укажите ID из /оружие.');return
        await act(message,'equip',weapon_id)

    @bot.on.message(text=['/убратьоружие','Убрать оружие'])
    async def unequip_weapon(message):await act(message,'unequip')

    @bot.on.message(text='/передатьоружие <weapon_id> <target_id>')
    async def transfer_weapon(message,weapon_id=None,target_id=None):
        try:weapon_id,target_id=int(weapon_id),int(target_id)
        except (ValueError,TypeError):
            await message.answer('/передатьоружие ID_оружия ID_персонажа');return
        await act(message,'transfer',weapon_id,target_id)
