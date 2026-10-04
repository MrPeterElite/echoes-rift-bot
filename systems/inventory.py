import json
import random
import secrets
import time
import database as db
from vkbottle import Keyboard, Text, KeyboardButtonColor
from systems.vitals import use_health_item
from systems.armor import list_armor
from systems.weapons import list_weapons
from systems.item_effects import describe_effect
from systems import duels
from pathlib import Path


CATEGORIES = {
    "food": "🍽 Продовольствие",
    "medicine": "💊 Медикаменты",
    "tools": "🛠 Инструменты",
    "furniture": "🪑 Интерьер каюты",
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
    text += "\n/предмет номер — описание и эффекты\n/использовать номер\n/уничтожитьпредмет номер количество\n/передатьпредмет ID номер количество"
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

    pending_uses = {}

    async def allowed_location(message, character):
        if message.peer_id == message.from_id:
            return True
        location = await db.get_location_by_peer(message.peer_id)
        current = await db.get_character_location(character[0])
        if not location or not current or location[0] != current[0]:
            await message.answer("Используйте предмет в ЛС или в своей текущей RP-локации.")
            return False
        return True

    async def apply_health_item(message, character, item, expected=None):
        result = await use_health_item(message.from_id, character[0], item, int(time.time()), expected)
        status = result['status']
        if status == 'confirm':
            token = secrets.token_hex(4)
            pending_uses[message.from_id] = dict(token=token, peer=message.peer_id, cid=character[0],
                item=item, quote=result['quote'], expires=int(time.time())+60)
            effect = item['effect']['type']
            details = (f"Новый запас еды: {result['target']} HP; прирост +{result['gain']}."
                       if effect=='food_hp' else f"Восстановится только {result['gain']} HP; здоровье станет {result['target']}.")
            keyboard = (Keyboard(inline=True)
                        .add(Text("✅ Использовать предмет", payload={"use_token":token}), color=KeyboardButtonColor.POSITIVE)
                        .row().add(Text("❌ Отменить использование"), color=KeyboardButtonColor.SECONDARY))
            await message.answer(f"{item['name']}: {details}\nБудет потрачена одна единица. Подтверждение действует минуту.",
                                 keyboard=keyboard.get_json())
            return
        if status != 'ok':
            errors = {
                'duel_only':'В дуэли используйте кнопку лечения в /дуель: лечение расходует ход.',
                'invalid_character':'Нужна ваша одобренная квента.',
                'incapacitated':'При 0 HP требуется помощь ведущего; предмет не потрачен.',
                'in_combat':'Во время сцены нельзя обновлять запас еды.',
                'not_stronger':'У вас уже есть такой же или больший запас еды. Предмет не потрачен.',
                'full_hp':'Здоровье полное. Предмет не потрачен.',
                'limit':'Лимит лечения исчерпан. Предмет не потрачен.',
                'missing_item':'Предмета уже нет в инвентаре.',
            }
            await message.answer(errors.get(status,'Не удалось применить эффект. Предмет не потрачен.'))
            return
        after = result['after']
        rp = random.choice(item.get('messages') or ['{name} использует предмет.']).replace('{name}',character[2])
        details = (f"🍽 Запас еды: +{after['food_hp']} HP на 30 минут."
                   if item['effect']['type']=='food_hp' else
                   f"❤️ +{result['gain']} HP · {result['before']['hp']} → {after['hp']}/{after['max_hp']}")
        await message.answer(rp+'\n'+details)

    @bot.on.message(text="/предмет <number>")
    async def inspect_item(message, number=None):
        character = await get_character_by_user(message.from_id)
        if not character:
            await message.answer("Персонаж не найден.")
            return
        row = get_item_by_inventory_number(await get_inventory(character[0]),number)
        if not row:
            await message.answer("Предмет с таким номером не найден.")
            return
        item = find_catalog_item(row[1])
        if not item:
            await message.answer(f"{row[1]} ×{row[2]} — описание отсутствует.")
            return
        await message.answer(f"{item['name']} ×{row[2]}\n{item.get('description','')}\n\n{describe_effect(item)}")

    @bot.on.message(text="/подтвердитьпредмет <token>")
    async def confirm_item(message, token=None):
        pending = pending_uses.get(message.from_id)
        if not pending or pending['token'] != token or pending['peer'] != message.peer_id:
            await message.answer("Подтверждение не найдено. Используйте предмет заново.")
            return
        pending_uses.pop(message.from_id, None)
        if pending['expires'] <= int(time.time()):
            await message.answer("Подтверждение истекло. Используйте предмет заново.")
            return
        character = await get_character_by_user(message.from_id)
        if not character or character[0] != pending['cid']:
            await message.answer("Персонаж изменился. Использование отменено.")
            return
        if await allowed_location(message,character):
            await apply_health_item(message,character,pending['item'],pending['quote'])

    @bot.on.message(text="✅ Использовать предмет")
    async def confirm_item_button(message):
        try:
            payload = getattr(message, 'payload', None) or {}
            if isinstance(payload, str):
                payload = json.loads(payload)
            token = payload.get('use_token') if isinstance(payload, dict) else None
        except (TypeError, ValueError):
            token = None
        await confirm_item(message, token)

    @bot.on.message(text=["/отменитьпредмет", "❌ Отменить использование"])
    async def cancel_item(message):
        pending_uses.pop(message.from_id,None)
        await message.answer("Использование отменено. Предмет не потрачен.")

    @bot.on.message(text="/инвентарь")
    async def inventory_handler(message):
        character = await get_character_by_user(message.from_id)
        if not character:
            await message.answer("Персонаж не найден.")
            return
        armor = await list_armor(character[0])
        extra = f"\n\n🛡 Бронежилетов: {len(armor)}. Открыть: /бронежилеты" if armor else ""
        weapons = await list_weapons(character[0])
        if weapons:extra += f'\n🔫 Оружия: {len(weapons)}. Открыть: /оружие'
        await message.answer(format_inventory(character, await get_inventory(character[0]), sci_line)+extra)

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
        pending_uses.pop(message.from_id,None)
        if catalog_item and catalog_item.get('effect',{}).get('type') in ('food_hp','heal'):
            if await allowed_location(message,character):
                await apply_health_item(message,character,catalog_item)
            return
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
        if catalog_item and catalog_item.get("effect",{}).get("type") == "rp":
            rp_text += "\n🎭 Только RP: игровые показатели не изменены."
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
        if quantity <= 0:
            await message.answer("Количество должно быть больше нуля.")
            return
        receiver = await get_character_by_id(character_id)
        if not receiver:
            await message.answer("Квента получателя не найдена.")
            return
        inv_item = get_item_by_inventory_number(await get_inventory(sender[0]), number)
        if not inv_item:
            await message.answer("Предмет с таким номером не найден.")
            return
        category, item_name, _ = inv_item
        catalog_item = find_catalog_item(item_name)
        if category in {"food", "medicine", "armor", "weapons"}:
            await duels.refresh_character_scene(sender[0], int(time.time()))
            await duels.refresh_character_scene(receiver[0], int(time.time()))
        if catalog_item and not catalog_item.get("transferable", True):
            await message.answer("Этот предмет нельзя передавать.")
            return
        ok, reason = await transfer_inventory_item(sender[0], receiver[0], item_name, quantity)
        if not ok:
            if reason == "in_combat":
                await message.answer(
                    "⛔ Боевые расходники нельзя передавать во время активной боевой сцены.\n"
                    "В бой допускаются только предметы, которые были у участников заранее."
                )
            else:
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
