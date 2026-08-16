from vkbottle.bot import Bot, Message
from vkbottle import Keyboard, KeyboardButtonColor, Text
from dotenv import load_dotenv
import os
import asyncio
import time

from database import (
    create_tables,
    create_user,
    get_user,
    reset_user,
    create_character,
    get_character_by_user,
    get_character_by_id,
    update_character_status,
    get_approved_characters,
    ensure_career_columns,
    update_character_job,
    update_last_salary,
    add_balance,
    ensure_faction_rank_columns,
    update_faction_rank,
    ensure_quest_tables,
    get_current_quest,
    get_last_quest,
    create_weekly_quest,
    submit_quest_report,
    get_quest_by_id,
    update_quest_status,
    add_xp,
    ensure_housing_tables,
    get_housing,
    assign_housing,
    remove_housing,
    update_housing_sector,
    update_housing_class,
    update_housing_payment,
    subtract_balance,
    ensure_location_tables,
    get_all_locations,
    get_location_by_code,
    get_location_by_peer,
    get_character_location,
    set_character_location,
    transfer_balance,
    get_top_richest,
    get_character_user_id,
    set_balance,
    get_characters_in_location,
    ensure_inventory_tables,
    get_inventory,
    add_inventory_item,
    remove_inventory_item,
    find_inventory_item,
    transfer_inventory_item,
    update_character_arts
)

from systems.characters import register_characters_handlers
from systems.careers import register_careers_handlers
from systems.economy import register_economy_handlers
from systems.locations import register_locations_handlers
from systems.housing import register_housing_handlers
from systems.factions import register_factions_handlers
from systems.rp import handle_rp_command
from systems.inventory import register_inventory_handlers
from systems.shop import register_shop_handlers, handle_shop_command
from systems.quests import register_quest_handlers
from systems.help import register_help_handlers
from systems.media import stabilize_attachments

load_dotenv()

# Токен VK. На разных хостингах он может приходить под разными именами.
# Некоторые панели сохраняют значение в виде "VK_TOKEN=vk1.a...", поэтому
# перед передачей в VKBottle нормализуем строку.
def _normalize_vk_token(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip().strip('"').strip("'")
    # Убираем ошибочно добавленное имя переменной из значения.
    for prefix in ("VK_TOKEN=", "BOT_TOKEN=", "VK_BOT_TOKEN=", "API_TOKEN=", "TOKEN="):
        if value.startswith(prefix):
            value = value[len(prefix):].strip()
            break
    return value

_token_sources = (
    ("VK_TOKEN", os.getenv("VK_TOKEN")),
    ("BOT_TOKEN", os.getenv("BOT_TOKEN")),
    ("VK_BOT_TOKEN", os.getenv("VK_BOT_TOKEN")),
    ("TOKEN", os.getenv("TOKEN")),
    ("API_TOKEN", os.getenv("API_TOKEN")),
)

TOKEN = ""
TOKEN_SOURCE = ""
for _name, _value in _token_sources:
    _candidate = _normalize_vk_token(_value)
    if _candidate:
        TOKEN = _candidate
        TOKEN_SOURCE = _name
        break

if not TOKEN:
    raise RuntimeError(
        "Не найден токен VK. Укажите VK_TOKEN, BOT_TOKEN или TOKEN в переменных окружения."
    )

# В лог выводится только источник, сам секрет никогда не печатается.
print(f"[config] VK token source: {TOKEN_SOURCE}")

# Текущий административный чат проекта. Значение можно переопределить
# переменной ADMIN_CHAT_ID на хостинге.
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "2000000001"))

bot = Bot(token=TOKEN)

drafts = {}
archive_users = set()


main_menu = (
    Keyboard(one_time=False)
    .add(Text("👤 Профиль"), color=KeyboardButtonColor.PRIMARY)
    .add(Text("📜 Квенты"), color=KeyboardButtonColor.POSITIVE)
    .row()
    .add(Text("💼 Карьера"), color=KeyboardButtonColor.SECONDARY)
    .add(Text("🏛 Фракции"), color=KeyboardButtonColor.SECONDARY)
    .row()
    .add(Text("🏠 Каюта"), color=KeyboardButtonColor.POSITIVE)
    .add(Text("🛒 Магазин"), color=KeyboardButtonColor.POSITIVE)
)

housing_menu = (
    Keyboard(one_time=False)
    .add(Text("🏠 Моя каюта"), color=KeyboardButtonColor.PRIMARY)
    .add(Text("💳 Оплатить аренду"), color=KeyboardButtonColor.POSITIVE)
    .row()
    .add(Text("⬅️ Назад"), color=KeyboardButtonColor.SECONDARY)
)


quenta_menu = (
    Keyboard(one_time=False)
    .add(Text("📜 Создать квенту"), color=KeyboardButtonColor.POSITIVE)
    .add(Text("📚 Архив квент"), color=KeyboardButtonColor.PRIMARY)
    .row()
    .add(Text("🗑 Удалить персонажа"), color=KeyboardButtonColor.NEGATIVE)
    .add(Text("⬅️ Назад"), color=KeyboardButtonColor.SECONDARY)
)

