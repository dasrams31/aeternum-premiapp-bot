"""
Aeternum PremiApp Bot - Background Subscription Expiry Reminder
Mengirimkan pengingat perpanjangan langganan akun pada H-3 dan H-1 ke pembeli.
"""

import asyncio
from datetime import datetime
import logging
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database import crud
from database.connection import async_session

logger = logging.getLogger(__name__)


def renewal_kb(product_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Perpanjang Sekarang", callback_data=f"prod_{product_id}")],
            [InlineKeyboardButton(text="🛍️ Buka Katalog", callback_data="user_catalog")],
        ]
    )


async def start_subscription_reminder_task(bot: Bot, interval_seconds: int = 1800) -> None:
    """Task background berkala untuk mengecek langganan yang akan habis (H-3 & H-1)."""
    logger.info("Background Subscription Expiry Reminder aktif.")
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            async with async_session() as session:
                h3_list, h1_list = await crud.get_due_subscription_reminders(session=session)

                # 1. Kirim Pengingat H-3
                for trx in h3_list:
                    product = await crud.get_product_by_id(session=session, product_id=trx.product_id)
                    prod_name = product.name if product else "Akun Premium"
                    exp_date = trx.expires_service_at.strftime("%d %b %Y") if trx.expires_service_at else "3 Hari Lagi"

                    text_h3 = (
                        f"⏰ <b>PENGINGAT MASA AKTIF (H-3)</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Hai! Akun <b>{prod_name}</b> Anda (Invoice: <code>#{trx.id}</code>) akan berakhir pada <b>{exp_date}</b>.\n\n"
                        f"Agar tidak terputus saat digunakan, Anda dapat melakukan perpanjangan sekarang melalui tombol di bawah:"
                    )
                    try:
                        await bot.send_message(
                            chat_id=trx.user_id,
                            text=text_h3,
                            reply_markup=renewal_kb(trx.product_id or 0),
                            parse_mode="HTML",
                        )
                        await crud.mark_reminder_sent(session=session, transaction_id=trx.id, reminder_type="H3")
                        logger.info(f"Terkirim reminder H-3 ke user {trx.user_id} untuk #{trx.id}")
                    except Exception as e:
                        logger.warning(f"Gagal kirim H-3 reminder ke {trx.user_id}: {e}")

                # 2. Kirim Pengingat H-1
                for trx in h1_list:
                    product = await crud.get_product_by_id(session=session, product_id=trx.product_id)
                    prod_name = product.name if product else "Akun Premium"

                    text_h1 = (
                        f"🚨 <b>PERINGATAN MASA AKTIF (H-1 BESOK)</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Masa aktif <b>{prod_name}</b> Anda akan <b>BERAKHIR BESOK</b>!\n\n"
                        f"Segera perpanjang akun Anda sekarang untuk menikmati akses tanpa jeda:"
                    )
                    try:
                        await bot.send_message(
                            chat_id=trx.user_id,
                            text=text_h1,
                            reply_markup=renewal_kb(trx.product_id or 0),
                            parse_mode="HTML",
                        )
                        await crud.mark_reminder_sent(session=session, transaction_id=trx.id, reminder_type="H1")
                        logger.info(f"Terkirim reminder H-1 ke user {trx.user_id} untuk #{trx.id}")
                    except Exception as e:
                        logger.warning(f"Gagal kirim H-1 reminder ke {trx.user_id}: {e}")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error pada subscription reminder task: {e}")
