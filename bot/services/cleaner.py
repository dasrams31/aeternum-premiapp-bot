"""
Aeternum PremiApp Bot - Background Expired Invoice & Stock Reservation Janitor
Membersihkan invoice PENDING yang kedaluwarsa dan mengembalikan stok yang terkunci secara otomatis.
"""

import asyncio
from datetime import datetime
import logging
from sqlalchemy import update
from database import crud
from database.connection import async_session
from database.models import Transaction

logger = logging.getLogger(__name__)


async def start_expired_invoice_cleaner(interval_seconds: int = 120) -> None:
    """Task background berkala untuk menandai invoice kadaluarsa dan merilis stok."""
    logger.info("Background cleaner invoice & stock reservation aktif.")
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            async with async_session() as session:
                now = datetime.utcnow()
                # 1. Update invoice status ke EXPIRED
                stmt = (
                    update(Transaction)
                    .where(Transaction.status == "PENDING")
                    .where(Transaction.expired_at < now)
                    .values(status="EXPIRED")
                )
                res = await session.execute(stmt)
                await session.commit()

                # 2. Kembalikan stok item yang kuncinya sudah expired
                released_stock = await crud.release_all_expired_reservations(session=session)

                if res.rowcount > 0 or released_stock > 0:
                    logger.info(
                        f"Janitor: {res.rowcount} invoice dibatalkan, {released_stock} stok dikembalikan ke sistem."
                    )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error pada invoice cleaner task: {e}")
