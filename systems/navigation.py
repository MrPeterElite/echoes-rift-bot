from vkbottle import Keyboard,Text,KeyboardButtonColor

HOME='🏠 Главное меню'

def menu(rows):
    kb=Keyboard(one_time=False)
    for n,row in enumerate(rows):
        if n:kb.row()
        for label in row:kb.add(Text(label),color=KeyboardButtonColor.PRIMARY if label!=HOME else KeyboardButtonColor.SECONDARY)
    return kb

MAIN_MENU=menu([['👤 Персонаж','🗺 Локации'],['🎒 Снаряжение','💼 Карьера'],['💳 Финансы','💡 Помощь и связь']])
CHARACTER_MENU=menu([['👤 Профиль','❤️ Состояние'],['📜 Управление персонажем','🏛 Фракции'],['🏠 Каюта'],[HOME]])
GEAR_MENU=menu([['🎒 Инвентарь','🛒 Магазин'],['🛡 Моя броня','🔫 Моё оружие'],[HOME]])
SUPPORT_MENU=menu([['📖 Как играть','💡 Связь'],[HOME]])

def register_navigation(bot,pause_draft,clear_sessions):
    @bot.on.message(text=['👤 Персонаж','🎒 Снаряжение','💡 Помощь и связь'])
    async def section_menu(message):
        if message.peer_id!=message.from_id:
            await message.answer('Откройте меню в личных сообщениях бота. Для боя в RP-чате используйте /дуель.');return
        await pause_draft(message);clear_sessions(message.from_id)
        sections={
            '👤 Персонаж':('👤 ПЕРСОНАЖ\nПрофиль, здоровье, персонаж, фракция и каюта.',CHARACTER_MENU),
            '🎒 Снаряжение':('🎒 СНАРЯЖЕНИЕ\nПредметы, магазин, броня и оружие.',GEAR_MENU),
            '💡 Помощь и связь':('💡 ПОМОЩЬ И СВЯЗЬ\nПравила и команды — в «Как играть». Предложения администрации — в «Связь».',SUPPORT_MENU),
        }
        text,kb=sections[message.text];await message.answer(text,keyboard=kb.get_json())
