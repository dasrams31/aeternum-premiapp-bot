"""
Aeternum PremiApp Bot - Background Expired Invoice & Stock Reservation Janitor
Membersihkan invoice PENDING yang kedaluwarsa dan mengembalikan stok yang terkunci secara otomatis.
"""

import asyncio
from datetime import datetime
import logging
from typing import Optional
from aiogram import Bot
from sqlalchemy import select, update
from database import crud
from database.connection import async_session
from database.models import Transaction

logger = logging.getLogger(__name__)


async def start_expired_invoice_cleaner(bot: Optional[Bot] = None, interval_seconds: int = 15) -> None:
    """Task background berkala untuk menandai invoice kadaluarsa, menghapus QRIS dari chat, dan merilis stok."""
    logger.info("Background cleaner invoice & stock reservation aktif (Interval: %ds).", interval_seconds)
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            async with async_session() as session:
                now = datetime.utcnow()
                # 1. Cari invoice yang PENDING dan expired_at < now
                stmt = (
                    select(Transaction)
                    .where(Transaction.status == "PENDING")
                    .where(Transaction.expired_at < now)
                )
                res = await session.execute(stmt)
                expired_trxs = list(res.scalars().all())

                if expired_trxs:
                    for trx in expired_trxs:
                        trx.status = "EXPIRED"

                        # Hapus pesan QRIS dari chat pembeli secara otomatis
                        if bot and trx.telegram_message_id:
                            try:
                                await bot.delete_message(chat_id=trx.user_id, message_id=trx.telegram_message_id)
                                await bot.send_message(
                                    chat_id=trx.user_id,
                                    text=(
                                        f"⏰ <b>INVOICE #{trx.id} TELAH KEDALUARSA</b>\n\n"
                                        f"Batas waktu pembayaran (15 menit) telah habis. "
                                        f"Kode QRIS telah dihapus otomatis dan stok telah dikembalikan ke sistem.\n\n"
                                        f"<i>Silakan pesan kembali melalui menu /start jika masih membutuhkan produk ini.</i>"
                                    ),
                                    parse_mode="HTML",
                                )
                            except Exception:
                                pass

                    await session.commit()

                # 2. Kembalikan stok item yang kuncinya sudah expired
                released_stock = await crud.release_all_expired_reservations(session=session)

                if expired_trxs or released_stock > 0:
                    logger.info(
                        f"Janitor: {len(expired_trxs)} invoice kedaluwarsa dibersihkan, {released_stock} stok dirilis."
                    )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error pada invoice cleaner task: {e}")
