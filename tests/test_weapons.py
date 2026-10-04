import asyncio
import unittest
import test_stability as base
from test_health import ITEMS, NOW
import database as db
from systems.weapons import list_weapons, weapon_action
from systems.vitals import get_health, admin_health_action
from stability import initialize_database

class WeaponTests(unittest.IsolatedAsyncioTestCase):
    draft=base.StabilityTests.draft
    sql=base.StabilityTests.sql
    asyncTearDown=base.StabilityTests.asyncTearDown
    async def asyncSetUp(self):
        await base.StabilityTests.asyncSetUp(self)
        await db.ensure_owner_admin(999,1)
        self.item=ITEMS['weapon_vibroknife']
    async def buy(self,n=1):
        self.assertTrue((await db.purchase_item(1,self.cid,self.item,n))[0])
        return (await list_weapons(self.cid))[0]['id']
    async def test_purchase_catalog_and_persistence(self):
        self.assertEqual(sum(i['category']=='weapons' for i in ITEMS.values()),9)
        wid=await self.buy(2)
        await weapon_action(1,self.cid,'equip',wid)
        await initialize_database()
        self.assertEqual(len(await list_weapons(self.cid)),2)
        self.assertEqual(await db.get_inventory(self.cid),[])
        self.assertEqual((await get_health(self.cid,NOW))['weapon_name'],self.item['name'])
        self.assertEqual((await db.get_user(1))[1],900)
    async def test_ownership_transfer_and_one_equipped(self):
        wid=await self.buy(2)
        self.assertEqual((await weapon_action(2,self.cid,'equip',wid))['status'],'error')
        await asyncio.gather(*(weapon_action(1,self.cid,'equip',i) for i in (wid,wid+1)))
        self.assertEqual(sum(i['equipped'] for i in await list_weapons(self.cid)),1)
        await weapon_action(1,self.cid,'unequip')
        self.assertEqual((await get_health(self.cid,NOW))['weapon_name'],'не выбрано')
        await weapon_action(1,self.cid,'transfer',wid,self.cids[1])
        self.assertEqual((await weapon_action(1,self.cid,'equip',wid))['status'],'error')
        self.assertEqual((await weapon_action(2,self.cids[1],'equip',wid))['status'],'ok')
    async def test_scene_blocks_changes_and_receiving(self):
        wid=await self.buy()
        await admin_health_action(999,'start',[self.cids[1]],[],NOW)
        self.assertEqual((await weapon_action(1,self.cid,'transfer',wid,self.cids[1]))['status'],'error')
        await admin_health_action(999,'start',[self.cid],[],NOW)
        for action in ('equip','unequip','transfer'):
            self.assertEqual((await weapon_action(1,self.cid,action,wid,self.cids[2]))['status'],'error')
    async def test_purchase_failure_rolls_back_money(self):
        self.sql("CREATE TRIGGER fail_weapon BEFORE INSERT ON weapon_instances BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(db.aiosqlite.IntegrityError):await db.purchase_item(1,self.cid,self.item,1)
        self.assertEqual((await db.get_user(1))[1],1500)
    async def test_grant_and_deletion(self):
        await db.add_inventory_item(self.cid,'weapons',self.item['name'],2)
        self.assertEqual(len(await list_weapons(self.cid)),2)
        async with db._transaction() as conn:await db._delete_character_state(conn,self.cid)
        self.assertEqual(await list_weapons(self.cid),[])
    async def test_ui_state_and_equip_button(self):
        import main
        handlers={h.handler.__name__:h.handler for h in main.bot.labeler.message_view.handlers}
        wid=await self.buy();msg=base.Message()
        await handlers['weapon_card'](msg,str(wid))
        self.assertIn(f'#{wid}',msg.keyboards[-1]['buttons'][0][0]['action']['label'])
        await handlers['equip_weapon'](msg,str(wid))
        await handlers['health_card'](msg)
        self.assertIn(self.item['name'],msg.answers[-1])
        await handlers['unequip_weapon'](msg)
        await handlers['health_card'](msg)
        self.assertIn('Оружие: не выбрано',msg.answers[-1])

if __name__=='__main__':unittest.main()
