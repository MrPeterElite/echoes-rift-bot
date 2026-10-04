from vkbottle.bot import Bot, Message
from vkbottle import Keyboard, KeyboardButtonColor, Text, BaseMiddleware
from dotenv import load_dotenv
import os
import asyncio
import time

load_dotenv()

from database import (
    create_user,
    get_user,
    reset_user,
    create_character,
    get_character_by_user,
    get_character_by_id,
    update_character_status,
    get_approved_characters,
    update_character_job,
    update_last_salary,
    add_balance,
    update_faction_rank,
    get_current_quest,
    get_last_quest,
    create_weekly_quest,
    submit_quest_report,
    get_quest_by_id,
    update_quest_status,
    get_housing,
    assign_housing,
    remove_housing,
    update_housing_sector,
    update_housing_class,
    update_housing_payment,
    get_housing_interiors,
    install_housing_interior,
    remove_housing_interior,
    update_housing_description,
    update_housing_visibility,
    subtract_balance,
    get_all_locations,
    get_location_by_code,
    get_location_by_peer,
    get_character_location,
    set_character_location,
    transfer_balance,
    get_top_richest,
    set_balance,
    get_characters_in_location,
    get_inventory,
    add_inventory_item,
    remove_inventory_item,
    find_inventory_item,
    transfer_inventory_item,
    ensure_owner_admin,
    get_bot_admin,
    list_bot_admins,
    upsert_bot_admin,
    deactivate_bot_admin,
    log_admin_action,
    issue_mute,
    get_active_mute,
    revoke_mute,
    delete_character_by_admin,
    create_promo_code,
    add_promo_reward,
    list_promo_codes,
    set_promo_active,
    redeem_promo_code,
    create_suggestion,
    get_last_suggestion_time,
    get_suggestion,
    list_suggestions,
    update_suggestion_status,
    get_pending_characters,
    get_pending_quests,
    complete_quest_with_rewards
)

from systems.characters import register_characters_handlers
from systems.dispatch import SerialMessageView
from systems.weapons_ui import register_weapon_handlers
from systems.armor_ui import register_armor_handlers
from systems.health_ui import register_health_handlers
from systems.legacy_admin import build_legacy_admin_router
from vkbottle.framework.labeler import BotLabeler
from stability import initialize_database
from systems.careers import register_careers_handlers
from systems.economy import register_economy_handlers
from systems.locations import register_locations_handlers
from systems.housing import (
    register_housing_handlers,
    handle_housing_command,
    HOUSING_CLASS_CAPACITY,
    get_used_slots,
)
from systems.factions import register_factions_handlers
from systems.rp import handle_rp_command
from systems.inventory import register_inventory_handlers
from systems.shop import register_shop_handlers, handle_shop_command
from systems.quests import register_quest_handlers
from systems.help import register_help_handlers
from systems.media import stabilize_attachments
from systems.admin import register_admin_handlers
from systems.suggestions import register_suggestion_handlers



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
_owner_raw = (os.getenv("BOT_OWNER_ID") or "").strip()
BOT_OWNER_ID = int(_owner_raw) if _owner_raw.isdigit() else 0
if not BOT_OWNER_ID:
    print("[config] WARNING: BOT_OWNER_ID is not configured; admin role system has no owner yet.")

bot = Bot(token=TOKEN, labeler=BotLabeler(message_view=SerialMessageView()))

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
    .row()
    .add(Text("💳 Финансы"), color=KeyboardButtonColor.PRIMARY)
    .add(Text("💡 Связь"), color=KeyboardButtonColor.PRIMARY)
    .row()
    .add(Text("❤️ Состояние"), color=KeyboardButtonColor.PRIMARY)
)

