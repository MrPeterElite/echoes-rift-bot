import json
import random
import time
from pathlib import Path


def load_quest_catalog():
    paths = [
        Path(__file__).resolve().parent.parent / "quests.json",
        Path(__file__).resolve().parent.parent / "data" / "quests.json",
    ]
    for path in paths:
        if path.exists():
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
    return {}


def format_quest(quest, sci_line):
    status_map = {
        "active": "🟡 ВЫПОЛНЯЕТСЯ",
        "review": "🔵 ОТЧЁТ НА ПРОВЕРКЕ",
        "rejected": "🔴 ОТЧЁТ ОТКЛОНЁН",
        "completed": "🟢 ВЫПОЛНЕНО",
    }
    return (
        "◢ ДОЛЖНОСТНОЕ ЗАДАНИЕ ◣\n"
        f"{sci_line()}\n\n"
        f"📌 {quest[2]}\n\n"
        f"{quest[3]}\n\n"
        f"💳 Награда: {quest[4]} CR\n"
        f"⭐ Опыт: {quest[5]} XP\n"
        f"📡 Статус: {status_map.get(quest[6], quest[6])}\n\n"
        "Для сдачи отчёта отправьте:\n"
        "/отчёт ваш текст отчёта"
    )


def register_quest_handlers(bot, deps):
    get_character_by_user = deps["get_character_by_user"]
    get_character_by_id = deps["get_character_by_id"]
    get_current_quest = deps["get_current_quest"]
    get_last_quest = deps["get_last_quest"]
    create_weekly_quest = deps["create_weekly_quest"]
    submit_quest_report = deps["submit_quest_report"]
    get_quest_by_id = deps["get_quest_by_id"]
    update_quest_status = deps["update_quest_status"]
    add_balance = deps["add_balance"]
    add_xp = deps["add_xp"]
    get_photo_attachment = deps["get_photo_attachment"]
    sci_line = deps["sci_line"]
    career_menu = deps["career_menu"]
    ADMIN_CHAT_ID = deps["ADMIN_CHAT_ID"]
    WEEK_SECONDS = deps["WEEK_SECONDS"]

    async def require_career(message):
        character = await get_character_by_user(message.from_id)
        if not character:
            await message.answer("Персонаж не найден. Сначала создайте квенту.", keyboard=career_menu.get_json())
            return None
        if character[10] != "approved":
            await message.answer("Квента должна быть одобрена администрацией.", keyboard=career_menu.get_json())
            return None
        if not character[11] or not character[12] or not (character[13] or 0):
            await message.answer("Сначала администрация должна назначить вам отдел и должность.", keyboard=career_menu.get_json())
            return None
        return character

    @bot.on.message(text="📌 Задание")
    async def quest_handler(message):
        character = await require_career(message)
        if not character:
            return

        current = await get_current_quest(character[0])
        if current:
            await message.answer(format_quest(current, sci_line), keyboard=career_menu.get_json())
            return

        last = await get_last_quest(character[0])
        now = int(time.time())
        if last and now - (last[7] or 0) < WEEK_SECONDS:
            left = WEEK_SECONDS - (now - (last[7] or 0))
            days, rem = divmod(max(0, left), 86400)
            hours, rem = divmod(rem, 3600)
            minutes = rem // 60
            await message.answer(
                "⏳ НОВОЕ ЗАДАНИЕ ПОКА НЕДОСТУПНО\n"
                f"{sci_line()}\n\n"
                f"Следующее должностное задание можно получить через: {days} д. {hours} ч. {minutes} мин.",
                keyboard=career_menu.get_json(),
            )
            return

        catalog = load_quest_catalog()
        pool = catalog.get(character[11], {}).get(character[12], [])
        if not pool:
            await message.answer(
                "Для вашей должности задания пока не настроены. Сообщите администрации.",
                keyboard=career_menu.get_json(),
            )
            return

        choices = pool
        if last:
            alternatives = [q for q in pool if q.get("title") != last[2]]
            if alternatives:
                choices = alternatives
        selected = random.choice(choices)
        quest_id = await create_weekly_quest(
            character[0], selected["title"], selected["description"],
            int(selected.get("credits", 0)), int(selected.get("xp", 0)), now,
        )
        quest = await get_quest_by_id(quest_id)
        await message.answer(format_quest(quest, sci_line), keyboard=career_menu.get_json())

    @bot.on.message(text="📨 Сдать отчёт")
    async def report_help_handler(message):
        character = await require_career(message)
        if not character:
            return
        quest = await get_current_quest(character[0])
        if not quest:
            await message.answer("Сначала получите задание кнопкой «📌 Задание».", keyboard=career_menu.get_json())
            return
        if quest[6] == "review":
            await message.answer("Ваш отчёт уже находится на проверке администрации.", keyboard=career_menu.get_json())
            return
        await message.answer(
            "📨 СДАЧА ОТЧЁТА\n"
            f"{sci_line()}\n\n"
            "Отправьте сообщение в формате:\n"
            "/отчёт текст выполненной работы\n\n"
            "При необходимости к этому же сообщению можно прикрепить фотографию.",
            keyboard=career_menu.get_json(),
        )

    @bot.on.message(text="/отчёт <report>")
    async def submit_report_handler(message, report=None):
        character = await require_career(message)
        if not character:
            return
        quest = await get_current_quest(character[0])
        if not quest:
            await message.answer("У вас нет активного должностного задания.", keyboard=career_menu.get_json())
            return
        if quest[6] == "review":
            await message.answer("Этот отчёт уже находится на проверке.", keyboard=career_menu.get_json())
            return
        report = (report or "").strip()
        if len(report) < 10:
            await message.answer("Отчёт слишком короткий. Опишите выполненную работу подробнее.")
            return
        attachment = get_photo_attachment(message)
        await submit_quest_report(quest[0], report, attachment, int(time.time()))

        admin_text = (
            "📨 НОВЫЙ ОТЧЁТ ПО ЗАДАНИЮ\n"
            f"{sci_line()}\n\n"
            f"🆔 Задание: #{quest[0]}\n"
            f"🧬 Персонаж: #{character[0]} — {character[2]}\n"
            f"📂 Отдел: {character[11]}\n"
            f"💼 Должность: {character[12]}\n\n"
            f"📌 {quest[2]}\n\n"
            f"📝 Отчёт:\n{report}\n\n"
            f"💳 Награда: {quest[4]} CR\n"
            f"⭐ Опыт: {quest[5]} XP\n\n"
            f"/принятьзадание {quest[0]}\n"
            f"/отклонитьзадание {quest[0]}"
        )
        kwargs = {"peer_id": ADMIN_CHAT_ID, "random_id": 0, "message": admin_text}
        if attachment:
            kwargs["attachment"] = attachment
        await bot.api.messages.send(**kwargs)
        await message.answer("✅ Отчёт отправлен администрации на проверку.", keyboard=career_menu.get_json())

    @bot.on.message(text="/принятьзадание <quest_id>")
    async def approve_quest_handler(message, quest_id=None):
        if message.peer_id != ADMIN_CHAT_ID:
            return
        try:
            quest_id = int(quest_id)
        except (TypeError, ValueError):
            await message.answer("Использование: /принятьзадание ID")
            return
        quest = await get_quest_by_id(quest_id)
        if not quest:
            await message.answer("Задание не найдено.")
            return
        if quest[6] != "review":
            await message.answer("Это задание сейчас не ожидает проверки.")
            return
        character = await get_character_by_id(quest[1])
        if not character:
            await message.answer("Персонаж задания не найден.")
            return
        await update_quest_status(quest_id, "completed")
        await add_balance(character[1], quest[4])
        await add_xp(character[1], quest[5])
        await bot.api.messages.send(
            peer_id=character[1], random_id=0,
            message=(
                "🟢 ДОЛЖНОСТНОЕ ЗАДАНИЕ ПРИНЯТО\n"
                f"{sci_line()}\n\n"
                f"📌 {quest[2]}\n\n"
                f"💳 Получено: +{quest[4]} CR\n"
                f"⭐ Получено: +{quest[5]} XP\n\n"
                "Новое задание станет доступно после недельного интервала."
            ),
        )
        await message.answer(f"✅ Задание #{quest_id} принято. Награда начислена.")

    @bot.on.message(text="/отклонитьзадание <quest_id>")
    async def reject_quest_handler(message, quest_id=None):
        if message.peer_id != ADMIN_CHAT_ID:
            return
        try:
            quest_id = int(quest_id)
        except (TypeError, ValueError):
            await message.answer("Использование: /отклонитьзадание ID")
            return
        quest = await get_quest_by_id(quest_id)
        if not quest:
            await message.answer("Задание не найдено.")
            return
        if quest[6] != "review":
            await message.answer("Это задание сейчас не ожидает проверки.")
            return
        character = await get_character_by_id(quest[1])
        await update_quest_status(quest_id, "rejected")
        if character:
            await bot.api.messages.send(
                peer_id=character[1], random_id=0,
                message=(
                    "🔴 ОТЧЁТ ПО ЗАДАНИЮ ОТКЛОНЁН\n"
                    f"{sci_line()}\n\n"
                    f"📌 {quest[2]}\n\n"
                    "Исправьте отчёт и отправьте его повторно командой /отчёт текст."
                ),
            )
        await message.answer(f"❌ Отчёт по заданию #{quest_id} отклонён.")
