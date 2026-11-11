"""
Aeternum PremiApp Bot - Background Stock Reservation Janitor

Sejak 11 Nov 2026 (perintah user) invoice TIDAK LAGI kedaluwarsa: tidak
ada lagi yang mengubah PENDING menjadi EXPIRED, menghapus pesan QRIS,
atau mengirim pemberitahuan habis-masa-berlaku ke pembeli.

Yang masih dibersihkan di sini hanyalah KUNCI STOK sementara
(ProductItem.reserved_until 15 menit): pesanan yang ditinggal pembeli
membebaskan itemnya supaya bisa dibeli orang lain. Invoice-nya sendiri
tetap PENDING sampai lunas / dibatalkan / ditolak admin, dan pengiriman
yang terlambat tetap jalan karena finalize_reserved_stock punya fallback
ke item lain yang masih tersedia.
"""

import asyncio
import logging
from typing import Optional

from aiogram import Bot

from database import crud
from database.connection import async_session

logger = logging.getLogger(__name__)


async def start_stock_reservation_cleaner(
    bot: Optional[Bot] = None, interval_seconds: int = 15
) -> None:
    """Task background berkala untuk merilis kunci stok yang kedaluwarsa."""
    logger.info(
        "Background cleaner reservasi stok aktif (Interval: %ds).", interval_seconds
    )
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            async with async_session() as session:
                released_stock = await crud.release_all_expired_reservations(
                    session=session
                )
                if released_stock > 0:
                    logger.info(
                        "Janitor: %d kunci stok kedaluwarsa dirilis.", released_stock
                    )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error pada stock reservation cleaner task: {e}")
