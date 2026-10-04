import json
from database import pay_rent
import time
from pathlib import Path



HOUSING_SLOT_LABELS = {
    "living": "🛏 Жилая зона",
    "personal": "🪑 Личная зона",
    "work": "🪑 Личная зона",  # legacy-совместимость со старыми комплектами
    "main": "🛋 Основная мебель",
    "lighting": "💡 Освещение",
    "decor": "🖼 Декор",
}

HOUSING_CLASS_CAPACITY = {
    "V": 1,
    "IV": 2,
    "III": 3,
    "II": 4,
    "I": 5,
}

HOUSING_CLASS_LEVEL = {
    "V": 1,
    "IV": 2,
    "III": 3,
    "II": 4,
    "I": 5,
}


def load_interior_catalog():
    paths = [
        Path(__file__).resolve().parent.parent / "shop_items.json",
        Path(__file__).resolve().parent.parent / "data" / "shop_items.json",
    ]
    for path in paths:
        if path.exists():
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            return {
                item["code"]: item
                for item in data.get("furniture", {}).get("items", [])
                if item.get("interior_set")
            }
    return {}


def find_interior_set_by_name(item_name):
    query = str(item_name).casefold().replace("ё", "е")
    for item in load_interior_catalog().values():
        name = str(item.get("name", "")).casefold().replace("ё", "е")
        if name == query:
            return item
    return None


def get_housing_description(housing):
    return housing[5] if len(housing) > 5 and housing[5] else ""


def get_housing_visibility(housing):
    return housing[6] if len(housing) > 6 and housing[6] else "public"


def get_used_slots(interiors):
    catalog = load_interior_catalog()
    used = []
    for _, set_code, _, _ in interiors:
        item = catalog.get(set_code)
        if not item:
            continue
        used.extend(item.get("housing_slots", []))
    return used


def format_slots(slots):
    if not slots:
        return "—"
    return ", ".join(HOUSING_SLOT_LABELS.get(slot, slot) for slot in slots)


def format_interior_summary(interiors):
    if not interiors:
        return "Интерьерные комплекты не установлены."

    catalog = load_interior_catalog()
    lines = []
    for index, (_, set_code, item_name, _) in enumerate(interiors, start=1):
        item = catalog.get(set_code, {})
        slots = item.get("housing_slots", [])
        lines.append(f"{index}. {item_name}\n   {format_slots(slots)}")
    return "\n".join(lines)


def format_public_housing_card(character, housing, interiors, housing_names, sci_line):
    housing_class = housing[1]
    sector = housing[2]
    capacity = HOUSING_CLASS_CAPACITY.get(housing_class, 1)
    used_slots = get_used_slots(interiors)
    description = get_housing_description(housing)

    text = (
        "◢ КАЮТА ПЕРСОНАЖА ◣\n"
        f"{sci_line()}\n\n"
        f"🧬 Владелец: #{character[0]} — {character[2]}\n"
        f"🏠 Жильё: {housing_names.get(housing_class, housing_class)}\n"
        f"📍 Сектор: {sector}\n"
        f"🧩 Интерьер: {len(set(used_slots))} / {capacity} слотов\n\n"
    )

    if description:
        text += f"✦ ОПИСАНИЕ\n{description}\n\n"

    text += "🪑 УСТАНОВЛЕННЫЕ КОМПЛЕКТЫ\n"
    text += format_interior_summary(interiors)
    return text



def get_housing_cover_item(interiors):
    """Выбирает визуальную обложку каюты из установленных комплектов.

    Приоритет отдаётся жилой/основной зоне, затем первому известному комплекту.
    """
    catalog = load_interior_catalog()
    known = []
    for _, set_code, _, _ in interiors:
        item = catalog.get(set_code)
        if item:
            known.append(item)
    if not known:
        return None
    for preferred_slot in ("living", "main", "personal", "decor", "lighting"):
        for item in known:
            if preferred_slot in item.get("housing_slots", []):
                return item
    return known[0]

