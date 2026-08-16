import time
from systems.utils import format_salary_cooldown

def register_housing_handlers(bot, deps):
    get_character_by_user = deps["get_character_by_user"]
    get_housing = deps["get_housing"]
    HOUSING_NAMES = deps["HOUSING_NAMES"]
    sci_line = deps["sci_line"]
    housing_menu = deps["housing_menu"]
    WEEK_SECONDS = deps["WEEK_SECONDS"]
    format_salary_cooldown = deps["format_salary_cooldown"]
    create_user = deps["create_user"]
    get_user = deps["get_user"]
    subtract_balance = deps["subtract_balance"]
    update_housing_payment = deps["update_housing_payment"]

    @bot.on.message(text="🏠 Каюта")
    async def housing_menu_handler(message):
        await message.answer(
            "◢ ЖИЛОЙ ТЕРМИНАЛ ◣\n"
            f"{sci_line()}\n\n"
            "Здесь можно посмотреть свою каюту и вручную оплатить аренду.",
            keyboard=housing_menu.get_json()
        )


    @bot.on.message(text="🏠 Моя каюта")
    async def my_housing_handler(message):
        character = await get_character_by_user(message.from_id)

        if not character:
            await message.answer(
                "◢ ЖИЛЬЁ НЕДОСТУПНО ◣\n\n"
                "Сначала создайте персонажа.",
                keyboard=housing_menu.get_json()
            )
            return

        housing = await get_housing(character[0])

        if not housing:
            await message.answer(
                "◢ КАЮТА НЕ НАЗНАЧЕНА ◣\n"
                f"{sci_line()}\n\n"
                "Администрация ещё не выдала вам жилой модуль.",
                keyboard=housing_menu.get_json()
            )
            return

        housing_class = housing[1]
        sector = housing[2]
        weekly_rent = housing[3]
        last_payment_time = housing[4] or 0

        if weekly_rent == 0:
            payment_info = "🏛️ Апартаменты I класса не облагаются арендой."
        elif last_payment_time == 0:
            payment_info = "💳 Аренда ещё ни разу не оплачивалась."
        else:
            now = int(time.time())
            next_payment = last_payment_time + WEEK_SECONDS
            seconds_left = next_payment - now

            if seconds_left > 0:
                payment_info = f"⏳ Следующая оплата доступна через: {format_salary_cooldown(seconds_left)}"
            else:
                payment_info = "⚠️ Аренду можно оплатить сейчас."

        await message.answer(
            "◢ МОЯ КАЮТА ◣\n"
            f"{sci_line()}\n\n"
            f"🧬 Персонаж: {character[2]}\n"
            f"🏠 Тип жилья: {HOUSING_NAMES.get(housing_class, housing_class)}\n"
            f"📍 Сектор: {sector}\n"
            f"💳 Аренда: {weekly_rent} CR / неделя\n\n"
            f"{payment_info}",
            keyboard=housing_menu.get_json()
        )


    @bot.on.message(text="💳 Оплатить аренду")
    async def pay_housing_rent_handler(message):
        await create_user(message.from_id)

        user = await get_user(message.from_id)
        character = await get_character_by_user(message.from_id)

        if not character:
            await message.answer(
                "Персонаж не найден.",
                keyboard=housing_menu.get_json()
            )
            return

        housing = await get_housing(character[0])

        if not housing:
            await message.answer(
                "Каюта не назначена.",
                keyboard=housing_menu.get_json()
            )
            return

        housing_class = housing[1]
        rent = housing[3]
        last_payment_time = housing[4] or 0

        if rent <= 0:
            await message.answer(
                "🏛️ Ваше жильё не облагается арендной платой.",
                keyboard=housing_menu.get_json()
            )
            return

        now = int(time.time())
        seconds_passed = now - last_payment_time

        if last_payment_time != 0 and seconds_passed < WEEK_SECONDS:
            seconds_left = WEEK_SECONDS - seconds_passed
            await message.answer(
                "⏳ АРЕНДА УЖЕ ОПЛАЧЕНА\n"
                f"{sci_line()}\n\n"
                f"Следующая оплата доступна через: {format_salary_cooldown(seconds_left)}",
                keyboard=housing_menu.get_json()
            )
            return

        if user[1] < rent:
            await message.answer(
                "🔴 НЕДОСТАТОЧНО СРЕДСТВ\n"
                f"{sci_line()}\n\n"
                f"Требуется: {rent} CR\n"
                f"Ваш баланс: {user[1]} CR",
                keyboard=housing_menu.get_json()
            )
            return

        await subtract_balance(message.from_id, rent)
        await update_housing_payment(character[0], now)

        updated_user = await get_user(message.from_id)

        await message.answer(
            "🟢 АРЕНДА ОПЛАЧЕНА\n"
            f"{sci_line()}\n\n"
            f"🏠 Жильё: {HOUSING_NAMES.get(housing_class, housing_class)}\n"
            f"💳 Списано: {rent} CR\n"
            f"💰 Баланс: {updated_user[1]} CR",
            keyboard=housing_menu.get_json()
        )

