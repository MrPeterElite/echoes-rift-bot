def register_locations_handlers(bot, deps):
    get_location_by_peer = deps["get_location_by_peer"]
    get_characters_in_location = deps["get_characters_in_location"]
    get_all_locations = deps["get_all_locations"]
    sci_line = deps["sci_line"]
    get_character_by_user = deps["get_character_by_user"]
    get_character_location = deps["get_character_location"]
    get_location_by_code = deps["get_location_by_code"]
    set_character_location = deps["set_character_location"]
    delete_message_from_chat = deps["delete_message_from_chat"]

    async def send_private(user_id: int, text: str):
        try:
            await bot.api.messages.send(
                peer_id=user_id,
                random_id=0,
                message=text,
            )
            return True
        except Exception:
            return False

    @bot.on.message(text="/локации")
    async def locations_list_handler(message):
        locations = await get_all_locations()
        text = "◢ ЛОКАЦИИ СТАНЦИИ ◣\n"
        text += f"{sci_line()}\n\n"
        for code, name, peer_id, invite_link in locations:
            text += f"{code} - {name}\n"
        text += (
            "\nПереход: /перейти код\n\n"
            "ℹ Переход меняет текущую RP-локацию персонажа. "
            "Бот больше не исключает игроков из бесед."
        )
        await message.answer(text)

    @bot.on.message(text="/гдея")
    async def where_am_i_handler(message):
        character = await get_character_by_user(message.from_id)
        if not character:
            await message.answer("Персонаж не найден.")
            return

        location = await get_character_location(character[0])
        if not location:
            await message.answer("Текущая локация персонажа не определена.")
            return

        await message.answer(
            "◢ ТЕКУЩАЯ ЛОКАЦИЯ ◣\n"
            f"{sci_line()}\n\n"
            f"🧬 Персонаж: {character[2]}\n"
            f"📍 Локация: {location[1]}\n\n"
            f"Вход в беседу:\n{location[3]}"
        )

    @bot.on.message(text="/кто здесь")
    async def who_here_handler(message):
        chat_location = await get_location_by_peer(message.peer_id)

        if not chat_location:
            await message.answer("Эта команда работает только в локационных чатах.")
            return

        character = await get_character_by_user(message.from_id)

        if not character:
            await message.answer("Персонаж не найден.")
            return

        current_location = await get_character_location(character[0])

        if current_location and current_location[0] != chat_location[0]:
            await message.answer(
                "⛔ Вы не находитесь в этой локации.\n"
                f"{sci_line()}\n\n"
                f"Ваша текущая локация: {current_location[1]}\n"
                f"Этот чат: {chat_location[1]}\n\n"
                f"Ссылка на вашу локацию:\n{current_location[3]}"
            )
            return

        characters = await get_characters_in_location(chat_location[0])

        if not characters:
            await message.answer(
                "◢ СКАНЕР ЛОКАЦИИ ◣\n"
                f"{sci_line()}\n\n"
                f"📍 Локация: {chat_location[1]}\n\n"
                "Сейчас здесь никого нет."
            )
            return

        text = "◢ СКАНЕР ЛОКАЦИИ ◣\n"
        text += f"{sci_line()}\n\n"
        text += f"📍 Локация: {chat_location[1]}\n"
        text += f"👥 Персонажей здесь: {len(characters)}\n\n"

        for index, row in enumerate(characters, start=1):
            character_id, name, faction, department, job_title = row
            text += f"{index}. #{character_id} - {name}\n"
            text += f"   🏛 {faction}\n"

            if department and job_title:
                text += f"   💼 {job_title}\n"

            text += "\n"

        await message.answer(text)

    @bot.on.message(text="/перейти <code>")
    async def move_location_handler(message, code: str):
        character = await get_character_by_user(message.from_id)
        if not character:
            await message.answer("Персонаж не найден.")
            return

        if character[10] != "approved":
            await message.answer("Переходы доступны только после одобрения квенты.")
            return

        code = code.lower().strip()
        target = await get_location_by_code(code)

        if not target:
            await message.answer("Такой локации нет. Напишите /локации.")
            return

        current = await get_character_location(character[0])

        # В новой системе беседы не используются как физическая блокировка.
        # Игрок может оставаться участником всех локационных чатов, а его
        # фактическое RP-положение хранится только в character_locations.
        if current and current[0] == target[0]:
            text = (
                "📍 ВЫ УЖЕ ЗДЕСЬ\n"
                f"{sci_line()}\n\n"
                f"Текущая локация: {target[1]}\n\n"
                f"Вход в беседу:\n{target[3]}"
            )
            if not await send_private(message.from_id, text):
                await message.answer(text)
            return

        await set_character_location(character[0], target[0])

        # Если переход написан прямо в локационном чате, убираем техническую
        # команду из RP-ленты. Пользователь при этом НЕ исключается из беседы.
        if await get_location_by_peer(message.peer_id):
            await delete_message_from_chat(message)

        previous_name = current[1] if current else "неизвестно"
        text = (
            "📍 ПЕРЕМЕЩЕНИЕ ВЫПОЛНЕНО\n"
            f"{sci_line()}\n\n"
            f"Откуда: {previous_name}\n"
            f"Куда: {target[1]}\n\n"
            "Бот больше не исключает вас из предыдущих бесед.\n"
            "RP-действия будут приниматься только в вашей текущей локации.\n\n"
            f"Вход в новую локацию:\n{target[3]}"
        )

        if not await send_private(message.from_id, text):
            await message.answer(text)
