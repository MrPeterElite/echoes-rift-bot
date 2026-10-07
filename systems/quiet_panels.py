"""Edit only bot-owned, persisted duel panels; never infer IDs from user messages."""
import asyncio
import json
import logging
from functools import wraps
import database as db
from systems.duel_callbacks import callback_keyboard

EMPTY_KEYBOARD=json.dumps({'inline':True,'buttons':[]})
log=logging.getLogger(__name__)

async def ensure_panel_tables():
    async with db._transaction() as conn:
        await conn.execute('''CREATE TABLE IF NOT EXISTS bot_duel_panels (
            peer INTEGER NOT NULL,panel_key TEXT NOT NULL,cmid INTEGER NOT NULL,
            PRIMARY KEY(peer,panel_key))''')

async def participant_key(message):
    conn=await db.connect()
    try:
        cur=await conn.execute("SELECT d.id FROM duels d JOIN characters c ON c.id IN (d.a,d.b) WHERE c.user_id=? AND d.status!='done' AND ((d.status='invite' AND COALESCE(d.origin_peer,d.peer)=?) OR (d.status='active' AND COALESCE(d.battle_peer,d.peer)=?)) ORDER BY d.id DESC LIMIT 1",(message.from_id,message.peer_id,message.peer_id))
        row=await cur.fetchone()
        return f'duel:{row[0]}' if row else None
    finally:await conn.close()

class PanelMessage:
    def __init__(self,message,bot,key):
        self.original=message;self.bot=bot;self.initial_key=key
    def __getattr__(self,name):return getattr(self.original,name)
    async def answer(self,text=None,**kwargs):
        if self.peer_id<2000000000:return await self.original.answer(text,**kwargs)
        key=await participant_key(self) or self.initial_key or f'user:{self.from_id}'
        conn=await db.connect()
        try:
            cur=await conn.execute('SELECT cmid FROM bot_duel_panels WHERE peer=? AND panel_key=?',(self.peer_id,key))
            row=await cur.fetchone()
            # The challenger's target selector becomes the shared invitation panel.
            if not row and key.startswith('duel:'):
                cur=await conn.execute('SELECT cmid FROM bot_duel_panels WHERE peer=? AND panel_key=?',(self.peer_id,f'user:{self.from_id}'))
                row=await cur.fetchone()
                if row:
                    await conn.execute('UPDATE bot_duel_panels SET panel_key=? WHERE peer=? AND panel_key=?',(key,self.peer_id,f'user:{self.from_id}'))
                    await conn.commit()
        finally:await conn.close()
        message_text=text or kwargs.pop('message',None) or 'Откройте /дуель.'
        keyboard=callback_keyboard(kwargs.get('keyboard',EMPTY_KEYBOARD))
        if row:
            try:
                edited=await self.bot.api.messages.edit(peer_id=self.peer_id,cmid=row[0],message=message_text,keyboard=keyboard)
                if edited is False:raise RuntimeError('VK did not edit the panel')
                return None
            except Exception as exc:
                log.warning('Cannot edit bot duel panel in peer %s: %s',self.peer_id,type(exc).__name__)
                if getattr(self.original,'is_duel_callback',False):
                    await self.original.notice('Не удалось обновить панель. Введите /дуель, чтобы восстановить её.');return
        sent=await self.original.answer(message_text,**dict(kwargs,keyboard=keyboard))
        error=sent.get('error') if isinstance(sent,dict) else getattr(sent,'error',None)
        if error:return sent
        cmid=sent.get('conversation_message_id') if isinstance(sent,dict) else getattr(sent,'conversation_message_id',None)
        if not isinstance(cmid,int) or isinstance(cmid,bool) or cmid<=0:return sent
        async with db._transaction() as conn:
            await conn.execute('INSERT INTO bot_duel_panels VALUES (?,?,?) ON CONFLICT(peer,panel_key) DO UPDATE SET cmid=excluded.cmid',(self.peer_id,key,cmid))
        # Delete the replaced panel only after its replacement was successfully sent.
        if row and row[0]!=cmid:
            try:await self.bot.api.messages.delete(peer_id=self.peer_id,cmids=[row[0]],delete_for_all=True)
            except Exception as exc:log.warning('Cannot delete replaced bot duel panel in peer %s: %s',self.peer_id,type(exc).__name__)
        return sent

def quiet_handlers(bot):
    locks={}
    def decorate(handler):
        @wraps(handler)
        async def wrapped(message,*args,**kwargs):
            # Serialize only one duel (not the whole battle chat), so several
            # independent fights can run in the same technical conversation.
            key=await participant_key(message)
            lock_key=key or f'peer:{message.peer_id}:user:{message.from_id}'
            lock=locks.setdefault(lock_key,asyncio.Lock())
            async with lock:
                return await handler(PanelMessage(message,bot,key),*args,**kwargs)
        return wrapped
    return decorate

