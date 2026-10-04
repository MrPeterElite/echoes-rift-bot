import asyncio
from pathlib import Path
from unittest.mock import AsyncMock
import unittest
import test_stability as base
from test_health import ITEMS, NOW
import database as db
from systems.armor import armor_action, list_armor, repair_cost
from systems import vitals

class ArmorTests(unittest.IsolatedAsyncioTestCase):
    asyncTearDown=base.StabilityTests.asyncTearDown
    draft=base.StabilityTests.draft
    sql=base.StabilityTests.sql
    async def asyncSetUp(self):
        await base.StabilityTests.asyncSetUp(self)
        await db.ensure_owner_admin(999,1)
        self.item=ITEMS['armor_civilian']
    async def buy(self,n=1):
        self.assertTrue((await db.purchase_item(1,self.cid,self.item,n))[0])
        return (await list_armor(self.cid))[0]['id']
    async def act(self,action,aid=None,**kw):return await armor_action(1,self.cid,action,aid,**kw)
    async def damage(self,n):
        self.assertTrue((await vitals.admin_health_action(999,'damage',[self.cid],[n],NOW))[0])
    async def test_individual_purchase_and_rewards(self):
        await self.buy(2)
        await db.add_inventory_item(self.cid,'armor',self.item['name'],1)
        rows=await list_armor(self.cid)
        self.assertEqual(len({i['id'] for i in rows}),3)
        self.assertEqual(await db.get_inventory(self.cid),[])
        self.assertEqual((await db.get_user(1))[1],1100)
    async def test_equip_transfer_and_damage_order(self):
        aid=await self.buy(2)
        await self.act('equip',aid)
        await db.add_inventory_item(self.cid,'food',ITEMS['station_meal']['name'],1)
        await vitals.use_health_item(1,self.cid,ITEMS['station_meal'],NOW)
        await self.damage(35)
        state=await vitals.get_health(self.cid,NOW)
        self.assertEqual((state['armor'],state['food_hp'],state['hp']),(0,0,95))
        await self.act('equip',aid+1)
        self.assertEqual(sum(i['equipped'] for i in await list_armor(self.cid)),1)
        await self.act('transfer',aid,target_id=self.cids[1])
        self.assertEqual((await list_armor(self.cids[1]))[0]['durability'],0)
        self.assertEqual((await armor_action(1,self.cid,'equip',aid))['status'],'error')
    async def test_concurrent_confirmed_repair(self):
        aid=await self.buy();await self.act('equip',aid);await self.damage(15)
        q=await self.act('repair',aid)
        self.assertEqual(q['status'],'confirm')
        self.assertEqual((await db.get_user(1))[1],1300)
        results=await asyncio.gather(*(self.act('repair',aid,expected=q['quote']) for _ in range(5)))
        self.assertEqual(sum(r['status']=='ok' for r in results),1)
        self.assertEqual((await db.get_user(1))[1],1250)
        self.assertEqual((await vitals.get_health(self.cid,NOW))['armor'],15)
    async def test_repair_stale_quote_insufficient_and_rollback(self):
        aid=await self.buy();await self.act('equip',aid);await self.damage(5)
        q=await self.act('repair',aid);await self.damage(5)
        r=await self.act('repair',aid,expected=q['quote']);self.assertEqual(r['status'],'confirm')
        await db.set_balance(1,0)
        self.assertEqual((await self.act('repair',aid,expected=r['quote']))['status'],'error')
        await db.set_balance(1,100)
        self.sql("CREATE TRIGGER fail_repair BEFORE UPDATE OF durability ON armor_instances BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(db.aiosqlite.IntegrityError):await self.act('repair',aid,expected=r['quote'])
        self.assertEqual((await db.get_user(1))[1],100)
        self.assertEqual((await list_armor(self.cid))[0]['durability'],5)
    async def test_scene_lock(self):
        aid=await self.buy();await self.act('equip',aid)
        await vitals.admin_health_action(999,'start',[self.cid],[],NOW)
        for action in ('equip','unequip','repair','transfer'):
            self.assertEqual((await self.act(action,aid,target_id=self.cids[1]))['status'],'error')
    async def test_photos_prices_and_repair_rounding(self):
        armor=[i for i in ITEMS.values() if i['category']=='armor']
        self.assertEqual(len(armor),6)
        self.assertEqual([repair_cost(0,i['max_durability'],i['price']) for i in armor],[50,100,175,275,425,650])
        self.assertEqual(repair_cost(14,15,200),4)
        for item in armor:
            f=Path(__file__).resolve().parents[1]/item['local_image']
            self.assertTrue(f.is_file())
            self.assertEqual(f.read_bytes()[:8],b'\x89PNG\r\n\x1a\n')
    async def test_ui_repair_confirmation(self):
        import main
        handlers={h.handler.__name__:h.handler for h in main.bot.labeler.message_view.handlers}
        aid=await self.buy();await self.act('equip',aid);await self.damage(15)
        msg=base.Message()
        await handlers['repair_armor'](msg,str(aid))
        msg.payload=msg.keyboards[-1]['buttons'][0][0]['action']['payload']
        await handlers['confirm_armor_repair'](msg)
        await handlers['confirm_armor_repair'](msg)
        self.assertEqual((await db.get_user(1))[1],1250)
    async def test_shop_sends_matching_image(self):
        from vkbottle import Bot, Keyboard, Text, KeyboardButtonColor
        from systems.shop import register_shop_handlers
        bot=Bot(token='test-offline-token')
        upload=AsyncMock(return_value='photo1_2')
        register_shop_handlers(bot,dict(Keyboard=Keyboard,Text=Text,KeyboardButtonColor=KeyboardButtonColor,sci_line=lambda:'',get_character_by_user=db.get_character_by_user,create_user=db.create_user,get_user=db.get_user,stabilize_attachments=upload))
        handlers={h.handler.__name__:h.handler for h in bot.labeler.message_view.handlers}
        msg=base.Message(text='🛡 Броня')
        msg.answer=AsyncMock()
        await handlers['category_handler'](msg)
        self.assertEqual(upload.call_args.args[3],self.item['local_image'])
        self.assertEqual(msg.answer.call_args.kwargs['attachment'],'photo1_2')
        self.assertIn(self.item['name'],msg.answer.call_args.kwargs['message'])

if __name__=='__main__':unittest.main()
