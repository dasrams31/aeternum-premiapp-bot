"""
Aeternum PremiApp Bot - Handler verifikasi gabung channel + grup.
"""

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.user_kb import NAV_INTRO_TEXT, main_menu_kb, main_reply_kb
from bot.services.verification import (
    check_membership,
    mark_verified,
    verification_keyboard,
    verification_text,
)
from config import settings

router = Router(name="verification_router")


@router.callback_query(F.data == "verify_check")
async def cb_verify_check(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    user = callback.from_user
    is_admin = user.id == settings.ADMIN_ID

    in_channel, in_group, in_aeternum = await check_membership(bot, user.id)
    if in_channel and in_group and in_aeternum:
        await mark_verified(session, user.id)
        text = (
            f"✅ <b>VERIFIKASI BERHASIL!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"Halo <b>{user.first_name}</b>, kamu sudah gabung Channel dan Grup Peka serta Channel Aeternum.\n"
            f"Akses penuh bot sudah terbuka. Silakan pilih menu di bawah ini 👇"
        )
        if callback.message:
            await callback.message.edit_text(
                text=text,
                reply_markup=main_menu_kb(is_admin=is_admin),
                parse_mode="HTML",
            )
            await callback.message.answer(
                text=NAV_INTRO_TEXT,
                reply_markup=main_reply_kb(is_admin=is_admin),
                parse_mode="HTML",
            )
        await callback.answer("Verifikasi berhasil! Selamat datang.")
        return

    missing = []
    if not in_channel:
        missing.append("Channel Peka")
    if not in_group:
        missing.append("Grup Peka")
    if not in_aeternum:
        missing.append("Channel Aeternum")
    if callback.message:
        await callback.message.edit_text(
            text=verification_text(not in_channel, not in_group, not in_aeternum),
            reply_markup=verification_keyboard(),
            parse_mode="HTML",
        )
    await callback.answer(
        f"Belum lengkap, kamu belum gabung: {', '.join(missing)}.",
        show_alert=True,
    )
