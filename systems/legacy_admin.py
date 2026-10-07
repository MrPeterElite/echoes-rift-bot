from systems.onboarding import entry_keyboard
def build_legacy_admin_router(deps):
    ADMIN_CHAT_ID = deps["ADMIN_CHAT_ID"]
    ADMIN_RUNTIME = deps["ADMIN_RUNTIME"]
    DEPARTMENTS = deps["DEPARTMENTS"]
    DEPARTMENT_CODES_TEXT = deps["DEPARTMENT_CODES_TEXT"]
    FACTION_RANKS = deps["FACTION_RANKS"]
    HOUSING_CLASS_CAPACITY = deps["HOUSING_CLASS_CAPACITY"]
    HOUSING_NAMES = deps["HOUSING_NAMES"]
    HOUSING_PRICES = deps["HOUSING_PRICES"]
    SALARY_BY_LEVEL = deps["SALARY_BY_LEVEL"]
    assign_housing = deps["assign_housing"]
    bot = deps["bot"]
    create_user = deps["create_user"]
    get_character_by_id = deps["get_character_by_id"]
    get_department_key_by_name = deps["get_department_key_by_name"]
    get_housing = deps["get_housing"]
    get_housing_interiors = deps["get_housing_interiors"]
    get_used_slots = deps["get_used_slots"]
    get_user = deps["get_user"]
    remove_housing = deps["remove_housing"]
    sci_line = deps["sci_line"]
    update_character_job = deps["update_character_job"]
    update_character_status = deps["update_character_status"]
    update_faction_rank = deps["update_faction_rank"]
    update_housing_class = deps["update_housing_class"]
    update_housing_sector = deps["update_housing_sector"]

    async def handle(message):
        text = message.text or ""
        if message.peer_id == ADMIN_CHAT_ID:
            # Сам факт нахождения в админ-беседе больше не даёт полномочий.
            if not await ADMIN_RUNTIME["has_role"](message.from_id, "moderator"):
                return True

            # Старые опасные команды сохранены, но требуют уровня Администратор+.
            admin_only_prefixes = (
                "/назначить ", "/повысить ", "/понизить ",
                "/фповысить ", "/фпонизить ",
                "/выдатькаюту ", "/забратькаюту ", "/переселить ", "/улучшитькаюту ",
                "/деньги ", "/снятьденьги ", "/баланс ", "/отделы"
            )
            if text.startswith(admin_only_prefixes) and not await ADMIN_RUNTIME["has_role"](message.from_id, "admin"):
                await message.answer("⛔ Для этой команды требуется роль Администратор или выше.")
                return True

            if text.startswith("/назначить "):
                parts = text.split()

                if len(parts) < 3:
                    await message.answer(
                        "Использование:\n"
                        "/назначить ID отдел\n\n"
                        "Пример:\n"
                        "/назначить 1 наука"
                    )
                    return True

                try:
                    character_id = int(parts[1])
                except ValueError:
                    await message.answer("Неверный ID персонажа.")
                    return True

                department_key = parts[2].lower()

                if department_key not in DEPARTMENTS:
                    await message.answer(
                        "Неизвестный отдел.\n\n"
                        "Доступные коды:\n"
                        "безопасность\n"
                        "медицина\n"
                        "наука\n"
                        "админ\n"
                        "инженерия\n"
                        "разведка\n"
                        "пепел"
                    )
                    return True

                character = await get_character_by_id(character_id)

                if not character:
                    await message.answer("Персонаж не найден.")
                    return True

                department = DEPARTMENTS[department_key]
                department_name = department["name"]
                job_title = department["jobs"][0]
                job_level = 1
                salary = SALARY_BY_LEVEL[job_level]

                await update_character_job(
                    character_id,
                    department_name,
                    job_title,
                    job_level
                )

                await bot.api.messages.send(
                    peer_id=character[1],
                    random_id=0,
                    message=(
                        "📡 КАРЬЕРНОЕ НАЗНАЧЕНИЕ\n"
                        f"{sci_line()}\n\n"
                        f"📂 Отдел: {department_name}\n"
                        f"💼 Должность: {job_title}\n"
                        f"📈 Уровень: {job_level}\n"
                        f"💳 Недельная зарплата: {salary} CR\n\n"
                        "Поздравляем с назначением."
                    )
                )

                await message.answer(
                    "🟢 НАЗНАЧЕНИЕ ВЫПОЛНЕНО\n"
                    f"{sci_line()}\n\n"
                    f"🆔 Персонаж: #{character_id}\n"
                    f"📂 Отдел: {department_name}\n"
                    f"💼 Должность: {job_title}\n"
                    f"💳 Зарплата: {salary} CR"
                )
                return True

            if text.startswith("/повысить "):
                parts = text.split()

                if len(parts) < 2:
                    await message.answer(
                        "Использование:\n"
                        "/повысить ID\n\n"
                        "Пример:\n"
                        "/повысить 4"
                    )
                    return True

                try:
                    character_id = int(parts[1])
                except ValueError:
                    await message.answer("Неверный ID персонажа.")
                    return True

                character = await get_character_by_id(character_id)

                if not character:
                    await message.answer("Персонаж не найден.")
                    return True

                department_name = character[11]
                current_level = character[13] or 0

                if not department_name or current_level == 0:
                    await message.answer(
                        "Сначала назначьте отдел командой:\n"
                        "/назначить ID отдел"
                    )
                    return True

                department_key = get_department_key_by_name(department_name)

                if not department_key:
                    await message.answer("Не удалось определить отдел.")
                    return True

                jobs = DEPARTMENTS[department_key]["jobs"]

                if current_level >= len(jobs):
                    await message.answer("Игрок уже находится на максимальной должности.")
                    return True

                new_level = current_level + 1
                new_job_title = jobs[new_level - 1]
                salary = SALARY_BY_LEVEL[new_level]

                await update_character_job(
                    character_id,
                    department_name,
                    new_job_title,
                    new_level
                )

                await bot.api.messages.send(
                    peer_id=character[1],
                    random_id=0,
                    message=(
                        "⬆️ КАРЬЕРНОЕ ПОВЫШЕНИЕ\n"
                        f"{sci_line()}\n\n"
                        f"📂 Отдел: {department_name}\n"
                        f"💼 Новая должность: {new_job_title}\n"
                        f"📈 Уровень: {new_level}\n"
                        f"💳 Недельная зарплата: {salary} CR\n\n"
                        "Поздравляем с повышением."
                    )
                )

                await message.answer(
                    "🟢 ПОВЫШЕНИЕ ВЫПОЛНЕНО\n"
                    f"{sci_line()}\n\n"
                    f"🆔 Персонаж: #{character_id}\n"
                    f"📂 Отдел: {department_name}\n"
                    f"💼 Новая должность: {new_job_title}\n"
                    f"💳 Зарплата: {salary} CR"
                )
                return True

            if text.startswith("/понизить "):
                parts = text.split()

                if len(parts) < 2:
                    await message.answer(
                        "Использование:\n"
                        "/понизить ID\n\n"
                        "Пример:\n"
                        "/понизить 4"
                    )
                    return True

                try:
                    character_id = int(parts[1])
                except ValueError:
                    await message.answer("Неверный ID персонажа.")
                    return True

                character = await get_character_by_id(character_id)

                if not character:
                    await message.answer("Персонаж не найден.")
                    return True

                department_name = character[11]
                current_level = character[13] or 0

                if not department_name or current_level == 0:
                    await message.answer("У игрока ещё нет назначенной должности.")
                    return True

                department_key = get_department_key_by_name(department_name)

                if not department_key:
                    await message.answer("Не удалось определить отдел.")
                    return True

                jobs = DEPARTMENTS[department_key]["jobs"]

                if current_level <= 1:
                    await message.answer("Игрок уже находится на минимальной должности.")
                    return True

                new_level = current_level - 1
                new_job_title = jobs[new_level - 1]
                salary = SALARY_BY_LEVEL[new_level]

                await update_character_job(
                    character_id,
                    department_name,
                    new_job_title,
                    new_level
                )

                await bot.api.messages.send(
                    peer_id=character[1],
                    random_id=0,
                    message=(
                        "⬇️ КАРЬЕРНОЕ ПОНИЖЕНИЕ\n"
                        f"{sci_line()}\n\n"
                        f"📂 Отдел: {department_name}\n"
                        f"💼 Новая должность: {new_job_title}\n"
                        f"📈 Уровень: {new_level}\n"
                        f"💳 Недельная зарплата: {salary} CR"
                    )
                )

                await message.answer(
                    "🟠 ПОНИЖЕНИЕ ВЫПОЛНЕНО\n"
                    f"{sci_line()}\n\n"
                    f"🆔 Персонаж: #{character_id}\n"
                    f"📂 Отдел: {department_name}\n"
                    f"💼 Новая должность: {new_job_title}\n"
                    f"💳 Зарплата: {salary} CR"
                )
                return True


            if text.startswith("/фповысить "):
                parts = text.split()
                try:
                    character_id = int(parts[1])
                except:
                    await message.answer("Использование: /фповысить ID")
                    return True
                character = await get_character_by_id(character_id)
                if not character:
                    await message.answer("Персонаж не найден.")
                    return True
                ranks = FACTION_RANKS.get(character[5])
                current_level = character[16] if len(character) > 16 and character[16] else 0
                if current_level >= len(ranks):
                    await message.answer("Игрок уже имеет максимальный фракционный ранг.")
                    return True
                new_level = current_level + 1
                new_rank = ranks[new_level - 1]
                await update_faction_rank(character_id, new_rank, new_level)
                await message.answer(f"🎖 Новый ранг: {new_rank}")
                return True

            if text.startswith("/фпонизить "):
                parts = text.split()
                try:
                    character_id = int(parts[1])
                except:
                    await message.answer("Использование: /фпонизить ID")
                    return True
                character = await get_character_by_id(character_id)
                if not character:
                    await message.answer("Персонаж не найден.")
                    return True
                ranks = FACTION_RANKS.get(character[5])
                current_level = character[16] if len(character) > 16 and character[16] else 0
                if current_level <= 1:
                    await message.answer("Игрок уже находится на минимальном ранге.")
                    return True
                new_level = current_level - 1
                new_rank = ranks[new_level - 1]
                await update_faction_rank(character_id, new_rank, new_level)
                await message.answer(f"🎖 Новый ранг: {new_rank}")
                return True


            if text.startswith("/выдатькаюту "):
                parts = text.split(maxsplit=3)

                if len(parts) < 4:
                    await message.answer(
                        "Использование:\n"
                        "/выдатькаюту ID класс сектор\n\n"
                        "Пример:\n"
                        "/выдатькаюту 4 V C-12"
                    )
                    return True

                try:
                    character_id = int(parts[1])
                except ValueError:
                    await message.answer("Неверный ID персонажа.")
                    return True

                housing_class = parts[2].upper()
                sector = parts[3]

                if housing_class not in HOUSING_PRICES:
                    await message.answer("Класс должен быть: V, IV, III, II или I.")
                    return True

                character = await get_character_by_id(character_id)

                if not character:
                    await message.answer("Персонаж не найден.")
                    return True

                current_housing = await get_housing(character_id)
                if current_housing:
                    interiors = await get_housing_interiors(character_id)
                    used_slots = len(set(get_used_slots(interiors)))
                    new_capacity = HOUSING_CLASS_CAPACITY.get(housing_class, 1)
                    if used_slots > new_capacity:
                        await message.answer(
                            "⛔ НЕЛЬЗЯ НАЗНАЧИТЬ ЭТОТ КЛАСС\n"
                            f"{sci_line()}\n\n"
                            f"Интерьер уже занимает {used_slots} слотов, "
                            f"а класс {housing_class} допускает только {new_capacity}.\n"
                            "Сначала необходимо снять часть комплектов."
                        )
                        return True

                await assign_housing(character_id, housing_class, sector)

                await bot.api.messages.send(
                    peer_id=character[1],
                    random_id=0,
                    message=(
                        "🏠 ЖИЛОЙ МОДУЛЬ НАЗНАЧЕН\n"
                        f"{sci_line()}\n\n"
                        f"🏠 Тип жилья: {HOUSING_NAMES[housing_class]}\n"
                        f"📍 Сектор: {sector}\n"
                        f"💳 Аренда: {HOUSING_PRICES[housing_class]} CR / неделя"
                    )
                )

                await message.answer(
                    "🟢 КАЮТА ВЫДАНА\n"
                    f"{sci_line()}\n\n"
                    f"🆔 Персонаж: #{character_id}\n"
                    f"🏠 Тип: {HOUSING_NAMES[housing_class]}\n"
                    f"📍 Сектор: {sector}\n"
                    f"💳 Аренда: {HOUSING_PRICES[housing_class]} CR / неделя"
                )
                return True

            if text.startswith("/забратькаюту "):
                parts = text.split()

                if len(parts) < 2:
                    await message.answer("Использование:\n/забратькаюту ID")
                    return True

                try:
                    character_id = int(parts[1])
                except ValueError:
                    await message.answer("Неверный ID персонажа.")
                    return True

                character = await get_character_by_id(character_id)

                if not character:
                    await message.answer("Персонаж не найден.")
                    return True

                returned_sets = await remove_housing(character_id)

                await bot.api.messages.send(
                    peer_id=character[1],
                    random_id=0,
                    message=(
                        "🔴 ЖИЛОЙ МОДУЛЬ ИЗЪЯТ\n"
                        f"{sci_line()}\n\n"
                        "Администрация изъяла вашу каюту.\n"
                        f"📦 Возвращено комплектов в инвентарь: {returned_sets}"
                    )
                )

                await message.answer(
                    f"🏠 Каюта персонажа #{character_id} изъята. "
                    f"В инвентарь возвращено комплектов: {returned_sets}."
                )
                return True

            if text.startswith("/переселить "):
                parts = text.split(maxsplit=2)

                if len(parts) < 3:
                    await message.answer("Использование:\n/переселить ID сектор")
                    return True

                try:
                    character_id = int(parts[1])
                except ValueError:
                    await message.answer("Неверный ID персонажа.")
                    return True

                character = await get_character_by_id(character_id)
                housing = await get_housing(character_id)

                if not character:
                    await message.answer("Персонаж не найден.")
                    return True

                if not housing:
                    await message.answer("У персонажа ещё нет каюты.")
                    return True

                sector = parts[2]

                await update_housing_sector(character_id, sector)

                await bot.api.messages.send(
                    peer_id=character[1],
                    random_id=0,
                    message=(
                        "📍 ПЕРЕСЕЛЕНИЕ ВЫПОЛНЕНО\n"
                        f"{sci_line()}\n\n"
                        f"Новый сектор: {sector}"
                    )
                )

                await message.answer(f"📍 Персонаж #{character_id} переселён в сектор {sector}.")
                return True

            if text.startswith("/улучшитькаюту "):
                parts = text.split()

                if len(parts) < 3:
                    await message.answer(
                        "Использование:\n"
                        "/улучшитькаюту ID класс\n\n"
                        "Пример:\n"
                        "/улучшитькаюту 4 II"
                    )
                    return True

                try:
                    character_id = int(parts[1])
                except ValueError:
                    await message.answer("Неверный ID персонажа.")
                    return True

                housing_class = parts[2].upper()

                if housing_class not in HOUSING_PRICES:
                    await message.answer("Класс должен быть: V, IV, III, II или I.")
                    return True

                character = await get_character_by_id(character_id)
                housing = await get_housing(character_id)

                if not character:
                    await message.answer("Персонаж не найден.")
                    return True

                if not housing:
                    await message.answer("У персонажа ещё нет каюты.")
                    return True

                interiors = await get_housing_interiors(character_id)
                used_slots = len(set(get_used_slots(interiors)))
                new_capacity = HOUSING_CLASS_CAPACITY.get(housing_class, 1)
                if used_slots > new_capacity:
                    await message.answer(
                        "⛔ НЕЛЬЗЯ ПОНИЗИТЬ КЛАСС ЖИЛЬЯ\n"
                        f"{sci_line()}\n\n"
                        f"Сейчас интерьер занимает {used_slots} слотов.\n"
                        f"Новый класс допускает только {new_capacity}.\n"
                        "Сначала владелец должен снять часть комплектов."
                    )
                    return True

                await update_housing_class(character_id, housing_class)

                await bot.api.messages.send(
                    peer_id=character[1],
                    random_id=0,
                    message=(
                        "⬆️ КЛАСС ЖИЛЬЯ ИЗМЕНЁН\n"
                        f"{sci_line()}\n\n"
                        f"🏠 Новый тип: {HOUSING_NAMES[housing_class]}\n"
                        f"💳 Аренда: {HOUSING_PRICES[housing_class]} CR / неделя"
                    )
                )

                await message.answer(
                    f"⬆️ Персонаж #{character_id}: жильё изменено на {HOUSING_NAMES[housing_class]}."
                )
                return True


            if text.startswith("/баланс "):
                parts = text.split()

                if len(parts) < 2:
                    await message.answer(
                        "Использование:\n"
                        "/баланс ID\n\n"
                        "Пример:\n"
                        "/баланс 4"
                    )
                    return True

                try:
                    character_id = int(parts[1])
                except ValueError:
                    await message.answer("ID должен быть числом.")
                    return True

                character = await get_character_by_id(character_id)

                if not character:
                    await message.answer("Персонаж не найден.")
                    return True

                await create_user(character[1])
                user = await get_user(character[1])

                await message.answer(
                    "◢ ПРОВЕРКА БАЛАНСА ◣\n"
                    f"{sci_line()}\n\n"
                    f"🆔 Персонаж: #{character_id}\n"
                    f"👤 Персонаж: {character[2]}\n"
                    f"💳 Баланс: {user[1]} CR"
                )
                return True

            if text.startswith("/отделы"):
                await message.answer(
                    "◢ КОДЫ ОТДЕЛОВ ◣\n"
                    f"{sci_line()}\n\n"
                    f"{DEPARTMENT_CODES_TEXT}\n\n"
                    "Пример назначения:\n"
                    "/назначить 4 наука"
                )
                return True

            if "Одобрить #" in text:
                try:
                    character_id = int(text.split("#")[-1].strip())
                except ValueError:
                    await message.answer("Неверный номер персонажа.")
                    return True

                character = await get_character_by_id(character_id)

                if not character:
                    await message.answer("Персонаж не найден.")
                    return True

                await update_character_status(character_id, "approved")

                await bot.api.messages.send(
                    peer_id=character[1],
                    random_id=0,
                    keyboard=await entry_keyboard(character[1]),
                    message=(
                        "🟢 ВЕРИФИКАЦИЯ ЗАВЕРШЕНА\n"
                        f"{sci_line()}\n\n"
                        "Ваш персонаж одобрен.\n"
                        "Доступ к системе Echoes of the Rift открыт."
                    )
                )

                await message.answer(f"✅ Персонаж #{character_id} одобрен.")
                return True

            if "Отклонить #" in text:
                try:
                    character_id = int(text.split("#")[-1].strip())
                except ValueError:
                    await message.answer("Неверный номер персонажа.")
                    return True

                character = await get_character_by_id(character_id)

                if not character:
                    await message.answer("Персонаж не найден.")
                    return True

                await update_character_status(character_id, "rejected")

                await bot.api.messages.send(
                    peer_id=character[1],
                    random_id=0,
                    keyboard=await entry_keyboard(character[1]),
                    message=(
                        "🔴 ПЕРСОНАЖ ОТКЛОНЁН\n"
                        f"{sci_line()}\n\n"
                        "Администрация отклонила вашего персонажа.\n"
                        "Вы можете удалить персонажа и создать нового."
                    )
                )

                await message.answer(f"❌ Персонаж #{character_id} отклонён.")
                return True

            return True
        return False

    return handle
