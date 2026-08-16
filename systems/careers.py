import time
from systems.utils import format_salary_cooldown

def register_careers_handlers(bot, deps):
    sci_line = deps["sci_line"]
    career_menu = deps["career_menu"]
    get_character_by_user = deps["get_character_by_user"]
    format_career = deps["format_career"]
    create_user = deps["create_user"]
    get_user = deps["get_user"]
    WEEK_SECONDS = deps["WEEK_SECONDS"]
    format_salary_cooldown = deps["format_salary_cooldown"]
    SALARY_BY_LEVEL = deps["SALARY_BY_LEVEL"]
    add_balance = deps["add_balance"]
    update_last_salary = deps["update_last_salary"]

    @bot.on.message(text="💼 Карьера")
    async def career_menu_handler(message):
        await message.answer(
            "◢ КАРЬЕРНЫЙ ТЕРМИНАЛ ◣\n"
            f"{sci_line()}\n\n"
            "Здесь отображается должность персонажа, доступна недельная зарплата и должностные задания.\n\n"
            "Отдел и повышения выдаёт только администрация.",
            keyboard=career_menu.get_json()
        )


    @bot.on.message(text="📋 Моя должность")
    async def my_career_handler(message):
        character = await get_character_by_user(message.from_id)

        if not character:
            await message.answer(
                "◢ КАРЬЕРА НЕ АКТИВНА ◣\n\n"
                "Сначала создайте квенту и дождитесь одобрения.",
                keyboard=career_menu.get_json()
            )
            return

        if character[10] != "approved":
            await message.answer(
                "⏳ КАРЬЕРА ЗАБЛОКИРОВАНА\n\n"
                "Квента должна быть одобрена администрацией.",
                keyboard=career_menu.get_json()
            )
            return

        await message.answer(
            "◢ КАРЬЕРНОЕ ДОСЬЕ ◣\n"
            f"{sci_line()}\n\n"
            f"🧬 Персонаж: {character[2]}\n"
            f"🏛 Фракция: {character[5]}\n\n"
            f"{format_career(character)}\n"
            f"{sci_line()}",
            keyboard=career_menu.get_json()
        )


    @bot.on.message(text="💳 Получить зарплату")
    async def salary_handler(message):
        await create_user(message.from_id)

        user = await get_user(message.from_id)
        character = await get_character_by_user(message.from_id)

        if not character:
            await message.answer(
                "◢ ВЫПЛАТА НЕДОСТУПНА ◣\n\n"
                "Персонаж не найден. Создайте квенту и дождитесь одобрения.",
                keyboard=career_menu.get_json()
            )
            return

        if character[10] != "approved":
            await message.answer(
                "⏳ ВЫПЛАТА ЗАБЛОКИРОВАНА\n\n"
                "Квента должна быть одобрена администрацией.",
                keyboard=career_menu.get_json()
            )
            return

        job_level = character[13] or 0

        if job_level == 0 or not character[11] or not character[12]:
            await message.answer(
                "◢ ОТДЕЛ НЕ НАЗНАЧЕН ◣\n\n"
                "Администрация ещё не назначила вам отдел и должность.",
                keyboard=career_menu.get_json()
            )
            return

        now = int(time.time())
        last_salary_time = character[14] or 0
        seconds_passed = now - last_salary_time

        if seconds_passed < WEEK_SECONDS:
            seconds_left = WEEK_SECONDS - seconds_passed
            await message.answer(
                "⏳ ВЫПЛАТА УЖЕ ПОЛУЧЕНА\n"
                f"{sci_line()}\n\n"
                f"Следующая зарплата доступна через: {format_salary_cooldown(seconds_left)}",
                keyboard=career_menu.get_json()
            )
            return

        salary = SALARY_BY_LEVEL.get(job_level, 0)

        await add_balance(message.from_id, salary)
        await update_last_salary(character[0], now)

        updated_user = await get_user(message.from_id)

        await message.answer(
            "🟢 НЕДЕЛЬНАЯ ВЫПЛАТА НАЧИСЛЕНА\n"
            f"{sci_line()}\n\n"
            f"📂 Отдел: {character[11]}\n"
            f"💼 Должность: {character[12]}\n"
            f"📈 Уровень: {job_level}\n"
            f"💳 Начислено: +{salary} CR\n\n"
            f"Текущий баланс: {updated_user[1]} CR",
            keyboard=career_menu.get_json()
        )

