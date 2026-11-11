"""
Aeternum PremiApp Bot - Gate verifikasi gabung 3 chat.

Sebelum memakai bot secara penuh, user harus gabung:
- Channel Peka     @peka_aichannel
- Grup Peka        @peka_aigroup
- Channel Aeternum @aeternum_premich

Alur:
- /start (atau pesan/tombol apa pun) dari user yang belum terverifikasi
  menampilkan prompt verifikasi: tombol gabung (URL) + tombol
  "Saya Sudah Gabung - Cek Sekarang".
- Tombol cek memanggil get_chat_member untuk ketiga chat; bila ketiganya
  member/administrator/creator, user ditandai terverifikasi dan langsung
  masuk menu utama.
- Cron checker (start_verification_checker) mengecek ulang user yang belum
  terverifikasi secara berkala: yang sudah gabung ditandai terverifikasi +
  dikirimi chat "verifikasi berhasil, silakan /start"; yang belum gabung
  dikirimi pengingat (maks 1x per 6 jam per user).

Admin (ADMIN_ID) selalu lolos tanpa verifikasi.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import text

from config import settings
from database import crud
from database.connection import async_session, engine

logger = logging.getLogger(__name__)

JOINED_STATUSES = {"creator", "administrator", "member"}


async def ensure_verification_columns() -> None:
    """Tambah kolom verifikasi ke tabel users bila belum ada (idempotent)."""
    async with engine.begin() as conn:
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE")
        )
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ")
        )
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS verify_last_check_at TIMESTAMPTZ")
        )
    logger.info("Kolom verifikasi users dipastikan ada.")


async def ensure_referral_discount_column() -> None:
    """Tambah kolom referral_discount ke tabel transactions bila belum ada (idempotent)."""
    async with engine.begin() as conn:
        await conn.execute(
            text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS referral_discount NUMERIC(12, 2) DEFAULT 0.0")
        )
    logger.info("Kolom referral_discount transactions dipastikan ada.")


async def ensure_admin_confirmed_column() -> None:
    """Tambah kolom admin_confirmed_at ke tabel transactions bila belum ada (idempotent).

    Dipakai tombol "Konfirmasi ke Admin" di pesan pembelian: sekali ketuk,
    kolom ini diisi waktu konfirmasi supaya ketukan berikutnya tidak mengirim
    notifikasi duplikat ke admin.
    """
    async with engine.begin() as conn:
        await conn.execute(
            text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS admin_confirmed_at TIMESTAMPTZ")
        )
    logger.info("Kolom admin_confirmed_at transactions dipastikan ada.")


async def ensure_issue_reported_column() -> None:
    """Tambah kolom issue_reported_at ke tabel transactions bila belum ada (idempotent).

    Dipakai tombol "Ada Kendala? Beri Tahu Admin" di pesan invoice: mencatat
    waktu laporan terakhir supaya satu invoice hanya bisa melapor sekali per
    10 menit dan admin tidak kebanjiran notifikasi dari ketukan berulang.
    """
    async with engine.begin() as conn:
        await conn.execute(
            text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS issue_reported_at TIMESTAMPTZ")
        )
    logger.info("Kolom issue_reported_at transactions dipastikan ada.")


async def ensure_manual_decision_columns() -> None:
    """Tambah kolom manual_approved_at + manual_rejected_at ke transactions.

    Dipakai tombol Terima / Tolak di notif checkout admin: mencatat waktu
    keputusan supaya ketukan ganda atau auto-confirm bersamaan tidak
    mengirim produk dua kali, dan supaya penolakan bersifat final.
    """
    async with engine.begin() as conn:
        await conn.execute(
            text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS manual_approved_at TIMESTAMPTZ")
        )
        await conn.execute(
            text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS manual_rejected_at TIMESTAMPTZ")
        )
    logger.info("Kolom manual_approved_at/manual_rejected_at transactions dipastikan ada.")


async def ensure_payment_proof_columns() -> None:
    """Tambah kolom bukti pembayaran ke tabel transactions.

    Dipakai alur "Kirim Bukti Pembayaran" di invoice QRIS (beli produk +
    top-up): payment_proof_file_id menyimpan file_id foto bukti dari
    pembeli, proof_sent_at mencatat waktu kirim (aware UTC).
    """
    async with engine.begin() as conn:
        await conn.execute(
            text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS payment_proof_file_id TEXT")
        )
        await conn.execute(
            text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS proof_sent_at TIMESTAMPTZ")
        )
    logger.info("Kolom payment_proof_file_id/proof_sent_at transactions dipastikan ada.")


async def check_membership(bot: Bot, user_id: int) -> tuple[bool, bool, bool]:
    """Cek apakah user sudah gabung 3 chat. (in_channel, in_group, in_aeternum)."""
    async def _joined(chat_id: int) -> bool:
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            return member.status in JOINED_STATUSES
        except Exception as e:
            logger.debug(f"Membership check gagal chat={chat_id} user={user_id}: {e}")
            return False

    in_channel = await _joined(settings.PEKA_CHANNEL_ID)
    in_group = await _joined(settings.PEKA_GROUP_ID)
    in_aeternum = await _joined(settings.AETERNUM_CHANNEL_ID)
    return in_channel, in_group, in_aeternum


async def is_user_verified(session, user_id: int) -> bool:
    """True untuk admin dan user yang sudah terverifikasi."""
    if user_id == settings.ADMIN_ID:
        return True
    user = await crud.get_user_by_id(session=session, user_id=user_id)
    return bool(user and user.is_verified)


async def mark_verified(session, user_id: int) -> None:
    user = await crud.get_user_by_id(session=session, user_id=user_id)
    if user and not user.is_verified:
        user.is_verified = True
        user.verified_at = datetime.now(timezone.utc)
        await session.commit()
        logger.info(f"User {user_id} terverifikasi gabung 3 chat (Peka + Aeternum).")


def verification_keyboard() -> InlineKeyboardMarkup:
    """Tombol gabung channel/grup + tombol cek."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📣 Gabung Channel Peka", url=f"https://t.me/{settings.PEKA_CHANNEL_USERNAME.lstrip('@')}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="👥 Gabung Grup Peka", url=f"https://t.me/{settings.PEKA_GROUP_USERNAME.lstrip('@')}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📣 Gabung Channel Aeternum", url=f"https://t.me/{settings.AETERNUM_CHANNEL_USERNAME.lstrip('@')}"
        )
    )
    builder.row(
        InlineKeyboardButton(text="✅ Saya Sudah Gabung — Cek Sekarang", callback_data="verify_check")
    )
    return builder.as_markup()


