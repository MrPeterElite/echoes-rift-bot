import asyncio
import json
import unittest
from unittest.mock import patch
import test_stability as base
import database as db
from systems import duels
from systems.navigation import MAIN_MENU,CHARACTER_MENU,GEAR_MENU,SUPPORT_MENU

NOW=2000000
PEER=2000000888

class NavigationTests(unittest.IsolatedAsyncioTestCase):
    draft=base.StabilityTests.draft
    sql=base.StabilityTests.sql
    asyncTearDown=base.StabilityTests.asyncTearDown
    async def asyncSetUp(self):
        await base.StabilityTests.asyncSetUp(self)
        self.sql("INSERT INTO locations(code,name,peer_id,invite_link) VALUES ('arena','Arena',?,'https://vk.me/join/test')",(PEER,))
        self.sql("INSERT INTO locations(code,name,peer_id,invite_link) VALUES ('away','Away',?,'https://vk.me/join/away')",(PEER+1,))
        for cid in self.cids:await db.set_character_location(cid,'arena')
    async def test_main_groups_and_home(self):
        main=json.loads(MAIN_MENU.get_json())
        self.assertEqual(sum(len(r) for r in main['buttons']),6)
        for kb in (CHARACTER_MENU,GEAR_MENU,SUPPORT_MENU):
            self.assertEqual(json.loads(kb.get_json())['buttons'][-1][0]['action']['label'],'🏠 Главное меню')
    async def test_button_preview_move_and_open_chat(self):
        import main
        h={x.handler.__name__:x.handler for x in main.bot.labeler.message_view.handlers}
        m=base.Message(1,'🗺 Локации')
        await h['location_menu'](m)
        m.text='📍 Away';m.payload={'location_pick':'away','owner':1,'cid':self.cid}
        await h['location_choose'](m)
        self.assertEqual((await db.get_character_location(self.cid))[0],'arena')
        m.payload=m.keyboards[-1]['buttons'][0][0]['action']['payload'];m.text='🚶 Перейти сюда'
        await h['location_choose'](m)
        self.assertEqual((await db.get_character_location(self.cid))[0],'away')
        self.assertEqual(m.keyboards[-1]['buttons'][0][0]['action']['type'],'open_link')
    async def test_wrong_owner_character_and_chat_rejected(self):
        import main
        h={x.handler.__name__:x.handler for x in main.bot.labeler.message_view.handlers}
        for owner,cid,peer in [(2,self.cid,1),(1,self.cids[1],1),(1,self.cid,PEER)]:
            m=base.Message(1,'🚶 Перейти сюда',peer);m.payload={'location_move':'away','owner':owner,'cid':cid}
            await h['location_choose'](m)
            self.assertEqual((await db.get_character_location(self.cid))[0],'arena')
    async def test_start_duel_between_check_and_command_write(self):
        import main
        h={x.handler.__name__:x.handler for x in main.bot.labeler.message_view.handlers}
        d=(await duels.invite(1,PEER,self.cids[1],NOW))['duel'];original=duels.refresh_character_scene
        async def interleave(cid,now):
            s=await original(cid,now)
            await duels.act(2,PEER,d['id'],0,'accept',NOW)
            return s
        m=base.Message(1,'/перейти away',PEER)
        with patch('systems.locations.duels.refresh_character_scene',side_effect=interleave),patch('systems.locations.time.time',return_value=NOW):
            await h['move_location_handler'](m,'away')
        self.assertEqual((await db.get_character_location(self.cid))[0],'arena')
        self.assertIn('Нельзя покинуть',m.answers[-1])
    async def test_simultaneous_move_and_accept_never_active_elsewhere(self):
        d=(await duels.invite(1,PEER,self.cids[1],NOW))['duel']
        await asyncio.gather(db.move_character_if_idle(1,self.cid,'away',NOW),duels.act(2,PEER,d['id'],0,'accept',NOW))
        status=self.sql('SELECT status FROM duels WHERE id=?',(d['id'],))[0][0]
        loc=(await db.get_character_location(self.cid))[0]
        self.assertFalse(status=='active' and loc=='away')
    async def test_invalid_target_and_manual_scene(self):
        self.assertEqual(await db.move_character_if_idle(1,self.cid,'missing',NOW),(False,'not_found'))
        self.sql('INSERT OR IGNORE INTO character_health(character_id) VALUES (?)',(self.cid,))
        self.sql("UPDATE character_health SET scene_key='manual' WHERE character_id=?",(self.cid,))
        self.assertEqual(await db.move_character_if_idle(1,self.cid,'away',NOW),(False,'in_combat'))
    async def test_section_handlers_exist_and_work(self):
        import main
        h={x.handler.__name__:x.handler for x in main.bot.labeler.message_view.handlers}
        for label in ('👤 Персонаж','🎒 Снаряжение','💡 Помощь и связь'):
            m=base.Message(1,label);await h['section_menu'](m)
            self.assertTrue(m.keyboards)
        m=base.Message(1,'🏠 Главное меню');await h['back_handler'](m)
        self.assertEqual(m.keyboards[-1],json.loads(MAIN_MENU.get_json()))

if __name__=='__main__':unittest.main()
