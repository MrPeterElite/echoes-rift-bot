import asyncio
import unittest
from unittest.mock import patch
import test_stability as base
from test_health import ITEMS,NOW
import database as db
from systems import duels,vitals
from stability import initialize_database

PEER=2000000888

class DuelTests(unittest.IsolatedAsyncioTestCase):
    draft=base.StabilityTests.draft
    sql=base.StabilityTests.sql
    asyncTearDown=base.StabilityTests.asyncTearDown
    async def asyncSetUp(self):
        await base.StabilityTests.asyncSetUp(self)
        await db.ensure_owner_admin(999,1)
        self.sql("INSERT INTO locations(code,name,peer_id) VALUES ('arena','Arena',?)",(PEER,))
        for cid in self.cids:await db.set_character_location(cid,'arena')
    async def start(self):
        r=await duels.invite(1,PEER,self.cids[1],NOW)
        d=r['duel']
        with patch('systems.duels.secrets.choice',return_value=self.cid):
            return (await duels.act(2,PEER,d['id'],d['revision'],'accept',NOW))['duel']
    async def action(self,uid,d,action,now=NOW):return await duels.act(uid,PEER,d['id'],d['revision'],action,now)
    async def test_invitation_consent_and_permissions(self):
        d=(await duels.invite(1,PEER,self.cids[1],NOW))['duel']
        self.assertNotIn('duel',await self.action(1,d,'accept'))
        self.assertNotIn('duel',await self.action(3,d,'accept'))
        self.assertEqual((await vitals.get_health(self.cid,NOW))['scene_key'],'')
        self.assertNotIn('duel',await duels.act(2,PEER+1,d['id'],0,'accept',NOW))
        self.assertNotIn('duel',await duels.invite(3,PEER,self.cid,NOW))
        await self.action(2,d,'decline')
        self.assertEqual(self.sql('SELECT * FROM duel_members'),[])
    async def test_turns_duplicate_and_restart(self):
        d=await self.start()
        self.assertNotIn('duel',await self.action(2,d,'attack'))
        results=await asyncio.gather(*(self.action(1,d,'attack') for _ in range(6)))
        self.assertEqual(sum('duel' in r for r in results),1)
        d=next(r['duel'] for r in results if 'duel' in r)
        await initialize_database()
        self.assertEqual((await duels.panel(2,PEER,NOW))['duel']['phase'],'defend')
        self.assertNotIn('duel',await self.action(1,d,'block'))
        with patch('systems.duels.secrets.randbelow',return_value=0):
            r=await self.action(2,d,'block')
        self.assertEqual((await vitals.get_health(self.cids[1],NOW))['hp'],95)
        self.assertEqual(r['duel']['actor'],self.cids[1])
        self.assertNotIn('duel',await self.action(2,d,'block'))
    async def test_dodge_and_miss(self):
        d=await self.start();d=(await self.action(1,d,'attack'))['duel']
        with patch('systems.duels.secrets.randbelow',return_value=0):r=await self.action(2,d,'dodge')
        self.assertEqual((await vitals.get_health(self.cids[1],NOW))['hp'],100)
        d=(await self.action(2,r['duel'],'attack'))['duel']
        with patch('systems.duels.secrets.randbelow',return_value=99):await self.action(1,d,'block')
        self.assertEqual((await vitals.get_health(self.cid,NOW))['hp'],100)
    async def test_heal_spends_turn_and_no_bypass(self):
        await vitals.admin_health_action(999,'hp',[self.cid],[50],NOW)
        await db.add_inventory_item(self.cid,'medicine',ITEMS['bandage']['name'],2)
        d=await self.start()
        self.assertEqual((await vitals.use_health_item(1,self.cid,ITEMS['bandage'],NOW))['status'],'duel_only')
        r=await self.action(1,d,'heal:bandage')
        self.assertEqual(r['duel']['actor'],self.cids[1])
        self.assertEqual((await vitals.get_health(self.cid,NOW))['hp'],60)
        self.assertEqual((await db.get_inventory(self.cid))[0][2],1)
        self.assertNotIn('duel',await self.action(1,r['duel'],'heal:bandage'))
    async def test_missing_medicine_no_turn_loss(self):
        await vitals.admin_health_action(999,'hp',[self.cid],[50],NOW)
        d=await self.start();self.assertNotIn('duel',await self.action(1,d,'heal:bandage'))
        self.assertEqual((await duels.panel(1,PEER,NOW))['duel']['revision'],d['revision'])
    async def test_damage_layers_and_victory_cleanup(self):
        await vitals.admin_health_action(999,'hp',[self.cids[1]],[1],NOW)
        await vitals.admin_health_action(999,'armor',[self.cids[1]],[2,2],NOW)
        self.sql('UPDATE character_health SET food_hp=2,food_max=2,food_expires=? WHERE character_id=?',(NOW+100,self.cids[1]))
        d=await self.start();d=(await self.action(1,d,'attack'))['duel']
        with patch('systems.duels.secrets.randbelow',side_effect=[0,99]):r=await self.action(2,d,'dodge')
        self.assertIn('Победитель',r['text'])
        s=await vitals.get_health(self.cids[1],NOW)
        self.assertEqual((s['hp'],s['armor'],s['food_hp'],s['scene_key']),(1,0,0,''))
        self.assertEqual(self.sql('SELECT * FROM duel_members'),[])
    async def test_draw_requires_both_and_deadline(self):
        d=await self.start();r=await self.action(1,d,'draw',NOW+50);d=r['duel']
        self.assertEqual(d['expires'],NOW+duels.TURN_TTL)
        self.assertNotIn('duel',await self.action(1,d,'draw'))
        r=await self.action(2,d,'draw');self.assertIn('взаимному',r['text'])
        self.assertEqual((await vitals.get_health(self.cid,NOW))['scene_key'],'')
    async def test_expiry_and_surrender(self):
        d=(await duels.invite(1,PEER,self.cids[1],NOW))['duel']
        self.assertNotIn('duel',await self.action(2,d,'accept',NOW+300))
        d=await self.start();await self.action(2,d,'surrender')
        self.assertEqual(self.sql('SELECT * FROM duel_members'),[])
        d=await self.start();await duels.panel(1,PEER,NOW+600)
        self.assertEqual((await vitals.get_health(self.cid,NOW+600))['scene_key'],'')
    async def test_admin_edit_block_and_delete_cleanup(self):
        d=await self.start()
        self.assertFalse((await vitals.admin_health_action(999,'damage',[self.cid],[1],NOW))[0])
        async with db._transaction() as conn:await db._delete_character_state(conn,self.cid)
        self.assertEqual((await vitals.get_health(self.cids[1],NOW))['scene_key'],'')
        self.assertEqual(self.sql('SELECT status FROM duels WHERE id=?',(d['id'],))[0][0],'done')
    async def test_equipment_locked_and_damage_rollback(self):
        from systems.weapons import weapon_action
        from systems.armor import armor_action
        d=await self.start()
        with patch('systems.weapons.time.time',return_value=NOW),patch('systems.armor.time.time',return_value=NOW):
            self.assertEqual((await weapon_action(1,self.cid,'unequip'))['status'],'error')
            self.assertEqual((await armor_action(1,self.cid,'unequip'))['status'],'error')
        d=(await self.action(1,d,'attack'))['duel']
        self.sql("CREATE TRIGGER fail_duel BEFORE UPDATE OF revision ON duels BEGIN SELECT RAISE(ABORT,'test'); END")
        with patch('systems.duels.secrets.randbelow',return_value=0),self.assertRaises(db.aiosqlite.IntegrityError):
            await self.action(2,d,'block')
        self.assertEqual((await vitals.get_health(self.cids[1],NOW))['hp'],100)
        self.assertEqual((await duels.panel(1,PEER,NOW))['duel']['phase'],'defend')
    async def test_admin_end_unlocks_both(self):
        await self.start()
        self.assertTrue((await vitals.admin_health_action(999,'end',[self.cid],[],NOW))[0])
        self.assertEqual(self.sql('SELECT * FROM duel_members'),[])
        self.assertEqual((await vitals.get_health(self.cids[1],NOW))['scene_key'],'')
    async def test_menu_and_button_routing(self):
        import main
        h={x.handler.__name__:x.handler for x in main.bot.labeler.message_view.handlers}
        msg=base.Message(1,'/дуель',PEER)
        with patch('systems.duels_ui.time.time',return_value=NOW):await h['duel_panel'](msg)
        msg.payload=msg.keyboards[-1]['buttons'][0][0]['action']['payload']
        with patch('systems.duels_ui.time.time',return_value=NOW):await h['duel_button'](msg)
        msg.from_id=2
        msg.payload=msg.keyboards[-1]['buttons'][0][0]['action']['payload']
        with patch('systems.duels_ui.time.time',return_value=NOW):await h['duel_button'](msg)
        self.assertIn('Первый ход',msg.answers[-1])
        self.assertLessEqual(len(msg.keyboards[-1]['buttons']),6)
    async def test_ui_buttons_payload_and_heal_menu(self):
        import main
        h={x.handler.__name__:x.handler for x in main.bot.labeler.message_view.handlers}
        await vitals.admin_health_action(999,'hp',[self.cid],[95],NOW)
        await db.add_inventory_item(self.cid,'medicine',ITEMS['field_medkit']['name'],1)
        d=await self.start();msg=base.Message(1,peer=PEER)
        msg.payload={'duel':d['id'],'rev':d['revision'],'action':'medmenu'}
        with patch('systems.duels_ui.time.time',return_value=NOW):await h['duel_button'](msg)
        button=msg.keyboards[-1]['buttons'][0][0]['action']
        self.assertIn('+5 HP',button['label']);self.assertLessEqual(len(button['label']),40)
        msg.payload=button['payload']
        with patch('systems.duels_ui.time.time',return_value=NOW):await h['duel_button'](msg)
        self.assertEqual((await vitals.get_health(self.cid,NOW))['hp'],100)

    async def test_separate_battle_chat_keeps_origin_location(self):
        battle_peer=PEER+99
        r=await duels.invite(1,PEER,self.cids[1],NOW,battle_peer)
        d=r['duel']
        self.assertEqual((d['origin_peer'],d['battle_peer']),(PEER,battle_peer))
        accepted=await duels.act(2,PEER,d['id'],d['revision'],'accept',NOW)
        self.assertTrue(accepted.get('battle_started'))
        d=accepted['duel']
        self.assertEqual((await duels.panel(1,PEER,NOW))['redirect_peer'],battle_peer)
        self.assertEqual((await duels.panel(1,battle_peer,NOW))['duel']['id'],d['id'])
        self.assertNotIn('duel',await duels.act(1,PEER,d['id'],d['revision'],'attack',NOW))
        loc=await db.get_character_location(self.cid)
        self.assertEqual(loc[0],'arena')

    async def test_try_and_movement_blocked_during_active_duel(self):
        await self.start()
        import main
        msg=base.Message(1,'/try мгновенно победить',PEER)
        with patch('systems.rp.time.time',return_value=NOW):
            self.assertTrue(await main.handle_rp_command(msg,main.bot,main.RP_DEPS))
        self.assertIn('/try недоступен',msg.answers[-1])
        self.sql("INSERT INTO locations(code,name,peer_id,invite_link) VALUES ('other','Other',?,'x')",(PEER+50,))
        handlers={x.handler.__name__:x.handler for x in main.bot.labeler.message_view.handlers}
        move=base.Message(1,'/перейти other',PEER)
        with patch('systems.locations.time.time',return_value=NOW):
            await handlers['move_location_handler'](move,'other')
        self.assertIn('Нельзя покинуть',move.answers[-1])
        self.assertEqual((await db.get_character_location(self.cid))[0],'arena')

if __name__=='__main__':unittest.main()
