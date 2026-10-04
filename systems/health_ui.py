import time
from vkbottle import Keyboard, Text, KeyboardButtonColor

import database as db
from systems.vitals import get_health, admin_health_action
from systems.item_effects import BASIC_HEAL_LIMIT


def format_health(character, state, now):
    if state['scene_key']:
        food_time = 'до конца сцены' if state['food_hp'] else 'нет'
    else:
        left = max(0,state['food_expires']-now)
        food_time = f'{left // 60} мин. {left % 60} сек.' if state['food_hp'] else 'нет'
    return (
        f"СОСТОЯНИЕ ПЕРСОНАЖА\n{character[2]} · #{character[0]}\n━━━━━━━━━━━━━━━━━━━━\n"
        f"❤️ Здоровье: {state['hp']}/{state['max_hp']}\n"
        f"🍽 Запас от еды: {state['food_hp']}/{state['food_max']} HP · {food_time}\n"
        f"🛡 Броня: {state['armor']}/{state['max_armor']} · {state.get('armor_name','не экипирована')}\n\n"
        f"🩹 Доступно лечения бинтами/гемостатиками: {BASIC_HEAL_LIMIT-state['basic_healed']}/{BASIC_HEAL_LIMIT} HP\n"
        + (f"🧰 Медкомплект в сцене: {'использован' if state['medkit_used'] else 'доступен'}\n" if state['scene_key'] else '')
        + ('⚔️ Идёт сцена. Действия учитывает ведущий.' if state['scene_key'] else '📍 Вне боевой сцены.')
        + ('\n⚠️ 0 HP: требуется помощь ведущего; обычное лечение недоступно.' if state['hp']==0 else '')
    )


def register_health_handlers(bot, admin_chat):
    @bot.on.message(text=['/состояние','❤️ Состояние','/дуель'])
    async def health_card(message):
        character = await db.get_character_by_user(message.from_id)
        if not character or character[10] != 'approved':
            await message.answer('Состояние доступно после одобрения персонажа.')
            return
        if message.peer_id != message.from_id:
            location = await db.get_location_by_peer(message.peer_id)
            current = await db.get_character_location(character[0])
            if message.text != '/дуель' or not location or not current or location[0] != current[0]:
                await message.answer('В своей RP-локации используйте /дуель. Подробное состояние доступно в ЛС: /состояние.')
                return
        now = int(time.time())
        kwargs = {}
        if message.peer_id == message.from_id:
            kwargs['keyboard'] = Keyboard().add(Text('🛡 Моя броня'),color=KeyboardButtonColor.PRIMARY).row().add(Text('⬅️ Профиль'),color=KeyboardButtonColor.SECONDARY).get_json()
        await message.answer(format_health(character,await get_health(character[0],now),now),**kwargs)

    @bot.on.message(text=['/здоровье <args>','/урон <args>','/броня <args>','/сценастарт <args>','/сценаконец <args>'])
    async def health_admin(message, args=None):
        if message.peer_id != admin_chat:
            await message.answer('Команда доступна только администрации в административном чате.')
            return
        command = message.text.split()[0]
        try:
            numbers = [int(v) for v in (args or '').split()]
            if command=='/урон' and len(numbers)==2:
                action, ids, values = 'damage',numbers[:1],numbers[1:]
            elif command=='/здоровье' and len(numbers)==2:
                action, ids, values = 'hp',numbers[:1],numbers[1:]
            elif command=='/броня' and len(numbers)==3:
                action, ids, values = 'armor',numbers[:1],numbers[1:]
            elif command=='/сценастарт' and 1 <= len(numbers) <= 30:
                action, ids, values = 'start',list(dict.fromkeys(numbers)),[]
            elif command=='/сценаконец' and len(numbers)==1:
                action, ids, values = 'end',numbers,[]
            else:
                raise ValueError
        except ValueError:
            await message.answer('Форматы:\n/урон ID сумма\n/здоровье ID HP\n/броня ID текущее максимум\n/сценастарт ID [ID ...]\n/сценаконец ID участника')
            return
        ok, text = await admin_health_action(message.from_id,action,ids,values,int(time.time()))
        await message.answer(('✅ ' if ok else '⛔ ')+text)
