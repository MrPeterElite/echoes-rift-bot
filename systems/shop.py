import json
from pathlib import Path


SHOP_CATEGORIES = {
    "🍽 Продовольствие": "food",
    "💊 Медикаменты": "medicine",
    "🛠 Инструменты": "tools",
}


def load_shop_items():
    paths = [
        Path(__file__).resolve().parent.parent / "shop_items.json",
        Path(__file__).resolve().parent.parent / "data" / "shop_items.json",
        Path("data") / "shop_items.json",
        Path("shop_items.json"),
    ]
    for path in paths:
        if path.exists():
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
    return {}


def get_items_by_category(category_code):
    return load_shop_items().get(category_code, {}).get("items", [])


def format_item(item, index, total, sci_line):
    return (
        f"{item.get('rarity', '⚪ Обычный')}\n"
        f"{item['name']}\n"
        f"{sci_line()}\n\n"
        f"💳 Цена: {item['price']} CR\n\n"
        f"{item.get('description', '')}\n\n"
        f"Товар {index + 1} из {total}"
    )


def register_shop_handlers(bot, deps):
    Keyboard = deps["Keyboard"]
    KeyboardButtonColor = deps["KeyboardButtonColor"]
    Text = deps["Text"]
    sci_line = deps["sci_line"]
    get_character_by_user = deps["get_character_by_user"]
    create_user = deps["create_user"]
    get_user = deps["get_user"]
    subtract_balance = deps["subtract_balance"]
    add_inventory_item = deps["add_inventory_item"]
    stabilize_attachments = deps["stabilize_attachments"]

    # user_id -> {category: str, index: int}
    sessions = {}

    shop_menu = (
        Keyboard(one_time=False)
        .add(Text("🍽 Продовольствие"), color=KeyboardButtonColor.POSITIVE)
        .add(Text("💊 Медикаменты"), color=KeyboardButtonColor.POSITIVE)
        .row()
        .add(Text("🛠 Инструменты"), color=KeyboardButtonColor.PRIMARY)
        .row()
        .add(Text("⬅️ Назад"), color=KeyboardButtonColor.SECONDARY)
    )

    def item_keyboard():
        return (
            Keyboard(one_time=False)
            .add(Text("⬅️ Предыдущий"), color=KeyboardButtonColor.SECONDARY)
            .add(Text("🛒 Купить"), color=KeyboardButtonColor.POSITIVE)
            .add(Text("➡️ Следующий"), color=KeyboardButtonColor.SECONDARY)
            .row()
            .add(Text("📂 Категории"), color=KeyboardButtonColor.PRIMARY)
        )

    async def require_private(message):
        if message.peer_id >= 2_000_000_000:
            await message.answer("🛒 Магазин доступен только в личных сообщениях бота.")
            return False
        return True

    async def send_shop_main(message):
        if not await require_private(message):
            return
        await message.answer(
            "◢ ТОРГОВЫЙ ТЕРМИНАЛ ◣\n"
            f"{sci_line()}\n\n"
            "Выберите раздел магазина.",
            keyboard=shop_menu.get_json(),
        )

    async def show_item(message, category_code, index):
        if not await require_private(message):
            return
        items = get_items_by_category(category_code)
        if not items:
            title = load_shop_items().get(category_code, {}).get("title", "Раздел")
            await message.answer(
                f"{title}\n{sci_line()}\n\nТовары в этом разделе пока не добавлены.",
                keyboard=shop_menu.get_json(),
            )
            return

        index %= len(items)
        sessions[message.from_id] = {"category": category_code, "index": index}
        item = items[index]
        kwargs = {
            "message": format_item(item, index, len(items), sci_line),
            "keyboard": item_keyboard().get_json(),
        }
        if item.get("photo"):
            stable_photo = await stabilize_attachments(bot, item["photo"], message.peer_id, item.get("local_image"))
            kwargs["attachment"] = stable_photo or item["photo"]
        await message.answer(**kwargs)

    async def buy_current(message, quantity=1):
        session = sessions.get(message.from_id)
        if not session:
            await message.answer("Сначала откройте магазин и выберите товар.")
            return True

        items = get_items_by_category(session["category"])
        if not items:
            await message.answer("В этом разделе нет товаров.")
            return True
        item = items[session["index"] % len(items)]

        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            quantity = 1
        if quantity <= 0:
            await message.answer("Количество должно быть больше нуля.")
            return True

        character = await get_character_by_user(message.from_id)
        if not character:
            await message.answer("Персонаж не найден.")
            return True
        if character[10] != "approved":
            await message.answer("Покупки доступны только после одобрения квенты.")
            return True

        await create_user(message.from_id)
        user = await get_user(message.from_id)
        total = item["price"] * quantity
        if user[1] < total:
            await message.answer(
                f"Недостаточно средств.\nСтоимость: {total} CR\nВаш баланс: {user[1]} CR"
            )
            return True

        await subtract_balance(message.from_id, total)
        await add_inventory_item(character[0], item["category"], item["name"], quantity)
        item_emoji = {
            "Сухпаёк": "🍱",
            "Бутылка воды": "💧",
            "Синт-кофе": "☕",
            "Протеиновый батончик": "🍫",
            "Горячий обед станции": "🍲",
            "Лапша быстрого приготовления": "🍜",
            "Ореховая смесь": "🥜",
            "Энергетический напиток": "⚡",
            "Вакуумный сэндвич": "🥪",
            "Колониальный чай": "🍵",
            "Фрукты колонии": "🍎",
            "Мясной набор колонии": "🍖",
            "Пепельный напиток": "🥃",
            "Разломный концентрат": "🥃",
            "Бинт": "🩹",
            "Обезболивающее": "💊",
            "Гемостатик": "🩸",
            "Стимулятор": "💉",
            "Антирад": "☢️",
            "Адреналиновый автоинъектор": "💉",
            "Полевой медицинский комплект": "🧰",
            "Автоинъектор «Феникс»": "💉",
            "Универсальный ключ": "🔧",
            "Промышленный фонарь": "🔦",
            "Набор инструментов": "🪛",
            "Плазменный резак": "🔥",
            "Сварочный аппарат": "⚡",
        }.get(item["name"], "🎒")

        quantity_text = f" ×{quantity}" if quantity > 1 else ""
        await message.answer(
            f"✅ Куплено: {item_emoji} {item['name']}{quantity_text}\n"
            f"💳 -{total} CR",
            keyboard=item_keyboard().get_json(),
        )
        return True

    @bot.on.message(text="🛒 Магазин")
    async def shop_handler(message):
        await send_shop_main(message)

    @bot.on.message(text="📂 Категории")
    async def categories_handler(message):
        await send_shop_main(message)

    @bot.on.message(text=list(SHOP_CATEGORIES.keys()))
    async def category_handler(message):
        await show_item(message, SHOP_CATEGORIES[message.text], 0)

    @bot.on.message(text="➡️ Следующий")
    async def next_handler(message):
        session = sessions.get(message.from_id)
        if not session:
            await send_shop_main(message)
            return
        await show_item(message, session["category"], session["index"] + 1)

    @bot.on.message(text="⬅️ Предыдущий")
    async def previous_handler(message):
        session = sessions.get(message.from_id)
        if not session:
            await send_shop_main(message)
            return
        await show_item(message, session["category"], session["index"] - 1)

    @bot.on.message(text="🛒 Купить")
    async def buy_button_handler(message):
        await buy_current(message, 1)

    return {
        "buy_current": buy_current,
        "show_item": show_item,
        "sessions": sessions,
    }


async def handle_shop_command(message, deps):
    text = (message.text or "").strip()
    if not text.startswith("/купить"):
        return False

    parts = text.split()
    quantity = parts[1] if len(parts) > 1 else 1
    return await deps["buy_current"](message, quantity)