career_menu = (
    Keyboard(one_time=False)
    .add(Text("📋 Моя должность"), color=KeyboardButtonColor.PRIMARY)
    .add(Text("💳 Получить зарплату"), color=KeyboardButtonColor.POSITIVE)
    .row()
    .add(Text("📌 Задание"), color=KeyboardButtonColor.PRIMARY)
    .add(Text("📨 Сдать отчёт"), color=KeyboardButtonColor.POSITIVE)
    .row()
    .add(Text("⬅️ Назад"), color=KeyboardButtonColor.SECONDARY)
)

faction_keyboard = (
    Keyboard(one_time=True)
    .add(Text("🛡️ ЗЕМНАЯ ДИРЕКТОРИЯ"), color=KeyboardButtonColor.PRIMARY)
    .row()
    .add(Text("⚙️ HELIOS DYNAMICS"), color=KeyboardButtonColor.PRIMARY)
    .row()
    .add(Text("🕯️ ОРДЕН ЗАВЕСЫ"), color=KeyboardButtonColor.PRIMARY)
    .row()
    .add(Text("🔥 КУЛЬТ ПЕПЕЛЬНОГО ОТКРОВЕНИЯ"), color=KeyboardButtonColor.NEGATIVE)
    .row()
    .add(Text("🚫 Без фракции"), color=KeyboardButtonColor.SECONDARY)
)

done_arts_keyboard = (
    Keyboard(one_time=False)
    .add(Text("✅ Готово"), color=KeyboardButtonColor.POSITIVE)
    .add(Text("🔄 Начать заново"), color=KeyboardButtonColor.NEGATIVE)
)

FACTION_ARTS = {
    "🛡️ ЗЕМНАЯ ДИРЕКТОРИЯ": "photo1087549445_457239184_8be8474942627563a1",
    "⚙️ HELIOS DYNAMICS": "photo1087549445_457239185_06ce2aa16538ecb429",
    "🕯️ ОРДЕН ЗАВЕСЫ": "photo1087549445_457239186_28623635beafdca140",
    "🔥 КУЛЬТ ПЕПЕЛЬНОГО ОТКРОВЕНИЯ": "photo1087549445_457239188_d321f88558bb660cff",
}

FACTION_DESCRIPTIONS = {
    "🛡️ ЗЕМНАЯ ДИРЕКТОРИЯ": (
        "Центральная структура Земли.\n"
        "Контроль, порядок, безопасность и власть."
    ),
    "⚙️ HELIOS DYNAMICS": (
        "Технологический гигант.\n"
        "Исследования Разлома, кибернетика и прогресс."
    ),
    "🕯️ ОРДЕН ЗАВЕСЫ": (
        "Таинственный орден.\n"
        "Завеса, аномалии, древние знания и скрытая истина."
    ),
    "🔥 КУЛЬТ ПЕПЕЛЬНОГО ОТКРОВЕНИЯ": (
        "Радикальный культ.\n"
        "Пепел, перерождение, фанатизм и очищение через Разлом."
    ),
    "🚫 Без фракции": (
        "Одиночки, наёмники, гражданские и независимые выжившие."
    )
}

HOUSING_PRICES = {
    "V": 125,
    "IV": 350,
    "III": 900,
    "II": 1500,
    "I": 0
}

HOUSING_NAMES = {
    "V": "🛌 Каюта V класса",
    "IV": "🛋️ Каюта IV класса",
    "III": "🏢 Каюта III класса",
    "II": "👑 Каюта II класса",
    "I": "🏛️ Апартаменты I класса"
}


SALARY_BY_LEVEL = {
    1: 150,
    2: 300,
    3: 550,
    4: 1000,
    5: 1500
}


DEPARTMENTS = {
    "безопасность": {
        "name": "🛡️ Комитет службы безопасности",
        "jobs": ["Кадет", "Оперативник", "Инспектор", "Глава службы безопасности"]
    },
    "медицина": {
        "name": "🚑 Медицинская служба",
        "jobs": ["Санитар", "Медсестра", "Ординатор", "Врач", "Глава медицинского отдела"]
    },
    "наука": {
        "name": "🔬 Комитет научных исследований",
        "jobs": ["Лаборант", "Исследователь", "Научный специалист", "Глава научного отдела"]
    },
    "админ": {
        "name": "🏛️ Административный корпус",
        "jobs": ["Модератор", "Администратор", "Глава административного корпуса"]
    },
    "инженерия": {
        "name": "⚙️ Инженерный отдел",
        "jobs": ["Рабочий", "Инженер", "Старший инженер", "Глава инженерного корпуса"]
    },
    "разведка": {
        "name": "🕶️ Служба разведки и наёмников",
        "jobs": ["Скаут", "Наёмник широкого профиля", "Наёмник узкого профиля", "Лидер наёмников"]
    },
    "пепел": {
        "name": "🔥 Проповедники Пепла",
        "jobs": ["Монах", "Священник", "Кардинал", "Камерарий", "Викарий"]
    }
}