def verification_text(missing_channel: bool, missing_group: bool, missing_aeternum: bool = False) -> str:
    missing = []
    if missing_channel:
        missing.append(f"Channel Peka ({settings.PEKA_CHANNEL_USERNAME})")
    if missing_group:
        missing.append(f"Grup Peka ({settings.PEKA_GROUP_USERNAME})")
    if missing_aeternum:
        missing.append(f"Channel Aeternum ({settings.AETERNUM_CHANNEL_USERNAME})")
    if not missing:
        return (
            "🔐 <b>VERIFIKASI AKSES</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Kamu sudah bergabung. Tekan tombol cek di bawah untuk membuka akses penuh bot."
        )
    return (
        "🔐 <b>VERIFIKASI AKSES — GABUNG DULU</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Sebelum memakai bot ini, gabung dulu di:\n"
        f"• <b>{'✅' if not missing_channel else '❌'} Channel Peka</b> ({settings.PEKA_CHANNEL_USERNAME})\n"
        f"• <b>{'✅' if not missing_group else '❌'} Grup Peka</b> ({settings.PEKA_GROUP_USERNAME})\n"
        f"• <b>{'✅' if not missing_aeternum else '❌'} Channel Aeternum</b> ({settings.AETERNUM_CHANNEL_USERNAME})\n\n"
        "Kamu belum gabung di: <b>" + ", ".join(missing) + "</b>.\n\n"
        "Tekan tombol gabung di bawah, lalu tekan "
        "<b>✅ Saya Sudah Gabung — Cek Sekarang</b>."
    )


