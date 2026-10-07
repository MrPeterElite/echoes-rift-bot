import time
import json
from database import get_character_archive_page
from database import save_character_draft, load_character_draft, delete_character_draft
from systems.navigation import CHARACTER_MENU
from systems.onboarding import entry_keyboard

def register_characters_handlers(bot, deps):
    runtime = {}
    format_status = deps["format_status"]
    format_career = deps["format_career"]
    get_user = deps["get_user"]
    create_user = deps["create_user"]
    quenta_menu = deps["quenta_menu"]
    sci_line = deps["sci_line"]
    get_character_by_user = deps["get_character_by_user"]
    faction_keyboard = deps["faction_keyboard"]
    FACTION_ARTS = deps["FACTION_ARTS"]
    FACTION_DESCRIPTIONS = deps["FACTION_DESCRIPTIONS"]
    reset_user = deps["reset_user"]
    archive_users = deps["archive_users"]
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

    deletion_requests = {}

    async def require_private(message):
        if message.peer_id != message.from_id:
            await message.answer("Создание и удаление персонажа доступны в личных сообщениях бота.")
            return False
        return True

    async def prompt_draft(message, draft):
        prompts = {
            "name": "Шаг 1/8: введите имя персонажа.",
            "age": "Шаг 2/8: введите возраст персонажа.",
            "gender": "Шаг 3/8: введите пол персонажа.",
            "faction": "Шаг 4/8: выберите фракцию.",
            "biology": "Шаг 5/8: опишите биологию персонажа.",
            "personality": "Шаг 6/8: опишите характер персонажа.",
            "history": "Шаг 7/8: напишите историю персонажа.",
            "arts": f"Шаг 8/8: прикрепите арты. Сохранено: {len(draft.get('arts', []))}/3. Затем нажмите «✅ Готово».",
        }
        keyboard = faction_keyboard if draft['step'] == 'faction' else done_arts_keyboard
        await message.answer(prompts[draft['step']], keyboard=keyboard.get_json())

    async def pause_draft(message):
        deletion_requests.pop(message.from_id, None)
        if message.peer_id != message.from_id:
            return
        draft = await load_character_draft(message.from_id)
        if draft:
            draft['active'] = False
            await save_character_draft(message.from_id, draft)

    @bot.on.message(text=["📜 Управление персонажем","📜 Квенты"])
    async def quenta_menu_handler(message):
        await message.answer(
            "◢ АРХИВНЫЙ ТЕРМИНАЛ ◣\n"
            f"{sci_line()}\n\n"
            "📜 Здесь можно создать, удалить или просмотреть персонажа.\n\n"
            "Выберите действие.",
            keyboard=quenta_menu.get_json()
        )


    @bot.on.message(text=["👤 Профиль", "⬅️ Профиль"])
    async def profile_handler(message):
        await create_user(message.from_id)

        user = await get_user(message.from_id)
        character = await get_character_by_user(message.from_id)

        if not character:
            await message.answer(
                "◢ ПРОФИЛЬ НЕ АКТИВИРОВАН ◣\n"
                f"{sci_line()}\n\n"
                "Персонаж не найден.\n"
                "Создайте персонажа для допуска к системе.",
                keyboard=CHARACTER_MENU.get_json()
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
            keyboard=CHARACTER_MENU.get_json()
        )








    @bot.on.message(text=["👤 Создать персонажа","✏️ Продолжить создание","📜 Создать квенту"])
    async def create_form_handler(message):
        if not await require_private(message):
            return
        old_character = await get_character_by_user(message.from_id)

        if old_character:
            await message.answer(
                "⚠️ ДОСЬЕ УЖЕ СУЩЕСТВУЕТ\n\n"
                "Чтобы создать нового персонажа, сначала удалите текущего персонажа.",
                keyboard=quenta_menu.get_json()
            )
            return

        draft = await load_character_draft(message.from_id)
        if not draft:
            draft = {"step": "name", "user_id": message.from_id, "arts": []}
        draft['active'] = True
        await save_character_draft(message.from_id, draft)
        await prompt_draft(message, draft)


    @bot.on.message(text="🗑 Удалить персонажа")
    async def delete_character_handler(message):
        if not await require_private(message):
            return
        character = await get_character_by_user(message.from_id)
        if not character:
            await message.answer("Персонажа нет. Черновик можно очистить кнопкой «🔄 Начать заново».")
            return
        deletion_requests[message.from_id] = (character[0], time.monotonic() + 300)
        keyboard = (Keyboard(one_time=True)
                    .add(Text("🗑 Подтвердить удаление персонажа"), color=KeyboardButtonColor.NEGATIVE)
                    .row().add(Text("↩ Отменить удаление персонажа"), color=KeyboardButtonColor.SECONDARY))
        await message.answer(
            f"Удалить персонажа #{character[0]} — {character[2]}?\n"
            "Персонаж, вещи, жильё, задания и опыт будут удалены. Баланс вернётся к 1500 CR. "
            "Подтверждение действует 5 минут.",
            keyboard=keyboard.get_json())

    @bot.on.message(text="🗑 Подтвердить удаление персонажа")
    async def confirm_delete_character(message):
        if not await require_private(message):
            return
        request = deletion_requests.pop(message.from_id, None)
        if not request or time.monotonic() > request[1]:
            await message.answer("Подтверждение устарело. Откройте удаление персонажа заново.", keyboard=await entry_keyboard(message.from_id))
            return
        if not await reset_user(message.from_id, expected_character_id=request[0]):
            await message.answer("Персонаж уже изменился. Удаление отменено.", keyboard=await entry_keyboard(message.from_id))
            return
        archive_users.discard(message.from_id)
        await message.answer("Персонаж удалён. Баланс восстановлен до 1500 CR, опыт сброшен. Можно создать нового персонажа.", keyboard=await entry_keyboard(message.from_id))

    @bot.on.message(text="↩ Отменить удаление персонажа")
    async def cancel_delete_character(message):
        deletion_requests.pop(message.from_id, None)
        await message.answer("Удаление отменено.", keyboard=await entry_keyboard(message.from_id))


    @bot.on.message(text=["📚 Персонажи","📚 Архив квент"])
    async def archive_handler(message):
        await show_archive_page(message,0)

    @bot.on.message(text=["◀ Персонажи", "Персонажи ▶"])
    async def archive_page_handler(message):
        try:
            payload=message.payload or {}
            if isinstance(payload,str): payload=json.loads(payload)
            if not isinstance(payload,dict) or payload.get('archive_owner')!=message.from_id or payload.get('archive_peer')!=message.peer_id:
                await message.answer('Откройте свой список через «📚 Персонажи».'); return
            page=payload['archive_page']
            if type(page) is not int: raise ValueError
        except (ValueError,TypeError,KeyError):
            await message.answer('Откройте архив заново через «📚 Персонажи».'); return
        await show_archive_page(message,page)

    async def show_archive_page(message,page):
        if message.peer_id == ADMIN_CHAT_ID:
            from database import get_bot_admin
            admin = await get_bot_admin(message.from_id)
            if not admin or not admin[2]:
                await message.answer('Архив в этой беседе доступен администрации.'); return
            if runtime.get('admin_archive_open'): runtime['admin_archive_open'](message.from_id)
        characters,page,pages,total = await get_character_archive_page(page)

        if not characters:
            await message.answer(
                "◢ АРХИВ ПУСТ ◣\n\n"
                "Пока нет одобренных персонажей.",
                keyboard=(Keyboard().add(Text('⬅️ Админ-панель')).get_json() if message.peer_id == ADMIN_CHAT_ID else quenta_menu.get_json())
            )
            return

        archive_users.add(message.from_id)

        text = f"◢ АРХИВ ПЕРСОНАЖЕЙ ◣\nСтраница {page+1}/{pages} · Всего: {total}\n━━━━━━━━━━━━━━━━━━━━\n\n"

        for character in characters:
            try: player_name = await get_vk_name(character[1])
            except Exception: player_name = f'VK ID {character[1]}'
            text += (
                f"#{character[0]} — {character[2][:100]}\n"
                f"👤 Игрок: {str(player_name)[:80]}\n"
                f"🏛 {(character[5] or 'Без фракции')[:80]}\n\n"
            )

        text += (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Чтобы открыть персонажа, напишите его номер.\n"
            "Например: 1"
        )

        kb=Keyboard(inline=True)
        if page:
            kb.add(Text('◀ Персонажи',payload={'archive_owner':message.from_id,'archive_peer':message.peer_id,'archive_page':page-1}))
        if page+1<pages:
            kb.add(Text('Персонажи ▶',payload={'archive_owner':message.from_id,'archive_peer':message.peer_id,'archive_page':page+1}))
        if page or page+1<pages: kb.row()
        kb.add(Text('⬅️ Админ-панель' if message.peer_id == ADMIN_CHAT_ID else '📜 Управление персонажем'))
        await message.answer(text, keyboard=kb.get_json())

    async def open_admin_archive_character(message,character_id):
        from database import get_bot_admin
        if message.peer_id != ADMIN_CHAT_ID: return
        admin=await get_bot_admin(message.from_id)
        if not admin or not admin[2]: return
        character=await get_character_by_id(character_id)
        if not character or character[10]!='approved':
            await message.answer('Этого персонажа нет в открытом архиве.'); return
        try: player_name=await get_vk_name(character[1])
        except Exception: player_name=f'VK ID {character[1]}'
        kb=Keyboard().add(Text('📚 Архив персонажей')).row().add(Text('⬅️ Админ-панель'))
        await message.answer(f"{format_character(character)}\n\n👤 Игрок: {player_name}\n🔗 https://vk.com/id{character[1]}",attachment=character[9] or None,keyboard=kb.get_json())


    @bot.on.message(text=[
        "🛡️ ЗЕМНАЯ ДИРЕКТОРИЯ",
        "⚙️ HELIOS DYNAMICS",
        "🕯️ ОРДЕН ЗАВЕСЫ",
        "🔥 КУЛЬТ ПЕПЕЛЬНОГО ОТКРОВЕНИЯ",
        "🚫 Без фракции"
    ])
    async def faction_selected_handler(message):
        if not await require_private(message):
            return
        draft = await load_character_draft(message.from_id)

        if not draft or not draft.get("active", True) or draft["step"] != "faction":
            return

        draft["faction"] = message.text
        draft["step"] = "biology"
        await save_character_draft(message.from_id, draft)

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
        if not await require_private(message):
            return
        await delete_character_draft(message.from_id)

        await message.answer(
            "🔄 СОЗДАНИЕ ПЕРСОНАЖА СБРОШЕНО\n\n"
            "Нажмите «👤 Создать персонажа», чтобы начать заново.",
            keyboard=await entry_keyboard(message.from_id)
        )


    @bot.on.message(text="✅ Готово")
    async def finish_arts_handler(message):
        if not await require_private(message):
            return
        draft = await load_character_draft(message.from_id)

        if not draft or not draft.get("active", True) or draft["step"] != "arts":
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

        try:
            await bot.api.messages.send(
                peer_id=ADMIN_CHAT_ID,
                random_id=0,
                message=(
                    "📡 НОВЫЙ ПЕРСОНАЖ НА ПРОВЕРКЕ\n"
                    f"{sci_line()}\n\n"
                    f"{format_character(character)}\n\n"
                    f"👤 Игрок: {player_name}\n"
                    f"🔗 Профиль игрока:\n{vk_link}"
                ),
                attachment=",".join(draft["arts"]),
                keyboard=admin_keyboard.get_json()
            )
        except Exception:
            # The saved quenta is still visible in /админ -> pending characters.
            await message.answer("Персонаж сохранён. Уведомление администрации не доставлено; он доступен в очереди проверки.")


        await delete_character_draft(message.from_id)

        await message.answer(
            "⏳ ПЕРСОНАЖ ОТПРАВЛЕН НА ВЕРИФИКАЦИЮ\n"
            f"{sci_line()}\n\n"
            "Ожидайте решения администрации.\n"
            "До одобрения персонаж неактивен.",
            keyboard=await entry_keyboard(message.from_id)
        )


    async def handle_character_message(message):
        text = message.text or ""
        user_id = message.from_id
        if message.peer_id != message.from_id or text.startswith('/'):
            return
        draft = await load_character_draft(user_id)
    
        if not draft or not draft.get("active", True):
            return
    
        step = draft["step"]
    
        if step == "name":
            draft["name"] = text
            draft["step"] = "age"
            await save_character_draft(user_id, draft)
            await message.answer("Шаг 2/8\nВведите возраст персонажа.")
            return
    
        if step == "age":
            draft["age"] = text
            draft["step"] = "gender"
            await save_character_draft(user_id, draft)
            await message.answer("Шаг 3/8\nВведите пол персонажа.")
            return
    
        if step == "gender":
            draft["gender"] = text
            draft["step"] = "faction"
            await save_character_draft(user_id, draft)
            await message.answer(
                "Шаг 4/8\nВыберите фракцию персонажа.",
                keyboard=faction_keyboard.get_json()
            )
            return
    
        if step == "biology":
            draft["biology"] = text
            draft["step"] = "personality"
            await save_character_draft(user_id, draft)
            await message.answer("Шаг 6/8\nОпишите характер персонажа.")
            return
    
        if step == "personality":
            draft["personality"] = text
            draft["step"] = "history"
            await save_character_draft(user_id, draft)
            await message.answer("Шаг 7/8\nНапишите историю персонажа.")
            return
    
        if step == "history":
            draft["history"] = text
            draft["step"] = "arts"
            await save_character_draft(user_id, draft)
            await message.answer(
                "Шаг 8/8\n"
                "Прикрепите от 1 до 3 артов персонажа.\n\n"
                "Когда закончите — нажмите «✅ Готово».",
                keyboard=done_arts_keyboard.get_json()
            )
            return
    
        if step == "arts":
            attachment = get_photo_attachment(message)
    
            if not attachment:
                await message.answer("Отправьте именно фото/арт.")
                return
    
            if len(draft["arts"]) >= 3:
                await message.answer(
                    "Лимит — 3 арта.\n"
                    "Нажмите «✅ Готово», чтобы отправить персонажа."
                )
                return
    
            draft["arts"].append(attachment)
            await save_character_draft(user_id, draft)
    
            await message.answer(
                f"🖼 Арт принят: {len(draft['arts'])}/3\n\n"
                "Можете отправить ещё или нажать «✅ Готово».",
                keyboard=done_arts_keyboard.get_json()
            )
            return

    runtime.update(handle_message=handle_character_message,pause_draft=pause_draft,create=create_form_handler,show_archive=show_archive_page,open_admin_archive_character=open_admin_archive_character)
    return runtime

