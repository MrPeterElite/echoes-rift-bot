import asyncio
import json
import time
import unittest
from unittest.mock import patch
import test_inventory_panel as base
from systems import inventory_panel as panel
from systems.inventory_transfer import transfer, recipients
import database as db
PEER=base.PEER


class TransferTests(unittest.IsolatedAsyncioTestCase):
    draft=base.InventoryPanelTests.draft
    sql=base.InventoryPanelTests.sql
    asyncSetUp=base.InventoryPanelTests.asyncSetUp
    asyncTearDown=base.InventoryPanelTests.asyncTearDown
    item=base.InventoryPanelTests.item
    click=base.InventoryPanelTests.click
    async def prepare(self):
        item=await self.item('station_meal')
        await self.click(lambda a:a.get('screen')=='transfer_people')
        await self.click(lambda a:a.get('target')==self.cids[1])
        await self.click(lambda a:a.get('quantity')==2)
        await self.click(lambda a:a.get('screen')=='transfer_confirm')
        return item

    async def test_button_transfer_duplicate_and_no_extra_messages(self):
        item=await self.prepare()
        row=await panel.load(PEER,1)
        index=next(i for i,a in enumerate(row['data']['actions']) if a.get('op')=='transfer_commit')
        obj=dict(user_id=1,peer_id=PEER,event_id='transfer',conversation_message_id=100,payload=dict(inventory_ui=1,uid=1,token=row['token'],index=index))
        await asyncio.gather(panel.handle_callback(self.bot,obj),panel.handle_callback(self.bot,obj))
        self.assertEqual((await db.get_inventory(self.cid))[0][2],1)
        self.assertEqual((await db.get_inventory(self.cids[1]))[0][1:],(item['name'],2))
        self.assertEqual(self.api.send.await_count,1)
        kb=json.loads(self.api.edit.call_args.kwargs['keyboard'])
        self.assertLessEqual(len(kb['buttons']),6)

    async def test_cancel_and_moving_recipient(self):
        await self.prepare()
        await self.click(lambda a:a.get('screen')=='item')
        self.assertEqual((await db.get_inventory(self.cid))[0][2],3)
        await self.click(lambda a:a.get('screen')=='transfer_people')
        await self.click(lambda a:a.get('target')==self.cids[1])
        await self.click(lambda a:a.get('screen')=='transfer_confirm')
        self.sql('DELETE FROM character_locations WHERE character_id=?',(self.cids[1],))
        await self.click(lambda a:a.get('op')=='transfer_commit')
        self.assertEqual((await db.get_inventory(self.cid))[0][2],3)
        self.assertFalse(await db.get_inventory(self.cids[1]))
        self.assertNotIn(self.cids[1],[r[0] for r in await recipients(self.cid)])

    async def test_atomic_failure_and_combat(self):
        await self.prepare()
        row=await panel.load(PEER,1)
        action=next(a for a in row['data']['actions'] if a.get('op')=='transfer_commit')
        with patch.object(db,'_put_item',side_effect=RuntimeError('test')):
            with self.assertRaises(RuntimeError): await transfer(1,self.cid,PEER,action)
        self.assertEqual((await db.get_inventory(self.cid))[0][2],3)
        self.sql("UPDATE character_health SET scene_key='manual' WHERE character_id=?",(self.cids[1],))
        self.assertIn('вне боя',await transfer(1,self.cid,PEER,action))
        self.assertFalse(await db.get_inventory(self.cids[1]))

    async def test_gear_preserves_durability_and_rejects_equipped(self):
        self.sql("INSERT INTO armor_instances(character_id,item_code,name,durability,max_durability,price) VALUES (?,'test','Vest',7,15,200)",(self.cid,))
        aid=self.sql('SELECT id FROM armor_instances')[0][0]
        action=dict(back=dict(category='armor',item_id=aid,name='Vest'),target=self.cids[1],target_name='Test',quantity=1,expires=int(time.time())+60)
        self.sql('UPDATE armor_instances SET equipped=1 WHERE id=?',(aid,))
        self.assertIn('Сначала снимите',await transfer(1,self.cid,PEER,action))
        self.sql('UPDATE armor_instances SET equipped=0 WHERE id=?',(aid,))
        self.assertIn('✅',await transfer(1,self.cid,PEER,action))
        self.assertEqual(self.sql('SELECT character_id,durability FROM armor_instances WHERE id=?',(aid,))[0],(self.cids[1],7))
        self.sql("INSERT INTO weapon_instances(character_id,item_code,name,weapon_type) VALUES (?,'test','Blaster','ranged')",(self.cid,))
        wid=self.sql('SELECT id FROM weapon_instances')[0][0]
        weapon=dict(action,back=dict(category='weapons',item_id=wid,name='Blaster'))
        self.assertIn('✅',await transfer(1,self.cid,PEER,weapon))
        self.assertEqual(self.sql('SELECT character_id FROM weapon_instances WHERE id=?',(wid,))[0][0],self.cids[1])

    async def test_expiry_quantity_and_changed_target(self):
        await self.prepare()
        row=await panel.load(PEER,1)
        action=next(a for a in row['data']['actions'] if a.get('op')=='transfer_commit')
        self.assertIn('истекло',await transfer(1,self.cid,PEER,dict(action,expires=0)))
        self.assertIn('Недостаточно',await transfer(1,self.cid,PEER,dict(action,quantity=99)))
        self.sql("UPDATE characters SET status='rejected' WHERE id=?",(self.cids[1],))
        self.assertIn('изменился',await transfer(1,self.cid,PEER,action))
        self.assertEqual((await db.get_inventory(self.cid))[0][2],3)
