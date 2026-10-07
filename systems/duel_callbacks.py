"""VK callback buttons: no player command messages in the RP timeline."""
import json
import logging
import os
import time
import database as db

log=logging.getLogger(__name__)

def callback_keyboard(raw):
    if os.getenv('DUEL_CALLBACKS','1').strip()=='0':
        return raw if isinstance(raw,str) else json.dumps(raw,ensure_ascii=False)
    data=json.loads(raw) if isinstance(raw,str) else raw
    for row in data.get('buttons',[]):
        for button in row:
            action=button['action']
            if action.get('type')=='text':
                payload=action.get('payload') or {}
                if isinstance(payload,str):payload=json.loads(payload)
                payload['duel_ui']=1
                action.update(type='callback',payload=json.dumps(payload,ensure_ascii=False))
    return json.dumps(data,ensure_ascii=False)

class CallbackMessage:
    is_duel_callback=True
    text=''
    def __init__(self,bot,obj):
        self.bot=bot;self.from_id=obj['user_id'];self.peer_id=obj['peer_id']
        self.event_id=obj['event_id'];self.payload=obj['payload'];self.answered=False
    async def notice(self,text):
        self.answered=True
        try:
            await self.bot.api.messages.send_message_event_answer(event_id=self.event_id,peer_id=self.peer_id,user_id=self.from_id,event_data=json.dumps({'type':'show_snackbar','text':text[:90]},ensure_ascii=False))
        except Exception as exc:log.warning('Duel callback acknowledgement failed: %s',type(exc).__name__)
    async def acknowledge(self):
        if self.answered:return
        try:await self.bot.api.messages.send_message_event_answer(event_id=self.event_id,peer_id=self.peer_id,user_id=self.from_id)
        except Exception as exc:log.warning('Duel callback acknowledgement failed: %s',type(exc).__name__)
    async def answer(self,text=None,**kwargs):
        sent=await self.bot.api.messages.send(peer_ids=[self.peer_id],random_id=0,message=text or '',**kwargs)
        return sent[0]

def register_callbacks(bot,panel_handler,button_handler):
    @bot.on.raw_event('message_event',dict)
    async def duel_callback(event):
        obj=event.get('object') or {};payload=obj.get('payload')
        if isinstance(payload,dict) and payload.get('inventory_ui')==1:
            if type(obj.get('user_id')) is int and type(obj.get('peer_id')) is int and obj.get('event_id'):
                from systems.inventory_panel import handle_callback
                await handle_callback(bot,obj)
            return
        if not isinstance(payload,dict) or payload.get('duel_ui')!=1:return
        if not isinstance(obj.get('user_id'),int) or not isinstance(obj.get('peer_id'),int) or not obj.get('event_id'):return
        message=CallbackMessage(bot,obj)
        try:
            character=await db.get_character_by_user(message.from_id)
            if not character or character[10]!='approved':
                await message.notice('Сначала создайте персонажа в ЛС и дождитесь одобрения.');return
            if await db.get_active_mute(message.from_id,int(time.time())):
                await message.notice('Действует ограничение доступа.');return
            if payload.get('action')=='panel':await panel_handler(message)
            else:await button_handler(message)
        finally:await message.acknowledge()
    return duel_callback
