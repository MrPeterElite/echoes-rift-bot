import json
import unittest
from unittest.mock import patch,AsyncMock
import test_stability as base
import database as db
from systems.onboarding import entry,CREATE,CONTINUE,STATUS,HELP

def labels(keyboard):return [b['action']['label'] for row in keyboard['buttons'] for b in row]

class OnboardingTests(unittest.IsolatedAsyncioTestCase):
    draft=base.StabilityTests.draft
    sql=base.StabilityTests.sql
    asyncSetUp=base.StabilityTests.asyncSetUp
    asyncTearDown=base.StabilityTests.asyncTearDown
    async def test_new_draft_pending_approved_menus(self):
        self.assertEqual(labels(json.loads((await entry(10))[1].get_json())),[CREATE,HELP])
        await db.save_character_draft(10,{'step':'name','user_id':10,'arts':[],'active':False})
        self.assertEqual(labels(json.loads((await entry(10))[1].get_json())),[CONTINUE,HELP])
        await db.update_character_status(self.cid,'pending')
        self.assertEqual(labels(json.loads((await entry(1))[1].get_json())),[STATUS,HELP])
        await db.update_character_status(self.cid,'approved')
        self.assertIn('🗺 Локации',labels(json.loads((await entry(1))[1].get_json())))
    async def test_pending_cannot_use_old_buttons_or_commands(self):
        import main
        await db.update_character_status(self.cid,'pending')
        for text in ('🛒 Магазин','/купить 1','/перейти холл','🎒 Снаряжение','/богачи','📚 Архив квент','👤 Создать персонажа'):
            m=base.Message(1,text);self.assertTrue(await main.ONBOARDING_GATE(m))
            self.assertEqual(labels(m.keyboards[-1]),[STATUS,HELP])
        self.assertEqual((await db.get_user(1))[1],1500)
    async def test_creation_free_text_does_not_reach_game_handlers(self):
        import main
        m=base.Message(10,CREATE)
        self.assertTrue(await main.ONBOARDING_GATE(m))
        m.text='🛒 Магазин';await main.ONBOARDING_GATE(m)
        self.assertEqual((await db.load_character_draft(10))['step'],'name')
        m.text='Алекс';await main.ONBOARDING_GATE(m)
        self.assertEqual((await db.load_character_draft(10))['step'],'age')
        m.text=HELP;await main.ONBOARDING_GATE(m)
        self.assertFalse((await db.load_character_draft(10))['active'])
        m.text=CONTINUE;await main.ONBOARDING_GATE(m)
        self.assertIn('возраст',m.answers[-1])
        m.text='/инвентарь';self.assertTrue(await main.ONBOARDING_GATE(m))
        self.assertEqual((await db.load_character_draft(10))['step'],'age')
    async def test_admin_without_character_keeps_admin_access(self):
        import main
        await db.ensure_owner_admin(999,1)
        self.assertFalse(await main.ONBOARDING_GATE(base.Message(999,'/админ',main.ADMIN_CHAT_ID)))
        self.assertTrue(await main.ONBOARDING_GATE(base.Message(999,'🛒 Магазин')))
    async def test_approved_status_button_and_delete_return(self):
        import main
        handlers={h.handler.__name__:h.handler for h in main.bot.labeler.message_view.handlers}
        m=base.Message(1,STATUS);await handlers['onboarding_status'](m)
        self.assertIn('🗺 Локации',labels(m.keyboards[-1]))
        await handlers['delete_character_handler'](m);await handlers['confirm_delete_character'](m)
        self.assertEqual(labels(m.keyboards[-1]),[CREATE,HELP])
        self.assertEqual((await db.get_user(1))[1],1500)
    async def test_callback_gate_without_approval(self):
        import main
        callback=main.bot.labeler.raw_event_view.handlers['message_event'][0].handler.handler
        await db.update_character_status(self.cid,'pending')
        with patch.object(type(main.bot.api.messages),'send_message_event_answer',new=AsyncMock()) as answer:
            await callback({'object':{'user_id':1,'peer_id':2000000888,'event_id':'x','payload':{'duel_ui':1,'action':'panel'}}})
        self.assertIn('одобрения',json.loads(answer.call_args.kwargs['event_data'])['text'])
    async def test_submission_and_approval_replace_keyboard(self):
        import main
        from types import SimpleNamespace
        handlers={h.handler.__name__:h.handler for h in main.bot.labeler.message_view.handlers}
        await db.save_character_draft(10,self.draft(10))
        m=base.Message(10,'✅ Готово')
        send=AsyncMock(return_value=1)
        api=SimpleNamespace(users=SimpleNamespace(get=AsyncMock(return_value=[SimpleNamespace(first_name='Test',last_name='User')])),messages=SimpleNamespace(send=send))
        with patch.object(main.bot,'api',api):
            await handlers['finish_arts_handler'](m)
            self.assertEqual(labels(m.keyboards[-1]),[STATUS,HELP])
            c=await db.get_character_by_user(10)
            await db.ensure_owner_admin(999,1)
            await main.LEGACY_ADMIN_ROUTER(base.Message(999,f'✅ Одобрить #{c[0]}',main.ADMIN_CHAT_ID))
        self.assertEqual((await db.get_character_by_user(10))[10],'approved')
        self.assertIn('🗺 Локации',labels(json.loads(send.call_args.kwargs['keyboard'])))
    async def test_middleware_is_registered_and_stops(self):
        import main
        from systems.onboarding import install_onboarding
        from vkbottle import Bot
        bot=Bot(token='test-offline-token')
        install_onboarding(bot,main.ADMIN_CHAT_ID,main.CHARACTER_RUNTIME,set(main.FACTION_DESCRIPTIONS),set())
        middleware=bot.labeler.message_view.middlewares[-1](base.Message(10,'/богачи'))
        await middleware.pre()
        self.assertFalse(middleware.can_forward)

if __name__=='__main__':unittest.main()