housing_menu = (
    Keyboard(one_time=False)
    .add(Text("🏠 Моя каюта"), color=KeyboardButtonColor.PRIMARY)
    .add(Text("🛋 Интерьер"), color=KeyboardButtonColor.POSITIVE)
    .row()
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


_mute_notice_at = {}


class MuteMiddleware(BaseMiddleware[Message]):
    async def pre(self):
        event = self.event
        if not getattr(event, "from_id", 0) or event.from_id <= 0:
            return
        now = int(time.time())
        mute = await get_active_mute(event.from_id, now)
        if not mute:
            return

        # В беседах удаляем сообщение для всех, в ЛС просто блокируем обработчик.
        if event.peer_id >= 2_000_000_000:
            try:
                await bot.api.messages.delete(
                    peer_id=event.peer_id,
                    cmids=[event.conversation_message_id],
                    delete_for_all=True,
                )
            except Exception:
                pass

        # Не спамим уведомлением при каждом сообщении: не чаще одного раза в 15 секунд.
        if now - _mute_notice_at.get(event.from_id, 0) >= 15:
            _mute_notice_at[event.from_id] = now
            expires_at = mute[6]
            if expires_at:
                left = max(0, expires_at - now)
                days, rem = divmod(left, 86400)
                hours, rem = divmod(rem, 3600)
                minutes = rem // 60
                remaining = f"{days} д. {hours} ч. {minutes} мин." if days else (f"{hours} ч. {minutes} мин." if hours else f"{minutes} мин.")
            else:
                remaining = "без срока"
            try:
                await bot.api.messages.send(
                    peer_id=event.from_id,
                    random_id=0,
                    message=(
                        "🔇 ВЫ ВРЕМЕННО ОГРАНИЧЕНЫ\n"
                        f"{sci_line()}\n\n"
                        f"Причина: {mute[3]}\n"
                        f"Осталось: {remaining}"
                    ),
                )
            except Exception:
                pass
        self.stop("active mute")


bot.labeler.message_view.register_middleware(MuteMiddleware)


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


@bot.on.message(text=["/старт", "/start", "Начать", "начать"])
async def start_handler(message: Message):
    await CHARACTER_RUNTIME["pause_draft"](message)
    await create_user(message.from_id)
    # Сбрасываем незавершённые пошаговые интерфейсы при явном возврате к старту.
    for runtime_name in ("ECONOMY_RUNTIME", "SUGGESTION_RUNTIME"):
        runtime = globals().get(runtime_name)
        if runtime:
            runtime.get("sessions", {}).pop(message.from_id, None)

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
    await CHARACTER_RUNTIME["pause_draft"](message)
    for runtime_name in ("ECONOMY_RUNTIME", "SUGGESTION_RUNTIME"):
        runtime = globals().get(runtime_name)
        if runtime:
            runtime.get("sessions", {}).pop(message.from_id, None)
    await message.answer(
        "◢ ГЛАВНЫЙ ТЕРМИНАЛ ◣\n\n"
        "Вы вернулись в основной интерфейс.",
        keyboard=main_menu.get_json()
    )


CHARACTER_RUNTIME = register_characters_handlers(
    bot,
    {
        "quenta_menu": quenta_menu,
        "sci_line": sci_line,
        "get_character_by_user": get_character_by_user,
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

ECONOMY_RUNTIME = register_economy_handlers(
    bot,
    {
        "Keyboard": Keyboard,
        "KeyboardButtonColor": KeyboardButtonColor,
        "Text": Text,
        "get_top_richest": get_top_richest,
        "sci_line": sci_line,
        "get_character_by_user": get_character_by_user,
        "get_character_by_id": get_character_by_id,
        "create_user": create_user,
        "transfer_balance": transfer_balance,
        "get_user": get_user,
        "redeem_promo_code": redeem_promo_code,
    }
)

ADMIN_RUNTIME = register_admin_handlers(
    bot,
    {
        "Keyboard": Keyboard,
        "KeyboardButtonColor": KeyboardButtonColor,
        "Text": Text,
        "ADMIN_CHAT_ID": ADMIN_CHAT_ID,
        "sci_line": sci_line,
        "get_bot_admin": get_bot_admin,
        "list_bot_admins": list_bot_admins,
        "upsert_bot_admin": upsert_bot_admin,
        "deactivate_bot_admin": deactivate_bot_admin,
        "log_admin_action": log_admin_action,
        "issue_mute": issue_mute,
        "revoke_mute": revoke_mute,
        "get_active_mute": get_active_mute,
        "delete_character_by_admin": delete_character_by_admin,
        "get_character_by_id": get_character_by_id,
        "get_user": get_user,
        "create_user": create_user,
        "add_balance": add_balance,
        "subtract_balance": subtract_balance,
        "set_balance": set_balance,
        "update_character_job": update_character_job,
        "update_faction_rank": update_faction_rank,
        "get_department_key_by_name": get_department_key_by_name,
        "DEPARTMENTS": DEPARTMENTS,
        "SALARY_BY_LEVEL": SALARY_BY_LEVEL,
        "FACTION_RANKS": FACTION_RANKS,
        "get_housing": get_housing,
        "get_housing_interiors": get_housing_interiors,
        "assign_housing": assign_housing,
        "remove_housing": remove_housing,
        "update_housing_class": update_housing_class,
        "HOUSING_NAMES": HOUSING_NAMES,
        "HOUSING_CLASS_CAPACITY": HOUSING_CLASS_CAPACITY,
        "get_used_slots": get_used_slots,
        "create_promo_code": create_promo_code,
        "add_promo_reward": add_promo_reward,
        "list_promo_codes": list_promo_codes,
        "set_promo_active": set_promo_active,
        "get_pending_characters": get_pending_characters,
        "get_pending_quests": get_pending_quests,
        "get_suggestion": get_suggestion,
        "list_suggestions": list_suggestions,
        "update_suggestion_status": update_suggestion_status,
    }
)

register_quest_handlers(
    bot,
    {
        "Keyboard": Keyboard,
        "KeyboardButtonColor": KeyboardButtonColor,
        "Text": Text,
        "get_character_by_user": get_character_by_user,
        "get_character_by_id": get_character_by_id,
        "get_current_quest": get_current_quest,
        "get_last_quest": get_last_quest,
        "create_weekly_quest": create_weekly_quest,
        "submit_quest_report": submit_quest_report,
        "get_quest_by_id": get_quest_by_id,
        "update_quest_status": update_quest_status,
        "complete_quest_with_rewards": complete_quest_with_rewards,
        "get_photo_attachment": get_photo_attachment,
        "sci_line": sci_line,
        "career_menu": career_menu,
        "ADMIN_CHAT_ID": ADMIN_CHAT_ID,
        "WEEK_SECONDS": WEEK_SECONDS,
        "has_admin_role": ADMIN_RUNTIME["has_role"],
    }
)

SUGGESTION_RUNTIME = register_suggestion_handlers(
    bot,
    {
        "Keyboard": Keyboard,
        "KeyboardButtonColor": KeyboardButtonColor,
        "Text": Text,
        "sci_line": sci_line,
        "ADMIN_CHAT_ID": ADMIN_CHAT_ID,
        "get_character_by_user": get_character_by_user,
        "get_photo_attachment": get_photo_attachment,
        "create_suggestion": create_suggestion,
        "get_last_suggestion_time": get_last_suggestion_time,
        "list_suggestions": list_suggestions,
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

HOUSING_RUNTIME = register_housing_handlers(
    bot,
    {
        "Keyboard": Keyboard,
        "KeyboardButtonColor": KeyboardButtonColor,
        "Text": Text,
        "get_character_by_user": get_character_by_user,
        "get_character_by_id": get_character_by_id,
        "get_housing": get_housing,
        "get_housing_interiors": get_housing_interiors,
        "install_housing_interior": install_housing_interior,
        "remove_housing_interior": remove_housing_interior,
        "update_housing_description": update_housing_description,
        "update_housing_visibility": update_housing_visibility,
        "get_inventory": get_inventory,
        "HOUSING_NAMES": HOUSING_NAMES,
        "sci_line": sci_line,
        "housing_menu": housing_menu,
        "WEEK_SECONDS": WEEK_SECONDS,
        "format_salary_cooldown": format_salary_cooldown,
        "create_user": create_user,
        "get_user": get_user,
        "subtract_balance": subtract_balance,
        "update_housing_payment": update_housing_payment,
        "stabilize_attachments": stabilize_attachments,
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




LEGACY_ADMIN_ROUTER = build_legacy_admin_router({
    "ADMIN_CHAT_ID": ADMIN_CHAT_ID,
    "ADMIN_RUNTIME": ADMIN_RUNTIME,
    "DEPARTMENTS": DEPARTMENTS,
    "DEPARTMENT_CODES_TEXT": DEPARTMENT_CODES_TEXT,
    "FACTION_RANKS": FACTION_RANKS,
    "HOUSING_CLASS_CAPACITY": HOUSING_CLASS_CAPACITY,
    "HOUSING_NAMES": HOUSING_NAMES,
    "HOUSING_PRICES": HOUSING_PRICES,
    "SALARY_BY_LEVEL": SALARY_BY_LEVEL,
    "assign_housing": assign_housing,
    "bot": bot,
    "create_user": create_user,
    "get_character_by_id": get_character_by_id,
    "get_department_key_by_name": get_department_key_by_name,
    "get_housing": get_housing,
    "get_housing_interiors": get_housing_interiors,
    "get_used_slots": get_used_slots,
    "get_user": get_user,
    "remove_housing": remove_housing,
    "sci_line": sci_line,
    "update_character_job": update_character_job,
    "update_character_status": update_character_status,
    "update_faction_rank": update_faction_rank,
    "update_housing_class": update_housing_class,
    "update_housing_sector": update_housing_sector,
})


register_health_handlers(bot, ADMIN_CHAT_ID)
register_armor_handlers(bot)
register_weapon_handlers(bot)


@bot.on.message()
async def router_handler(message: Message):
    text = message.text or ""

    if await ADMIN_RUNTIME["handle_legacy_finance"](message):
        return

    # Свободный ввод пошаговых интерфейсов обрабатывается до общего роутинга.
    if await ADMIN_RUNTIME["handle_admin_message"](message):
        return
    if await ECONOMY_RUNTIME["handle_economy_message"](message):
        return
    if await SUGGESTION_RUNTIME["handle_suggestion_message"](message):
        return

    if await handle_shop_command(message, SHOP_DEPS):
        return

    if await handle_housing_command(message, HOUSING_RUNTIME):
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

    if await LEGACY_ADMIN_ROUTER(message):
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

    await CHARACTER_RUNTIME["handle_message"](message)


async def startup():
    await initialize_database()
    await ensure_owner_admin(BOT_OWNER_ID, int(time.time()))


if __name__ == "__main__":
    asyncio.run(startup())
    bot.run()
