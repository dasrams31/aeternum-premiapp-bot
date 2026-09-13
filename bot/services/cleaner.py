"""
Aeternum PremiApp Bot - Background Expired Invoice Janitor
Membersihkan invoice PENDING yang melewati batas kedaluwarsa (15 menit).
"""

import asyncio
from datetime import datetime
import logging
from sqlalchemy import update
from database.connection import async_session
from database.models import Transaction

logger = logging.getLogger(__name__)


async def start_expired_invoice_cleaner(interval_seconds: int = 120) -> None:
    """Task background berkala untuk menandai invoice kadaluarsa sebagai EXPIRED."""
    logger.info("Background cleaner invoice kedaluwarsa aktif.")
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            async with async_session() as session:
                now = datetime.utcnow()
                stmt = (
                    update(Transaction)
                    .where(Transaction.status == "PENDING")
                    .where(Transaction.expired_at < now)
                    .values(status="EXPIRED")
                )
                res = await session.execute(stmt)
                await session.commit()
                if res.rowcount > 0:
                    logger.info(f"Otomatis membatalkan {res.rowcount} invoice yang kedaluwarsa.")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error pada invoice cleaner task: {e}")
