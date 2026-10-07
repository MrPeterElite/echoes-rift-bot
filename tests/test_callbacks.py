import json
import unittest
from unittest.mock import AsyncMock,patch
from types import SimpleNamespace
from vkbottle import Bot
import test_stability as base
from systems.duels_ui import register_duel_handlers
from systems.duel_callbacks import callback_keyboard

from systems import duels
import database as db

NOW=2000000
PEER=2000000888

class CallbackTests(unittest.IsolatedAsyncioTestCase):
    draft=base.StabilityTests.draft
    sql=base.StabilityTests.sql
    asyncTearDown=base.StabilityTests.asyncTearDown
    async def asyncSetUp(self):
        await base.StabilityTests.asyncSetUp(self)
        self.sql("INSERT INTO locations(code,name,peer_id) VALUES ('rp','RP',?)",(PEER,))
        for cid in self.cids:await db.set_character_location(cid,'rp')
        self.bot=Bot(token='test-offline-token');register_duel_handlers(self.bot,0)
        self.callback=self.bot.labeler.raw_event_view.handlers['message_event'][0].handler.handler
    async def call(self,uid,payload):
        with patch('systems.duels_ui.time.time',return_value=NOW):
            await self.callback({'object':{'user_id':uid,'peer_id':PEER,'event_id':'event','payload':dict(payload,duel_ui=1)}})
    async def test_callback_flow_one_message_and_private_errors(self):
        send=AsyncMock(return_value=[SimpleNamespace(conversation_message_id=77)])
        edit=AsyncMock(return_value=True);ack=AsyncMock()
        methods=type(self.bot.api.messages)
        with patch.object(methods,'send',send),patch.object(methods,'edit',edit),patch.object(methods,'send_message_event_answer',ack):
            await self.call(1,{'action':'panel'})
            keyboard=json.loads(send.call_args.kwargs['keyboard'])
            self.assertEqual(keyboard['buttons'][0][0]['action']['type'],'callback')
            await self.call(1,{'duel_target':self.cids[1],'owner':1})
            d=(await duels.panel(1,PEER,NOW))['duel']
            self.assertEqual(d['battle_peer'],PEER)
            await self.call(2,{'duel':d['id'],'rev':0,'action':'accept'})
            self.assertEqual(send.await_count,1)
            edits=edit.await_count
            await self.call(3,{'duel':d['id'],'rev':1,'action':'attack'})
            self.assertEqual(edit.await_count,edits)
            self.assertEqual(send.await_count,1)
            self.assertIn('участникам',json.loads(ack.call_args.kwargs['event_data'])['text'])
            await self.call(1,{'duel':d['id'],'rev':1,'action':'surrender'})
            self.assertEqual(send.await_count,1)
            self.assertEqual(json.loads(edit.call_args.kwargs['keyboard'])['buttons'],[])
    async def test_callback_edit_failure_no_chat_flood(self):
        self.sql('INSERT INTO bot_duel_panels VALUES (?,?,?)',(PEER,'user:1',77))
        methods=type(self.bot.api.messages)
        with patch.object(methods,'send',new=AsyncMock()) as send,patch.object(methods,'edit',new=AsyncMock(side_effect=RuntimeError())),patch.object(methods,'send_message_event_answer',new=AsyncMock()) as ack:
            await self.call(1,{'action':'panel'})
            send.assert_not_awaited();self.assertIn('/дуель',json.loads(ack.call_args.kwargs['event_data'])['text'])
    async def test_back_button_and_conversion(self):
        raw=json.dumps({'inline':True,'buttons':[[{'action':{'type':'text','label':'Назад','payload':json.dumps({'action':'panel'})}}]]})
        action=json.loads(callback_keyboard(raw))['buttons'][0][0]['action']
        self.assertEqual(action['type'],'callback');self.assertEqual(json.loads(action['payload'])['duel_ui'],1)
    async def test_unknown_callback_ignored(self):
        methods=type(self.bot.api.messages)
        with patch.object(methods,'send_message_event_answer',new=AsyncMock()) as ack:
            await self.callback({'object':{'user_id':1,'peer_id':PEER,'event_id':'x','payload':{'other':1}}})
            ack.assert_not_awaited()
    async def test_text_fallback_setting(self):
        raw=json.dumps({'inline':True,'buttons':[[{'action':{'type':'text','label':'Назад','payload':'{}'}}]]})
        with patch.dict('os.environ',{'DUEL_CALLBACKS':'0'}):
            self.assertEqual(callback_keyboard(raw),raw)

if __name__=='__main__':unittest.main()

