import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import test_stability as base
from systems.quiet_panels import PanelMessage,EMPTY_KEYBOARD

PEER=2000000777

class QuietTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=base.StabilityTests.asyncSetUp
    asyncTearDown=base.StabilityTests.asyncTearDown
    draft=base.StabilityTests.draft
    sql=base.StabilityTests.sql
    def setup_panel(self,uid=1,cmid=55):
        message=base.Message(uid,peer=PEER)
        message.conversation_message_id=999
        message.answer=AsyncMock(return_value=SimpleNamespace(conversation_message_id=cmid))
        bot=SimpleNamespace(api=SimpleNamespace(messages=SimpleNamespace(edit=AsyncMock(return_value=True),delete=AsyncMock())))
        return message,bot,PanelMessage(message,bot,None)
    async def test_edit_reuses_own_message_after_restart(self):
        m,b,p=self.setup_panel()
        await p.answer('Первое',keyboard='{}')
        p=PanelMessage(m,b,None)
        await p.answer('Второе',keyboard='{}')
        self.assertEqual(m.answer.await_count,1)
        self.assertEqual(b.api.messages.edit.call_args.kwargs['cmid'],55)
        self.assertEqual(b.api.messages.edit.call_args.kwargs['peer_id'],PEER)
        b.api.messages.delete.assert_not_awaited()
    async def test_replacement_deletes_only_known_bot_message(self):
        m,b,p=self.setup_panel();await p.answer('First')
        b.api.messages.edit.side_effect=RuntimeError('edit rejected')
        m.answer.return_value=SimpleNamespace(conversation_message_id=56)
        await p.answer('New')
        b.api.messages.delete.assert_awaited_once_with(peer_id=PEER,cmids=[55],delete_for_all=True)
        self.assertEqual(self.sql('SELECT cmid FROM bot_duel_panels')[0][0],56)
        self.assertNotEqual(b.api.messages.delete.call_args.kwargs['cmids'],[999])
    async def test_failed_send_does_not_delete_old_panel(self):
        m,b,p=self.setup_panel();await p.answer('First')
        b.api.messages.edit.side_effect=RuntimeError('edit rejected')
        m.answer.side_effect=RuntimeError('send rejected')
        with self.assertRaises(RuntimeError):await p.answer('New')
        b.api.messages.delete.assert_not_awaited()
        self.assertEqual(self.sql('SELECT cmid FROM bot_duel_panels')[0][0],55)
    async def test_no_incoming_id_fallback_and_private_passthrough(self):
        m,b,p=self.setup_panel();m.answer.return_value=None
        await p.answer('First');await p.answer('Second')
        b.api.messages.edit.assert_not_awaited();b.api.messages.delete.assert_not_awaited()
        self.assertEqual(self.sql('SELECT * FROM bot_duel_panels'),[])
        m.peer_id=1;m.answer.return_value=SimpleNamespace(conversation_message_id=5)
        await p.answer('Private')
        self.assertEqual(self.sql('SELECT * FROM bot_duel_panels'),[])
    async def test_final_result_clears_buttons_and_peers_isolated(self):
        m,b,p=self.setup_panel();await p.answer('First',keyboard='{}');await p.answer('Finished')
        self.assertEqual(b.api.messages.edit.call_args.kwargs['keyboard'],EMPTY_KEYBOARD)
        m.peer_id=PEER+1
        await p.answer('Other chat')
        self.assertEqual(m.answer.await_count,2)
        self.assertEqual(len(self.sql('SELECT * FROM bot_duel_panels')),2)
    async def test_shared_invitation_accept_and_final_use_same_panel(self):
        from vkbottle import Bot
        import database as db
        from systems.duels_ui import register_duel_handlers
        from systems import duels
        self.sql("INSERT INTO locations(code,name,peer_id) VALUES ('quiet','Quiet',?)",(PEER,))
        for cid in self.cids:await db.set_character_location(cid,'quiet')
        bot=Bot(token='test-offline-token');register_duel_handlers(bot)
        h={x.handler.__name__:x.handler for x in bot.labeler.message_view.handlers}
        first=base.Message(1,'/дуель',PEER)
        first.answer=AsyncMock(return_value=SimpleNamespace(conversation_message_id=70))
        second=base.Message(2,peer=PEER);second.answer=AsyncMock()
        with patch.object(type(bot.api.messages),'edit',new=AsyncMock(return_value=True)) as edit:
            await h['duel_panel'](first)
            first.payload={'duel_target':self.cids[1],'owner':1}
            await h['duel_button'](first)
            d=(await duels.panel(2,PEER,0))['duel']
            second.payload={'duel':d['id'],'rev':d['revision'],'action':'accept'}
            await h['duel_button'](second)
            d=(await duels.panel(2,PEER,0))['duel']
            second.payload={'duel':d['id'],'rev':d['revision'],'action':'surrender'}
            await h['duel_button'](second)
            self.assertEqual(first.answer.await_count,1)
            second.answer.assert_not_awaited()
            self.assertTrue(all(c.kwargs['cmid']==70 for c in edit.call_args_list))
            self.assertEqual(edit.call_args.kwargs['keyboard'],EMPTY_KEYBOARD)
        self.assertEqual(self.sql('SELECT panel_key FROM bot_duel_panels'),[(f"duel:{d['id']}",)])

