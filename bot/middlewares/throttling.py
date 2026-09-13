"""
Aeternum PremiApp Bot - Throttling & Anti-Spam Middleware
Mencegah spam click / flooding perintah bot dari pengguna.
"""

from typing import Any, Awaitable, Callable, Dict
import time
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject


class ThrottlingMiddleware(BaseMiddleware):
    """
    Membatasi frekuensi interaksi pengguna (Rate Limiting).
    Default: maksimal 1 request per 0.8 detik per pengguna.
    """

    def __init__(self, rate_limit: float = 0.8) -> None:
        self.rate_limit = rate_limit
        self.last_user_time: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id:
            current_time = time.time()
            last_time = self.last_user_time.get(user_id, 0.0)

            # Jika request terlalu cepat
            if current_time - last_time < self.rate_limit:
                if isinstance(event, CallbackQuery):
                    await event.answer("⚠️ Mohon tunggu sebentar...", show_alert=False)
                return None

            self.last_user_time[user_id] = current_time

            # Bersihkan memori cache lama jika cache terlalu besar (> 10.000 user)
            if len(self.last_user_time) > 10000:
                cutoff = current_time - 60
                self.last_user_time = {
                    uid: t for uid, t in self.last_user_time.items() if t > cutoff
                }

        return await handler(event, data)
