import time


SUGGESTION_COOLDOWN = 30 * 60


def register_suggestion_handlers(bot, deps):
    Keyboard = deps["Keyboard"]
    KeyboardButtonColor = deps["KeyboardButtonColor"]
    Text = deps["Text"]
    sci_line = deps["sci_line"]
    ADMIN_CHAT_ID = deps["ADMIN_CHAT_ID"]
    get_character_by_user = deps["get_character_by_user"]
    get_photo_attachment = deps["get_photo_attachment"]
    create_suggestion = deps["create_suggestion"]
    get_last_suggestion_time = deps["get_last_suggestion_time"]
    list_suggestions = deps["list_suggestions"]

    sessions = {}

    suggestion_menu = (
        Keyboard(one_time=False)
        .add(Text("💡 Предложить идею"), color=KeyboardButtonColor.POSITIVE)
        .add(Text("📋 Мои предложения"), color=KeyboardButtonColor.PRIMARY)
        .row()
        .add(Text("⬅️ Назад"), color=KeyboardButtonColor.SECONDARY)
    )

    @bot.on.message(text="💡 Связь")
    async def suggestion_main(message):
        if message.peer_id >= 2_000_000_000:
            await message.answer("Связь с администрацией доступна в личных сообщениях бота.")
            return
        sessions.pop(message.from_id, None)
        await message.answer(
            "💡 СВЯЗЬ С АДМИНИСТРАЦИЕЙ\n"
            f"{sci_line()}\n\n"
            "Здесь можно отправить предложение по игре или боту. Это не канал для экстренной модерации.",
            keyboard=suggestion_menu.get_json(),
        )

    @bot.on.message(text="💡 Предложить идею")
    async def suggestion_start(message):
        if message.peer_id >= 2_000_000_000:
            return
        now = int(time.time())
        last = await get_last_suggestion_time(message.from_id)
        if last and now - last < SUGGESTION_COOLDOWN:
            left = SUGGESTION_COOLDOWN - (now - last)
            await message.answer(f"⏳ Новое предложение можно отправить через {left // 60 + 1} мин.")
            return
        sessions[message.from_id] = {"mode": "suggestion_text"}
        await message.answer(
            "Напишите предложение одним сообщением. При необходимости прикрепите одну картинку.\n\n"
            "Минимум 10 символов."
        )

    @bot.on.message(text="📋 Мои предложения")
    async def my_suggestions(message):
        if message.peer_id >= 2_000_000_000:
            return
        # list_suggestions is admin-oriented, so filter a small recent slice locally.
        rows = await list_suggestions(None, 100)
        rows = [r for r in rows if r[1] == message.from_id][:10]
        if not rows:
            await message.answer("Вы ещё не отправляли предложений.", keyboard=suggestion_menu.get_json())
            return
        labels = {"new": "🟡 Новое", "reviewed": "🟢 Рассмотрено", "answered": "💬 Есть ответ", "rejected": "🔴 Отклонено"}
        lines = ["📋 МОИ ПРЕДЛОЖЕНИЯ", sci_line(), ""]
        for row in rows:
            lines.append(f"#{row[0]} — {labels.get(row[5], row[5])} — {row[3][:90]}")
            if row[6]:
                lines.append(f"↳ Ответ: {row[6][:150]}")
        await message.answer("\n".join(lines), keyboard=suggestion_menu.get_json())

    async def handle_suggestion_message(message):
        session = sessions.get(message.from_id)
        if not session or session.get("mode") != "suggestion_text":
            return False
        if message.peer_id >= 2_000_000_000:
            return False
        text = (message.text or "").strip()
        if len(text) < 10:
            await message.answer("Предложение слишком короткое. Опишите идею подробнее.")
            return True
        now = int(time.time())
        last = await get_last_suggestion_time(message.from_id)
        if last and now - last < SUGGESTION_COOLDOWN:
            sessions.pop(message.from_id, None)
            await message.answer("⏳ Сработало ограничение частоты. Попробуйте позже.", keyboard=suggestion_menu.get_json())
            return True
        character = await get_character_by_user(message.from_id)
        character_id = character[0] if character else None
        attachment = get_photo_attachment(message)
        suggestion_id = await create_suggestion(message.from_id, character_id, text[:3000], attachment, now)
        sessions.pop(message.from_id, None)
        kb = (
            Keyboard(one_time=False)
            .add(Text(f"💡 Открыть #{suggestion_id}"), color=KeyboardButtonColor.PRIMARY)
        )
        kwargs = {
            "peer_id": ADMIN_CHAT_ID,
            "random_id": 0,
            "message": (
                f"💡 НОВОЕ ПРЕДЛОЖЕНИЕ #{suggestion_id}\n{sci_line()}\n\n"
                f"VK ID: {message.from_id}\n"
                f"Квента: #{character_id or '—'}\n\n"
                f"{text[:3000]}\n\n"
                f"/предложение {suggestion_id}"
            ),
            "keyboard": kb.get_json(),
        }
        if attachment:
            kwargs["attachment"] = attachment
        try:
            await bot.api.messages.send(**kwargs)
        except Exception:
            pass
        await message.answer(
            f"✅ Предложение #{suggestion_id} передано администрации.",
            keyboard=suggestion_menu.get_json(),
        )
        return True

    return {
        "sessions": sessions,
        "handle_suggestion_message": handle_suggestion_message,
        "suggestion_menu": suggestion_menu,
    }
