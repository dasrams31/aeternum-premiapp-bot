"""
Aeternum PremiApp Bot - Sambutan user yang bergabung ke grup Peka /
channel Aeternum, plus auto-accept join requests ke grup Peka, plus
verifikasi anti-bot (soal matematika) untuk member baru grup Peka, plus
hapus realtime pesan servis join ("X was accepted to the group") di grup
Peka.

Bot menerima update chat_member karena administrator di ketiga chat.
Hanya perpindahan left/kicked -> member yang diumumkan, dan hanya untuk
manusia (bukan bot lain). Gabung channel Peka TIDAK diberi sambutan
(channel Peka bersih buat broadcast). Grup Peka sudah join_by_request,
jadi permintaan gabung yang masuk langsung disetujui bot.
"""

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, ChatJoinRequest, ChatMemberUpdated, Message

from bot.services.broadcast import broadcast_user_joined, welcome_new_group_member
from bot.services.group_captcha import cancel_captcha, start_captcha, verify_captcha
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
            # Grup Peka: captcha anti-bot dulu (restrict + soal
            # matematika), lalu sambutan lengkap seperti biasa.
            if user.id != settings.ADMIN_ID:
                await start_captcha(
                    bot, event.chat.id, user.id, user.first_name or "teman baru"
                )
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
    elif old == "member" and new in ("left", "kicked"):
        # Keluar sebelum verifikasi: bersihkan pesan captcha + timeout.
        if event.chat.id == settings.PEKA_GROUP_ID:
            await cancel_captcha(bot, event.chat.id, event.new_chat_member.user.id)


@router.message(F.new_chat_members, F.chat.id == settings.PEKA_GROUP_ID)
async def delete_join_service_message(message: Message) -> None:
    """Hapus realtime pesan servis join di grup Peka (order user 21 Nov 19:20).

    Setiap member baru (termasuk yang masuk lewat approve join request)
    memunculkan pesan servis "X was accepted to the group". Bot admin
    langsung menghapusnya supaya grup bersih. Captcha + sambutan tetap
    jalan lewat on_chat_member (update terpisah, tidak tergantung pesan
    ini). Pesan lama (sebelum handler ini hidup) tidak ikut terhapus.
    """
    try:
        await message.delete()
        logger.info(
            "Deleted join service message %s in Peka group", message.message_id
        )
    except Exception as exc:  # noqa: BLE001 - already deleted / no rights
        logger.warning(
            "Failed to delete join service message %s: %s",
            message.message_id,
            exc,
        )


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


@router.callback_query(F.data.startswith("captcha:"))
async def on_captcha_button(callback: CallbackQuery, bot: Bot) -> None:
    """Tombol jawaban soal matematika di pesan verifikasi grup Peka."""
    if callback.message is None or callback.message.chat.id != settings.PEKA_GROUP_ID:
        await callback.answer("Tombol ini hanya berlaku di grup Peka.")
        return
    parts = (callback.data or "").split(":")
    try:
        target_id = int(parts[1])
        choice = int(parts[2])
    except (ValueError, IndexError):
        await callback.answer("Tombol tidak valid.")
        return
    if callback.from_user.id != target_id:
        await callback.answer("Tombol ini bukan untuk kamu.", show_alert=True)
        return
    result = await verify_captcha(bot, callback.message.chat.id, target_id, choice)
    if result == "ok":
        await callback.answer("Terverifikasi. Selamat datang di grup Peka!")
    elif result == "already":
        await callback.answer("Kamu sudah terverifikasi.")
    elif result == "wrong":
        await callback.answer("Salah, coba soal baru.")
    elif result == "failed":
        await callback.answer(
            "Kesempatan habis. Kamu dibisukan. Keluar lalu masuk lagi untuk coba lagi.",
            show_alert=True,
        )
    else:
        await callback.answer(
            "Verifikasi sudah tidak berlaku. Keluar lalu masuk lagi untuk coba ulang.",
            show_alert=True,
        )
