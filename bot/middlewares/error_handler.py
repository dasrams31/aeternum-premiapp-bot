"""
Aeternum PremiApp Bot - Global Error Handling Middleware & Leak Prevention
Menangkap semua exception tak terduga, menyembunyikan detail internal dari pengguna,
dan mem-forward traceback lengkap langsung ke DM Admin Telegram.
"""

import logging
import traceback
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, TelegramObject

from config import settings

logger = logging.getLogger(__name__)


class GlobalErrorMiddleware(BaseMiddleware):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as exc:
            user_id = "Unknown"
            username = "-"
            event_type = type(event).__name__

            if isinstance(event, (Message, CallbackQuery)) and event.from_user:
                user_id = str(event.from_user.id)
                username = f"@{event.from_user.username}" if event.from_user.username else event.from_user.first_name

            tb_str = traceback.format_exc()
            logger.error(f"Unhandled exception on {event_type} from {user_id} ({username}):\n{tb_str}")

            # 1. Pesan Masking ke Pengguna (Tanpa kebocoran teknis/path internal)
            user_friendly_msg = (
                "⚠️ <b>Terjadi kendala teknis sementara.</b>\n"
                "Laporan sistem telah diteruskan ke tim pengembang untuk penanganan segera. "
                "Silakan coba kembali dalam beberapa saat atau hubungi bantuan via @dasrams."
            )

            try:
                if isinstance(event, Message):
                    await event.answer(user_friendly_msg, parse_mode="HTML")
                elif isinstance(event, CallbackQuery) and event.message:
                    await event.message.answer(user_friendly_msg, parse_mode="HTML")
                    await event.answer()
            except Exception:
                pass

            # 2. Kirim Traceback Lengkap ke DM Admin
            try:
                # Potong traceback jika terlalu panjang untuk batas pesan Telegram (4096 char)
                tb_clipped = tb_str[-2500:] if len(tb_str) > 2500 else tb_str
                admin_alert = (
                    f"🚨 <b>SYSTEM ERROR CRASH ALERT!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 <b>User:</b> {username} (ID: <code>{user_id}</code>)\n"
                    f"📌 <b>Event:</b> <code>{event_type}</code>\n"
                    f"⚠️ <b>Error:</b> <code>{str(exc)}</code>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📜 <b>Traceback:</b>\n"
                    f"<pre>{tb_clipped}</pre>"
                )
                await self.bot.send_message(
                    chat_id=settings.ADMIN_ID,
                    text=admin_alert,
                    parse_mode="HTML",
                )
            except Exception as admin_err:
                logger.error(f"Gagal mengirim alert error ke admin: {admin_err}")

            return None
