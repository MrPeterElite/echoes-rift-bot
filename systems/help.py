def register_help_handlers(bot, deps):
    get_character_by_user = deps["get_character_by_user"]
    sci_line = deps["sci_line"]

    async def send_help(message):
        character = await get_character_by_user(message.from_id)
        char_line = ""
        if character:
            char_line = f"🧬 Персонаж: {character[2]}\n"
            if character[11] and character[12]:
                char_line += f"💼 Должность: {character[12]}\n"
            char_line += "\n"

        text = (
            "◢ КОМАНДЫ ИГРОКА ◣\n"
            f"{sci_line()}\n\n"
            f"{char_line}"
            "🎭 RP-КОМАНДЫ\n"
            "/me действие — действие персонажа\n"
            "/do описание — описание сцены или окружения\n"
            "/say фраза — реплика персонажа\n"
            "/try действие — попытка действия с броском 1–100\n"
            "/кто здесь — персонажи в текущей локации\n\n"
            "📍 ПЕРЕМЕЩЕНИЕ\n"
            "/гдея — текущая локация\n"
            "/локации — список локаций и их кодов\n"
            "/перейти код — перейти в другую локацию\n\n"
            "🎒 ИНВЕНТАРЬ\n"
            "/инвентарь — список предметов\n"
            "/использовать № — использовать предмет\n"
            "/уничтожитьпредмет № количество — удалить предмет\n"
            "/передатьпредмет ID № количество — передать предмет другому персонажу\n\n"
            "💳 ЭКОНОМИКА\n"
            "/перевести ID сумма — перевести кредиты\n"
            "/богачи — рейтинг состояний\n\n"
            "💼 РАБОТА\n"
            "📌 Задание — получить/посмотреть должностное задание в меню «Карьера»\n"
            "/отчёт текст — отправить отчёт по заданию\n\n"
            "🛒 МАГАЗИН\n"
            "Откройте «🛒 Магазин» в личных сообщениях бота.\n"
            "/купить количество — купить выбранный товар\n\n"
            "ℹ️ /команды или /помощь — открыть эту справку.\n"
            "Административные команды здесь намеренно не отображаются."
        )
        await message.answer(text)

    @bot.on.message(text="/команды")
    async def commands_handler(message):
        await send_help(message)

    @bot.on.message(text="/помощь")
    async def help_handler(message):
        await send_help(message)
