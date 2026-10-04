import time


def register_economy_handlers(bot, deps):
    Keyboard = deps["Keyboard"]
    KeyboardButtonColor = deps["KeyboardButtonColor"]
    Text = deps["Text"]
    get_top_richest = deps["get_top_richest"]
    sci_line = deps["sci_line"]
    get_character_by_user = deps["get_character_by_user"]
    get_character_by_id = deps["get_character_by_id"]
    create_user = deps["create_user"]
    transfer_balance = deps["transfer_balance"]
    get_user = deps["get_user"]
    redeem_promo_code = deps["redeem_promo_code"]

    sessions = {}

    finance_menu = (
        Keyboard(one_time=False)
        .add(Text("💰 Мой баланс"), color=KeyboardButtonColor.PRIMARY)
        .add(Text("💸 Перевести CR"), color=KeyboardButtonColor.POSITIVE)
        .row()
        .add(Text("🎁 Промокод"), color=KeyboardButtonColor.PRIMARY)
        .add(Text("🏆 Богачи"), color=KeyboardButtonColor.SECONDARY)
        .row()
        .add(Text("⬅️ Назад"), color=KeyboardButtonColor.SECONDARY)
    )

    confirm_transfer_menu = (
        Keyboard(one_time=True)
        .add(Text("✅ Подтвердить перевод"), color=KeyboardButtonColor.POSITIVE)
        .add(Text("❌ Отменить перевод"), color=KeyboardButtonColor.NEGATIVE)
    )

    async def require_private(message):
        if message.peer_id >= 2_000_000_000:
            await message.answer("💳 Финансовый терминал доступен в личных сообщениях бота.")
            return False
        return True

    async def require_character(message):
        character = await get_character_by_user(message.from_id)
        if not character:
            await message.answer("Персонаж не найден.")
            return None
        if character[10] != "approved":
            await message.answer("Финансовые операции доступны после одобрения квенты.")
            return None
        await create_user(message.from_id)
        return character

    async def show_finance(message):
        if not await require_private(message):
            return
        character = await require_character(message)
        if not character:
            return
        user = await get_user(message.from_id)
        sessions.pop(message.from_id, None)
        await message.answer(
            "◢ ФИНАНСОВЫЙ ТЕРМИНАЛ ◣\n"
            f"{sci_line()}\n\n"
            f"👤 {character[2]}\n"
            f"💳 Баланс: {user[1]} CR\n\n"
            "Выберите операцию.",
            keyboard=finance_menu.get_json(),
        )

    async def show_richest(message):
        top = await get_top_richest(10)
        if not top:
            await message.answer(
                "◢ РЕЙТИНГ СОСТОЯНИЙ ◣\n"
                f"{sci_line()}\n\n"
                "Пока нет одобренных персонажей в рейтинге.",
                keyboard=finance_menu.get_json(),
            )
            return
        text = "◢ РЕЙТИНГ СОСТОЯНИЙ ◣\n" + sci_line() + "\n\n"
        for index, row in enumerate(top, start=1):
            user_id, balance, character_id, character_name = row
            name = character_name or f"id{user_id}"
            text += f"{index}. #{character_id} — {name}: {balance} CR\n"
        await message.answer(text, keyboard=finance_menu.get_json())

    async def perform_transfer(message, receiver_character, amount):
        sender_character = await require_character(message)
        if not sender_character:
            return False
        if not receiver_character or receiver_character[10] != "approved":
            await message.answer("Получатель должен иметь одобренную квенту.")
            return False
        if receiver_character[1] == message.from_id:
            await message.answer("Нельзя перевести кредиты самому себе.")
            return False
        await create_user(receiver_character[1])
        ok, reason = await transfer_balance(message.from_id, receiver_character[1], amount)
        if not ok:
            errors = {
                "not_enough_money": "Недостаточно средств для перевода.",
                "invalid_amount": "Сумма перевода должна быть больше 0.",
                "same_user": "Нельзя перевести кредиты самому себе.",
                "sender_not_found": "Ваш финансовый профиль не найден.",
                "receiver_not_found": "Финансовый профиль получателя не найден.",
            }
            await message.answer(errors.get(reason, "Перевод не выполнен."))
            return False
        sender_user = await get_user(message.from_id)
        receiver_user = await get_user(receiver_character[1])
        await message.answer(
            "🟢 ПЕРЕВОД ВЫПОЛНЕН\n"
            f"{sci_line()}\n\n"
            f"👤 Получатель: #{receiver_character[0]} — {receiver_character[2]}\n"
            f"💳 Сумма: {amount} CR\n"
            f"💰 Ваш баланс: {sender_user[1]} CR",
            keyboard=finance_menu.get_json(),
        )
        try:
            await bot.api.messages.send(
                peer_id=receiver_character[1], random_id=0,
                message=(
                    "💸 ВХОДЯЩИЙ ПЕРЕВОД\n"
                    f"{sci_line()}\n\n"
                    f"👤 Отправитель: #{sender_character[0]} — {sender_character[2]}\n"
                    f"💳 Получено: {amount} CR\n"
                    f"💰 Ваш баланс: {receiver_user[1]} CR"
                )
            )
        except Exception:
            pass
        return True

    async def activate_promo(message, code):
        character = await require_character(message)
        if not character:
            return
        ok, result, rewards = await redeem_promo_code(
            code, message.from_id, character[0], int(time.time())
        )
        if not ok:
            errors = {
                "not_found": "Промокод не найден.",
                "inactive": "Этот промокод отключён.",
                "expired": "Срок действия промокода истёк.",
                "limit": "Лимит активаций этого промокода исчерпан.",
                "already_used": "Вы уже активировали этот промокод.",
                "no_rewards": "Промокод настроен некорректно: награды отсутствуют.",
                "character_invalid": "Для активации нужна ваша действующая одобренная квента.",
                "in_combat": "Промокод содержит боевые предметы. Активируйте его после завершения боевой сцены.",
            }
            await message.answer("❌ " + errors.get(result, "Промокод не активирован."), keyboard=finance_menu.get_json())
            return
        lines = [f"🎁 ПРОМОКОД {result} АКТИВИРОВАН", sci_line(), "", "Получено:"]
        for reward_type, reward_key, item_name, item_category, amount in rewards:
            if reward_type == "currency":
                lines.append(f"💳 +{amount} CR")
            else:
                lines.append(f"🎒 {item_name} ×{amount}")
        user = await get_user(message.from_id)
        lines += ["", f"💰 Баланс: {user[1]} CR"]
        await message.answer("\n".join(lines), keyboard=finance_menu.get_json())

    @bot.on.message(text="💳 Финансы")
    async def finance_handler(message):
        await show_finance(message)

    @bot.on.message(text="💰 Мой баланс")
    async def balance_button_handler(message):
        if not await require_private(message):
            return
        character = await require_character(message)
        if not character:
            return
        user = await get_user(message.from_id)
        await message.answer(
            f"💰 ВАШ БАЛАНС\n{sci_line()}\n\n🧬 #{character[0]} — {character[2]}\n💳 {user[1]} CR",
            keyboard=finance_menu.get_json(),
        )

    @bot.on.message(text="💸 Перевести CR")
    async def transfer_button_start(message):
        if not await require_private(message):
            return
        if not await require_character(message):
            return
        sessions[message.from_id] = {"mode": "transfer_target"}
        await message.answer("Введите ID квенты получателя.")

    @bot.on.message(text="✅ Подтвердить перевод")
    async def transfer_confirm_button(message):
        session = sessions.pop(message.from_id, {})
        if session.get("mode") != "transfer_confirm":
            await message.answer("Нет перевода, ожидающего подтверждения.", keyboard=finance_menu.get_json())
            return
        receiver = await get_character_by_id(session["target_id"])
        amount = session["amount"]
        sessions.pop(message.from_id, None)
        await perform_transfer(message, receiver, amount)

    @bot.on.message(text="❌ Отменить перевод")
    async def transfer_cancel_button(message):
        sessions.pop(message.from_id, None)
        await message.answer("Перевод отменён.", keyboard=finance_menu.get_json())

    @bot.on.message(text="🎁 Промокод")
    async def promo_button_start(message):
        if not await require_private(message):
            return
        if not await require_character(message):
            return
        sessions[message.from_id] = {"mode": "promo"}
        await message.answer("Введите промокод одним сообщением.")

    @bot.on.message(text="🏆 Богачи")
    async def richest_button_handler(message):
        await show_richest(message)

    @bot.on.message(text="/богачи")
    async def richest_handler(message):
        await show_richest(message)

    @bot.on.message(text="/перевести <character_id> <amount>")
    async def transfer_handler(message, character_id=None, amount=None):
        try:
            character_id = int(character_id)
            amount = int(amount)
        except (TypeError, ValueError):
            await message.answer("Использование:\n/перевести ID сумма\n\nПример:\n/перевести 7 500")
            return
        if amount <= 0:
            await message.answer("Сумма перевода должна быть больше 0.")
            return
        receiver = await get_character_by_id(character_id)
        await perform_transfer(message, receiver, amount)

    @bot.on.message(text="/промокод <code>")
    async def promo_command_handler(message, code=None):
        await activate_promo(message, (code or "").strip())

    async def handle_economy_message(message):
        session = sessions.get(message.from_id)
        if not session:
            return False
        if message.peer_id >= 2_000_000_000:
            return False
        text = (message.text or "").strip()
        mode = session.get("mode")

        if mode == "transfer_target":
            try:
                target_id = int(text)
            except ValueError:
                await message.answer("ID квенты должен быть числом.")
                return True
            receiver = await get_character_by_id(target_id)
            if not receiver or receiver[10] != "approved":
                await message.answer("Одобренная квента с таким ID не найдена.")
                return True
            if receiver[1] == message.from_id:
                await message.answer("Нельзя переводить деньги самому себе.")
                return True
            session["target_id"] = target_id
            session["mode"] = "transfer_amount"
            await message.answer(f"Получатель: #{receiver[0]} — {receiver[2]}\nВведите сумму CR.")
            return True

        if mode == "transfer_amount":
            try:
                amount = int(text)
                if amount <= 0:
                    raise ValueError
            except ValueError:
                await message.answer("Введите положительную сумму целым числом.")
                return True
            await create_user(message.from_id)
            user = await get_user(message.from_id)
            if user[1] < amount:
                await message.answer(f"Недостаточно средств. Ваш баланс: {user[1]} CR")
                return True
            receiver = await get_character_by_id(session["target_id"])
            session["amount"] = amount
            session["mode"] = "transfer_confirm"
            await message.answer(
                "💸 ПОДТВЕРЖДЕНИЕ ПЕРЕВОДА\n"
                f"{sci_line()}\n\n"
                f"Получатель: #{receiver[0]} — {receiver[2]}\n"
                f"Сумма: {amount} CR\n\n"
                "Проверьте данные перед отправкой.",
                keyboard=confirm_transfer_menu.get_json(),
            )
            return True

        if mode == "promo":
            sessions.pop(message.from_id, None)
            await activate_promo(message, text)
            return True

        return False

    return {
        "finance_menu": finance_menu,
        "sessions": sessions,
        "handle_economy_message": handle_economy_message,
        "activate_promo": activate_promo,
    }
