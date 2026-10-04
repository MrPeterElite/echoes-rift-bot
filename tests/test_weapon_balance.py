import math
from pathlib import Path
from unittest.mock import AsyncMock, patch
import unittest
import test_weapons as weapons_base
from test_health import ITEMS, NOW
import test_stability as base
import database as db
from systems.vitals import get_health, admin_health_action
from systems.weapons import weapon_action, list_weapons
from systems.shop import format_item


class BalanceTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=weapons_base.WeaponTests.asyncSetUp
    asyncTearDown=weapons_base.WeaponTests.asyncTearDown
    draft=weapons_base.WeaponTests.draft
    sql=weapons_base.WeaponTests.sql
    buy=weapons_base.WeaponTests.buy
    async def test_all_nine_stats_images_and_damage(self):
        weapons=[i for i in ITEMS.values() if i['category']=='weapons']
        self.assertEqual(len(weapons),9)
        for item in weapons:
            path=Path(__file__).resolve().parents[1]/item['local_image']
            self.assertEqual(path.read_bytes()[:8],b'\x89PNG\r\n\x1a\n')
            self.assertIn(str(item['damage']),format_item(item,0,9,lambda:''))
            self.assertTrue(3<=math.ceil(100/item['damage'])<=9)
            await db.add_inventory_item(self.cid,'weapons',item['name'],1)
            weapon=(await list_weapons(self.cid))[-1]
            await weapon_action(1,self.cid,'equip',weapon['id'])
            self.assertEqual((await get_health(self.cid,NOW))['weapon_damage'],item['damage'])
            await admin_health_action(999,'hp',[self.cid],[100],NOW)
            await admin_health_action(999,'armor',[self.cid],[10,10],NOW)
            self.sql('UPDATE character_health SET food_hp=5,food_max=5,food_expires=? WHERE character_id=?',(NOW+1800,self.cid))
            await admin_health_action(999,'damage',[self.cid],[item['damage']],NOW)
            state=await get_health(self.cid,NOW)
            self.assertEqual(state['hp'],100-max(0,item['damage']-15))
    async def test_weapon_card_uses_photo_and_stats(self):
        import main
        handlers={h.handler.__name__:h.handler for h in main.bot.labeler.message_view.handlers}
        wid=await self.buy();message=base.Message();message.answer=AsyncMock()
        with patch('systems.weapons_ui.stabilize_attachments',new=AsyncMock(return_value='photo1_9')) as upload:
            await handlers['weapon_card'](message,str(wid))
        self.assertEqual(upload.call_args.args[3],self.item['local_image'])
        self.assertEqual(message.answer.call_args.kwargs['attachment'],'photo1_9')
        self.assertIn('Урон за попадание: 12',message.answer.call_args.args[0])