WEEK_SECONDS = 7 * 24 * 60 * 60


DEPARTMENT_CODES_TEXT = (
    "безопасность — 🛡️ Комитет службы безопасности\n"
    "медицина — 🚑 Медицинская служба\n"
    "наука — 🔬 Комитет научных исследований\n"
    "админ — 🏛️ Административный корпус\n"
    "инженерия — ⚙️ Инженерный отдел\n"
    "разведка — 🕶️ Служба разведки и наёмников\n"
    "пепел — 🔥 Проповедники Пепла"
)


FACTION_RANKS = {
    "🛡️ ЗЕМНАЯ ДИРЕКТОРИЯ": ["Рекрут Директории", "Агент Директории", "Старший агент", "Координатор сектора", "Комиссар Директории"],
    "⚙️ HELIOS DYNAMICS": ["Стажёр Helios", "Сотрудник Helios", "Старший специалист", "Куратор проекта", "Директор комплекса"],
    "🕯️ ОРДЕН ЗАВЕСЫ": ["Послушник Завесы", "Адепт Завесы", "Хранитель Завесы", "Архонт Завесы", "Провидец Завесы"],
    "🔥 КУЛЬТ ПЕПЕЛЬНОГО ОТКРОВЕНИЯ": ["Неофит Пепла", "Брат Пепла", "Глашатай Откровения", "Апостол Пепла", "Пророк Пепла"],
    "🚫 Без фракции": ["Гражданский", "Вольный житель", "Независимый агент", "Авторитет окраин", "Легенда Разлома"]
}


def format_faction_rank(character):
    rank = character[15] if len(character) > 15 else None
    return rank or "не назначен"


def sci_line():
    return "━━━━━━━━━━━━━━━━━━━━"


async def delete_message_from_chat(message: Message):
    try:
        await bot.api.messages.delete(
            peer_id=message.peer_id,
            cmids=[message.conversation_message_id],
            delete_for_all=True
        )
        return True
    except Exception:
        return False



register_inventory_handlers(
    bot,
    {
        "get_character_by_user": get_character_by_user,
        "get_character_by_id": get_character_by_id,
        "get_inventory": get_inventory,
        "add_inventory_item": add_inventory_item,
        "remove_inventory_item": remove_inventory_item,
        "transfer_inventory_item": transfer_inventory_item,
        "find_inventory_item": find_inventory_item,
        "sci_line": sci_line,
        "ADMIN_CHAT_ID": ADMIN_CHAT_ID,
    }
)


SHOP_RUNTIME = register_shop_handlers(
    bot,
    {
        "Keyboard": Keyboard,
        "KeyboardButtonColor": KeyboardButtonColor,
        "Text": Text,
        "sci_line": sci_line,
        "get_character_by_user": get_character_by_user,
        "create_user": create_user,
        "get_user": get_user,
        "subtract_balance": subtract_balance,
        "add_inventory_item": add_inventory_item,
        "stabilize_attachments": stabilize_attachments,
    }
)

SHOP_DEPS = {
    "buy_current": SHOP_RUNTIME["buy_current"],
}


RP_DEPS = {
    "get_character_by_user": get_character_by_user,
    "get_location_by_peer": get_location_by_peer,
    "get_character_location": get_character_location,
    "delete_message_from_chat": delete_message_from_chat,
    "sci_line": sci_line,
}


async def get_vk_name(user_id: int):
    try:
        users = await bot.api.users.get(user_ids=[user_id])
        user = users[0]
        return f"{user.first_name} {user.last_name}"
    except Exception:
        return f"id{user_id}"


def get_photo_attachment(message: Message):
    if not message.attachments:
        return None

    for attachment in message.attachments:
        if attachment.photo:
            photo = attachment.photo
            if photo.access_key:
                return f"photo{photo.owner_id}_{photo.id}_{photo.access_key}"
            return f"photo{photo.owner_id}_{photo.id}"

    return None


def format_status(status):
    return {
        "pending": "⏳ ОЖИДАЕТ ВЕРИФИКАЦИИ",
        "approved": "🟢 ВЕРИФИЦИРОВАН",
        "rejected": "🔴 ОТКЛОНЁН"
    }.get(status, status)


def get_department_key_by_name(department_name):
    for key, data in DEPARTMENTS.items():
        if data["name"] == department_name:
            return key
    return None


def get_salary_by_character(character):
    job_level = character[13] or 0
    return SALARY_BY_LEVEL.get(job_level, 0)


def format_career(character):
    department = character[11] or "не назначен"
    job_title = character[12] or "не назначена"
    job_level = character[13] or 0
    salary = SALARY_BY_LEVEL.get(job_level, 0)

    if job_level == 0:
        return (
            "📂 Отдел: не назначен\n"
            "💼 Должность: не назначена\n"
            "📈 Карьерный уровень: 0\n"
            "💳 Недельная зарплата: 0 CR"
        )

    return (
        f"📂 Отдел: {department}\n"
        f"💼 Должность: {job_title}\n"
        f"📈 Карьерный уровень: {job_level}\n"
        f"💳 Недельная зарплата: {salary} CR"
    )


