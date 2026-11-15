"""
Aeternum PremiApp Bot - Sambutan user yang bergabung ke grup Peka /
channel Aeternum, plus auto-accept join requests ke grup Peka.

Bot menerima update chat_member karena administrator di ketiga chat.
Hanya perpindahan left/kicked -> member yang diumumkan, dan hanya untuk
manusia (bukan bot lain). Gabung channel Peka TIDAK diberi sambutan
(channel Peka bersih buat broadcast). Grup Peka sudah join_by_request,
jadi permintaan gabung yang masuk langsung disetujui bot.
"""

import logging

from aiogram import Bot, Router
from aiogram.types import ChatJoinRequest, ChatMemberUpdated

from bot.services.broadcast import broadcast_user_joined, welcome_new_group_member
from config import settings

router = Router(name="broadcast_router")

logger = logging.getLogger(__name__)

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


@router.chat_join_request()
async def on_chat_join_request(event: ChatJoinRequest, bot: Bot) -> None:
    """Auto-accept permintaan gabung ke grup Peka.

    Hanya grup Peka (sudah join_by_request). Bot harus admin dengan
    can_invite_users. Permintaan dari bot lain dilewati. Kegagalan
    (mis. permintaan sudah ditarik/disetujui admin lain) dicatat saja,
    jangan sampai menjatuhkan polling.
    """
    if event.chat.id != settings.PEKA_GROUP_ID:
        return
    user = event.from_user
    if user.is_bot:
        return
    try:
        await bot.approve_chat_join_request(event.chat.id, user.id)
        logger.info(
            "Auto-approved join request: user_id=%s username=%s chat_id=%s",
            user.id,
            user.username,
            event.chat.id,
        )
    except Exception as exc:  # noqa: BLE001 - request may be gone already
        logger.warning(
            "Auto-approve join request failed: user_id=%s error=%s",
            user.id,
            exc,
        )