async def send_verification_prompt(bot: Bot, user_id: int) -> None:
    """Kirim prompt verifikasi (cek status gabung dulu supaya checklistnya akurat)."""
    in_channel, in_group, in_aeternum = await check_membership(bot, user_id)
    try:
        await bot.send_message(
            chat_id=user_id,
            text=verification_text(not in_channel, not in_group, not in_aeternum),
            reply_markup=verification_keyboard(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Gagal kirim prompt verifikasi ke {user_id}: {e}")


async def _check_one_user(bot: Bot, user_id: int) -> None:
    """Satu putaran cek untuk satu user yang belum terverifikasi."""
    async with async_session() as session:
        user = await crud.get_user_by_id(session=session, user_id=user_id)
        if not user or user.is_verified or user_id == settings.ADMIN_ID:
            return
        in_channel, in_group, in_aeternum = await check_membership(bot, user_id)
        now = datetime.now(timezone.utc)
        user.verify_last_check_at = now
        await session.commit()
        if in_channel and in_group and in_aeternum:
            await mark_verified(session, user_id)
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        "✅ <b>VERIFIKASI BERHASIL!</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        "Kamu sudah gabung Channel dan Grup Peka serta Channel Aeternum. "
                        "Akses penuh bot sudah terbuka.\n\n"
                        "Silakan /start untuk memulai bot."
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning(f"Gagal kirim chat verifikasi berhasil ke {user_id}: {e}")
        else:
            missing = []
            if not in_channel:
                missing.append(f"Channel Peka ({settings.PEKA_CHANNEL_USERNAME})")
            if not in_group:
                missing.append(f"Grup Peka ({settings.PEKA_GROUP_USERNAME})")
            if not in_aeternum:
                missing.append(f"Channel Aeternum ({settings.AETERNUM_CHANNEL_USERNAME})")
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        "⏳ <b>VERIFIKASI BELUM LENGKAP</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        "Kami cek kamu belum gabung di: <b>" + ", ".join(missing) + "</b>.\n\n"
                        "Gabung dulu lewat tombol di bawah, lalu tekan "
                        "<b>✅ Saya Sudah Gabung — Cek Sekarang</b>. "
                        "Kami akan cek lagi otomatis berkala."
                    ),
                    reply_markup=verification_keyboard(),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning(f"Gagal kirim chat verifikasi gagal ke {user_id}: {e}")


async def start_verification_checker(bot: Bot, interval_seconds: int | None = None) -> None:
    """Cron verifikasi: cek ulang user yang belum terverifikasi secara berkala.

    Target per putaran maks 20 user: yang belum pernah dicek, atau terakhir
    dicek >6 jam lalu. Pengingat gagal terkirim maks 1x/6 jam per user
    (diatur oleh verify_last_check_at). Semua user lama ikut dicek, bukan
    cuma yang baru: gate di middleware tetap yang menegakkan verifikasi
    saat mereka memakai bot.
    """
    interval = interval_seconds or settings.VERIFY_CHECK_INTERVAL_SECONDS
    await ensure_verification_columns()
    logger.info("Background Verification Checker aktif (interval %ss).", interval)
    await asyncio.sleep(30)
    while True:
        try:
            async with async_session() as session:
                now = datetime.now(timezone.utc)
                rows = await session.execute(
                    text(
                        "SELECT id FROM users WHERE id != :admin "
                        "AND COALESCE(is_verified, FALSE) = FALSE "
                        "AND (verify_last_check_at IS NULL "
                        "OR verify_last_check_at < :six_hours_ago) "
                        "ORDER BY created_at DESC LIMIT 20"
                    ),
                    {
                        "admin": settings.ADMIN_ID,
                        "six_hours_ago": now - timedelta(hours=6),
                    },
                )
                user_ids = [r[0] for r in rows.all()]
            for uid in user_ids:
                try:
                    await _check_one_user(bot, uid)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(f"Verification check gagal untuk user {uid}.")
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Verification checker gagal (lanjut putaran berikut).")
        await asyncio.sleep(interval)
