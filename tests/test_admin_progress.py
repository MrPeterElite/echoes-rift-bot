import asyncio
import json
import unittest
import test_stability as base
import database as db
from systems.admin_progress import change_progress, FACTIONS, MAX_XP


class AdminProgressTests(unittest.IsolatedAsyncioTestCase):
    draft = base.StabilityTests.draft
    sql = base.StabilityTests.sql
    asyncSetUp = base.StabilityTests.asyncSetUp
    asyncTearDown = base.StabilityTests.asyncTearDown

    async def test_xp_changes_and_limits(self):
        await db.ensure_owner_admin(999, 1)
        for action, amount, expected in [('xp_add', 100, 100), ('xp_subtract', 30, 70), ('xp_set', 0, 0)]:
            self.assertEqual(await change_progress(999, self.cid, action, amount, 1), (True, expected))
        for action, amount in [('xp_subtract', 1), ('xp_add', -1), ('xp_add', 0), ('xp_set', MAX_XP+1), ('xp_add', True)]:
            self.assertFalse((await change_progress(999, self.cid, action, amount, 1))[0])
        self.assertEqual((await db.get_user(1))[1:4], (1500, 0, 1))
        self.assertEqual(self.sql('SELECT COUNT(*) FROM admin_audit_log')[0][0], 3)

    async def test_permissions_deleted_target_and_faction_validation(self):
        await db.upsert_bot_admin(22, 'moderator', 999, 1)
        faction = next(iter(FACTIONS.values()))
        self.assertEqual(await change_progress(22, self.cid, 'xp_set', 9, 1), (False, 'forbidden'))
        await db.upsert_bot_admin(22, 'admin', 999, 1)
        self.assertEqual(await change_progress(22, self.cid, 'faction_set', 'unknown', 1), (False, 'invalid'))
        self.assertEqual(await change_progress(22, 99999, 'faction_set', faction, 1), (False, 'not_found'))
        await db.deactivate_bot_admin(22)
        self.assertEqual(await change_progress(22, self.cid, 'faction_set', faction, 1), (False, 'forbidden'))

    async def test_faction_rank_reset_and_audit(self):
        await db.ensure_owner_admin(999, 1)
        faction = next(iter(FACTIONS.values()))
        await db.update_faction_rank(self.cid, 'Old rank', 3)
        self.assertEqual(await change_progress(999, self.cid, 'faction_set', faction, 1), (True, faction))
        c = await db.get_character_by_id(self.cid)
        self.assertEqual((c[5], c[15], c[16]), (faction, None, 0))
        await db.update_faction_rank(self.cid, 'New rank', 2)
        self.assertEqual(await change_progress(999, self.cid, 'faction_set', faction, 1), (False, 'unchanged'))
        self.assertEqual((await db.get_character_by_id(self.cid))[15], 'New rank')
        detail = json.loads(self.sql('SELECT details FROM admin_audit_log')[0][0])
        self.assertEqual(detail['previous_rank'], 'Old rank')
        self.assertEqual((await db.get_user(1))[1], 1500)

    async def test_concurrent_xp_and_audit_rollback(self):
        await db.ensure_owner_admin(999, 1)
        result = await asyncio.gather(*(change_progress(999, self.cid, 'xp_add', 10, 1) for _ in range(8)))
        self.assertTrue(all(r[0] for r in result))
        self.assertEqual((await db.get_user(1))[2], 80)
        self.sql("CREATE TRIGGER fail_audit BEFORE INSERT ON admin_audit_log BEGIN SELECT RAISE(ABORT, 'test'); END")
        for action, value in [('xp_add', 5), ('faction_set', next(iter(FACTIONS.values())))]:
            with self.assertRaises(Exception): await change_progress(999, self.cid, action, value, 1)
        self.assertEqual((await db.get_user(1))[2], 80)
        self.assertEqual((await db.get_character_by_id(self.cid))[5], 'none')

    async def test_buttons_fallback_cancellation_and_chat_boundary(self):
        import main
        await db.ensure_owner_admin(999, 1)
        runtime = main.ADMIN_RUNTIME
        m = base.Message(999, peer=main.ADMIN_CHAT_ID)
        await runtime['show_player'](m, self.cid)
        for text in ['⭐ Опыт игрока', '➕ Выдать XP', '12']:
            m.text = text
            self.assertTrue(await runtime['handle_admin_message'](m))
        self.assertEqual((await db.get_user(1))[2], 12)
        for text in ['🧾 Установить XP', '⬅️ К игроку', '0']:
            m.text = text; await runtime['handle_admin_message'](m)
        self.assertEqual((await db.get_user(1))[2], 12)
        for text in ['🏛 Фракция игрока', '🔄 Изменить фракцию', '⚙ HELIOS Dynamics']:
            m.text = text; self.assertTrue(await runtime['handle_admin_message'](m))
        self.assertEqual((await db.get_character_by_id(self.cid))[5], FACTIONS['⚙ HELIOS Dynamics'])
        handlers = {h.handler.__name__: h.handler for h in main.bot.labeler.message_view.handlers}
        await handlers['experience_start'](base.Message(999, '➕ Выдать XP'))
        self.assertEqual(runtime['sessions'][999]['mode'], 'player')

    async def test_exact_buttons_and_revoked_role_before_amount(self):
        import main
        await db.upsert_bot_admin(22, 'admin', 999, 1)
        handlers = {h.handler.__name__: h.handler for h in main.bot.labeler.message_view.handlers}
        m = base.Message(22, '🧾 Установить XP', main.ADMIN_CHAT_ID)
        await main.ADMIN_RUNTIME['show_player'](m, self.cid)
        await handlers['experience_start'](m)
        await db.upsert_bot_admin(22, 'moderator', 999, 1)
        m.text = '99'; await main.ADMIN_RUNTIME['handle_admin_message'](m)
        self.assertEqual((await db.get_user(1))[2], 0)
