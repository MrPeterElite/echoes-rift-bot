"""Single source for stats of shop items and already-owned weapons."""
import json
from pathlib import Path


def weapon_stats(code):
    catalog=json.loads((Path(__file__).resolve().parents[1]/'shop_items.json').read_text(encoding='utf-8'))
    return next((item for item in catalog.get('weapons',{}).get('items',[]) if item['code']==code),{})


def describe_weapon(item):
    if not item.get('damage'):
        return 'Характеристики оружия не заданы.'
    return (f"💥 Урон за попадание: {item['damage']} · {item['damage_type']}\n"
            f"🎯 Дистанция: {item['range_label']}\n"
            'Урон сначала снимает броню, затем запас еды, затем HP.\n'
            'Попадание подтверждает ведущий. Критические попадания и пробитие пока не применяются.')
