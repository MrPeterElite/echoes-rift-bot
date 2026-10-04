FOOD_DURATION = 30 * 60
FOOD_CAP = 30
BASIC_HEAL_LIMIT = 20


def describe_effect(item):
    effect = item.get('effect', {})
    kind = effect.get('type')
    if kind == 'food_hp':
        return (f"🍽 +{effect['amount']} временных HP на {FOOD_DURATION // 60} минут.\n"
                "Если сцена началась до истечения срока — запас действует до её конца.\n"
                f"Бонусы не складываются, максимум +{FOOD_CAP} HP. Более сильный заменяет слабый.\n"
                "Только вне боя. Основное здоровье и броню не восстанавливает.")
    if kind == 'heal':
        limit = (f"Бинтами и гемостатиками вместе: до {BASIC_HEAL_LIMIT} HP до полного выздоровления."
                 if effect['group']=='basic' else "В бою — один раз на персонажа.")
        return f"❤️ Восстанавливает {effect['amount']} HP.\n{limit}"
    if item.get('category') == 'armor':
        return (f"🛡 Прочность: {item['max_durability']}/{item['max_durability']}\n"
                "Принимает урон вместо здоровья. Не исчезает при поломке.\n"
                f"Полный ремонт: {(item['price']+3)//4} CR. Надевается и ремонтируется вне боя.")
    if item.get('category') in ('food', 'medicine'):
        return "🎭 Пока используется только для RP."
    return ''
