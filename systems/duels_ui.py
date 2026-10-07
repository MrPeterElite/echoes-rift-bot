import json
import time

from vkbottle import Keyboard, Text, KeyboardButtonColor

import database as db
from systems import duels
from systems.vitals import get_health
from systems.quiet_panels import quiet_handlers
from systems.duel_callbacks import register_callbacks


def register_duel_handlers(bot, battle_chat_id=None, battle_chat_link=''):
    """Register duel UI.

    Challenges are created/accepted in the real RP location. Once accepted,
    all mechanical duel buttons live in BATTLE_CHAT_ID. The characters never
    change their stored physical location.
    """
    quiet = quiet_handlers(bot)
    battle_chat_id = None if battle_chat_id is None else int(battle_chat_id or 0)
    battle_chat_link = (battle_chat_link or '').strip()

    def battle_hint():
        if battle_chat_link:
            return f"\n🔗 Боевая беседа: {battle_chat_link}"
        return "\nОткройте общую боевую беседу проекта."

    async def notify_battle_started(d):
        if not battle_chat_id:
            return
        mention_a = f"[id{d['user_a']}|{d['name_a']}]" if d.get('user_a') else d['name_a']
        mention_b = f"[id{d['user_b']}|{d['name_b']}]" if d.get('user_b') else d['name_b']
        text = (
            f"⚔️ ДУЭЛЬ #{d['id']} НАЧАЛАСЬ\n"
            f"{mention_a} — {mention_b}\n"
            f"📍 Исходная RP-локация: {d.get('origin_name','неизвестно')}\n\n"
            "Участники остаются физически в исходной локации. "
            "Здесь проходит системная часть боя.\n"
            "Напишите /дуель, чтобы открыть общую панель боя."
        )
        try:
            await bot.api.messages.send(peer_id=battle_chat_id, random_id=0, message=text)
        except Exception:
            pass
        # A private reminder is useful when a participant is not currently
        # looking at the battle chat; failures are harmless (closed DMs etc.).
        dm = (
            f"⚔️ Дуэль #{d['id']} принята.\n"
            f"Исходная локация: {d.get('origin_name','неизвестно')}.\n"
            "Системная часть боя проходит в боевой беседе."
            + battle_hint()
            + "\nВ боевой беседе напишите /дуель."
        )
        for uid in {d.get('user_a'), d.get('user_b')}:
            if not uid:
                continue
            try:
                await bot.api.messages.send(peer_id=uid, random_id=0, message=dm)
            except Exception:
                pass

    async def notify_origin_finished(d, result_text):
        peer = int(d.get('origin_peer') or d.get('peer') or 0)
        if not peer:
            return
        text = (
            f"⚔️ ДУЭЛЬ #{d['id']} ЗАВЕРШЕНА\n"
            f"{d.get('name_a','?')} (#{d['a']}) — {d.get('name_b','?')} (#{d['b']})\n"
            f"📍 {d.get('origin_name','Исходная локация')}\n\n"
            f"{result_text}\n\n"
            "Полученный урон и износ экипировки сохранены."
        )
        try:
            await bot.api.messages.send(peer_id=peer, random_id=0, message=text)
        except Exception:
            pass

    async def show(message, result):
        text = result.get('text', '')
        if getattr(message,'is_duel_callback',False) and not any(k in result for k in ('duel','targets','finished')):
            await message.notice(text or 'Откройте панель дуэли.');return
        kb = Keyboard(inline=True)
        d = result.get('duel')

        def button(label, action, color=KeyboardButtonColor.PRIMARY):
            kb.add(
                Text(label, payload={'duel': d['id'], 'rev': d['revision'], 'action': action}),
                color=color,
            ).row()

        if d:
            text += (
                f"\n⚔️ ДУЭЛЬ #{d['id']}\n"
                f"{d['name_a']} (#{d['a']}) — {d['name_b']} (#{d['b']})\n"
                f"📍 Исходная RP-локация: {d.get('origin_name','неизвестно')}\n"
            )
            if d['status'] == 'invite':
                text += 'Приглашённый игрок должен принять вызов в течение 5 минут.'
                button('✅ Принять бой', 'accept', KeyboardButtonColor.POSITIVE)
                button('❌ Отказаться', 'decline', KeyboardButtonColor.NEGATIVE)
                button('Отменить вызов', 'cancel', KeyboardButtonColor.SECONDARY)
            else:
                for key in ('a', 'b'):
                    s = await get_health(d[key], int(time.time()))
                    text += (
                        f"#{d[key]}: ❤️ {s['hp']}/100 · 🍽 {s['food_hp']} · "
                        f"🛡 {s['armor']}/{s['max_armor']} · 🔫 {s['weapon_name']} "
                        f"(урон {d['damage_' + key]})\n"
                    )
                if d['phase'] == 'turn':
                    text += f"Ход #{d['actor']}: атака или лечение."
                    button('⚔️ Атаковать', 'attack')
                    button('💊 Лечение', 'medmenu')
                else:
                    defender = d['b'] if d['actor'] == d['a'] else d['a']
                    text += f'Защищается #{defender}. Блок −40% урона; уклонение — шанс 40%.'
                    button('🛡 Блок', 'block')
                    button('💨 Уклонение', 'dodge')
                button('🤝 Завершить по согласию', 'draw', KeyboardButtonColor.SECONDARY)
                button('🏳 Сдаться', 'surrender_menu', KeyboardButtonColor.NEGATIVE)
                if d['draw_by']:
                    text += f"\n#{d['draw_by']} предлагает закончить бой. Кнопка согласия завершит бой для соперника."
                text += '\nОжидание действия — 10 минут. /дуель восстанавливает панель.'
        elif 'targets' in result:
            targets = result['targets']
            page = result.get('page', 0)
            page = max(0, min(page, max(0, (len(targets) - 1) // 4)))
            text = (
                '⚔️ Выберите соперника. Бой начнётся только после его согласия.\n'
                + ('Сейчас нет доступных соперников в этой локации.' if not targets else '')
            )
            for cid, name in targets[page * 4:page * 4 + 4]:
                kb.add(
                    Text(f'Вызвать #{cid}', payload={'duel_target': cid, 'owner': message.from_id}),
                    color=KeyboardButtonColor.PRIMARY,
                ).row()
                text += f'#{cid} — {name}\n'
            if page:
                kb.add(Text('Предыдущие соперники', payload={'duel_page': page - 1, 'owner': message.from_id})).row()
            if (page + 1) * 4 < len(targets):
                kb.add(Text('Следующие соперники', payload={'duel_page': page + 1, 'owner': message.from_id})).row()
        elif result.get('redirect_peer') == battle_chat_id and battle_chat_id:
            text += battle_hint() + '\nВ боевой беседе напишите /дуель.'

        data = json.loads(kb.get_json())
        data['buttons'] = [row for row in data['buttons'] if row]
        await message.answer(
            text or 'Откройте /дуель.',
            **({'keyboard': json.dumps(data, ensure_ascii=False)} if data['buttons'] else {}),
        )

    async def tell(message,text):
        if getattr(message,'is_duel_callback',False):await message.notice(text)
        else:await message.answer(text)

    @bot.on.message(text='/дуель')
    @quiet
    async def duel_panel(message):
        await show(message, await duels.panel(message.from_id, message.peer_id, int(time.time())))

    @bot.on.message(text=[
        'Вызвать #<target>', 'Предыдущие соперники', 'Следующие соперники',
        '✅ Принять бой', '❌ Отказаться', 'Отменить вызов',
        '⚔️ Атаковать', '🛡 Блок', '💨 Уклонение', '💊 Лечение',
        '🤝 Завершить по согласию', '🏳 Сдаться', 'Подтвердить сдачу', 'Лечить: <label>',
    ])
    @quiet
    async def duel_button(message, **kwargs):
        try:
            payload = getattr(message, 'payload', None) or {}
            if isinstance(payload, str):
                payload = json.loads(payload)
            if not isinstance(payload, dict):
                raise ValueError
            if 'owner' in payload and payload['owner'] != message.from_id:
                raise ValueError
            now = int(time.time())
            if 'duel_target' in payload or 'duel_page' in payload:
                if payload.get('owner') != message.from_id:
                    raise ValueError
                if 'duel_target' in payload:
                    result = await duels.invite(
                        message.from_id,
                        message.peer_id,
                        int(payload['duel_target']),
                        now,
                        battle_chat_id,
                    )
                else:
                    result = await duels.panel(message.from_id, message.peer_id, now)
                    result['page'] = int(payload['duel_page'])
                await show(message, result)
                return
            did, rev, action = int(payload['duel']), int(payload['rev']), payload['action']
        except (ValueError, TypeError, KeyError):
            await tell(message,'Нажмите актуальную кнопку из /дуель.')
            return

        if action in ('medmenu', 'surrender_menu'):
            result = await duels.panel(message.from_id, message.peer_id, now)
            d = result.get('duel')
            cid = result.get('cid')
            if (
                not d or d['id'] != did or d['revision'] != rev
                or d['battle_peer'] != message.peer_id or d['status'] != 'active'
            ):
                await tell(message,'Панель устарела. Откройте /дуель.')
                return
            kb = Keyboard(inline=True)
            if action == 'surrender_menu':
                kb.add(
                    Text(
                        'Подтвердить сдачу',
                        payload={'duel': did, 'rev': rev, 'action': 'surrender', 'owner': message.from_id},
                    ),
                    color=KeyboardButtonColor.NEGATIVE,
                )
                kb.row().add(Text('↩ К бою',payload={'action':'panel'}))
                await message.answer(
                    'Сдаться и признать победу соперника? HP и износ сохранятся.',
                    keyboard=kb.get_json(),
                )
                return
            if d['actor'] != cid or d['phase'] != 'turn':
                await tell(message,'Лечение доступно вместо атаки в свой ход.')
                return
            from systems.inventory import find_catalog_item
            s = await get_health(cid, now)
            count = 0
            for _, name, quantity in await db.get_inventory(cid):
                item = find_catalog_item(name)
                effect = (item or {}).get('effect', {})
                if effect.get('type') != 'heal' or quantity < 1:
                    continue
                gain = min(
                    effect['amount'],
                    100 - s['hp'],
                    20 - s['basic_healed'] if effect['group'] == 'basic'
                    else (0 if s['medkit_used'] else effect['amount']),
                )
                if gain <= 0:
                    continue
                if count:
                    kb.row()
                kb.add(Text(
                    f'Лечить: +{gain} HP · '
                    + {'bandage': 'Бинт', 'hemostatic': 'Гемостатик', 'field_medkit': 'Медкомплект'}.get(item['code'], 'Предмет'),
                    payload={'duel': did, 'rev': rev, 'action': 'heal:' + item['code']},
                ))
                count += 1
            if not count:
                await tell(message,'Доступного лечения нет: проверьте HP, лимиты и инвентарь.');return
            kb.row().add(Text('↩ К бою',payload={'action':'panel'}))
            await message.answer(
                'Нажатие потратит один предмет и ваш ход. /дуель — вернуться.'
                if count else 'Доступного лечения нет: проверьте HP, лимиты и инвентарь.',
                **({'keyboard': kb.get_json()} if count else {}),
            )
            return

        result = await duels.act(message.from_id, message.peer_id, did, rev, action, now)

        # Acceptance happens in the original RP chat, but the active combat UI
        # must never stay there.
        if result.get('battle_started') and result.get('duel'):
            d = result['duel']
            await message.answer(
                f"⚔️ Вызов принят. Дуэль #{d['id']} перенесена в боевую беседу."
                + battle_hint()
                + "\nПерсонажи физически остаются в этой RP-локации. В боевой беседе используйте /дуель.",
            )
            await notify_battle_started(d)
            return

        await show(message, result)
        if result.get('finished') and not result.get('already_finished') and duels.origin_peer(result['finished']) != duels.battle_peer(result['finished']):
            await notify_origin_finished(result['finished'], result.get('text', 'Дуэль завершена.'))

    register_callbacks(bot,duel_panel,duel_button)
    return {
        'battle_chat_id': battle_chat_id,
        'battle_chat_link': battle_chat_link,
    }