def format_salary_cooldown(seconds_left):
    days = seconds_left // 86400
    hours = (seconds_left % 86400) // 3600
    minutes = (seconds_left % 3600) // 60

    if days > 0:
        return f"{days} дн. {hours} ч."
    if hours > 0:
        return f"{hours} ч. {minutes} мин."
    return f"{minutes} мин."


def format_character(character):
    arts = character[9].split(",") if character[9] else []

    return (
        f"◢ ECHOES OF THE RIFT [TRP] ◣\n"
        f"{sci_line()}\n"
        f"📡 ДОСЬЕ ПЕРСОНАЖА\n\n"
        f"🆔 Квента: #{character[0]}\n"
        f"👤 Имя: {character[2]}\n"
        f"🎂 Возраст: {character[3]}\n"
        f"⚧ Пол: {character[4]}\n"
        f"🏛 Фракция: {character[5]}\n"
        f"🎖 Ранг фракции: {format_faction_rank(character)}\n\n"
        f"🧬 БИОЛОГИЯ:\n{character[6]}\n\n"
        f"🧠 ХАРАКТЕР:\n{character[7]}\n\n"
        f"📖 ИСТОРИЯ:\n{character[8]}\n\n"
        f"🖼 Артов: {len(arts)} / 3\n"
        f"📌 Статус: {format_status(character[10])}\n"
        f"{sci_line()}"
    )


@bot.on.message(text="/attach")
async def attach_handler(message: Message):
    attachment = get_photo_attachment(message)

    if not attachment:
        await message.answer("Прикрепи картинку к сообщению и напиши /attach.")
        return

    await message.answer(f"Код картинки:\n\n{attachment}")


@bot.on.message(text="/peer")
async def peer_handler(message: Message):
    await message.answer(f"ID беседы: {message.peer_id}")


@bot.on.message(text="/старт")
async def start_handler(message: Message):
    await create_user(message.from_id)

    await message.answer(
        "🌌 ◢ ECHOES OF THE RIFT [TRP] ◣\n"
        f"{sci_line()}\n\n"
        "📡 Система активирована.\n"
        "Терминал синхронизирован.\n"
        "Доступ к основному интерфейсу открыт.\n\n"
        "Выберите раздел управления.",
        keyboard=main_menu.get_json()
    )


@bot.on.message(text="⬅️ Назад")
async def back_handler(message: Message):
    await message.answer(
        "◢ ГЛАВНЫЙ ТЕРМИНАЛ ◣\n\n"
        "Вы вернулись в основной интерфейс.",
        keyboard=main_menu.get_json()
    )


register_characters_handlers(
    bot,
    {
        "quenta_menu": quenta_menu,
        "sci_line": sci_line,
        "get_character_by_user": get_character_by_user,
        "drafts": drafts,
        "faction_keyboard": faction_keyboard,
        "FACTION_ARTS": FACTION_ARTS,
        "FACTION_DESCRIPTIONS": FACTION_DESCRIPTIONS,
        "reset_user": reset_user,
        "archive_users": archive_users,
        "get_approved_characters": get_approved_characters,
        "get_vk_name": get_vk_name,
        "done_arts_keyboard": done_arts_keyboard,
        "get_photo_attachment": get_photo_attachment,
        "create_character": create_character,
        "get_character_by_id": get_character_by_id,
        "Keyboard": Keyboard,
        "KeyboardButtonColor": KeyboardButtonColor,
        "Text": Text,
        "ADMIN_CHAT_ID": ADMIN_CHAT_ID,
        "format_character": format_character,
        "create_user": create_user,
        "get_user": get_user,
        "format_career": format_career,
        "main_menu": main_menu,
        "format_status": format_status,
        "stabilize_attachments": stabilize_attachments,
    }
)

register_careers_handlers(
    bot,
    {
        "sci_line": sci_line,
        "career_menu": career_menu,
        "get_character_by_user": get_character_by_user,
        "format_career": format_career,
        "create_user": create_user,
        "get_user": get_user,
        "WEEK_SECONDS": WEEK_SECONDS,
        "format_salary_cooldown": format_salary_cooldown,
        "SALARY_BY_LEVEL": SALARY_BY_LEVEL,
        "add_balance": add_balance,
        "update_last_salary": update_last_salary,
    }
)

register_quest_handlers(
    bot,
    {
        "get_character_by_user": get_character_by_user,
        "get_character_by_id": get_character_by_id,
        "get_current_quest": get_current_quest,
        "get_last_quest": get_last_quest,
        "create_weekly_quest": create_weekly_quest,
        "submit_quest_report": submit_quest_report,
        "get_quest_by_id": get_quest_by_id,
        "update_quest_status": update_quest_status,
        "add_balance": add_balance,
        "add_xp": add_xp,
        "get_photo_attachment": get_photo_attachment,
        "sci_line": sci_line,
        "career_menu": career_menu,
        "ADMIN_CHAT_ID": ADMIN_CHAT_ID,
        "WEEK_SECONDS": WEEK_SECONDS,
    }
)

