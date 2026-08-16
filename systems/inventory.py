import json
import random
from pathlib import Path


CATEGORIES = {
    "food": "🍽 Продовольствие",
    "medicine": "💊 Медикаменты",
    "tools": "🛠 Инструменты",
}


def load_item_catalog():
    paths = [
        Path(__file__).resolve().parent.parent / "shop_items.json",
        Path(__file__).resolve().parent.parent / "data" / "shop_items.json",
    ]
    for path in paths:
        if path.exists():
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
    return {}


def find_catalog_item(item_name):
    query = str(item_name).casefold().replace("ё", "е")
    for category in load_item_catalog().values():
        for item in category.get("items", []):
            name = str(item.get("name", "")).casefold().replace("ё", "е")
            if name == query:
                return item
    return None


def format_inventory(character, items, sci_line):
    text = "◢ ИНВЕНТАРЬ ◣\n"
    text += f"{sci_line()}\n\n"
    text += f"🧬 Персонаж: {character[2]}\n\n"
    if not items:
        return text + "Инвентарь пуст."
    for index, row in enumerate(items, start=1):
        category, item_name, quantity = row
        text += f"{index}. {item_name} ×{quantity} — {CATEGORIES.get(category, category)}\n"
    text += "\n/использовать номер\n/уничтожитьпредмет номер количество\n/передатьпредмет ID номер количество"
    return text


def get_item_by_inventory_number(items, number):
    try:
        number = int(number)
    except (TypeError, ValueError):
        return None
    if number < 1 or number > len(items):
        return None
    return items[number - 1]


def register_inventory_handlers(bot, deps):
    get_character_by_user = deps["get_character_by_user"]
    get_character_by_id = deps["get_character_by_id"]
    get_inventory = deps["get_inventory"]
    remove_inventory_item = deps["remove_inventory_item"]
    transfer_inventory_item = deps["transfer_inventory_item"]
    sci_line = deps["sci_line"]
    ADMIN_CHAT_ID = deps["ADMIN_CHAT_ID"]

    @bot.on.message(text="/инвентарь")
    async def inventory_handler(message):
        character = await get_character_by_user(message.from_id)
        if not character:
            await message.answer("Персонаж не найден.")
            return
        await message.answer(format_inventory(character, await get_inventory(character[0]), sci_line))

    @bot.on.message(text="/использовать <number>")
    async def use_item_handler(message, number=None):
        character = await get_character_by_user(message.from_id)
        if not character:
            await message.answer("Персонаж не найден.")
            return
        items = await get_inventory(character[0])
        inv_item = get_item_by_inventory_number(items, number)
        if not inv_item:
            await message.answer("Предмет с таким номером не найден.")
            return

        category, item_name, quantity = inv_item
        catalog_item = find_catalog_item(item_name)
        if catalog_item and not catalog_item.get("usable", False):
            await message.answer("Этот предмет нельзя использовать.")
            return

        # Расходники списываются после использования. Постоянные инструменты остаются в инвентаре.
        if (catalog_item or {}).get("consumable", True):
            ok, _ = await remove_inventory_item(character[0], item_name, 1)
            if not ok:
                await message.answer("Не удалось использовать предмет.")
                return

        special_use_message = (catalog_item or {}).get("special_use_message")
        if special_use_message:
            rp_text = special_use_message.replace("{name}", character[2])
        else:
            messages = (catalog_item or {}).get("messages") or ["🎒 {name} использует предмет: " + item_name + "."]
            rp_text = random.choice(messages).replace("{name}", character[2])

        # В игровой чат отправляется только RP-текст, без фотографии предмета.
        await message.answer(rp_text)

    @bot.on.message(text="/уничтожитьпредмет <number>")
    async def destroy_one_handler(message, number=None):
        await destroy_item(message, number, 1)

    @bot.on.message(text="/уничтожитьпредмет <number> <quantity>")
    async def destroy_many_handler(message, number=None, quantity=None):
        await destroy_item(message, number, quantity)

    async def destroy_item(message, number, quantity):
        character = await get_character_by_user(message.from_id)
        if not character:
            await message.answer("Персонаж не найден.")
            return
        inv_item = get_item_by_inventory_number(await get_inventory(character[0]), number)
        if not inv_item:
            await message.answer("Предмет с таким номером не найден.")
            return
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            quantity = 1
        if quantity <= 0:
            await message.answer("Количество должно быть больше нуля.")
            return
        _, item_name, _ = inv_item
        ok, reason = await remove_inventory_item(character[0], item_name, quantity)
        if not ok:
            await message.answer("У вас недостаточно таких предметов." if reason == "not_enough" else "Предмет не найден.")
            return
        await message.answer(f"🗑 ПРЕДМЕТ УНИЧТОЖЕН\n{sci_line()}\n\n🎒 {item_name}\n📦 Количество: {quantity}")

    @bot.on.message(text="/передатьпредмет <character_id> <number> <quantity>")
    async def transfer_item_handler(message, character_id=None, number=None, quantity=None):
        sender = await get_character_by_user(message.from_id)
        if not sender:
            await message.answer("Персонаж не найден.")
            return
        try:
            character_id, quantity = int(character_id), int(quantity)
        except (TypeError, ValueError):
            await message.answer("Использование: /передатьпредмет ID номер количество")
            return
        receiver = await get_character_by_id(character_id)
        if not receiver:
            await message.answer("Квента получателя не найдена.")
            return
        inv_item = get_item_by_inventory_number(await get_inventory(sender[0]), number)
        if not inv_item:
            await message.answer("Предмет с таким номером не найден.")
            return
        _, item_name, _ = inv_item
        catalog_item = find_catalog_item(item_name)
        if catalog_item and not catalog_item.get("transferable", True):
            await message.answer("Этот предмет нельзя передавать.")
            return
        ok, reason = await transfer_inventory_item(sender[0], receiver[0], item_name, quantity)
        if not ok:
            await message.answer("У вас недостаточно таких предметов." if reason == "not_enough" else "У вас нет такого предмета.")
            return
        await message.answer(
            f"🟢 ПРЕДМЕТ ПЕРЕДАН\n{sci_line()}\n\n"
            f"👤 Получатель: #{receiver[0]} — {receiver[2]}\n🎒 {item_name}\n📦 Количество: {quantity}"
        )

    @bot.on.message(text="/предметы <character_id>")
    async def admin_inventory_handler(message, character_id=None):
        if message.peer_id != ADMIN_CHAT_ID:
            return
        try:
            character_id = int(character_id)
        except (TypeError, ValueError):
            await message.answer("Использование: /предметы ID")
            return
        character = await get_character_by_id(character_id)
        if not character:
            await message.answer("Квента не найдена.")
            return
        await message.answer(format_inventory(character, await get_inventory(character_id), sci_line))
