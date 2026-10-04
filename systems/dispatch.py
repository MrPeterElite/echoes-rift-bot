"""Serialize each player's messages, including middleware and failed handlers."""
import asyncio
from weakref import WeakValueDictionary

from vkbottle.dispatch.views.bot import BotMessageView


class SerialMessageView(BotMessageView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._player_locks = WeakValueDictionary()

    async def handle_event(self, event, ctx_api, state_dispenser):
        obj = event.get("object", {})
        message = obj.get("message", obj)
        user_id = message.get("from_id")
        if user_id is None:
            return await super().handle_event(event, ctx_api, state_dispenser)
        lock = self._player_locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            return await super().handle_event(event, ctx_api, state_dispenser)