register_economy_handlers(
    bot,
    {
        "get_top_richest": get_top_richest,
        "sci_line": sci_line,
        "get_character_by_user": get_character_by_user,
        "get_character_by_id": get_character_by_id,
        "create_user": create_user,
        "transfer_balance": transfer_balance,
        "get_user": get_user,
    }
)

register_locations_handlers(
    bot,
    {
        "get_all_locations": get_all_locations,
        "sci_line": sci_line,
        "get_character_by_user": get_character_by_user,
        "get_character_location": get_character_location,
        "get_location_by_code": get_location_by_code,
        "set_character_location": set_character_location,
        "delete_message_from_chat": delete_message_from_chat,
        "get_characters_in_location": get_characters_in_location,
        "get_location_by_peer": get_location_by_peer,
    }
)

register_housing_handlers(
    bot,
    {
        "get_character_by_user": get_character_by_user,
        "get_housing": get_housing,
        "HOUSING_NAMES": HOUSING_NAMES,
        "sci_line": sci_line,
        "housing_menu": housing_menu,
        "WEEK_SECONDS": WEEK_SECONDS,
        "format_salary_cooldown": format_salary_cooldown,
        "create_user": create_user,
        "get_user": get_user,
        "subtract_balance": subtract_balance,
        "update_housing_payment": update_housing_payment,
    }
)

register_factions_handlers(
    bot,
    {
        "sci_line": sci_line,
        "main_menu": main_menu,
        "FACTION_DESCRIPTIONS": FACTION_DESCRIPTIONS,
        "FACTION_ARTS": FACTION_ARTS,
        "stabilize_attachments": stabilize_attachments,
    }
)

register_help_handlers(
    bot,
    {
        "get_character_by_user": get_character_by_user,
        "sci_line": sci_line,
    }
)




