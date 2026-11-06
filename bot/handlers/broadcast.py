"""
Aeternum PremiApp Bot - Sambutan user yang bergabung ke grup Peka /
channel Aeternum.

Bot menerima update chat_member karena administrator di ketiga chat.
Hanya perpindahan left/kicked -> member yang diumumkan, dan hanya untuk
manusia (bukan bot lain). Gabung channel Peka TIDAK diberi sambutan
(channel Peka bersih buat broadcast).
"""

from aiogram import Bot, Router
from aiogram.types import ChatMemberUpdated

from bot.services.broadcast import broadcast_user_joined, welcome_new_group_member
from config import settings

router = Router(name="broadcast_router")

WATCHED_CHATS = {settings.PEKA_CHANNEL_ID, settings.PEKA_GROUP_ID, settings.AETERNUM_CHANNEL_ID}


@router.chat_member()
async def on_chat_member(event: ChatMemberUpdated, bot: Bot) -> None:
    if event.chat.id not in WATCHED_CHATS:
        return
    old = event.old_chat_member.status
    new = event.new_chat_member.status
    if old in ("left", "kicked") and new == "member":
        user = event.new_chat_member.user
        if user.is_bot:
            return
        if event.chat.id == settings.PEKA_GROUP_ID:
            # Grup Peka: sambutan lengkap (tag nama + username + info singkat Peka).
            await welcome_new_group_member(
                bot,
                event.chat.id,
                user.id,
                user.first_name or "teman baru",
                user.username,
            )
        elif event.chat.id == settings.AETERNUM_CHANNEL_ID:
            # Channel Aeternum: kabar singkat saja.
            await broadcast_user_joined(
                bot, event.chat.id, user.first_name or "teman baru"
            )
        # Channel Peka: tanpa sambutan (bersih buat broadcast).
