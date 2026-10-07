import unittest
from unittest.mock import AsyncMock, patch
import test_stability as base
import database as db

class ArchiveTests(unittest.IsolatedAsyncioTestCase):
    draft=base.StabilityTests.draft
    sql=base.StabilityTests.sql
    asyncSetUp=base.StabilityTests.asyncSetUp
    asyncTearDown=base.StabilityTests.asyncTearDown

    async def populate(self):
        for uid in range(10,34):
            cid=await db.create_character(self.draft(uid))
            await db.update_character_status(cid,'approved')
        await db.create_character(self.draft(100))

    async def test_all_pages_cover_every_approved_character(self):
        await self.populate()
        seen=[]
        for page in range(3):
            rows,current,pages,total=await db.get_character_archive_page(page)
            self.assertEqual((current,pages,total),(page,3,27))
            seen.extend(r[0] for r in rows)
        self.assertEqual(seen,[r[0] for r in await db.get_approved_characters()])
        self.assertEqual(len(set(seen)),27)
        self.assertIn(self.cid,seen)
        self.assertEqual((await db.get_character_archive_page(999))[1],2)
        self.assertEqual((await db.get_character_archive_page(-1))[1],0)

    async def test_buttons_owner_boundary_and_numeric_opening(self):
        import main
        await self.populate()
        h={x.handler.__name__:x.handler for x in main.bot.labeler.message_view.handlers}
        m=base.Message(1,'📚 Персонажи')
        api=type(main.bot.api.users)
        with patch.object(api,'get',new=AsyncMock(side_effect=RuntimeError('offline'))):
            await h['archive_handler'](m)
            self.assertIn('Страница 1/3',m.answers[-1])
            self.assertLess(len(m.answers[-1]),4096)
            m.payload=m.keyboards[-1]['buttons'][0][0]['action']['payload']
            await h['archive_page_handler'](m)
            self.assertIn('Страница 2/3',m.answers[-1])
            other=base.Message(2,'Персонажи ▶');other.payload=m.payload
            await h['archive_page_handler'](other)
            self.assertIn('свой список',other.answers[-1])
        self.assertIn(1,main.archive_users)

    async def test_empty_and_shrinking_archive(self):
        await self.populate()
        self.sql("UPDATE characters SET status='rejected' WHERE id!=?",(self.cid,))
        rows,page,pages,total=await db.get_character_archive_page(2)
        self.assertEqual((len(rows),page,pages,total),(1,0,1,1))
        await db.update_character_status(self.cid,'pending')
        self.assertEqual(await db.get_character_archive_page(),([],0,1,0))

    async def test_admin_chat_archive_and_card_without_character(self):
        import main
        await db.upsert_bot_admin(999,'moderator',999,1)
        m=base.Message(999,'📚 Архив персонажей',main.ADMIN_CHAT_ID)
        with patch.object(type(main.bot.api.users),'get',new=AsyncMock(side_effect=RuntimeError('offline'))):
            self.assertFalse(await main.ONBOARDING_GATE(m))
            self.assertTrue(await main.ADMIN_RUNTIME['handle_admin_message'](m))
            self.assertIn('АРХИВ ПЕРСОНАЖЕЙ',m.answers[-1])
            self.assertEqual(main.ADMIN_RUNTIME['sessions'][999]['mode'],'archive')
            m.text=str(self.cid)
            self.assertTrue(await main.ADMIN_RUNTIME['handle_admin_message'](m))
            self.assertIn('https://vk.com/id1',m.answers[-1])
            m.text='⬅️ Админ-панель'
            await main.ADMIN_RUNTIME['handle_admin_message'](m)
            self.assertNotIn(999,main.ADMIN_RUNTIME['sessions'])
        outsider=base.Message(1,'📚 Архив персонажей',main.ADMIN_CHAT_ID)
        h={x.handler.__name__:x.handler for x in main.bot.labeler.message_view.handlers}
        await h['admin_archive_handler'](outsider)
        self.assertIn('Недостаточно',outsider.answers[-1])
