import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import test_stability as base
import database as db
from systems import vitals
from systems.item_effects import describe_effect

NOW=2_000_000
CATALOG=json.loads((Path(__file__).resolve().parents[1]/'shop_items.json').read_text(encoding='utf-8'))
ITEMS={i['code']:i for c in CATALOG.values() for i in c['items']}

class HealthTests(unittest.IsolatedAsyncioTestCase):
    asyncTearDown=base.StabilityTests.asyncTearDown
    draft=base.StabilityTests.draft
    sql=base.StabilityTests.sql
    async def asyncSetUp(self):
        await base.StabilityTests.asyncSetUp(self)
        await db.ensure_owner_admin(999,1)
    async def give(self,code,n=1):
        i=ITEMS[code];await db.add_inventory_item(self.cid,i['category'],i['name'],n)
    async def hp(self,n):
        self.assertTrue((await vitals.admin_health_action(999,'hp',[self.cid],[n],NOW))[0])
    async def use(self,code,now=NOW,expected=None):
        return await vitals.use_health_item(1,self.cid,ITEMS[code],now,expected)
    async def state(self,now=NOW):return await vitals.get_health(self.cid,now)
    async def test_defaults_and_armor(self):
        s=await self.state();self.assertEqual((s['hp'],s['max_hp'],s['armor'],s['max_armor']),(100,100,0,0))
        self.assertFalse((await vitals.admin_health_action(999,'armor',[self.cid],[50,20],NOW))[0])
        self.assertTrue((await vitals.admin_health_action(999,'armor',[self.cid],[20,50],NOW))[0])
        self.assertFalse((await vitals.admin_health_action(2,'hp',[self.cid],[1],NOW))[0])
        self.assertEqual((await self.state())['hp'],100)
    async def test_food_expiry_exact(self):
        await self.give('station_meal')
        self.assertEqual((await self.use('station_meal'))['status'],'ok')
        self.assertEqual((await self.state(NOW+1799))['food_hp'],15)
        self.assertEqual((await self.state(NOW+1800))['food_hp'],0)
    async def test_food_no_heal_no_stack(self):
        await self.hp(40);await self.give('ration_pack',3)
        r=await asyncio.gather(*(self.use('ration_pack') for _ in range(3)))
        self.assertEqual(sum(x['status']=='ok' for x in r),1)
        self.assertEqual((await self.state())['hp'],40)
        self.assertEqual((await db.get_inventory(self.cid))[0][2],2)
    async def test_food_replace_confirmation(self):
        await self.give('ration_pack');await self.give('station_meal')
        await self.use('ration_pack')
        quote=await self.use('station_meal')
        self.assertEqual((quote['status'],quote['gain']),('confirm',7))
        self.assertEqual((await self.use('station_meal',expected=quote['quote']))['status'],'ok')
        self.assertEqual((await self.state())['food_hp'],15)
    async def test_scene_freezes_food_then_clears(self):
        await self.give('station_meal',2);await self.use('station_meal')
        self.assertTrue((await vitals.admin_health_action(999,'start',[self.cid],[],NOW+1700))[0])
        self.assertEqual((await self.state(NOW+5000))['food_hp'],15)
        self.assertEqual((await self.use('station_meal',NOW+5000))['status'],'in_combat')
        await vitals.admin_health_action(999,'end',[self.cid],[],NOW+5000)
        self.assertEqual((await self.state(NOW+5000))['food_hp'],0)
    async def test_expired_food_not_frozen_on_start(self):
        await self.give('station_meal');await self.use('station_meal')
        await vitals.admin_health_action(999,'start',[self.cid],[],NOW+1800)
        self.assertEqual((await self.state(NOW+2000))['food_hp'],0)
    async def test_basic_shared_limit_and_partial(self):
        await self.hp(40);await self.give('bandage');await self.give('hemostatic',2)
        await self.use('bandage')
        q=await self.use('hemostatic');self.assertEqual((q['status'],q['gain']),('confirm',10))
        await self.use('hemostatic',expected=q['quote'])
        self.assertEqual((await self.state())['hp'],60)
        self.assertEqual((await self.use('hemostatic'))['status'],'limit')
    async def test_full_hp_no_consumption(self):
        await self.give('hemostatic')
        self.assertEqual((await self.use('hemostatic'))['status'],'full_hp')
        self.assertEqual((await db.get_inventory(self.cid))[0][2],1)
    async def test_heal_partial_max_and_reset(self):
        await self.hp(95);await self.give('hemostatic')
        q=await self.use('hemostatic');self.assertEqual(q['gain'],5)
        await self.use('hemostatic',expected=q['quote'])
        s=await self.state();self.assertEqual((s['hp'],s['basic_healed']),(100,0))
    async def test_healing_preserves_food_and_armor(self):
        await self.hp(40);await self.give('station_meal');await self.use('station_meal')
        await vitals.admin_health_action(999,'armor',[self.cid],[5,20],NOW)
        await self.give('hemostatic');await self.use('hemostatic')
        s=await self.state();self.assertEqual((s['hp'],s['food_hp'],s['armor']),(60,15,5))
    async def test_medkit_once_in_scene_and_basic_independent(self):
        await self.hp(10);await self.give('field_medkit',2);await self.give('hemostatic')
        await vitals.admin_health_action(999,'start',[self.cid],[],NOW)
        self.assertEqual((await self.use('field_medkit'))['gain'],50)
        self.assertEqual((await self.use('field_medkit'))['status'],'limit')
        await self.use('hemostatic');self.assertEqual((await self.state())['hp'],80)
        await vitals.admin_health_action(999,'end',[self.cid],[],NOW)
        self.assertEqual((await self.state())['basic_healed'],20)
    async def test_zero_hp_no_consumption(self):
        await self.hp(0)
        for code in ('hemostatic','station_meal','field_medkit'):
            await self.give(code)
            self.assertEqual((await self.use(code))['status'],'incapacitated')
        self.assertEqual(len(await db.get_inventory(self.cid)),3)
    async def test_confirmation_rechecks_state(self):
        await self.hp(95);await self.give('hemostatic')
        q=await self.use('hemostatic')
        await self.hp(80)
        r=await self.use('hemostatic',expected=q['quote'])
        self.assertEqual((r['status'],r['gain']),('confirm',20))
        self.assertEqual((await self.state())['hp'],80)
    async def test_healing_atomic_rollback(self):
        await self.hp(50);await self.give('hemostatic')
        original=db._take_item
        async def fail(*args):
            await original(*args)
            raise RuntimeError('injected')
        with patch.object(db,'_take_item',fail),self.assertRaises(RuntimeError):await self.use('hemostatic')
        self.assertEqual((await self.state())['hp'],50)
        self.assertEqual((await db.get_inventory(self.cid))[0][2],1)
    async def test_concurrent_healing_limit(self):
        await self.hp(10);await self.give('hemostatic',5)
        r=await asyncio.gather(*(self.use('hemostatic') for _ in range(5)))
        self.assertEqual(sum(x['status']=='ok' for x in r),1)
        self.assertEqual((await self.state())['hp'],30)
    async def test_restart_and_delete(self):
        await self.hp(40);await self.give('station_meal');await self.use('station_meal')
        from stability import initialize_database
        await initialize_database()
        self.assertEqual((await self.state())['food_hp'],15)
        await db.reset_user(1,self.cid)
        self.assertIsNone(await self.state())
        self.cid=await db.create_character(self.draft())
        self.assertEqual((await self.state())['hp'],100)
        self.assertEqual((await db.get_user(1))[1],1500)
    async def test_catalog_and_shop_effects(self):
        from systems.shop import format_item
        self.assertEqual(ITEMS['field_medkit']['price'],400)
        self.assertIn('+15',format_item(ITEMS['station_meal'],0,1,lambda:''))
        self.assertIn('30 минут',describe_effect(ITEMS['station_meal']))
        self.assertIn('20 HP',describe_effect(ITEMS['hemostatic']))
        self.assertIn('RP',describe_effect(ITEMS['water_bottle']))
        self.assertEqual(len([i for i in ITEMS.values() if i.get('effect',{}).get('type')=='food_hp']),8)
    async def test_ui_partial_confirmation_and_card(self):
        import main
        handlers={h.handler.__name__:h.handler for h in main.bot.labeler.message_view.handlers}
        await self.hp(95);await self.give('hemostatic')
        msg=base.Message(1,'/использовать 1')
        await handlers['use_item_handler'](msg,'1')
        self.assertEqual((await self.state())['hp'],95)
        payload=msg.keyboards[-1]['buttons'][0][0]['action']['payload']
        msg.payload=payload
        await handlers['confirm_item_button'](msg)
        await handlers['confirm_item_button'](msg)
        self.assertEqual((await self.state())['hp'],100)
        self.assertEqual(await db.get_inventory(self.cid),[])
        msg.text='/состояние';await handlers['health_card'](msg)
        self.assertIn('100/100',msg.answers[-1])
        msg.text='/предмет 1';await handlers['inspect_item'](msg,'1')
        self.assertIn('не найден',msg.answers[-1])

if __name__=='__main__':unittest.main()
