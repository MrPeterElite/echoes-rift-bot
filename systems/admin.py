from database import adjust_balance_by_admin
import time

from systems.shop import load_shop_items


ROLE_LEVELS = {
    "moderator": 1,
    "admin": 2,
    "senior": 3,
    "owner": 4,
}

ROLE_LABELS = {
    "moderator": "🟢 Модератор",
    "admin": "🟠 Администратор",
    "senior": "🔴 Старший администратор",
    "owner": "👑 Владелец",
}


def parse_duration(value: str):
    value = (value or "").strip().lower()
    if value in {"навсегда", "вечный", "permanent", "perm"}:
        return 0
    if len(value) < 2:
        return None
    unit = value[-1]
    try:
        amount = int(value[:-1])
    except ValueError:
        return None
    if amount <= 0:
        return None
    multipliers = {"м": 60, "ч": 3600, "д": 86400}
    if unit not in multipliers:
        return None
    return amount * multipliers[unit]


def format_duration(seconds: int):
    if seconds == 0:
        return "навсегда"
    days, rem = divmod(max(0, seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days} д.")
    if hours:
        parts.append(f"{hours} ч.")
    if minutes or not parts:
        parts.append(f"{minutes} мин.")
    return " ".join(parts)


def _catalog_index():
    catalog = load_shop_items()
    result = {}
    for category, section in catalog.items():
        for item in section.get("items", []):
            result[item.get("code", "").lower()] = {
                "category": item.get("category") or category,
                "name": item.get("name", item.get("code", "")),
                "code": item.get("code", ""),
            }
    return result


def register_admin_handlers(bot, deps):
    Keyboard = deps["Keyboard"]
    KeyboardButtonColor = deps["KeyboardButtonColor"]
    Text = deps["Text"]
    ADMIN_CHAT_ID = deps["ADMIN_CHAT_ID"]
    sci_line = deps["sci_line"]

    get_bot_admin = deps["get_bot_admin"]
    list_bot_admins = deps["list_bot_admins"]
    upsert_bot_admin = deps["upsert_bot_admin"]
    deactivate_bot_admin = deps["deactivate_bot_admin"]
    log_admin_action = deps["log_admin_action"]
    issue_mute = deps["issue_mute"]
    revoke_mute = deps["revoke_mute"]
    get_active_mute = deps["get_active_mute"]
    delete_character_by_admin = deps["delete_character_by_admin"]

    get_character_by_id = deps["get_character_by_id"]
    get_user = deps["get_user"]
    create_user = deps["create_user"]
    update_character_job = deps["update_character_job"]
    update_faction_rank = deps["update_faction_rank"]
    get_department_key_by_name = deps["get_department_key_by_name"]
    DEPARTMENTS = deps["DEPARTMENTS"]
    SALARY_BY_LEVEL = deps["SALARY_BY_LEVEL"]
    FACTION_RANKS = deps["FACTION_RANKS"]

    get_housing = deps["get_housing"]
    get_housing_interiors = deps["get_housing_interiors"]
    assign_housing = deps["assign_housing"]
    remove_housing = deps["remove_housing"]
    HOUSING_NAMES = deps["HOUSING_NAMES"]
    HOUSING_CLASS_CAPACITY = deps["HOUSING_CLASS_CAPACITY"]
    get_used_slots = deps["get_used_slots"]

    create_promo_code = deps["create_promo_code"]
    add_promo_reward = deps["add_promo_reward"]
    list_promo_codes = deps["list_promo_codes"]
    set_promo_active = deps["set_promo_active"]

    get_pending_characters = deps["get_pending_characters"]
    get_pending_quests = deps["get_pending_quests"]
    get_suggestion = deps["get_suggestion"]
    list_suggestions = deps["list_suggestions"]
    update_suggestion_status = deps["update_suggestion_status"]

    sessions = {}

    async def admin_role(user_id):
        row = await get_bot_admin(user_id)
        if not row or not row[2]:
            return None
        return row[1]

    async def has_role(user_id, minimum="moderator"):
        role = await admin_role(user_id)
        return bool(role and ROLE_LEVELS.get(role, 0) >= ROLE_LEVELS.get(minimum, 999))

    async def require_admin(message, minimum="moderator", require_chat=True):
        if require_chat and message.peer_id != ADMIN_CHAT_ID:
            return None
        role = await admin_role(message.from_id)
        if not role or ROLE_LEVELS.get(role, 0) < ROLE_LEVELS.get(minimum, 999):
            if message.peer_id == ADMIN_CHAT_ID:
                await message.answer("⛔ Недостаточно административных прав.")
            return None
        return role

    def admin_menu(role="moderator"):
        kb = (
            Keyboard(one_time=False)
            .add(Text("👤 Управление игроком"), color=KeyboardButtonColor.PRIMARY)
            .add(Text("📜 Персонажи на проверке"), color=KeyboardButtonColor.POSITIVE)
            .row()
            .add(Text("📌 Отчёты на проверке"), color=KeyboardButtonColor.POSITIVE)
            .add(Text("💳 Админ-экономика"), color=KeyboardButtonColor.PRIMARY)
            .row()
            .add(Text("🎁 Промокоды"), color=KeyboardButtonColor.PRIMARY)
            .add(Text("💡 Предложения"), color=KeyboardButtonColor.PRIMARY)
        )
        if ROLE_LEVELS.get(role, 0) >= ROLE_LEVELS["owner"]:
            kb.row().add(Text("👥 Администраторы"), color=KeyboardButtonColor.NEGATIVE)
        return kb.row().add(Text("✖️ Закрыть админ-панель"), color=KeyboardButtonColor.SECONDARY)

    def player_keyboard(role):
        kb = (
            Keyboard(one_time=False)
            .add(Text("💼 Карьера игрока"), color=KeyboardButtonColor.PRIMARY)
            .add(Text("🏛 Фракция игрока"), color=KeyboardButtonColor.PRIMARY)
            .row()
            .add(Text("💳 Финансы игрока"), color=KeyboardButtonColor.POSITIVE)
            .add(Text("🏠 Жильё игрока"), color=KeyboardButtonColor.POSITIVE)
            .row()
            .add(Text("🔇 Наказания игрока"), color=KeyboardButtonColor.NEGATIVE)
        )
        if ROLE_LEVELS.get(role, 0) >= ROLE_LEVELS["senior"]:
            kb.add(Text("🗑 Удалить персонажа"), color=KeyboardButtonColor.NEGATIVE)
        return kb.row().add(Text("⬅️ Админ-панель"), color=KeyboardButtonColor.SECONDARY)

    def career_keyboard():
        return (
            Keyboard(one_time=False)
            .add(Text("📂 Назначить отдел"), color=KeyboardButtonColor.PRIMARY)
            .add(Text("⬆️ Повысить игрока"), color=KeyboardButtonColor.POSITIVE)
            .row()
            .add(Text("⬇️ Понизить игрока"), color=KeyboardButtonColor.NEGATIVE)
            .add(Text("🚪 Уволить игрока"), color=KeyboardButtonColor.NEGATIVE)
            .row()
            .add(Text("⬅️ К игроку"), color=KeyboardButtonColor.SECONDARY)
        )

    def finance_keyboard():
        return (
            Keyboard(one_time=False)
            .add(Text("➕ Выдать CR"), color=KeyboardButtonColor.POSITIVE)
            .add(Text("➖ Списать CR"), color=KeyboardButtonColor.NEGATIVE)
            .row()
            .add(Text("🧾 Установить баланс"), color=KeyboardButtonColor.PRIMARY)
            .add(Text("⬅️ К игроку"), color=KeyboardButtonColor.SECONDARY)
        )

    def housing_admin_keyboard():
        return (
            Keyboard(one_time=False)
            .add(Text("🏠 Выдать/изменить каюту"), color=KeyboardButtonColor.POSITIVE)
            .add(Text("🗑 Изъять каюту"), color=KeyboardButtonColor.NEGATIVE)
            .row()
            .add(Text("⬅️ К игроку"), color=KeyboardButtonColor.SECONDARY)
        )

    def punishment_keyboard():
        return (
            Keyboard(one_time=False)
            .add(Text("🔇 Выдать мут"), color=KeyboardButtonColor.NEGATIVE)
            .add(Text("🔊 Снять мут"), color=KeyboardButtonColor.POSITIVE)
            .row()
            .add(Text("⬅️ К игроку"), color=KeyboardButtonColor.SECONDARY)
        )

    def promo_keyboard():
        return (
            Keyboard(one_time=False)
            .add(Text("➕ Создать промокод"), color=KeyboardButtonColor.POSITIVE)
            .add(Text("📋 Список промокодов"), color=KeyboardButtonColor.PRIMARY)
            .row()
            .add(Text("⛔ Отключить промокод"), color=KeyboardButtonColor.NEGATIVE)
            .add(Text("⬅️ Админ-панель"), color=KeyboardButtonColor.SECONDARY)
        )

    def promo_rewards_keyboard():
        return (
            Keyboard(one_time=False)
            .add(Text("💳 Добавить CR"), color=KeyboardButtonColor.POSITIVE)
            .add(Text("🎒 Добавить предмет"), color=KeyboardButtonColor.PRIMARY)
            .row()
            .add(Text("✅ Создать промокод"), color=KeyboardButtonColor.POSITIVE)
            .add(Text("❌ Отмена промокода"), color=KeyboardButtonColor.NEGATIVE)
        )

    async def show_admin_menu(message):
        role = await require_admin(message)
        if not role:
            return
        sessions.pop(message.from_id, None)
        await message.answer(
            "⚙️ АДМИНИСТРАТИВНАЯ ПАНЕЛЬ\n"
            f"{sci_line()}\n\n"
            f"Ваша роль: {ROLE_LABELS.get(role, role)}\n\n"
            "Выберите раздел управления.",
            keyboard=admin_menu(role).get_json(),
        )

    async def show_player(message, character_id):
        role = await require_admin(message)
        if not role:
            return
        character = await get_character_by_id(character_id)
        if not character:
            await message.answer("Персонаж не найден.")
            return
        await create_user(character[1])
        user = await get_user(character[1])
        housing = await get_housing(character_id)
        mute = await get_active_mute(character[1], int(time.time()))
        sessions[message.from_id] = {"mode": "player", "character_id": character_id}
        await message.answer(
            "👤 УПРАВЛЕНИЕ ИГРОКОМ\n"
            f"{sci_line()}\n\n"
            f"🆔 Персонаж: #{character[0]}\n"
            f"👤 Персонаж: {character[2]}\n"
            f"📌 Статус: {character[10]}\n"
            f"🏛 Фракция: {character[5]}\n"
            f"🎖 Ранг: {character[15] if len(character) > 15 and character[15] else 'не назначен'}\n\n"
            f"📂 Отдел: {character[11] or 'не назначен'}\n"
            f"💼 Должность: {character[12] or 'не назначена'}\n"
            f"💳 Баланс: {user[1] if user else 0} CR\n"
            f"⭐ XP: {user[2] if user else 0}\n"
            f"🏠 Каюта: {HOUSING_NAMES.get(housing[1], housing[1]) if housing else 'не назначена'}\n"
            f"🔇 Мут: {'активен' if mute else 'нет'}",
            keyboard=player_keyboard(role).get_json(),
        )

    @bot.on.message(text=["/админ", "⚙️ Админ-панель"])
    async def admin_panel_handler(message):
        await show_admin_menu(message)

    @bot.on.message(text="⬅️ Админ-панель")
    async def admin_back_handler(message):
        await show_admin_menu(message)

    @bot.on.message(text="✖️ Закрыть админ-панель")
    async def admin_close_handler(message):
        if not await require_admin(message):
            return
        sessions.pop(message.from_id, None)
        await message.answer("Административная панель закрыта.")

    @bot.on.message(text="👤 Управление игроком")
    async def admin_player_start(message):
        if not await require_admin(message, "admin"):
            return
        sessions[message.from_id] = {"mode": "await_character_id"}
        await message.answer("Введите ID персонажа игрока, которым хотите управлять.")

    @bot.on.message(text="⬅️ К игроку")
    async def admin_player_back(message):
        if not await require_admin(message, "admin"):
            return
        session = sessions.get(message.from_id, {})
        character_id = session.get("character_id")
        if not character_id:
            await message.answer("Сначала выберите игрока через «👤 Управление игроком».")
            return
        await show_player(message, character_id)

    @bot.on.message(text="💼 Карьера игрока")
    async def player_career_menu(message):
        if not await require_admin(message, "admin"):
            return
        session = sessions.get(message.from_id, {})
        character = await get_character_by_id(session.get("character_id", 0))
        if not character:
            await message.answer("Сначала выберите игрока.")
            return
        await message.answer(
            f"💼 {character[2]}\n📂 {character[11] or 'не назначен'}\n💼 {character[12] or 'не назначена'}",
            keyboard=career_keyboard().get_json(),
        )

    @bot.on.message(text="📂 Назначить отдел")
    async def choose_department(message):
        if not await require_admin(message, "admin"):
            return
        session = sessions.get(message.from_id, {})
        if not session.get("character_id"):
            await message.answer("Сначала выберите игрока.")
            return
        kb = Keyboard(one_time=True)
        labels = []
        for key, data in DEPARTMENTS.items():
            label = f"📂 {key}"
            labels.append(label)
            kb.add(Text(label), color=KeyboardButtonColor.PRIMARY).row()
        sessions[message.from_id]["mode"] = "choose_department"
        await message.answer("Выберите отдел:", keyboard=kb.get_json())

    @bot.on.message(text="⬆️ Повысить игрока")
    async def promote_player(message):
        if not await require_admin(message, "admin"):
            return
        session = sessions.get(message.from_id, {})
        cid = session.get("character_id")
        character = await get_character_by_id(cid or 0)
        if not character or not character[11] or not (character[13] or 0):
            await message.answer("Игрок ещё не назначен в отдел.")
            return
        key = get_department_key_by_name(character[11])
        jobs = DEPARTMENTS.get(key, {}).get("jobs", [])
        level = character[13] or 0
        if level >= len(jobs):
            await message.answer("Это максимальная должность в отделе.")
            return
        new_level = level + 1
        await update_character_job(cid, character[11], jobs[new_level - 1], new_level)
        await log_admin_action(message.from_id, "career_promote", character[1], cid, jobs[new_level - 1], int(time.time()))
        await message.answer(f"✅ Повышен до: {jobs[new_level - 1]} ({SALARY_BY_LEVEL.get(new_level, 0)} CR/нед.)")
        await show_player(message, cid)

    @bot.on.message(text="⬇️ Понизить игрока")
    async def demote_player(message):
        if not await require_admin(message, "admin"):
            return
        session = sessions.get(message.from_id, {})
        cid = session.get("character_id")
        character = await get_character_by_id(cid or 0)
        if not character or not character[11] or not (character[13] or 0):
            await message.answer("Игрок ещё не назначен в отдел.")
            return
        level = character[13] or 0
        if level <= 1:
            await message.answer("Игрок уже на минимальной должности.")
            return
        key = get_department_key_by_name(character[11])
        jobs = DEPARTMENTS.get(key, {}).get("jobs", [])
        new_level = level - 1
        await update_character_job(cid, character[11], jobs[new_level - 1], new_level)
        await log_admin_action(message.from_id, "career_demote", character[1], cid, jobs[new_level - 1], int(time.time()))
        await message.answer(f"✅ Понижен до: {jobs[new_level - 1]}")
        await show_player(message, cid)

    @bot.on.message(text="🚪 Уволить игрока")
    async def fire_player(message):
        if not await require_admin(message, "admin"):
            return
        cid = sessions.get(message.from_id, {}).get("character_id")
        character = await get_character_by_id(cid or 0)
        if not character:
            await message.answer("Сначала выберите игрока.")
            return
        await update_character_job(cid, None, None, 0)
        await log_admin_action(message.from_id, "career_fire", character[1], cid, "", int(time.time()))
        await message.answer("🚪 Игрок уволен из отдела.")
        await show_player(message, cid)

    @bot.on.message(text="🏛 Фракция игрока")
    async def faction_menu(message):
        if not await require_admin(message, "admin"):
            return
        cid = sessions.get(message.from_id, {}).get("character_id")
        character = await get_character_by_id(cid or 0)
        if not character:
            await message.answer("Сначала выберите игрока.")
            return
        kb = (
            Keyboard(one_time=False)
            .add(Text("⬆️ Повысить ранг"), color=KeyboardButtonColor.POSITIVE)
            .add(Text("⬇️ Понизить ранг"), color=KeyboardButtonColor.NEGATIVE)
            .row().add(Text("⬅️ К игроку"), color=KeyboardButtonColor.SECONDARY)
        )
        await message.answer(
            f"🏛 {character[5]}\n🎖 {character[15] if len(character) > 15 and character[15] else 'не назначен'}",
            keyboard=kb.get_json(),
        )

    @bot.on.message(text="⬆️ Повысить ранг")
    async def promote_faction(message):
        if not await require_admin(message, "admin"):
            return
        cid = sessions.get(message.from_id, {}).get("character_id")
        character = await get_character_by_id(cid or 0)
        if not character:
            return
        ranks = FACTION_RANKS.get(character[5], [])
        current = character[16] if len(character) > 16 and character[16] else 0
        if current >= len(ranks):
            await message.answer("Максимальный ранг.")
            return
        new_level = current + 1
        await update_faction_rank(cid, ranks[new_level - 1], new_level)
        await log_admin_action(message.from_id, "faction_promote", character[1], cid, ranks[new_level - 1], int(time.time()))
        await message.answer(f"✅ Новый ранг: {ranks[new_level - 1]}")
        await show_player(message, cid)

    @bot.on.message(text="⬇️ Понизить ранг")
    async def demote_faction(message):
        if not await require_admin(message, "admin"):
            return
        cid = sessions.get(message.from_id, {}).get("character_id")
        character = await get_character_by_id(cid or 0)
        if not character:
            return
        ranks = FACTION_RANKS.get(character[5], [])
        current = character[16] if len(character) > 16 and character[16] else 0
        if current <= 1:
            await message.answer("Игрок уже на минимальном ранге.")
            return
        new_level = current - 1
        await update_faction_rank(cid, ranks[new_level - 1], new_level)
        await log_admin_action(message.from_id, "faction_demote", character[1], cid, ranks[new_level - 1], int(time.time()))
        await message.answer(f"✅ Новый ранг: {ranks[new_level - 1]}")
        await show_player(message, cid)

    @bot.on.message(text="💳 Финансы игрока")
    async def finance_player_menu(message):
        if not await require_admin(message, "admin"):
            return
        cid = sessions.get(message.from_id, {}).get("character_id")
        character = await get_character_by_id(cid or 0)
        if not character:
            await message.answer("Сначала выберите игрока.")
            return
        await create_user(character[1])
        user = await get_user(character[1])
        await message.answer(f"💳 Баланс {character[2]}: {user[1]} CR", keyboard=finance_keyboard().get_json())

    @bot.on.message(text=["➕ Выдать CR", "➖ Списать CR", "🧾 Установить баланс"])
    async def finance_action_start(message):
        if not await require_admin(message, "admin"):
            return
        session = sessions.get(message.from_id, {})
        if not session.get("character_id"):
            await message.answer("Сначала выберите игрока.")
            return
        modes = {
            "➕ Выдать CR": "finance_add",
            "➖ Списать CR": "finance_subtract",
            "🧾 Установить баланс": "finance_set",
        }
        session["mode"] = modes[message.text]
        await message.answer("Введите сумму CR целым числом.")

    @bot.on.message(text="🏠 Жильё игрока")
    async def housing_player_menu(message):
        if not await require_admin(message, "admin"):
            return
        cid = sessions.get(message.from_id, {}).get("character_id")
        housing = await get_housing(cid or 0)
        text = "🏠 Каюта не назначена." if not housing else f"🏠 {HOUSING_NAMES.get(housing[1], housing[1])}\n📍 Сектор: {housing[2]}"
        await message.answer(text, keyboard=housing_admin_keyboard().get_json())

    @bot.on.message(text="🏠 Выдать/изменить каюту")
    async def housing_assign_start(message):
        if not await require_admin(message, "admin"):
            return
        if not sessions.get(message.from_id, {}).get("character_id"):
            await message.answer("Сначала выберите игрока.")
            return
        sessions[message.from_id]["mode"] = "housing_class"
        kb = Keyboard(one_time=True)
        for cls in ["V", "IV", "III", "II", "I"]:
            kb.add(Text(f"🏠 Класс {cls}"), color=KeyboardButtonColor.PRIMARY)
        await message.answer("Выберите класс каюты:", keyboard=kb.get_json())

    @bot.on.message(text="🗑 Изъять каюту")
    async def housing_remove_action(message):
        if not await require_admin(message, "admin"):
            return
        cid = sessions.get(message.from_id, {}).get("character_id")
        character = await get_character_by_id(cid or 0)
        if not character:
            return
        returned = await remove_housing(cid)
        await log_admin_action(message.from_id, "housing_remove", character[1], cid, f"returned_items={returned}", int(time.time()))
        await message.answer(f"✅ Каюта изъята. Возвращено комплектов в инвентарь: {returned}.")
        await show_player(message, cid)

    @bot.on.message(text="🔇 Наказания игрока")
    async def punishment_player_menu(message):
        if not await require_admin(message, "admin"):
            return
        cid = sessions.get(message.from_id, {}).get("character_id")
        character = await get_character_by_id(cid or 0)
        if not character:
            return
        mute = await get_active_mute(character[1], int(time.time()))
        status = "нет активного мута"
        if mute:
            status = "навсегда" if not mute[6] else format_duration(mute[6] - int(time.time()))
            status = f"активен ({status}), причина: {mute[3]}"
        await message.answer(f"🔇 Мут: {status}", keyboard=punishment_keyboard().get_json())

    @bot.on.message(text="🔇 Выдать мут")
    async def mute_button_start(message):
        if not await require_admin(message, "admin"):
            return
        if not sessions.get(message.from_id, {}).get("character_id"):
            return
        sessions[message.from_id]["mode"] = "mute_duration"
        await message.answer("Введите длительность: 30м, 2ч, 1д или «навсегда».")

    @bot.on.message(text="🔊 Снять мут")
    async def unmute_button(message):
        if not await require_admin(message, "admin"):
            return
        cid = sessions.get(message.from_id, {}).get("character_id")
        character = await get_character_by_id(cid or 0)
        if not character:
            return
        changed = await revoke_mute(character[1], message.from_id, int(time.time()))
        if changed:
            await log_admin_action(message.from_id, "unmute", character[1], cid, "", int(time.time()))
            await message.answer("🔊 Мут снят.")
        else:
            await message.answer("У игрока нет активного мута.")
        await show_player(message, cid)

    @bot.on.message(text="🗑 Удалить персонажа")
    async def delete_quest_button(message):
        if not await require_admin(message, "senior"):
            return
        cid = sessions.get(message.from_id, {}).get("character_id")
        if not cid:
            return
        sessions[message.from_id]["mode"] = "delete_reason"
        await message.answer("⚠️ Введите причину удаления персонажа. После этого потребуется отдельное подтверждение.")

    @bot.on.message(text="✅ ПОДТВЕРДИТЬ УДАЛЕНИЕ")
    async def delete_confirm(message):
        if not await require_admin(message, "senior"):
            return
        session = sessions.get(message.from_id, {})
        cid = session.get("character_id")
        reason = session.get("delete_reason")
        if not cid or not reason or session.get("mode") != "delete_confirm":
            await message.answer("Нет подготовленного удаления.")
            return
        ok, user_id, name = await delete_character_by_admin(cid, reset_account=True)
        if not ok:
            await message.answer("Персонаж уже не существует.")
            return
        await log_admin_action(message.from_id, "character_delete", user_id, cid, reason, int(time.time()))
        sessions.pop(message.from_id, None)
        try:
            await bot.api.messages.send(
                peer_id=user_id, random_id=0,
                message=f"🗑 Ваш персонаж #{cid} ({name}) удалён администрацией.\nПричина: {reason}\nБаланс восстановлен до 1500 CR; опыт и уровень сброшены."
            )
        except Exception:
            pass
        await message.answer(f"🗑 Персонаж #{cid} удалён. Причина записана в журнал.")

    @bot.on.message(text="❌ ОТМЕНИТЬ УДАЛЕНИЕ")
    async def delete_cancel(message):
        if not await require_admin(message, "senior"):
            return
        session = sessions.get(message.from_id, {})
        cid = session.get("character_id")
        if cid:
            await show_player(message, cid)

    @bot.on.message(text="🎁 Промокоды")
    async def promo_menu_handler(message):
        if not await require_admin(message, "senior"):
            return
        sessions.pop(message.from_id, None)
        await message.answer("🎁 УПРАВЛЕНИЕ ПРОМОКОДАМИ", keyboard=promo_keyboard().get_json())

    @bot.on.message(text="➕ Создать промокод")
    async def promo_create_start(message):
        if not await require_admin(message, "senior"):
            return
        sessions[message.from_id] = {"mode": "promo_code", "promo": {"rewards": []}}
        await message.answer("Введите код латиницей/цифрами, например RIFT2026.")

    @bot.on.message(text="💳 Добавить CR")
    async def promo_add_cr_start(message):
        if not await require_admin(message, "senior"):
            return
        session = sessions.get(message.from_id, {})
        if "promo" not in session:
            await message.answer("Сначала начните создание промокода.")
            return
        session["mode"] = "promo_add_cr"
        await message.answer("Введите количество CR.")

    @bot.on.message(text="🎒 Добавить предмет")
    async def promo_add_item_start(message):
        if not await require_admin(message, "senior"):
            return
        session = sessions.get(message.from_id, {})
        if "promo" not in session:
            await message.answer("Сначала начните создание промокода.")
            return
        session["mode"] = "promo_add_item"
        await message.answer(
            "Введите код предмета и количество через пробел.\nПример: field_medkit 2\n\nКоманда /кодымагазина покажет доступные коды."
        )

    @bot.on.message(text="✅ Создать промокод")
    async def promo_finish(message):
        if not await require_admin(message, "senior"):
            return
        session = sessions.get(message.from_id, {})
        promo = session.get("promo")
        if not promo or not promo.get("code") or not promo.get("rewards"):
            await message.answer("Нужно указать код и хотя бы одну награду.")
            return
        now = int(time.time())
        try:
            promo_id = await create_promo_code(
                promo["code"], promo.get("max_uses", 0), promo.get("expires_at", 0), message.from_id, now
            )
        except Exception as exc:
            await message.answer(f"Не удалось создать промокод. Возможно, код уже существует.\n{type(exc).__name__}")
            return
        for reward in promo["rewards"]:
            await add_promo_reward(promo_id, **reward)
        await log_admin_action(message.from_id, "promo_create", None, None, promo["code"], now)
        lines = []
        for reward in promo["rewards"]:
            if reward["reward_type"] == "currency":
                lines.append(f"💳 {reward['amount']} CR")
            else:
                lines.append(f"🎒 {reward['item_name']} ×{reward['amount']}")
        sessions.pop(message.from_id, None)
        await message.answer(
            f"✅ Промокод {promo['code']} создан.\n" + "\n".join(lines),
            keyboard=promo_keyboard().get_json(),
        )

    @bot.on.message(text="❌ Отмена промокода")
    async def promo_cancel(message):
        if not await require_admin(message, "senior"):
            return
        sessions.pop(message.from_id, None)
        await message.answer("Создание промокода отменено.", keyboard=promo_keyboard().get_json())

    @bot.on.message(text="📋 Список промокодов")
    async def promo_list_handler(message):
        if not await require_admin(message, "senior"):
            return
        rows = await list_promo_codes(25)
        if not rows:
            await message.answer("Промокодов пока нет.", keyboard=promo_keyboard().get_json())
            return
        now = int(time.time())
        lines = ["🎁 ПРОМОКОДЫ", sci_line(), ""]
        for row in rows:
            _, code, max_uses, used, expires, active, *_ = row
            state = "🟢" if active and (not expires or expires > now) else "🔴"
            limit = f"{used}/{max_uses}" if max_uses else f"{used}/∞"
            lines.append(f"{state} {code} — {limit}")
        await message.answer("\n".join(lines), keyboard=promo_keyboard().get_json())

    @bot.on.message(text="⛔ Отключить промокод")
    async def promo_disable_start(message):
        if not await require_admin(message, "senior"):
            return
        sessions[message.from_id] = {"mode": "promo_disable"}
        await message.answer("Введите код, который нужно отключить.")

    @bot.on.message(text="/кодымагазина")
    async def shop_codes_handler(message):
        if not await require_admin(message, "senior"):
            return
        catalog = _catalog_index()
        lines = ["🎒 КОДЫ ПРЕДМЕТОВ", sci_line(), ""]
        for code, data in sorted(catalog.items()):
            lines.append(f"{code} — {data['name']}")
        text = "\n".join(lines)
        # VK has message limits; split safely.
        for start in range(0, len(text), 3500):
            await message.answer(text[start:start + 3500])

    @bot.on.message(text="💡 Предложения")
    async def suggestions_admin_list(message):
        if not await require_admin(message, "moderator"):
            return
        rows = await list_suggestions("new", 15)
        if not rows:
            await message.answer("Новых предложений нет.", keyboard=admin_menu(await admin_role(message.from_id)).get_json())
            return
        lines = ["💡 НОВЫЕ ПРЕДЛОЖЕНИЯ", sci_line(), ""]
        for row in rows:
            lines.append(f"#{row[0]} — персонаж #{row[2] or '—'} — {row[3][:90]}")
        lines.append("\nЧтобы открыть: /предложение ID")
        await message.answer("\n".join(lines))

    @bot.on.message(text="💡 Открыть #<suggestion_id>")
    async def suggestion_open_button(message, suggestion_id=None):
        if not await require_admin(message, "moderator"):
            return
        try:
            suggestion_id = int(suggestion_id)
        except (TypeError, ValueError):
            return
        suggestion = await get_suggestion(suggestion_id)
        if not suggestion:
            await message.answer("Предложение не найдено.")
            return
        sessions[message.from_id] = {"mode": "suggestion", "suggestion_id": suggestion_id}
        kb = (
            Keyboard(one_time=False)
            .add(Text("✅ Отметить рассмотренным"), color=KeyboardButtonColor.POSITIVE)
            .add(Text("💬 Ответить игроку"), color=KeyboardButtonColor.PRIMARY)
            .row()
            .add(Text("❌ Отклонить предложение"), color=KeyboardButtonColor.NEGATIVE)
            .add(Text("⬅️ Админ-панель"), color=KeyboardButtonColor.SECONDARY)
        )
        kwargs = {
            "message": (
                f"💡 ПРЕДЛОЖЕНИЕ #{suggestion[0]}\n{sci_line()}\n\n"
                f"VK ID: {suggestion[1]}\nПерсонаж: #{suggestion[2] or '—'}\nСтатус: {suggestion[5]}\n\n"
                f"{suggestion[3]}"
            ),
            "keyboard": kb.get_json(),
        }
        if suggestion[4]:
            kwargs["attachment"] = suggestion[4]
        await message.answer(**kwargs)

    @bot.on.message(text="/предложение <suggestion_id>")
    async def suggestion_open_command(message, suggestion_id=None):
        if not await require_admin(message, "moderator"):
            return
        try:
            suggestion_id = int(suggestion_id)
        except (TypeError, ValueError):
            await message.answer("Использование: /предложение ID")
            return
        suggestion = await get_suggestion(suggestion_id)
        if not suggestion:
            await message.answer("Предложение не найдено.")
            return
        sessions[message.from_id] = {"mode": "suggestion", "suggestion_id": suggestion_id}
        kb = (
            Keyboard(one_time=False)
            .add(Text("✅ Отметить рассмотренным"), color=KeyboardButtonColor.POSITIVE)
            .add(Text("💬 Ответить игроку"), color=KeyboardButtonColor.PRIMARY)
            .row()
            .add(Text("❌ Отклонить предложение"), color=KeyboardButtonColor.NEGATIVE)
            .add(Text("⬅️ Админ-панель"), color=KeyboardButtonColor.SECONDARY)
        )
        kwargs = {
            "message": (
                f"💡 ПРЕДЛОЖЕНИЕ #{suggestion[0]}\n{sci_line()}\n\n"
                f"VK ID: {suggestion[1]}\nПерсонаж: #{suggestion[2] or '—'}\nСтатус: {suggestion[5]}\n\n"
                f"{suggestion[3]}"
            ),
            "keyboard": kb.get_json(),
        }
        if suggestion[4]:
            kwargs["attachment"] = suggestion[4]
        await message.answer(**kwargs)

    @bot.on.message(text="✅ Отметить рассмотренным")
    async def suggestion_done(message):
        if not await require_admin(message, "moderator"):
            return
        sid = sessions.get(message.from_id, {}).get("suggestion_id")
        suggestion = await get_suggestion(sid or 0)
        if not suggestion:
            return
        await update_suggestion_status(sid, "reviewed", message.from_id, int(time.time()))
        await log_admin_action(message.from_id, "suggestion_reviewed", suggestion[1], suggestion[2], f"suggestion={sid}", int(time.time()))
        await message.answer(f"✅ Предложение #{sid} отмечено рассмотренным.")

    @bot.on.message(text="❌ Отклонить предложение")
    async def suggestion_reject(message):
        if not await require_admin(message, "moderator"):
            return
        sid = sessions.get(message.from_id, {}).get("suggestion_id")
        suggestion = await get_suggestion(sid or 0)
        if not suggestion:
            return
        await update_suggestion_status(sid, "rejected", message.from_id, int(time.time()))
        try:
            await bot.api.messages.send(peer_id=suggestion[1], random_id=0, message=f"❌ Предложение #{sid} рассмотрено, но отклонено администрацией.")
        except Exception:
            pass
        await log_admin_action(message.from_id, "suggestion_rejected", suggestion[1], suggestion[2], f"suggestion={sid}", int(time.time()))
        await message.answer(f"❌ Предложение #{sid} отклонено.")

    @bot.on.message(text="💬 Ответить игроку")
    async def suggestion_reply_start(message):
        if not await require_admin(message, "moderator"):
            return
        session = sessions.get(message.from_id, {})
        if not session.get("suggestion_id"):
            return
        session["mode"] = "suggestion_reply"
        await message.answer("Введите ответ игроку одним сообщением.")

    @bot.on.message(text="📜 Персонажи на проверке")
    async def pending_characters_handler(message):
        if not await require_admin(message, "moderator"):
            return
        rows = await get_pending_characters(20)
        if not rows:
            await message.answer("Новых персонажей на проверке нет.")
            return
        text = "📜 ПЕРСОНАЖА НА ПРОВЕРКЕ\n" + sci_line() + "\n\n"
        for row in rows:
            text += f"#{row[0]} — {row[2]} — {row[5]}\n"
        text += "\nОткройте персонажа через архив/ID; кнопки одобрения остаются на карточке нового персонажа."
        await message.answer(text)

    @bot.on.message(text="📌 Отчёты на проверке")
    async def pending_quests_handler(message):
        if not await require_admin(message, "moderator"):
            return
        rows = await get_pending_quests(20)
        if not rows:
            await message.answer("Отчётов на проверке нет.")
            return
        text = "📌 ОТЧЁТЫ НА ПРОВЕРКЕ\n" + sci_line() + "\n\n"
        for q in rows:
            text += f"#{q[0]} — персонаж #{q[1]} — {q[2]}\n"
        text += "\nКоманды /принятьзадание ID и /отклонитьзадание ID сохранены."
        await message.answer(text)

    @bot.on.message(text="💳 Админ-экономика")
    async def admin_economy_help(message):
        if not await require_admin(message, "admin"):
            return
        await message.answer("Выберите игрока через «👤 Управление игроком», затем откройте «💳 Финансы игрока».")

    @bot.on.message(text="👥 Администраторы")
    async def admins_list_handler(message):
        if not await require_admin(message, "owner"):
            return
        rows = await list_bot_admins()
        lines = ["👥 АДМИНИСТРАТОРЫ", sci_line(), ""]
        for row in rows:
            lines.append(f"{'🟢' if row[2] else '⚫'} {row[0]} — {ROLE_LABELS.get(row[1], row[1])}")
        lines += ["", "/админдобавить VK_ID moderator|admin|senior", "/админудалить VK_ID"]
        await message.answer("\n".join(lines))

    @bot.on.message(text="/админдобавить <vk_id> <role>")
    async def admin_add_command(message, vk_id=None, role=None):
        if not await require_admin(message, "owner"):
            return
        try:
            vk_id = int(vk_id)
        except (TypeError, ValueError):
            await message.answer("Использование: /админдобавить VK_ID moderator|admin|senior")
            return
        role = (role or "").lower()
        if role not in {"moderator", "admin", "senior"}:
            await message.answer("Роль: moderator, admin или senior.")
            return
        await upsert_bot_admin(vk_id, role, message.from_id, int(time.time()))
        await log_admin_action(message.from_id, "admin_add", vk_id, None, role, int(time.time()))
        await message.answer(f"✅ VK ID {vk_id} назначен: {ROLE_LABELS[role]}")

    @bot.on.message(text="/админудалить <vk_id>")
    async def admin_remove_command(message, vk_id=None):
        if not await require_admin(message, "owner"):
            return
        try:
            vk_id = int(vk_id)
        except (TypeError, ValueError):
            await message.answer("Использование: /админудалить VK_ID")
            return
        await deactivate_bot_admin(vk_id)
        await log_admin_action(message.from_id, "admin_remove", vk_id, None, "", int(time.time()))
        await message.answer(f"✅ Администратор {vk_id} отключён.")

    @bot.on.message(text="/мут <character_id> <duration> <reason>")
    async def mute_command(message, character_id=None, duration=None, reason=None):
        role = await require_admin(message, "admin")
        if not role:
            return
        try:
            character_id = int(character_id)
        except (TypeError, ValueError):
            await message.answer("Использование: /мут ID 30м причина")
            return
        seconds = parse_duration(duration)
        if seconds is None:
            await message.answer("Длительность: 30м, 2ч, 1д или навсегда.")
            return
        if seconds == 0 and ROLE_LEVELS.get(role, 0) < ROLE_LEVELS["senior"]:
            await message.answer("Постоянный мут доступен только старшим администраторам.")
            return
        character = await get_character_by_id(character_id)
        if not character:
            await message.answer("Персонаж не найден.")
            return
        reason = (reason or "").strip()
        if not reason:
            await message.answer("Укажите причину мута.")
            return
        now = int(time.time())
        expires_at = 0 if seconds == 0 else now + seconds
        await issue_mute(character[1], character_id, reason, message.from_id, now, expires_at)
        await log_admin_action(message.from_id, "mute", character[1], character_id, f"{duration}: {reason}", now)
        await message.answer(f"🔇 #{character_id} получил мут {format_duration(seconds)}.\nПричина: {reason}")

    @bot.on.message(text="/размут <character_id>")
    async def unmute_command(message, character_id=None):
        if not await require_admin(message, "admin"):
            return
        try:
            character_id = int(character_id)
        except (TypeError, ValueError):
            await message.answer("Использование: /размут ID")
            return
        character = await get_character_by_id(character_id)
        if not character:
            await message.answer("Персонаж не найден.")
            return
        changed = await revoke_mute(character[1], message.from_id, int(time.time()))
        if changed:
            await log_admin_action(message.from_id, "unmute", character[1], character_id, "", int(time.time()))
            await message.answer("🔊 Мут снят.")
        else:
            await message.answer("Активного мута нет.")

    @bot.on.message(text=["/удалитьперсонажа <character_id>", "/удалитьквенту <character_id>"])
    async def delete_character_command(message, character_id=None):
        if not await require_admin(message, "senior"):
            return
        try:
            character_id = int(character_id)
        except (TypeError, ValueError):
            await message.answer("Использование: /удалитьперсонажа ID")
            return
        character = await get_character_by_id(character_id)
        if not character:
            await message.answer("Персонаж не найден.")
            return
        sessions[message.from_id] = {"mode": "delete_reason", "character_id": character_id}
        await message.answer(f"⚠️ Подготовлено удаление #{character_id} — {character[2]}.\nВведите причину удаления.")

    def normalize_admin_button_text(value):
        """Нормализует текст кнопок VK перед ручной диспетчеризацией.

        VK/клиенты могут по-разному передавать variation selector у emoji,
        а в беседе иногда к тексту добавляется упоминание сообщества.
        """
        text = (value or "").strip().replace("\ufe0f", "")
        if text.startswith("[club") and "]" in text:
            text = text.split("]", 1)[1].strip()
        return " ".join(text.split())

    # Резервный роутинг админ-кнопок. Точные @bot.on.message(text=...)
    # остаются для обычного пути, а этот словарь ловит клики, которые VK/VKBottle
    # не сопоставил с VBMLRule и которые дошли до общего router_handler.
    admin_button_handlers = {
        normalize_admin_button_text("⬅️ Админ-панель"): admin_back_handler,
        normalize_admin_button_text("✖️ Закрыть админ-панель"): admin_close_handler,
        normalize_admin_button_text("👤 Управление игроком"): admin_player_start,
        normalize_admin_button_text("⬅️ К игроку"): admin_player_back,
        normalize_admin_button_text("💼 Карьера игрока"): player_career_menu,
        normalize_admin_button_text("📂 Назначить отдел"): choose_department,
        normalize_admin_button_text("⬆️ Повысить игрока"): promote_player,
        normalize_admin_button_text("⬇️ Понизить игрока"): demote_player,
        normalize_admin_button_text("🚪 Уволить игрока"): fire_player,
        normalize_admin_button_text("🏛 Фракция игрока"): faction_menu,
        normalize_admin_button_text("⬆️ Повысить ранг"): promote_faction,
        normalize_admin_button_text("⬇️ Понизить ранг"): demote_faction,
        normalize_admin_button_text("💳 Финансы игрока"): finance_player_menu,
        normalize_admin_button_text("➕ Выдать CR"): finance_action_start,
        normalize_admin_button_text("➖ Списать CR"): finance_action_start,
        normalize_admin_button_text("🧾 Установить баланс"): finance_action_start,
        normalize_admin_button_text("🏠 Жильё игрока"): housing_player_menu,
        normalize_admin_button_text("🏠 Выдать/изменить каюту"): housing_assign_start,
        normalize_admin_button_text("🗑 Изъять каюту"): housing_remove_action,
        normalize_admin_button_text("🔇 Наказания игрока"): punishment_player_menu,
        normalize_admin_button_text("🔇 Выдать мут"): mute_button_start,
        normalize_admin_button_text("🔊 Снять мут"): unmute_button,
        normalize_admin_button_text("🗑 Удалить персонажа"): delete_quest_button,
        normalize_admin_button_text("✅ ПОДТВЕРДИТЬ УДАЛЕНИЕ"): delete_confirm,
        normalize_admin_button_text("❌ ОТМЕНИТЬ УДАЛЕНИЕ"): delete_cancel,
        normalize_admin_button_text("🎁 Промокоды"): promo_menu_handler,
        normalize_admin_button_text("➕ Создать промокод"): promo_create_start,
        normalize_admin_button_text("💳 Добавить CR"): promo_add_cr_start,
        normalize_admin_button_text("🎒 Добавить предмет"): promo_add_item_start,
        normalize_admin_button_text("✅ Создать промокод"): promo_finish,
        normalize_admin_button_text("❌ Отмена промокода"): promo_cancel,
        normalize_admin_button_text("📋 Список промокодов"): promo_list_handler,
        normalize_admin_button_text("⛔ Отключить промокод"): promo_disable_start,
        normalize_admin_button_text("💡 Предложения"): suggestions_admin_list,
        normalize_admin_button_text("✅ Отметить рассмотренным"): suggestion_done,
        normalize_admin_button_text("❌ Отклонить предложение"): suggestion_reject,
        normalize_admin_button_text("💬 Ответить игроку"): suggestion_reply_start,
        normalize_admin_button_text("📜 Персонажи на проверке"): pending_characters_handler,
        normalize_admin_button_text("📌 Отчёты на проверке"): pending_quests_handler,
        normalize_admin_button_text("💳 Админ-экономика"): admin_economy_help,
        normalize_admin_button_text("👥 Администраторы"): admins_list_handler,
    }

    async def handle_legacy_finance(message):
        text = (message.text or "").strip()
        command = text.split(maxsplit=1)[0] if text else ""
        modes = {"/деньги": "finance_add", "/снятьденьги": "finance_subtract"}
        if command not in modes:
            return False
        if not await require_admin(message, "admin"):
            return True
        try:
            _, cid, amount = text.split()
            cid, amount = int(cid), int(amount)
        except ValueError:
            await message.answer(f"Использование: {command} ID сумма")
            return True
        ok, reason = await adjust_balance_by_admin(message.from_id, cid, modes[command], amount, int(time.time()))
        await message.answer("✅ Финансы обновлены." if ok else "Операция не выполнена: проверьте сумму, персонажа и баланс.")
        return True

    async def handle_admin_message(message):
        """Обрабатывает кнопки и свободный ввод пошаговой админ-панели."""
        if message.peer_id != ADMIN_CHAT_ID:
            return False
        role = await admin_role(message.from_id)
        if not role:
            return False

        raw_text = (message.text or "").strip()
        text = normalize_admin_button_text(raw_text)

        # Сначала ловим статические кнопки панели. Это резервный путь для
        # сообщений, которые не были пойманы точными VBML-правилами выше.
        handler = admin_button_handlers.get(text)
        if handler is not None:
            # finance_action_start использует message.text как ключ. При
            # отсутствии variation selector подберём режим по нормализованному тексту.
            if handler is finance_action_start:
                session = sessions.get(message.from_id, {})
                if not session.get("character_id"):
                    await message.answer("Сначала выберите игрока.")
                    return True
                finance_modes = {
                    normalize_admin_button_text("➕ Выдать CR"): "finance_add",
                    normalize_admin_button_text("➖ Списать CR"): "finance_subtract",
                    normalize_admin_button_text("🧾 Установить баланс"): "finance_set",
                }
                session["mode"] = finance_modes[text]
                await message.answer("Введите сумму CR целым числом.")
                return True
            await handler(message)
            return True

        # Динамическая кнопка предложения: «💡 Открыть #123».
        if text.startswith(normalize_admin_button_text("💡 Открыть #")):
            try:
                suggestion_id = int(text.rsplit("#", 1)[1])
            except (IndexError, ValueError):
                return False
            await suggestion_open_button(message, suggestion_id)
            return True

        session = sessions.get(message.from_id)
        if not session:
            return False
        mode = session.get("mode")

        if mode == "await_character_id":
            try:
                cid = int(text)
            except ValueError:
                await message.answer("ID персонажа должен быть числом.")
                return True
            await show_player(message, cid)
            return True

        cid = session.get("character_id")
        character = await get_character_by_id(cid or 0) if cid else None

        if mode == "choose_department" and text.startswith("📂 "):
            if not await has_role(message.from_id, "admin") or not character:
                return True
            key = text[2:].strip()
            if key not in DEPARTMENTS:
                await message.answer("Неизвестный отдел.")
                return True
            data = DEPARTMENTS[key]
            await update_character_job(cid, data["name"], data["jobs"][0], 1)
            await log_admin_action(message.from_id, "career_assign", character[1], cid, key, int(time.time()))
            await message.answer(f"✅ Назначен отдел: {data['name']}\nДолжность: {data['jobs'][0]}")
            await show_player(message, cid)
            return True

        if mode in {"finance_add", "finance_subtract", "finance_set"}:
            if not character or not await has_role(message.from_id, "admin"):
                return True
            try:
                amount = int(text)
            except ValueError:
                await message.answer("Введите целое число.")
                return True
            if amount < 0 or (mode != "finance_set" and amount == 0):
                await message.answer("Сумма должна быть положительной.")
                return True
            ok, reason = await adjust_balance_by_admin(message.from_id, cid, mode, amount, int(time.time()))
            if not ok:
                await message.answer("Операция не выполнена: проверьте права, сумму и текущий баланс.")
                return True
            await message.answer("✅ Финансы обновлены.")
            await show_player(message, cid)
            return True

        if mode == "housing_class" and text.startswith("🏠 Класс "):
            if not character or not await has_role(message.from_id, "admin"):
                return True
            cls = text.split()[-1]
            if cls not in HOUSING_CLASS_CAPACITY:
                await message.answer("Неизвестный класс.")
                return True
            housing = await get_housing(cid)
            if housing:
                interiors = await get_housing_interiors(cid)
                used = len(set(get_used_slots(interiors)))
                if used > HOUSING_CLASS_CAPACITY[cls]:
                    await message.answer(
                        f"⛔ В интерьере занято {used} слотов, новый класс поддерживает {HOUSING_CLASS_CAPACITY[cls]}. Сначала снимите часть комплектов."
                    )
                    return True
            session["housing_class"] = cls
            session["mode"] = "housing_sector"
            await message.answer("Введите сектор/номер каюты, например C-12.")
            return True

        if mode == "housing_sector":
            if not character or not await has_role(message.from_id, "admin"):
                return True
            sector = text[:50]
            cls = session.get("housing_class", "V")
            housing = await get_housing(cid)
            if housing:
                await assign_housing(cid, cls, sector)
            else:
                await assign_housing(cid, cls, sector)
            await log_admin_action(message.from_id, "housing_assign", character[1], cid, f"{cls} {sector}", int(time.time()))
            await message.answer(f"✅ Назначена каюта {cls} класса, сектор {sector}.")
            await show_player(message, cid)
            return True

        if mode == "mute_duration":
            seconds = parse_duration(text)
            if seconds is None:
                await message.answer("Формат: 30м, 2ч, 1д или навсегда.")
                return True
            if seconds == 0 and not await has_role(message.from_id, "senior"):
                await message.answer("Постоянный мут доступен только старшему администратору.")
                return True
            session["mute_seconds"] = seconds
            session["mode"] = "mute_reason"
            await message.answer("Введите причину мута.")
            return True

        if mode == "mute_reason":
            if not character or not await has_role(message.from_id, "admin"):
                return True
            reason = text[:500]
            seconds = session.get("mute_seconds")
            now = int(time.time())
            expires = 0 if seconds == 0 else now + seconds
            await issue_mute(character[1], cid, reason, message.from_id, now, expires)
            await log_admin_action(message.from_id, "mute", character[1], cid, f"{format_duration(seconds)}: {reason}", now)
            try:
                await bot.api.messages.send(
                    peer_id=character[1], random_id=0,
                    message=f"🔇 Вам выдан мут: {format_duration(seconds)}\nПричина: {reason}"
                )
            except Exception:
                pass
            await message.answer(f"🔇 Мут выдан: {format_duration(seconds)}.")
            await show_player(message, cid)
            return True

        if mode == "delete_reason":
            if not await has_role(message.from_id, "senior") or not character:
                return True
            reason = text[:500]
            session["delete_reason"] = reason
            session["mode"] = "delete_confirm"
            kb = (
                Keyboard(one_time=True)
                .add(Text("✅ ПОДТВЕРДИТЬ УДАЛЕНИЕ"), color=KeyboardButtonColor.NEGATIVE)
                .add(Text("❌ ОТМЕНИТЬ УДАЛЕНИЕ"), color=KeyboardButtonColor.SECONDARY)
            )
            await message.answer(
                f"⚠️ УДАЛЕНИЕ ПЕРСОНАЖА #{cid}\n{sci_line()}\n\n"
                f"Персонаж: {character[2]}\nПричина: {reason}\n\n"
                "Будут удалены персонаж, инвентарь, жильё, задания и местоположение. Баланс будет восстановлен до 1500 CR; XP и уровень будут сброшены.",
                keyboard=kb.get_json(),
            )
            return True

        if mode == "promo_code":
            code = text.upper().replace(" ", "")[:32]
            if len(code) < 3 or not code.replace("_", "").isalnum():
                await message.answer("Код должен содержать минимум 3 символа: латиница/цифры/_.")
                return True
            session["promo"]["code"] = code
            session["mode"] = "promo_limit"
            await message.answer("Введите общий лимит активаций. 0 = без лимита.")
            return True

        if mode == "promo_limit":
            try:
                limit = int(text)
                if limit < 0: raise ValueError
            except ValueError:
                await message.answer("Введите 0 или положительное число.")
                return True
            session["promo"]["max_uses"] = limit
            session["mode"] = "promo_days"
            await message.answer("Сколько дней действует промокод? 0 = без срока.")
            return True

        if mode == "promo_days":
            try:
                days = int(text)
                if days < 0: raise ValueError
            except ValueError:
                await message.answer("Введите 0 или положительное число дней.")
                return True
            session["promo"]["expires_at"] = 0 if days == 0 else int(time.time()) + days * 86400
            session["mode"] = "promo_rewards"
            await message.answer("Добавьте одну или несколько наград.", keyboard=promo_rewards_keyboard().get_json())
            return True

        if mode == "promo_add_cr":
            try:
                amount = int(text)
                if amount <= 0: raise ValueError
            except ValueError:
                await message.answer("Введите положительное количество CR.")
                return True
            session["promo"]["rewards"].append({
                "reward_type": "currency", "amount": amount,
                "reward_key": "cr", "item_name": "", "item_category": ""
            })
            session["mode"] = "promo_rewards"
            await message.answer(f"✅ Добавлено: {amount} CR. Можно добавить ещё награду.", keyboard=promo_rewards_keyboard().get_json())
            return True

        if mode == "promo_add_item":
            parts = text.split()
            if not parts:
                return True
            code = parts[0].lower()
            try:
                quantity = int(parts[1]) if len(parts) > 1 else 1
                if quantity <= 0: raise ValueError
            except ValueError:
                await message.answer("Количество должно быть положительным числом.")
                return True
            item = _catalog_index().get(code)
            if not item:
                await message.answer("Код предмета не найден. Используйте /кодымагазина.")
                return True
            session["promo"]["rewards"].append({
                "reward_type": "item", "amount": quantity,
                "reward_key": item["code"], "item_name": item["name"], "item_category": item["category"]
            })
            session["mode"] = "promo_rewards"
            await message.answer(f"✅ Добавлено: {item['name']} ×{quantity}.", keyboard=promo_rewards_keyboard().get_json())
            return True

        if mode == "promo_disable":
            changed = await set_promo_active(text, False)
            sessions.pop(message.from_id, None)
            await message.answer("⛔ Промокод отключён." if changed else "Промокод не найден.", keyboard=promo_keyboard().get_json())
            return True

        if mode == "suggestion_reply":
            sid = session.get("suggestion_id")
            suggestion = await get_suggestion(sid or 0)
            if not suggestion:
                await message.answer("Предложение не найдено.")
                return True
            response = text[:1500]
            await update_suggestion_status(sid, "answered", message.from_id, int(time.time()), response)
            try:
                await bot.api.messages.send(
                    peer_id=suggestion[1], random_id=0,
                    message=f"💬 ОТВЕТ НА ПРЕДЛОЖЕНИЕ #{sid}\n{sci_line()}\n\n{response}"
                )
            except Exception:
                pass
            await log_admin_action(message.from_id, "suggestion_answer", suggestion[1], suggestion[2], f"suggestion={sid}", int(time.time()))
            await message.answer("✅ Ответ отправлен игроку.")
            session["mode"] = "suggestion"
            return True

        return False

    return {
        "sessions": sessions,
        "admin_role": admin_role,
        "has_role": has_role,
        "handle_admin_message": handle_admin_message,
        "handle_legacy_finance": handle_legacy_finance,
        "show_player": show_player,
    }
