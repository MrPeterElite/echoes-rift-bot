def register_economy_handlers(bot, deps):
    get_top_richest = deps["get_top_richest"]
    sci_line = deps["sci_line"]
    get_character_by_user = deps["get_character_by_user"]
    get_character_by_id = deps["get_character_by_id"]
    create_user = deps["create_user"]
    transfer_balance = deps["transfer_balance"]
    get_user = deps["get_user"]

    @bot.on.message(text="/богачи")
    async def richest_handler(message):
        top = await get_top_richest(10)

        if not top:
            await message.answer(
                "◢ РЕЙТИНГ СОСТОЯНИЙ ◣\n"
                f"{sci_line()}\n\n"
                "Пока нет одобренных персонажей в рейтинге."
            )
            return

        text = "◢ РЕЙТИНГ СОСТОЯНИЙ ◣\n"
        text += f"{sci_line()}\n\n"

        for index, row in enumerate(top, start=1):
            user_id, balance, character_id, character_name = row
            name = character_name or f"id{user_id}"
            text += f"{index}. #{character_id} — {name}: {balance} CR\n"

        await message.answer(text)


    @bot.on.message(text="/перевести <character_id> <amount>")
    async def transfer_handler(message, character_id=None, amount=None):
        try:
            character_id = int(character_id)
            amount = int(amount)
        except (TypeError, ValueError):
            await message.answer(
                "Использование:\n"
                "/перевести ID сумма\n\n"
                "Пример:\n"
                "/перевести 7 500"
            )
            return

        if amount <= 0:
            await message.answer("Сумма перевода должна быть больше 0.")
            return

        sender_character = await get_character_by_user(message.from_id)

        if not sender_character:
            await message.answer("Персонаж не найден.")
            return

        if sender_character[10] != "approved":
            await message.answer("Переводы доступны только после одобрения квенты.")
            return

        receiver_character = await get_character_by_id(character_id)

        if not receiver_character:
            await message.answer("Квента получателя не найдена.")
            return

        if receiver_character[10] != "approved":
            await message.answer("Получатель должен иметь одобренную квенту.")
            return

        if receiver_character[1] == message.from_id:
            await message.answer("Нельзя перевести кредиты самому себе.")
            return

        await create_user(message.from_id)
        await create_user(receiver_character[1])

        ok, reason = await transfer_balance(message.from_id, receiver_character[1], amount)

        if not ok:
            if reason == "not_enough_money":
                await message.answer("Недостаточно средств для перевода.")
            else:
                await message.answer("Перевод не выполнен.")
            return

        sender_user = await get_user(message.from_id)
        receiver_user = await get_user(receiver_character[1])

        await message.answer(
            "🟢 ПЕРЕВОД ВЫПОЛНЕН\n"
            f"{sci_line()}\n\n"
            f"👤 Получатель: #{receiver_character[0]} — {receiver_character[2]}\n"
            f"💳 Сумма: {amount} CR\n"
            f"💰 Ваш баланс: {sender_user[1]} CR"
        )

        try:
            await bot.api.messages.send(
                peer_id=receiver_character[1],
                random_id=0,
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

