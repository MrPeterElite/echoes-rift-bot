import json
from contextlib import closing
import asyncio
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace

# Import without ever opening the bundled/live DB or connecting to VK.
_BOOT = tempfile.TemporaryDirectory()
os.environ['DATABASE_PATH'] = str(Path(_BOOT.name) / 'bootstrap.db')
Path(os.environ['DATABASE_PATH']).touch()
os.environ['VK_TOKEN'] = 'test-offline-token'
os.environ['BOT_OWNER_ID'] = '999'
os.environ['BATTLE_CHAT_ID'] = '2000000888'
import database as db
from stability import initialize_database

class Message:
    def __init__(self, uid=1, text='', peer=None):
        self.from_id = uid
        self.peer_id = uid if peer is None else peer
        self.text = text
        self.answers = []
        self.keyboards = []
        self.attachments = []
    async def answer(self, text=None, **kwargs):
        self.answers.append(text or kwargs.get('message',''))
        if 'keyboard' in kwargs:self.keyboards.append(json.loads(kwargs['keyboard']))

class StabilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.network_guard=patch("vkbottle.api.API.request", new=AsyncMock(side_effect=AssertionError("Network is disabled in tests")))
        self.network_guard.start()
        self.temp = tempfile.TemporaryDirectory()
        db.DB_NAME = str(Path(self.temp.name)/'test.db')
        await initialize_database()
        self.cids = []
        for uid in (1,2,3):
            await db.create_user(uid)
            cid = await db.create_character(self.draft(uid))
            await db.update_character_status(cid, 'approved')
            self.cids.append(cid)
        self.cid = self.cids[0]
    async def asyncTearDown(self):
        self.network_guard.stop()
        self.temp.cleanup()
    def draft(self, uid=1):
        return dict(user_id=uid,name='Test',age='30',gender='x',faction='none',biology='human',personality='calm',history='history',arts=['photo1_1'],step='arts',active=True)
    def sql(self, sql, args=()):
        with closing(sqlite3.connect(db.DB_NAME)) as conn, conn:
            return conn.execute(sql,args).fetchall()
    async def quest(self):
        return await db.create_weekly_quest(self.cid,'Test','description',100,10,2_000_000)
    async def test_salary_concurrent(self):
        await db.update_character_job(self.cid,'dept','job',1)
        results=await asyncio.gather(*(db.claim_salary(1,2_000_000,604800,{1:100}) for _ in range(12)))
        self.assertEqual(sum(r[0] for r in results),1)
        self.assertEqual((await db.get_user(1))[1],1600)
    async def test_salary_rollback(self):
        await db.update_character_job(self.cid,'dept','job',1)
        self.sql("CREATE TRIGGER fail_salary BEFORE UPDATE OF last_salary_time ON characters BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
        with self.assertRaises(db.aiosqlite.IntegrityError):
            await db.claim_salary(1,2_000_000,604800,{1:100})
        self.assertEqual((await db.get_user(1))[1],1500)
    async def test_purchase_concurrent(self):
        await db.set_balance(1,100)
        item=dict(name='Test',category='food',price=80)
        results=await asyncio.gather(*(db.purchase_item(1,self.cid,item,1) for _ in range(8)))
        self.assertEqual(sum(r[0] for r in results),1)
        self.assertEqual((await db.get_user(1))[1],20)
        self.assertEqual((await db.get_inventory(self.cid))[0][2],1)
    async def test_purchase_rollback(self):
        async def fail(*args):raise RuntimeError('injected failure')
        with patch.object(db,'_put_item',fail),self.assertRaises(RuntimeError):
            await db.purchase_item(1,self.cid,dict(name='Test',category='food',price=80),1)
        self.assertEqual((await db.get_user(1))[1],1500)
    async def test_purchase_restrictions(self):
        for item in (dict(price=1,purchasable=False),dict(price=1,required_faction='other'),dict(price=-1)):
            item.update(name='Test',category='food')
            self.assertFalse((await db.purchase_item(1,self.cid,item,1))[0])
        self.assertEqual((await db.get_user(1))[1],1500)
    async def test_rent_concurrent(self):
        await db.assign_housing(self.cid,'V','A1')
        results=await asyncio.gather(*(db.pay_rent(1,self.cid,2_000_000,604800) for _ in range(8)))
        self.assertEqual(sum(r[0] for r in results),1)
        self.assertEqual((await db.get_user(1))[1],1375)
    async def test_rent_rollback(self):
        await db.assign_housing(self.cid,'V','A1')
        self.sql("CREATE TRIGGER fail_rent BEFORE UPDATE OF last_payment_time ON housing BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
        with self.assertRaises(db.aiosqlite.IntegrityError):
            await db.pay_rent(1,self.cid,2_000_000,604800)
        self.assertEqual((await db.get_user(1))[1],1500)
    async def test_item_transfer_concurrent(self):
        await db.add_inventory_item(self.cid,'food','Test',1)
        results=await asyncio.gather(*(db.transfer_inventory_item(self.cid,cid,'Test',1) for cid in self.cids[1:]))
        self.assertEqual(sum(r[0] for r in results),1)
        self.assertEqual(self.sql('SELECT SUM(quantity) FROM inventory')[0][0],1)
    async def test_item_transfer_rollback(self):
        await db.add_inventory_item(self.cid,'food','Test',1)
        async def fail(*args):raise RuntimeError('injected failure')
        with patch.object(db,'_put_item',fail),self.assertRaises(RuntimeError):
            await db.transfer_inventory_item(self.cid,self.cids[1],'Test',1)
        self.assertEqual((await db.get_inventory(self.cid))[0][2],1)
    async def test_item_use_concurrent(self):
        await db.add_inventory_item(self.cid,'food','Test',1)
        results=await asyncio.gather(*(db.remove_inventory_item(self.cid,'Test',1) for _ in range(8)))
        self.assertEqual(sum(r[0] for r in results),1)
    async def test_quest_issue_concurrent(self):
        ids=await asyncio.gather(*(self.quest() for _ in range(8)))
        self.assertEqual(len(set(ids)),1)
        self.assertEqual(self.sql('SELECT COUNT(*) FROM weekly_quests')[0][0],1)
    async def test_quest_report_and_reward_once(self):
        q=await self.quest()
        results=await asyncio.gather(*(db.submit_quest_report(q,'report',None,2_000_001) for _ in range(8)))
        self.assertEqual(sum(results),1)
        results=await asyncio.gather(*(db.complete_quest_with_rewards(q) for _ in range(8)))
        self.assertEqual(sum(r[0] for r in results),1)
        self.assertFalse(await db.update_quest_status(q,'rejected'))
        self.assertFalse(await db.submit_quest_report(q,'again',None,2_000_002))
        self.assertEqual((await db.get_user(1))[1:3],(1600,10))
    async def test_quest_approve_reject_race(self):
        q=await self.quest();await db.submit_quest_report(q,'report',None,2_000_001)
        approved,rejected=await asyncio.gather(db.complete_quest_with_rewards(q),db.update_quest_status(q,'rejected'))
        self.assertEqual(int(approved[0])+int(rejected),1)
        self.assertEqual((await db.get_user(1))[1],1600 if approved[0] else 1500)
        self.assertEqual((await db.get_quest_by_id(q))[6],'completed' if approved[0] else 'rejected')
    async def test_delete_restores_1500_and_removes_state(self):
        await db.set_balance(1,37);await db.assign_housing(self.cid,'V','A1')
        await db.add_inventory_item(self.cid,'food','Test',1);await self.quest()
        self.assertFalse(await db.reset_user(1,expected_character_id=9999))
        self.assertTrue(await db.reset_user(1,expected_character_id=self.cid))
        await db.create_user(1);await db.create_character(self.draft())
        self.assertEqual((await db.get_user(1))[1],1500)
        for table in ('housing','inventory','weekly_quests'):
            self.assertEqual(self.sql('SELECT COUNT(*) FROM '+table)[0][0],0)
    async def test_draft_restart_and_submission(self):
        draft=self.draft(10)
        self.assertTrue(await db.save_character_draft(10,draft))
        await initialize_database()
        self.assertEqual(await db.load_character_draft(10),draft)
        ids=await asyncio.gather(*(db.create_character(draft) for _ in range(5)))
        self.assertEqual(len(set(ids)),1)
        self.assertIsNone(await db.load_character_draft(10))
    async def test_admin_finance_permissions_and_audit(self):
        self.assertFalse((await db.adjust_balance_by_admin(999,self.cid,'finance_add',100,1))[0])
        await db.ensure_owner_admin(999,1)
        results=await asyncio.gather(*(db.adjust_balance_by_admin(999,self.cid,'finance_subtract',1000,1) for _ in range(4)))
        self.assertEqual(sum(r[0] for r in results),1)
        self.assertEqual((await db.get_user(1))[1],500)
        self.assertEqual(self.sql('SELECT COUNT(*) FROM admin_audit_log')[0][0],1)
    async def test_money_transfer_concurrent(self):
        await db.set_balance(1,100)
        results=await asyncio.gather(*(db.transfer_balance(1,2,80) for _ in range(8)))
        self.assertEqual(sum(r[0] for r in results),1)
        self.assertEqual((await db.get_user(1))[1],20)
        self.assertEqual((await db.get_user(2))[1],1580)

    async def test_combat_supply_purchase_and_transfer_blocked_in_scene(self):
        self.sql("INSERT OR IGNORE INTO character_health(character_id) VALUES (?)",(self.cid,))
        self.sql("UPDATE character_health SET scene_key='manual-scene' WHERE character_id=?",(self.cid,))
        item=dict(name='Combat ration',category='food',price=80,purchasable=True)
        self.assertEqual((await db.purchase_item(1,self.cid,item,1))[1],'in_combat')
        self.sql("UPDATE character_health SET scene_key='' WHERE character_id=?",(self.cid,))
        await db.add_inventory_item(self.cid,'food','Combat ration',1)
        self.sql("INSERT OR IGNORE INTO character_health(character_id) VALUES (?)",(self.cids[1],))
        self.sql("UPDATE character_health SET scene_key='manual-scene' WHERE character_id=?",(self.cids[1],))
        self.assertEqual((await db.transfer_inventory_item(self.cid,self.cids[1],'Combat ration',1))[1],'in_combat')
        self.assertEqual((await db.get_inventory(self.cid))[0][2],1)

    async def test_migration_repeat_preserves_custom_location(self):
        self.sql("UPDATE locations SET name='Custom' WHERE code='холл'")
        await initialize_database();await initialize_database()
        self.assertEqual(self.sql("SELECT name FROM locations WHERE code='холл'")[0][0],'Custom')
        self.assertEqual(self.sql('PRAGMA integrity_check'),[('ok',)])
    async def test_ui_delete_confirmation_and_cancel(self):
        import main
        handlers={h.handler.__name__:h.handler for h in main.bot.labeler.message_view.handlers}
        msg=Message()
        await handlers['delete_character_handler'](msg)
        self.assertIsNotNone(await db.get_character_by_user(1))
        await handlers['cancel_delete_character'](msg)
        await handlers['confirm_delete_character'](msg)
        self.assertIsNotNone(await db.get_character_by_user(1))
        await handlers['delete_character_handler'](msg)
        await handlers['confirm_delete_character'](msg)
        self.assertIsNone(await db.get_character_by_user(1))
        self.assertEqual((await db.get_user(1))[1],1500)
    async def test_ui_draft_resume(self):
        import main
        handlers={h.handler.__name__:h.handler for h in main.bot.labeler.message_view.handlers}
        msg=Message(10)
        await handlers['create_form_handler'](msg)
        msg.text='Name';await main.CHARACTER_RUNTIME['handle_message'](msg)
        self.assertEqual((await db.load_character_draft(10))['step'],'age')
        await main.CHARACTER_RUNTIME['pause_draft'](msg)
        msg.text='unrelated';await main.CHARACTER_RUNTIME['handle_message'](msg)
        self.assertEqual((await db.load_character_draft(10))['step'],'age')
        await handlers['create_form_handler'](msg)
        self.assertIn('возраст',msg.answers[-1])

    async def test_ui_confirmation_expires(self):
        import main
        handlers={h.handler.__name__:h.handler for h in main.bot.labeler.message_view.handlers}
        msg=Message()
        with patch('systems.characters.time',SimpleNamespace(monotonic=lambda:10)):
            await handlers['delete_character_handler'](msg)
        with patch('systems.characters.time',SimpleNamespace(monotonic=lambda:311)):
            await handlers['confirm_delete_character'](msg)
        self.assertIsNotNone(await db.get_character_by_user(1))
    async def test_ui_full_quenta_and_repeat_submit(self):
        import main
        handlers={h.handler.__name__:h.handler for h in main.bot.labeler.message_view.handlers}
        msg=Message(10)
        await handlers['create_form_handler'](msg)
        for text in ('Name','30','x'):
            msg.text=text;await main.CHARACTER_RUNTIME['handle_message'](msg)
        msg.text='🚫 Без фракции';await handlers['faction_selected_handler'](msg)
        for text in ('human','calm','history'):
            msg.text=text;await main.CHARACTER_RUNTIME['handle_message'](msg)
        draft=await db.load_character_draft(10)
        self.assertEqual(draft['step'],'arts')
        draft['arts']=['photo-1_1'];await db.save_character_draft(10,draft)
        with patch.object(main.bot,'api',SimpleNamespace(users=SimpleNamespace(get=AsyncMock(return_value=[SimpleNamespace(first_name='Test',last_name='User')])),messages=SimpleNamespace(send=AsyncMock(return_value=1)))):
            await handlers['finish_arts_handler'](msg)
            await handlers['finish_arts_handler'](msg)
        self.assertEqual(self.sql('SELECT COUNT(*) FROM characters WHERE user_id=10')[0][0],1)
        self.assertIsNone(await db.load_character_draft(10))
    async def test_admin_delete_resets_balance(self):
        await db.set_balance(1,9000)
        self.assertTrue((await db.delete_character_by_admin(self.cid))[0])
        self.assertEqual((await db.get_user(1))[1:4],(1500,0,1))
    async def test_admin_buttons_fallback_and_legacy_finance(self):
        import main
        await db.ensure_owner_admin(999,1)
        msg=Message(999,'👤 Управление игроком',main.ADMIN_CHAT_ID)
        self.assertTrue(await main.ADMIN_RUNTIME['handle_admin_message'](msg))
        msg.text=str(self.cid)
        self.assertTrue(await main.ADMIN_RUNTIME['handle_admin_message'](msg))
        msg.text=f'/снятьденьги {self.cid} 100'
        self.assertTrue(await main.ADMIN_RUNTIME['handle_legacy_finance'](msg))
        self.assertEqual((await db.get_user(1))[1],1400)
        bad=Message(2,f'/деньги {self.cid} 100',main.ADMIN_CHAT_ID)
        await main.ADMIN_RUNTIME['handle_legacy_finance'](bad)
        self.assertEqual((await db.get_user(1))[1],1400)
    async def test_serial_dispatch_release_after_error(self):
        from systems.dispatch import SerialMessageView
        from vkbottle.dispatch.views.bot import BotMessageView
        view=SerialMessageView();state={'active':0,'peak':0}
        async def handle(*args):
            state['active']+=1;state['peak']=max(state['active'],state['peak'])
            await asyncio.sleep(0)
            state['active']-=1
        event={'object':{'message':{'from_id':1}}}
        with patch.object(BotMessageView,'handle_event',handle):
            await asyncio.gather(*(view.handle_event(event,None,None) for _ in range(10)))
        self.assertEqual(state['peak'],1)
        with patch.object(BotMessageView,'handle_event',AsyncMock(side_effect=RuntimeError('test'))):
            with self.assertRaises(RuntimeError):await view.handle_event(event,None,None)
        with patch.object(BotMessageView,'handle_event',handle):
            await asyncio.wait_for(view.handle_event(event,None,None),1)
    async def test_promo_redeem_once(self):
        promo=await db.create_promo_code('TEST',10,0,999,1)
        await db.add_promo_reward(promo,'currency',100)
        results=await asyncio.gather(*(db.redeem_promo_code('TEST',1,self.cid,2) for _ in range(6)))
        self.assertEqual(sum(r[0] for r in results),1)
        self.assertEqual((await db.get_user(1))[1],1600)

if __name__=='__main__':unittest.main(verbosity=2)
