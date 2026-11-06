"""
Aeternum PremiApp Bot - Middleware gate verifikasi.

User yang belum terverifikasi gabung channel + grup Peka tidak bisa memakai
menu bot apa pun sebelum verifikasi. Yang lolos tanpa gate:
- admin (ADMIN_ID)
- user yang sudah terverifikasi (flag DB)
- command /start (di situlah prompt verifikasi ditampilkan)
- callback verify_check (tombol cek gabung)
- chat selain private (grup/channel tidak digate)

Prompt verifikasi dikirim maks 1x per 5 menit per user supaya tidak spam
saat user menekan tombol berkali-kali.
"""

import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.verification import is_user_verified, send_verification_prompt
from config import settings
from database import crud

PROMPT_COOLDOWN_S = 300


class VerificationMiddleware(BaseMiddleware):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self._last_prompt: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        chat = getattr(event, "chat", None)
        if user is None or chat is None or chat.type != "private":
            return await handler(event, data)
        if user.id == settings.ADMIN_ID:
            return await handler(event, data)

        # /start dan tombol cek verifikasi selalu lolos (jalur verifikasinya).
        if isinstance(event, Message) and (event.text or "").strip().startswith("/start"):
            return await handler(event, data)
        if isinstance(event, CallbackQuery) and (event.data or "").startswith("verify_"):
            return await handler(event, data)

        session: AsyncSession | None = data.get("session")
        if session is None:
            return await handler(event, data)

        db_user = await crud.get_user_by_id(session=session, user_id=user.id)
        if db_user is None:
            await crud.get_or_create_user(
                session=session,
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                is_admin=False,
            )
            db_user = await crud.get_user_by_id(session=session, user_id=user.id)
        if db_user and db_user.is_verified:
            return await handler(event, data)

        # Belum terverifikasi: tampilkan prompt (dibatasi cooldown) lalu blokir.
        now = time.time()
        if now - self._last_prompt.get(user.id, 0) > PROMPT_COOLDOWN_S:
            self._last_prompt[user.id] = now
            await send_verification_prompt(self.bot, user.id)
        if isinstance(event, CallbackQuery):
            await event.answer(
                "Gabung Channel + Grup Peka dulu, lalu tekan Cek Sekarang.",
                show_alert=True,
            )
        return None
