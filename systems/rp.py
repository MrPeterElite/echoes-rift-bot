import random


async def handle_rp_command(message, bot, deps):
    text = message.text or ""

    commands = ["/me", "/do", "/say", "/try"]
    command = None

    for item in commands:
        if text == item or text.startswith(item + " "):
            command = item
            break

    if not command:
        return False

    content = text[len(command):].strip()

    if not content:
        usage = {
            "/me": "Использование: /me действие",
            "/do": "Использование: /do описание сцены",
            "/say": "Использование: /say фраза",
            "/try": "Использование: /try действие",
        }
        await message.answer(usage[command])
        return True

    get_character_by_user = deps["get_character_by_user"]
    get_location_by_peer = deps["get_location_by_peer"]
    get_character_location = deps["get_character_location"]
    delete_message_from_chat = deps["delete_message_from_chat"]
    sci_line = deps["sci_line"]

    character = await get_character_by_user(message.from_id)

    if not character:
        await message.answer("Персонаж не найден.")
        return True

    if character[10] != "approved":
        await message.answer("RP-команды доступны только после одобрения квенты.")
        return True

    chat_location = await get_location_by_peer(message.peer_id)

    if not chat_location:
        await message.answer("RP-команды работают только в локационных чатах.")
        return True

    current_location = await get_character_location(character[0])

    if current_location and current_location[0] != chat_location[0]:
        await delete_message_from_chat(message)

        try:
            await bot.api.messages.send(
                peer_id=message.from_id,
                random_id=0,
                message=(
                    "⛔ ВЫ НЕ НАХОДИТЕСЬ В ЭТОЙ ЛОКАЦИИ\n"
                    f"{sci_line()}\n\n"
                    f"Ваша текущая локация: {current_location[1]}\n"
                    f"Этот чат: {chat_location[1]}\n\n"
                    f"Ссылка на вашу локацию:\n{current_location[3]}"
                )
            )
        except Exception:
            pass

        return True

    await delete_message_from_chat(message)

    if command == "/me":
        await message.answer(
            f"📍 {chat_location[1]}\n"
            f"{sci_line()}\n\n"
            f"✦ {character[2]} {content}"
        )
        return True

    if command == "/do":
        await message.answer(
            f"📍 {chat_location[1]}\n"
            f"{sci_line()}\n\n"
            f"◇ {content}"
        )
        return True

    if command == "/say":
        await message.answer(
            f"📍 {chat_location[1]}\n"
            f"{sci_line()}\n\n"
            f"{character[2]}: «{content}»"
        )
        return True

    if command == "/try":
        roll = random.randint(1, 100)
        success = roll >= 50

        if success:
            result_title = "🟢 УСПЕХ"
            result_text = f"{character[2]} успешно выполняет действие: {content}"
        else:
            result_title = "🔴 ПРОВАЛ"
            result_text = f"{character[2]} не смог выполнить действие: {content}"

        await message.answer(
            f"📍 {chat_location[1]}\n"
            f"{sci_line()}\n\n"
            f"{result_title}\n"
            f"🎲 Бросок: {roll}/100\n\n"
            f"{result_text}"
        )
        return True

    return False
