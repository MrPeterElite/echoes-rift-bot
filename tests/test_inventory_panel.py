import asyncio
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
import test_stability as base
from test_health import ITEMS
import database as db
from systems import inventory_panel as panel, vitals, duels

PEER=2000000888

class InventoryPanelTests(unittest.IsolatedAsyncioTestCase):
    draft=base.StabilityTests.draft
    sql=base.StabilityTests.sql
    asyncTearDown=base.StabilityTests.asyncTearDown
    async def asyncSetUp(self):
        await base.StabilityTests.asyncSetUp(self)
        panel._locks.clear()
        self.sql("INSERT INTO locations(code,name,peer_id) VALUES ('arena','Arena',?)",(PEER,))
        for cid in self.cids: await db.set_character_location(cid,'arena')
        self.api=SimpleNamespace(send=AsyncMock(return_value=[{'conversation_message_id':100}]),edit=AsyncMock(return_value=True),delete=AsyncMock(return_value=True),send_message_event_answer=AsyncMock())
        self.bot=SimpleNamespace(api=SimpleNamespace(messages=self.api))
        self.message=base.Message(1,'/инвентарь',PEER)
        await panel.open_panel(self.bot,self.message)

    async def click(self,predicate,uid=1):
        row=await panel.load(PEER,1)
        i=next(i for i,a in enumerate(row['data']['actions']) if predicate(a))
        obj=dict(user_id=uid,peer_id=PEER,event_id='event',conversation_message_id=row['cmid'],payload=dict(inventory_ui=1,uid=1,token=row['token'],index=i))
        await panel.handle_callback(self.bot,obj)
        return obj

    async def item(self,code):
        item=ITEMS[code]
        await db.add_inventory_item(self.cid,item['category'],item['name'],3)
        await self.click(lambda a:a.get('category')==item['category'])
        await self.click(lambda a:a.get('name')==item['name'])
        return item

    async def test_repeat_open_state_and_keyboard_limits(self):
        await panel.open_panel(self.bot,self.message,'state')
        self.assertEqual(self.api.send.await_count,1)
        self.assertIn('СОСТОЯНИЕ',self.api.edit.call_args.kwargs['message'])
        keyboard=json.loads(self.api.edit.call_args.kwargs['keyboard'])
        self.assertLessEqual(len(keyboard['buttons']),6)
        self.assertTrue(all(b['action']['type']=='callback' for r in keyboard['buttons'] for b in r))

    async def test_consumption_preview_double_click_and_restart(self):
        item=await self.item('station_meal')
        await self.click(lambda a:a.get('op')=='preview')
        self.assertEqual((await db.get_inventory(self.cid))[0][2],3)
        row=await panel.load(PEER,1)
        i=next(i for i,a in enumerate(row['data']['actions']) if a.get('op')=='use')
        obj=dict(user_id=1,peer_id=PEER,event_id='double',conversation_message_id=100,payload=dict(inventory_ui=1,uid=1,token=row['token'],index=i))
        await asyncio.gather(panel.handle_callback(self.bot,obj),panel.handle_callback(self.bot,obj))
        panel._locks.clear()
        await panel.handle_callback(self.bot,obj)
        self.assertEqual((await db.get_inventory(self.cid))[0][2],2)
        self.assertEqual((await vitals.get_health(self.cid,int(time.time())))['food_hp'],item['effect']['amount'])

    async def test_foreign_stale_and_changed_character(self):
        row=await panel.load(PEER,1)
        await self.click(lambda a:a.get('screen')=='state',uid=2)
        self.assertEqual((await panel.load(PEER,1))['token'],row['token'])
        obj=await self.click(lambda a:a.get('screen')=='state')
        count=self.api.edit.await_count
        await panel.handle_callback(self.bot,obj)
        self.assertEqual(self.api.edit.await_count,count)
        await db.reset_user(1,expected_character_id=self.cid)
        await panel.handle_callback(self.bot,obj)
        self.assertEqual(self.api.edit.await_count,count)

    async def test_duel_started_after_preview_blocks_consumption(self):
        await self.item('station_meal')
        await self.click(lambda a:a.get('op')=='preview')
        now=int(time.time())
        d=(await duels.invite(1,PEER,self.cids[1],now))['duel']
        await duels.act(2,PEER,d['id'],0,'accept',now)
        await self.click(lambda a:a.get('op')=='use')
        self.assertEqual((await db.get_inventory(self.cid))[0][2],3)
        self.assertIn('расходует ход',self.api.edit.call_args.kwargs['message'])

    async def test_equipment_and_combat_lock(self):
        self.sql("INSERT INTO weapon_instances(character_id,item_code,name,weapon_type) VALUES (?,'weapon_01_vibroknife','Knife','melee')",(self.cid,))
        await self.click(lambda a:a.get('category')=='weapons')
        await self.click(lambda a:a.get('screen')=='item')
        await self.click(lambda a:a.get('op')=='equip')
        self.assertEqual(self.sql('SELECT equipped FROM weapon_instances')[0][0],1)
        self.sql("UPDATE character_health SET scene_key='manual' WHERE character_id=?",(self.cid,))
        await self.click(lambda a:a.get('op')=='unequip')
        self.assertEqual(self.sql('SELECT equipped FROM weapon_instances')[0][0],1)

    async def test_edit_failure_does_not_resend_or_repeat_effect(self):
        await self.item('station_meal')
        await self.click(lambda a:a.get('op')=='preview')
        self.api.edit.side_effect=RuntimeError('VK unavailable')
        obj=await self.click(lambda a:a.get('op')=='use')
        await panel.handle_callback(self.bot,obj)
        self.assertEqual(self.api.send.await_count,1)
        self.assertEqual((await db.get_inventory(self.cid))[0][2],2)
        self.api.edit.side_effect=None
        await panel.open_panel(self.bot,self.message)
        self.assertEqual(self.api.send.await_count,1)

    async def test_close_removes_only_saved_bot_message(self):
        obj=await self.click(lambda a:a.get('op')=='close')
        self.api.delete.assert_awaited_once_with(peer_id=PEER,cmids=[100],delete_for_all=True)
        self.assertIsNone(await panel.load(PEER,1))
        await panel.handle_callback(self.bot,obj)
        self.assertEqual(self.api.delete.await_count,1)

    async def test_full_hp_expiry_and_cancel_do_not_consume(self):
        await self.item('bandage')
        await self.click(lambda a:a.get('op')=='preview')
        self.assertIn('Здоровье полное',self.api.edit.call_args.kwargs['message'])
        self.sql('UPDATE character_health SET hp=95 WHERE character_id=?',(self.cid,))
        await self.click(lambda a:a.get('op')=='preview')
        row=await panel.load(PEER,1)
        for a in row['data']['actions']:
            if a.get('op')=='use': a['expires']=0
        self.sql('UPDATE bot_inventory_panels SET data=?',(json.dumps(row['data']),))
        await self.click(lambda a:a.get('op')=='use')
        self.assertEqual((await db.get_inventory(self.cid))[0][2],3)
        await self.click(lambda a:a.get('op')=='preview')
        await self.click(lambda a:a.get('screen')=='item')
        self.assertEqual((await db.get_inventory(self.cid))[0][2],3)