@bot.on.message()
async def router_handler(message: Message):
    text = message.text or ""

    if await handle_shop_command(message, SHOP_DEPS):
        return

    if text.lower().strip().startswith("/старт"):
        await start_handler(message)
        return

    if await handle_rp_command(message, bot, RP_DEPS):
        return


    if not text.startswith("/"):
        chat_location = await get_location_by_peer(message.peer_id)
        if chat_location:
            character = await get_character_by_user(message.from_id)
            if character:
                current_location = await get_character_location(character[0])
                if current_location and current_location[0] != chat_location[0]:
                    # Новая система перемещения: игрок остаётся участником беседы,
                    # но сообщения вне текущей RP-локации удаляются. Никаких kick.
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
                                "Чтобы перейти сюда, используйте:\n"
                                f"/перейти {chat_location[0]}\n\n"
                                f"Ссылка на вашу текущую локацию:\n{current_location[3]}"
                            )
                        )
                    except Exception:
                        pass
                    return

    if message.peer_id == ADMIN_CHAT_ID:
        if text.startswith("/назначить "):
            parts = text.split()

            if len(parts) < 3:
                await message.answer(
                    "Использование:\n"
                    "/назначить ID отдел\n\n"
                    "Пример:\n"
                    "/назначить 1 наука"
                )
                return

            try:
                character_id = int(parts[1])
            except ValueError:
                await message.answer("Неверный ID квенты.")
                return

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
                return

            character = await get_character_by_id(character_id)

            if not character:
                await message.answer("Квента не найдена.")
                return

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
                f"🆔 Квента: #{character_id}\n"
                f"📂 Отдел: {department_name}\n"
                f"💼 Должность: {job_title}\n"
                f"💳 Зарплата: {salary} CR"
            )
            return

        if text.startswith("/повысить "):
            parts = text.split()

            if len(parts) < 2:
                await message.answer(
                    "Использование:\n"
                    "/повысить ID\n\n"
                    "Пример:\n"
                    "/повысить 4"
                )
                return

            try:
                character_id = int(parts[1])
            except ValueError:
                await message.answer("Неверный ID квенты.")
                return

            character = await get_character_by_id(character_id)

            if not character:
                await message.answer("Квента не найдена.")
                return

            department_name = character[11]
            current_level = character[13] or 0

            if not department_name or current_level == 0:
                await message.answer(
                    "Сначала назначьте отдел командой:\n"
                    "/назначить ID отдел"
                )
                return

            department_key = get_department_key_by_name(department_name)

            if not department_key:
                await message.answer("Не удалось определить отдел.")
                return

            jobs = DEPARTMENTS[department_key]["jobs"]

            if current_level >= len(jobs):
                await message.answer("Игрок уже находится на максимальной должности.")
                return

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
                f"🆔 Квента: #{character_id}\n"
                f"📂 Отдел: {department_name}\n"
                f"💼 Новая должность: {new_job_title}\n"
                f"💳 Зарплата: {salary} CR"
            )
            return

        if text.startswith("/понизить "):
            parts = text.split()

            if len(parts) < 2:
                await message.answer(
                    "Использование:\n"
                    "/понизить ID\n\n"
                    "Пример:\n"
                    "/понизить 4"
                )
                return

            try:
                character_id = int(parts[1])
            except ValueError:
                await message.answer("Неверный ID квенты.")
                return

            character = await get_character_by_id(character_id)

            if not character:
                await message.answer("Квента не найдена.")
                return

            department_name = character[11]
            current_level = character[13] or 0

            if not department_name or current_level == 0:
                await message.answer("У игрока ещё нет назначенной должности.")
                return

            department_key = get_department_key_by_name(department_name)

            if not department_key:
                await message.answer("Не удалось определить отдел.")
                return

            jobs = DEPARTMENTS[department_key]["jobs"]

            if current_level <= 1:
                await message.answer("Игрок уже находится на минимальной должности.")
                return

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
                f"🆔 Квента: #{character_id}\n"
                f"📂 Отдел: {department_name}\n"
                f"💼 Новая должность: {new_job_title}\n"
                f"💳 Зарплата: {salary} CR"
            )
            return


        if text.startswith("/фповысить "):
            parts = text.split()
            try:
                character_id = int(parts[1])
            except:
                await message.answer("Использование: /фповысить ID")
                return
            character = await get_character_by_id(character_id)
            if not character:
                await message.answer("Квента не найдена.")
                return
            ranks = FACTION_RANKS.get(character[5])
            current_level = character[16] if len(character) > 16 and character[16] else 0
            if current_level >= len(ranks):
                await message.answer("Игрок уже имеет максимальный фракционный ранг.")
                return
            new_level = current_level + 1
            new_rank = ranks[new_level - 1]
            await update_faction_rank(character_id, new_rank, new_level)
            await message.answer(f"🎖 Новый ранг: {new_rank}")
            return

        if text.startswith("/фпонизить "):
            parts = text.split()
            try:
                character_id = int(parts[1])
            except:
                await message.answer("Использование: /фпонизить ID")
                return
            character = await get_character_by_id(character_id)
            if not character:
                await message.answer("Квента не найдена.")
                return
            ranks = FACTION_RANKS.get(character[5])
            current_level = character[16] if len(character) > 16 and character[16] else 0
            if current_level <= 1:
                await message.answer("Игрок уже находится на минимальном ранге.")
                return
            new_level = current_level - 1
            new_rank = ranks[new_level - 1]
            await update_faction_rank(character_id, new_rank, new_level)
            await message.answer(f"🎖 Новый ранг: {new_rank}")
            return


        if text.startswith("/выдатькаюту "):
            parts = text.split(maxsplit=3)

            if len(parts) < 4:
                await message.answer(
                    "Использование:\n"
                    "/выдатькаюту ID класс сектор\n\n"
                    "Пример:\n"
                    "/выдатькаюту 4 V C-12"
                )
                return

            try:
                character_id = int(parts[1])
            except ValueError:
                await message.answer("Неверный ID квенты.")
                return

            housing_class = parts[2].upper()
            sector = parts[3]

            if housing_class not in HOUSING_PRICES:
                await message.answer("Класс должен быть: V, IV, III, II или I.")
                return

            character = await get_character_by_id(character_id)

            if not character:
                await message.answer("Квента не найдена.")
                return

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
                f"🆔 Квента: #{character_id}\n"
                f"🏠 Тип: {HOUSING_NAMES[housing_class]}\n"
                f"📍 Сектор: {sector}\n"
                f"💳 Аренда: {HOUSING_PRICES[housing_class]} CR / неделя"
            )
            return

        if text.startswith("/забратькаюту "):
            parts = text.split()

            if len(parts) < 2:
                await message.answer("Использование:\n/забратькаюту ID")
                return

            try:
                character_id = int(parts[1])
            except ValueError:
                await message.answer("Неверный ID квенты.")
                return

            character = await get_character_by_id(character_id)

            if not character:
                await message.answer("Квента не найдена.")
                return

            await remove_housing(character_id)

            await bot.api.messages.send(
                peer_id=character[1],
                random_id=0,
                message=(
                    "🔴 ЖИЛОЙ МОДУЛЬ ИЗЪЯТ\n"
                    f"{sci_line()}\n\n"
                    "Администрация изъяла вашу каюту."
                )
            )

            await message.answer(f"🏠 Каюта квенты #{character_id} изъята.")
            return

        if text.startswith("/переселить "):
            parts = text.split(maxsplit=2)

            if len(parts) < 3:
                await message.answer("Использование:\n/переселить ID сектор")
                return

            try:
                character_id = int(parts[1])
            except ValueError:
                await message.answer("Неверный ID квенты.")
                return

            character = await get_character_by_id(character_id)
            housing = await get_housing(character_id)

            if not character:
                await message.answer("Квента не найдена.")
                return

            if not housing:
                await message.answer("У персонажа ещё нет каюты.")
                return

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

            await message.answer(f"📍 Квента #{character_id} переселена в сектор {sector}.")
            return

        if text.startswith("/улучшитькаюту "):
            parts = text.split()

            if len(parts) < 3:
                await message.answer(
                    "Использование:\n"
                    "/улучшитькаюту ID класс\n\n"
                    "Пример:\n"
                    "/улучшитькаюту 4 II"
                )
                return

            try:
                character_id = int(parts[1])
            except ValueError:
                await message.answer("Неверный ID квенты.")
                return

            housing_class = parts[2].upper()

            if housing_class not in HOUSING_PRICES:
                await message.answer("Класс должен быть: V, IV, III, II или I.")
                return

            character = await get_character_by_id(character_id)
            housing = await get_housing(character_id)

            if not character:
                await message.answer("Квента не найдена.")
                return

            if not housing:
                await message.answer("У персонажа ещё нет каюты.")
                return

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
                f"⬆️ Квента #{character_id}: жильё изменено на {HOUSING_NAMES[housing_class]}."
            )
            return


        if text.startswith("/деньги "):
            parts = text.split()

            if len(parts) < 3:
                await message.answer(
                    "Использование:\n"
                    "/деньги ID сумма\n\n"
                    "Пример:\n"
                    "/деньги 4 500"
                )
                return

            try:
                character_id = int(parts[1])
                amount = int(parts[2])
            except ValueError:
                await message.answer("ID и сумма должны быть числами.")
                return

            if amount <= 0:
                await message.answer("Сумма должна быть больше 0.")
                return

            character = await get_character_by_id(character_id)

            if not character:
                await message.answer("Квента не найдена.")
                return

            await create_user(character[1])
            await add_balance(character[1], amount)
            user = await get_user(character[1])

            await bot.api.messages.send(
                peer_id=character[1],
                random_id=0,
                message=(
                    "🟢 НАЧИСЛЕНИЕ КРЕДИТОВ\n"
                    f"{sci_line()}\n\n"
                    f"💳 Получено: +{amount} CR\n"
                    f"💰 Баланс: {user[1]} CR"
                )
            )

            await message.answer(
                "🟢 КРЕДИТЫ НАЧИСЛЕНЫ\n"
                f"{sci_line()}\n\n"
                f"🆔 Квента: #{character_id}\n"
                f"👤 Персонаж: {character[2]}\n"
                f"💳 Начислено: +{amount} CR\n"
                f"💰 Баланс: {user[1]} CR"
            )
            return

        if text.startswith("/снятьденьги "):
            parts = text.split()

            if len(parts) < 3:
                await message.answer(
                    "Использование:\n"
                    "/снятьденьги ID сумма\n\n"
                    "Пример:\n"
                    "/снятьденьги 4 500"
                )
                return

            try:
                character_id = int(parts[1])
                amount = int(parts[2])
            except ValueError:
                await message.answer("ID и сумма должны быть числами.")
                return

            if amount <= 0:
                await message.answer("Сумма должна быть больше 0.")
                return

            character = await get_character_by_id(character_id)

            if not character:
                await message.answer("Квента не найдена.")
                return

            await create_user(character[1])
            user = await get_user(character[1])

            if user[1] < amount:
                await message.answer(
                    "У игрока недостаточно средств.\n"
                    f"Баланс: {user[1]} CR"
                )
                return

            await subtract_balance(character[1], amount)
            updated_user = await get_user(character[1])

            await bot.api.messages.send(
                peer_id=character[1],
                random_id=0,
                message=(
                    "🔴 СПИСАНИЕ КРЕДИТОВ\n"
                    f"{sci_line()}\n\n"
                    f"💳 Списано: -{amount} CR\n"
                    f"💰 Баланс: {updated_user[1]} CR"
                )
            )

            await message.answer(
                "🔴 КРЕДИТЫ СПИСАНЫ\n"
                f"{sci_line()}\n\n"
                f"🆔 Квента: #{character_id}\n"
                f"👤 Персонаж: {character[2]}\n"
                f"💳 Списано: -{amount} CR\n"
                f"💰 Баланс: {updated_user[1]} CR"
            )
            return

        if text.startswith("/баланс "):
            parts = text.split()

            if len(parts) < 2:
                await message.answer(
                    "Использование:\n"
                    "/баланс ID\n\n"
                    "Пример:\n"
                    "/баланс 4"
                )
                return

            try:
                character_id = int(parts[1])
            except ValueError:
                await message.answer("ID должен быть числом.")
                return

            character = await get_character_by_id(character_id)

            if not character:
                await message.answer("Квента не найдена.")
                return

            await create_user(character[1])
            user = await get_user(character[1])

            await message.answer(
                "◢ ПРОВЕРКА БАЛАНСА ◣\n"
                f"{sci_line()}\n\n"
                f"🆔 Квента: #{character_id}\n"
                f"👤 Персонаж: {character[2]}\n"
                f"💳 Баланс: {user[1]} CR"
            )
            return

        if text.startswith("/отделы"):
            await message.answer(
                "◢ КОДЫ ОТДЕЛОВ ◣\n"
                f"{sci_line()}\n\n"
                f"{DEPARTMENT_CODES_TEXT}\n\n"
                "Пример назначения:\n"
                "/назначить 4 наука"
            )
            return

        if "Одобрить #" in text:
            try:
                character_id = int(text.split("#")[-1].strip())
            except ValueError:
                await message.answer("Неверный номер квенты.")
                return

            character = await get_character_by_id(character_id)

            if not character:
                await message.answer("Квента не найдена.")
                return

            await update_character_status(character_id, "approved")

            await bot.api.messages.send(
                peer_id=character[1],
                random_id=0,
                message=(
                    "🟢 ВЕРИФИКАЦИЯ ЗАВЕРШЕНА\n"
                    f"{sci_line()}\n\n"
                    "Ваша квента одобрена.\n"
                    "Доступ к системе Echoes of the Rift открыт."
                )
            )

            await message.answer(f"✅ Квента #{character_id} одобрена.")
            return

        if "Отклонить #" in text:
            try:
                character_id = int(text.split("#")[-1].strip())
            except ValueError:
                await message.answer("Неверный номер квенты.")
                return

            character = await get_character_by_id(character_id)

            if not character:
                await message.answer("Квента не найдена.")
                return

            await update_character_status(character_id, "rejected")

            await bot.api.messages.send(
                peer_id=character[1],
                random_id=0,
                message=(
                    "🔴 КВЕНТА ОТКЛОНЕНА\n"
                    f"{sci_line()}\n\n"
                    "Администрация отклонила вашу квенту.\n"
                    "Вы можете удалить персонажа и создать нового."
                )
            )

            await message.answer(f"❌ Квента #{character_id} отклонена.")
            return

        return

    if message.from_id in archive_users and text.isdigit():
        character_id = int(text)
        character = await get_character_by_id(character_id)

        if not character:
            await message.answer("Анкета с таким номером не найдена.")
            return

        if character[10] != "approved":
            await message.answer("Эта анкета не находится в открытом архиве.")
            return

        player_name = await get_vk_name(character[1])
        vk_link = f"https://vk.com/id{character[1]}"
        # Для архива используем вложения ровно в том виде, в котором они
        # были сохранены при создании квенты. Старые пользовательские photo-ID
        # VK умеет прикреплять напрямую, а попытка повторно искать/перезаливать
        # их через media-слой может надолго блокировать открытие анкеты.
        arts = character[9] if character[9] else None

        await message.answer(
            f"{format_character(character)}\n\n"
            f"👤 Игрок: {player_name}\n"
            f"🔗 Профиль ВК: {vk_link}",
            attachment=arts,
            keyboard=quenta_menu.get_json()
        )
        return

    user_id = message.from_id
    draft = drafts.get(user_id)

    if not draft:
        return

    step = draft["step"]

    if step == "name":
        draft["name"] = text
        draft["step"] = "age"
        await message.answer("Шаг 2/8\nВведите возраст персонажа.")
        return

    if step == "age":
        draft["age"] = text
        draft["step"] = "gender"
        await message.answer("Шаг 3/8\nВведите пол персонажа.")
        return

    if step == "gender":
        draft["gender"] = text
        draft["step"] = "faction"
        await message.answer(
            "Шаг 4/8\nВыберите фракцию персонажа.",
            keyboard=faction_keyboard.get_json()
        )
        return

    if step == "biology":
        draft["biology"] = text
        draft["step"] = "personality"
        await message.answer("Шаг 6/8\nОпишите характер персонажа.")
        return

    if step == "personality":
        draft["personality"] = text
        draft["step"] = "history"
        await message.answer("Шаг 7/8\nНапишите историю персонажа.")
        return

    if step == "history":
        draft["history"] = text
        draft["step"] = "arts"
        await message.answer(
            "Шаг 8/8\n"
            "Прикрепите от 1 до 3 артов персонажа.\n\n"
            "Когда закончите — нажмите «✅ Готово».",
            keyboard=done_arts_keyboard.get_json()
        )
        return

    if step == "arts":
        attachment = get_photo_attachment(message)

        if not attachment:
            await message.answer("Отправьте именно фото/арт.")
            return

        if len(draft["arts"]) >= 3:
            await message.answer(
                "Лимит — 3 арта.\n"
                "Нажмите «✅ Готово», чтобы отправить квенту."
            )
            return

        draft["arts"].append(attachment)

        await message.answer(
            f"🖼 Арт принят: {len(draft['arts'])}/3\n\n"
            "Можете отправить ещё или нажать «✅ Готово».",
            keyboard=done_arts_keyboard.get_json()
        )
        return


asyncio.run(create_tables())
asyncio.run(ensure_career_columns())
asyncio.run(ensure_faction_rank_columns())
asyncio.run(ensure_quest_tables())
asyncio.run(ensure_housing_tables())
asyncio.run(ensure_location_tables())
asyncio.run(ensure_inventory_tables())

bot.run()
