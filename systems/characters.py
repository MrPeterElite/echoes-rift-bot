from systems.utils import format_status
def register_characters_handlers(bot, deps):
    format_status = deps["format_status"]
    main_menu = deps["main_menu"]
    format_career = deps["format_career"]
    get_user = deps["get_user"]
    create_user = deps["create_user"]
    quenta_menu = deps["quenta_menu"]
    sci_line = deps["sci_line"]
    get_character_by_user = deps["get_character_by_user"]
    drafts = deps["drafts"]
    faction_keyboard = deps["faction_keyboard"]
    FACTION_ARTS = deps["FACTION_ARTS"]
    FACTION_DESCRIPTIONS = deps["FACTION_DESCRIPTIONS"]
    reset_user = deps["reset_user"]
    archive_users = deps["archive_users"]
    get_approved_characters = deps["get_approved_characters"]
    get_vk_name = deps["get_vk_name"]
    done_arts_keyboard = deps["done_arts_keyboard"]
    get_photo_attachment = deps["get_photo_attachment"]
    create_character = deps["create_character"]
    get_character_by_id = deps["get_character_by_id"]
    Keyboard = deps["Keyboard"]
    KeyboardButtonColor = deps["KeyboardButtonColor"]
    Text = deps["Text"]
    ADMIN_CHAT_ID = deps["ADMIN_CHAT_ID"]
    format_character = deps["format_character"]
    stabilize_attachments = deps["stabilize_attachments"]

    @bot.on.message(text="📜 Квенты")
    async def quenta_menu_handler(message):
        await message.answer(
            "◢ АРХИВНЫЙ ТЕРМИНАЛ ◣\n"
            f"{sci_line()}\n\n"
            "📜 Здесь можно создать, удалить или просмотреть квенты.\n\n"
            "Выберите действие.",
            keyboard=quenta_menu.get_json()
        )


    @bot.on.message(text="👤 Профиль")
    async def profile_handler(message):
        await create_user(message.from_id)

        user = await get_user(message.from_id)
        character = await get_character_by_user(message.from_id)

        if not character:
            await message.answer(
                "◢ ПРОФИЛЬ НЕ АКТИВИРОВАН ◣\n"
                f"{sci_line()}\n\n"
                "Персонаж не найден.\n"
                "Создайте квенту для допуска к системе.",
                keyboard=main_menu.get_json()
            )
            return

        player_name = await get_vk_name(message.from_id)

        await message.answer(
            f"◢ ИДЕНТИФИКАЦИОННЫЙ ПРОФИЛЬ ◣\n"
            f"{sci_line()}\n\n"
            f"👤 Игрок: {player_name}\n"
            f"🧬 Персонаж: {character[2]}\n"
            f"🏛 Фракция: {character[5]}\n"
            f"📌 Статус: {format_status(character[10])}\n\n"
            f"{format_career(character)}\n\n"
            f"💳 Баланс: {user[1]} CR\n"
            f"⭐ Опыт: {user[2]}\n"
            f"📈 Уровень: {user[3]}\n\n"
            f"{sci_line()}",
            keyboard=main_menu.get_json()
        )








    @bot.on.message(text="📜 Создать квенту")
    async def create_form_handler(message):
        old_character = await get_character_by_user(message.from_id)

        if old_character and old_character[10] in ["pending", "approved"]:
            await message.answer(
                "⚠️ ДОСЬЕ УЖЕ СУЩЕСТВУЕТ\n\n"
                "Чтобы создать новую квенту, сначала удалите текущего персонажа.",
                keyboard=quenta_menu.get_json()
            )
            return

        drafts[message.from_id] = {
            "step": "name",
            "user_id": message.from_id,
            "arts": []
        }

        await message.answer(
            "◢ СОЗДАНИЕ КВЕНТЫ ◣\n"
            f"{sci_line()}\n\n"
            "Шаг 1/8\n"
            "Введите имя персонажа."
        )


    @bot.on.message(text="🗑 Удалить персонажа")
    async def delete_character_handler(message):
        await reset_user(message.from_id)
        drafts.pop(message.from_id, None)
        archive_users.discard(message.from_id)

        await message.answer(
            "🔴 ПЕРСОНАЖ УДАЛЁН\n"
            f"{sci_line()}\n\n"
            "Досье очищено.\n"
            "Экономика сброшена.\n"
            "Баланс восстановлен до 1500 CR.\n\n"
            "Вы можете создать новую квенту.",
            keyboard=quenta_menu.get_json()
        )


    @bot.on.message(text="📚 Архив квент")
    async def archive_handler(message):
        characters = await get_approved_characters()

        if not characters:
            await message.answer(
                "◢ АРХИВ ПУСТ ◣\n\n"
                "Пока нет одобренных квент.",
                keyboard=quenta_menu.get_json()
            )
            return

        archive_users.add(message.from_id)

        text = "◢ АРХИВ КВЕНТ ◣\n━━━━━━━━━━━━━━━━━━━━\n\n"

        for character in characters:
            player_name = await get_vk_name(character[1])
            text += (
                f"#{character[0]} — {character[2]}\n"
                f"👤 Игрок: {player_name}\n"
                f"🏛 {character[5]}\n\n"
            )

        text += (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Чтобы открыть квенту, напишите её номер.\n"
            "Например: 1"
        )

        await message.answer(text, keyboard=quenta_menu.get_json())


    @bot.on.message(text=[
        "🛡️ ЗЕМНАЯ ДИРЕКТОРИЯ",
        "⚙️ HELIOS DYNAMICS",
        "🕯️ ОРДЕН ЗАВЕСЫ",
        "🔥 КУЛЬТ ПЕПЕЛЬНОГО ОТКРОВЕНИЯ",
        "🚫 Без фракции"
    ])
    async def faction_selected_handler(message):
        draft = drafts.get(message.from_id)

        if not draft or draft["step"] != "faction":
            return

        draft["faction"] = message.text
        draft["step"] = "biology"

        art = FACTION_ARTS.get(message.text)
        desc = FACTION_DESCRIPTIONS.get(message.text, "")

        if art:
            stable_art = await stabilize_attachments(bot, art, message.peer_id)
            await message.answer(
                f"{message.text}\n\n{desc}",
                attachment=stable_art or art
            )
        else:
            await message.answer(
                f"{message.text}\n\n{desc}"
            )

        await message.answer(
            "Шаг 5/8\n"
            "Опишите биологию персонажа.\n\n"
            "Например: человек, мутант, синтетик, изменённый Разломом."
        )


    @bot.on.message(text="🔄 Начать заново")
    async def restart_form_handler(message):
        drafts.pop(message.from_id, None)

        await message.answer(
            "🔄 СОЗДАНИЕ КВЕНТЫ СБРОШЕНО\n\n"
            "Нажмите «📜 Создать квенту», чтобы начать заново.",
            keyboard=quenta_menu.get_json()
        )


    @bot.on.message(text="✅ Готово")
    async def finish_arts_handler(message):
        draft = drafts.get(message.from_id)

        if not draft or draft["step"] != "arts":
            return

        if len(draft["arts"]) == 0:
            await message.answer("Нужно прикрепить хотя бы один арт персонажа.")
            return

        stable_arts = []
        for art in draft["arts"]:
            stable_art = await stabilize_attachments(bot, art, message.peer_id)
            stable_arts.append(stable_art or art)
        draft["arts"] = stable_arts

        character_id = await create_character(draft)
        character = await get_character_by_id(character_id)

        admin_keyboard = (
            Keyboard(one_time=False)
            .add(Text(f"✅ Одобрить #{character_id}"), color=KeyboardButtonColor.POSITIVE)
            .add(Text(f"❌ Отклонить #{character_id}"), color=KeyboardButtonColor.NEGATIVE)
        )

        player_name = await get_vk_name(message.from_id)
        vk_link = f"https://vk.com/id{message.from_id}"

        await bot.api.messages.send(
            peer_id=ADMIN_CHAT_ID,
            random_id=0,
            message=(
                "📡 НОВАЯ КВЕНТА ОБНАРУЖЕНА\n"
                f"{sci_line()}\n\n"
                f"{format_character(character)}\n\n"
                f"👤 Игрок: {player_name}\n"
                f"🔗 Профиль игрока:\n{vk_link}"
            ),
            attachment=",".join(draft["arts"]),
            keyboard=admin_keyboard.get_json()
        )

        drafts.pop(message.from_id, None)

        await message.answer(
            "⏳ КВЕНТА ОТПРАВЛЕНА НА ВЕРИФИКАЦИЮ\n"
            f"{sci_line()}\n\n"
            "Ожидайте решения администрации.\n"
            "До одобрения персонаж неактивен.",
            keyboard=quenta_menu.get_json()
        )