def register_housing_handlers(bot, deps):
    Keyboard = deps["Keyboard"]
    KeyboardButtonColor = deps["KeyboardButtonColor"]
    Text = deps["Text"]
    get_character_by_user = deps["get_character_by_user"]
    get_character_by_id = deps["get_character_by_id"]
    get_housing = deps["get_housing"]
    get_housing_interiors = deps["get_housing_interiors"]
    install_housing_interior = deps["install_housing_interior"]
    remove_housing_interior = deps["remove_housing_interior"]
    update_housing_description = deps["update_housing_description"]
    update_housing_visibility = deps["update_housing_visibility"]
    get_inventory = deps["get_inventory"]
    HOUSING_NAMES = deps["HOUSING_NAMES"]
    sci_line = deps["sci_line"]
    housing_menu = deps["housing_menu"]
    WEEK_SECONDS = deps["WEEK_SECONDS"]
    format_salary_cooldown = deps["format_salary_cooldown"]
    create_user = deps["create_user"]
    get_user = deps["get_user"]
    stabilize_attachments = deps.get("stabilize_attachments")

    interior_menu = (
        Keyboard(one_time=False)
        .add(Text("📦 Мои комплекты"), color=KeyboardButtonColor.PRIMARY)
        .add(Text("🪑 Установить комплект"), color=KeyboardButtonColor.POSITIVE)
        .row()
        .add(Text("↩️ Снять комплект"), color=KeyboardButtonColor.SECONDARY)
        .add(Text("✏️ Описание каюты"), color=KeyboardButtonColor.SECONDARY)
        .row()
        .add(Text("🌐 Публичность"), color=KeyboardButtonColor.PRIMARY)
        .add(Text("📡 Показать каюту"), color=KeyboardButtonColor.POSITIVE)
        .row()
        .add(Text("🏠 Моя каюта"), color=KeyboardButtonColor.PRIMARY)
        .add(Text("⬅️ Назад"), color=KeyboardButtonColor.SECONDARY)
    )

    async def get_owner_context(message):
        character = await get_character_by_user(message.from_id)
        if not character:
            await message.answer("Персонаж не найден.", keyboard=housing_menu.get_json())
            return None
        if character[10] != "approved":
            await message.answer("Интерьер доступен после одобрения квенты.", keyboard=housing_menu.get_json())
            return None
        housing = await get_housing(character[0])
        if not housing:
            await message.answer("Каюта не назначена.", keyboard=housing_menu.get_json())
            return None
        return character, housing

    async def show_owner_screen(message):
        context = await get_owner_context(message)
        if not context:
            return True
        character, housing = context
        interiors = await get_housing_interiors(character[0])
        housing_class = housing[1]
        capacity = HOUSING_CLASS_CAPACITY.get(housing_class, 1)
        used_slots = get_used_slots(interiors)
        visibility = get_housing_visibility(housing)
        visibility_text = "🌐 Публичная" if visibility == "public" else "🔒 Закрытая"
        description = get_housing_description(housing)

        await message.answer(
            "◢ КАЮТА 2.0 — ИНТЕРЬЕР ◣\n"
            f"{sci_line()}\n\n"
            f"🧬 Персонаж: {character[2]}\n"
            f"🏠 {HOUSING_NAMES.get(housing_class, housing_class)}\n"
            f"📍 Сектор: {housing[2]}\n"
            f"🧩 Занято слотов: {len(set(used_slots))} / {capacity}\n"
            f"👁 Доступ: {visibility_text}\n\n"
            f"✦ Описание: {description if description else 'не задано'}\n\n"
            "Управляйте интерьерными комплектами через кнопки ниже.\n"
            "Другие игроки могут открыть публичную каюту командой /каюта ID.",
            keyboard=interior_menu.get_json(),
        )
        return True

    async def show_sets_inventory(message):
        context = await get_owner_context(message)
        if not context:
            return True
        character, _ = context
        items = [row for row in await get_inventory(character[0]) if row[0] == "furniture"]
        if not items:
            await message.answer(
                "📦 КОМПЛЕКТЫ ИНТЕРЬЕРА\n"
                f"{sci_line()}\n\n"
                "В инвентаре нет комплектов для каюты.\n"
                "Купить их можно в разделе «🪑 Интерьер каюты» магазина.",
                keyboard=interior_menu.get_json(),
            )
            return True

        text = "📦 КОМПЛЕКТЫ ИНТЕРЬЕРА\n" + sci_line() + "\n\n"
        for index, (_, item_name, quantity) in enumerate(items, start=1):
            item = find_interior_set_by_name(item_name) or {}
            slots = item.get("housing_slots", [])
            min_class = item.get("min_housing_class", "V")
            text += (
                f"{index}. {item_name} ×{quantity}\n"
                f"   {format_slots(slots)} · минимум {min_class} класс\n"
            )
        text += "\nУстановка: /установитькомплект НОМЕР"
        await message.answer(text, keyboard=interior_menu.get_json())
        return True

    async def show_installed_for_removal(message):
        context = await get_owner_context(message)
        if not context:
            return True
        character, _ = context
        interiors = await get_housing_interiors(character[0])
        if not interiors:
            await message.answer("В каюте пока нет установленных комплектов.", keyboard=interior_menu.get_json())
            return True

        text = "↩️ УСТАНОВЛЕННЫЕ КОМПЛЕКТЫ\n" + sci_line() + "\n\n"
        for index, (_, set_code, item_name, _) in enumerate(interiors, start=1):
            item = load_interior_catalog().get(set_code, {})
            text += f"{index}. {item_name}\n   {format_slots(item.get('housing_slots', []))}\n"
        text += "\nСнять: /снятькомплект НОМЕР"
        await message.answer(text, keyboard=interior_menu.get_json())
        return True

    async def install_by_number(message, number):
        context = await get_owner_context(message)
        if not context:
            return True
        character, housing = context

        try:
            number = int(number)
        except (TypeError, ValueError):
            await message.answer("Использование: /установитькомплект НОМЕР")
            return True

        furniture = [row for row in await get_inventory(character[0]) if row[0] == "furniture"]
        if number < 1 or number > len(furniture):
            await message.answer("Комплект с таким номером не найден.")
            return True

        _, item_name, _ = furniture[number - 1]
        item = find_interior_set_by_name(item_name)
        if not item or not item.get("interior_set"):
            await message.answer("Этот предмет не является интерьерным комплектом.")
            return True

        required_faction = item.get("required_faction")
        if required_faction and character[5] != required_faction:
            await message.answer(
                f"⛔ Этот комплект доступен только персонажам фракции: "
                f"{item.get('required_faction_label', required_faction)}."
            )
            return True

        housing_class = housing[1]
        min_class = item.get("min_housing_class", "V")
        if HOUSING_CLASS_LEVEL.get(housing_class, 0) < HOUSING_CLASS_LEVEL.get(min_class, 1):
            await message.answer(
                f"⛔ Для комплекта «{item_name}» требуется каюта {min_class} класса или выше."
            )
            return True

        interiors = await get_housing_interiors(character[0])
        used_slots = set(get_used_slots(interiors))
        new_slots = set(item.get("housing_slots", []))
        conflicts = used_slots & new_slots
        if conflicts:
            await message.answer(
                "⛔ Нужные слоты уже заняты:\n" +
                "\n".join(f"• {HOUSING_SLOT_LABELS.get(slot, slot)}" for slot in sorted(conflicts)) +
                "\n\nСначала снимите конфликтующий комплект."
            )
            return True

        capacity = HOUSING_CLASS_CAPACITY.get(housing_class, 1)
        if len(used_slots | new_slots) > capacity:
            await message.answer(
                "⛔ НЕДОСТАТОЧНО МЕСТА\n"
                f"{sci_line()}\n\n"
                f"Класс каюты позволяет использовать {capacity} слотов.\n"
                f"Сейчас занято: {len(used_slots)}\n"
                f"Комплект требует ещё: {len(new_slots)}"
            )
            return True

        ok, reason = await install_housing_interior(
            character[0],
            item["code"],
            item["name"],
            int(time.time()),
            list(new_slots),
            capacity,
        )
        if not ok:
            if reason == "not_found":
                error_text = "Комплект больше не найден в инвентаре."
            elif reason == "slot_conflict":
                error_text = "Один из слотов уже успел занять другой комплект. Обновите экран интерьера."
            elif reason == "capacity":
                error_text = "Лимит слотов уже достигнут. Обновите экран интерьера."
            else:
                error_text = "Не удалось установить комплект."
            await message.answer(error_text)
            return True

        await message.answer(
            "🟢 КОМПЛЕКТ УСТАНОВЛЕН\n"
            f"{sci_line()}\n\n"
            f"🪑 {item['name']}\n"
            f"🧩 Слоты: {format_slots(item.get('housing_slots', []))}",
            keyboard=interior_menu.get_json(),
        )
        return True

    async def remove_by_number(message, number):
        context = await get_owner_context(message)
        if not context:
            return True
        character, _ = context
        try:
            number = int(number)
        except (TypeError, ValueError):
            await message.answer("Использование: /снятькомплект НОМЕР")
            return True

        interiors = await get_housing_interiors(character[0])
        if number < 1 or number > len(interiors):
            await message.answer("Установленный комплект с таким номером не найден.")
            return True

        interior_id = interiors[number - 1][0]
        ok, _, item_name = await remove_housing_interior(character[0], interior_id)
        if not ok:
            await message.answer("Комплект уже был снят или не найден.")
            return True

        await message.answer(
            "↩️ КОМПЛЕКТ СНЯТ\n"
            f"{sci_line()}\n\n"
            f"📦 {item_name}\n"
            "Предмет возвращён в инвентарь.",
            keyboard=interior_menu.get_json(),
        )
        return True

    async def set_description(message, description):
        context = await get_owner_context(message)
        if not context:
            return True
        character, _ = context
        description = (description or "").strip()
        if not description:
            await message.answer("Использование: /описаниекаюты ТЕКСТ")
            return True
        if description.casefold() in {"сброс", "очистить", "нет"}:
            description = ""
        if len(description) > 700:
            await message.answer("Описание слишком длинное. Максимум — 700 символов.")
            return True
        await update_housing_description(character[0], description)
        await message.answer(
            "✅ Описание каюты обновлено." if description else "✅ Описание каюты очищено.",
            keyboard=interior_menu.get_json(),
        )
        return True

    async def toggle_visibility(message):
        context = await get_owner_context(message)
        if not context:
            return True
        character, housing = context
        current = get_housing_visibility(housing)
        new_value = "private" if current == "public" else "public"
        await update_housing_visibility(character[0], new_value)
        await message.answer(
            "🌐 Каюта теперь публичная. Другие игроки могут открыть её через /каюта ID."
            if new_value == "public"
            else "🔒 Каюта теперь закрыта. Просмотр по /каюта ID запрещён.",
            keyboard=interior_menu.get_json(),
        )
        return True

    async def show_guest(message, character_id):
        try:
            character_id = int(character_id)
        except (TypeError, ValueError):
            await message.answer("Использование: /каюта ID")
            return True

        target = await get_character_by_id(character_id)
        if not target or target[10] != "approved":
            await message.answer("Каюта этого персонажа недоступна.")
            return True
        housing = await get_housing(target[0])
        if not housing:
            await message.answer("У персонажа нет назначенной каюты.")
            return True

        owner = await get_character_by_user(message.from_id)
        is_owner = owner and owner[0] == target[0]
        if get_housing_visibility(housing) != "public" and not is_owner:
            await message.answer("🔒 Владелец закрыл каюту от публичного просмотра.")
            return True

        interiors = await get_housing_interiors(target[0])
        kwargs = {"message": format_public_housing_card(target, housing, interiors, HOUSING_NAMES, sci_line)}
        cover = get_housing_cover_item(interiors)
        if cover and stabilize_attachments and cover.get("local_image"):
            attachment = await stabilize_attachments(bot, cover.get("photo"), message.peer_id, cover.get("local_image"))
            if attachment:
                kwargs["attachment"] = attachment
        await message.answer(**kwargs)
        return True

    async def publish_card(message):
        context = await get_owner_context(message)
        if not context:
            return True
        character, housing = context
        interiors = await get_housing_interiors(character[0])
        kwargs = {
            "message": "📡 ВЛАДЕЛЕЦ ПОКАЗЫВАЕТ КАЮТУ\n\n"
            + format_public_housing_card(character, housing, interiors, HOUSING_NAMES, sci_line)
        }
        cover = get_housing_cover_item(interiors)
        if cover and stabilize_attachments and cover.get("local_image"):
            attachment = await stabilize_attachments(bot, cover.get("photo"), message.peer_id, cover.get("local_image"))
            if attachment:
                kwargs["attachment"] = attachment
        await message.answer(**kwargs)
        return True

    @bot.on.message(text="🏠 Каюта")
    async def housing_menu_handler(message):
        await message.answer(
            "◢ ЖИЛОЙ ТЕРМИНАЛ ◣\n"
            f"{sci_line()}\n\n"
            "Здесь можно посмотреть свою каюту, управлять интерьером и оплатить аренду.",
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
        capacity = HOUSING_CLASS_CAPACITY.get(housing_class, 1)
        interiors = await get_housing_interiors(character[0])
        used_slots = len(set(get_used_slots(interiors)))

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
            f"🧩 Интерьер: {used_slots} / {capacity} слотов\n"
            f"💳 Аренда: {weekly_rent} CR / неделя\n\n"
            f"{payment_info}",
            keyboard=housing_menu.get_json()
        )

    @bot.on.message(text="🛋 Интерьер")
    async def interior_button_handler(message):
        await show_owner_screen(message)

    @bot.on.message(text="📦 Мои комплекты")
    async def sets_inventory_handler(message):
        await show_sets_inventory(message)

    @bot.on.message(text="🪑 Установить комплект")
    async def install_help_handler(message):
        await show_sets_inventory(message)

    @bot.on.message(text="↩️ Снять комплект")
    async def remove_help_handler(message):
        await show_installed_for_removal(message)

    @bot.on.message(text="✏️ Описание каюты")
    async def description_help_handler(message):
        await message.answer(
            "✏️ ОПИСАНИЕ КАЮТЫ\n"
            f"{sci_line()}\n\n"
            "Задайте атмосферное описание командой:\n"
            "/описаниекаюты Ваш текст\n\n"
            "Очистить описание:\n"
            "/описаниекаюты сброс\n\n"
            "Максимум: 700 символов.",
            keyboard=interior_menu.get_json(),
        )

    @bot.on.message(text="🌐 Публичность")
    async def visibility_handler(message):
        await toggle_visibility(message)

    @bot.on.message(text="📡 Показать каюту")
    async def publish_button_handler(message):
        await publish_card(message)

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

        ok, reason, value = await pay_rent(message.from_id, character[0], now, WEEK_SECONDS)
        if not ok:
            text = ("Аренда уже оплачена." if reason == "cooldown"
                    else "Оплата не выполнена: проверьте баланс и назначенную каюту.")
            await message.answer(text, keyboard=housing_menu.get_json())
            return
        rent = value

        updated_user = await get_user(message.from_id)

        await message.answer(
            "🟢 АРЕНДА ОПЛАЧЕНА\n"
            f"{sci_line()}\n\n"
            f"🏠 Жильё: {HOUSING_NAMES.get(housing_class, housing_class)}\n"
            f"💳 Списано: {rent} CR\n"
            f"💰 Баланс: {updated_user[1]} CR",
            keyboard=housing_menu.get_json()
        )

    return {
        "show_owner_screen": show_owner_screen,
        "show_guest": show_guest,
        "show_sets_inventory": show_sets_inventory,
        "show_installed_for_removal": show_installed_for_removal,
        "install_by_number": install_by_number,
        "remove_by_number": remove_by_number,
        "set_description": set_description,
        "publish_card": publish_card,
    }


async def handle_housing_command(message, runtime):
    text = (message.text or "").strip()
    lower = text.casefold()

    if lower in {"/каюта", "/интерьер"}:
        return await runtime["show_owner_screen"](message)

    if lower.startswith("/каюта "):
        return await runtime["show_guest"](message, text.split(maxsplit=1)[1])

    if lower.startswith("/установитькомплект"):
        parts = text.split(maxsplit=1)
        number = parts[1] if len(parts) > 1 else None
        return await runtime["install_by_number"](message, number)

    if lower.startswith("/снятькомплект"):
        parts = text.split(maxsplit=1)
        number = parts[1] if len(parts) > 1 else None
        return await runtime["remove_by_number"](message, number)

    if lower.startswith("/описаниекаюты"):
        parts = text.split(maxsplit=1)
        description = parts[1] if len(parts) > 1 else ""
        return await runtime["set_description"](message, description)

    if lower == "/показатькаюту":
        return await runtime["publish_card"](message)

    return False
