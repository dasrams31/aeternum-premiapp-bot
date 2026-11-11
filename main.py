"""
Aeternum PremiApp Bot - Main Application Entrypoint
Menjalankan Telegram Bot Polling, FastAPI Webhook Server, Auto-Payment Poller, Cleaner & Subscription Reminders.
"""

import asyncio
import logging
import sys
import uvicorn

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from database.connection import init_db
from bot.middlewares.db_session import DatabaseMiddleware
from bot.middlewares.error_handler import GlobalErrorMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.services.cleaner import start_stock_reservation_cleaner
from bot.services.payment_poller import start_auto_payment_poller
from bot.services.subscription import start_subscription_reminder_task
from bot.handlers import broadcast as broadcast_handlers
from bot.handlers import verification as verification_handlers
from bot.middlewares.verification import VerificationMiddleware
from bot.services.stock_updater import start_daily_stock_updater
from bot.services.verification import start_verification_checker
from bot.handlers import (
    admin,
    catalog,
    history,
    order,
    order_chat,
    payment_proof,
    review,
    start,
    wallet,
    warranty,
)
from webhook.server import app as webhook_app, set_bot_instance


async def main() -> None:
    # 1. Setup Logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger("aeternum_premiapp")
    logger.info("Memulai Aeternum PremiApp Bot & Webhook Server...")

    # 2. Inisialisasi Database Schema
    await init_db()
    from bot.services.verification import (
        ensure_admin_confirmed_column,
        ensure_issue_reported_column,
        ensure_manual_decision_columns,
        ensure_order_chat_tables,
        ensure_payment_proof_columns,
        ensure_referral_discount_column,
        ensure_verification_columns,
    )

    await ensure_verification_columns()
    await ensure_referral_discount_column()
    await ensure_admin_confirmed_column()
    await ensure_issue_reported_column()
    await ensure_manual_decision_columns()
    await ensure_payment_proof_columns()
    await ensure_order_chat_tables()

    # 3. Inisialisasi AiohttpSession
    session = AiohttpSession(timeout=60.0)

    # 4. Inisialisasi Bot & Dispatcher
    bot = Bot(
        token=settings.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Berikan instance bot ke webhook server untuk notifikasi pengiriman otomatis
    set_bot_instance(bot)

    # 5. Daftarkan Middlewares (Global Error Handler, Throttling Anti-Spam & DB Session)
    dp.update.middleware(GlobalErrorMiddleware(bot=bot))
    dp.message.middleware(ThrottlingMiddleware(rate_limit=0.8))
    dp.callback_query.middleware(ThrottlingMiddleware(rate_limit=0.8))
    dp.message.middleware(VerificationMiddleware(bot=bot))
    dp.callback_query.middleware(VerificationMiddleware(bot=bot))
    dp.update.middleware(DatabaseMiddleware())

    # 6. Daftarkan Seluruh Routers
    dp.include_router(verification_handlers.router)
    dp.include_router(broadcast_handlers.router)
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(catalog.router)
    dp.include_router(wallet.router)
    dp.include_router(order.router)
    dp.include_router(payment_proof.router)
    dp.include_router(order_chat.router)
    dp.include_router(history.router)
    dp.include_router(review.router)
    dp.include_router(warranty.router)

    # 7. Konfigurasi Webhook Server (FastAPI + Uvicorn)
    config = uvicorn.Config(
        app=webhook_app,
        host="0.0.0.0",
        port=settings.PORT,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)

    # 8. Mulai Background Tasks:
    # a. Auto Payment Poller (Deteksi Bayar Otomatis per 6 Detik)
    # b. Cleaner Reservasi Stok Kedaluwarsa (invoice TIDAK lagi expire)
    # c. Subscription Reminders (H-3 & H-1)
    # d. Daily Stock Updater (sinkron flag ready TEXT_STOCK + notifikasi restock)
    payment_poller_task = asyncio.create_task(start_auto_payment_poller(bot=bot, interval_seconds=6))
    cleaner_task = asyncio.create_task(start_stock_reservation_cleaner(bot=bot, interval_seconds=15))
    subscription_task = asyncio.create_task(start_subscription_reminder_task(bot=bot, interval_seconds=1800))
    stock_task = asyncio.create_task(start_daily_stock_updater(bot=bot))
    verify_task = asyncio.create_task(start_verification_checker(bot=bot))

    logger.info(f"FastAPI Webhook berjalan di port {settings.PORT}")
    logger.info("Bot Telegram mulai mendengarkan event polling...")
    logger.info("Auto-Payment Poller aktif berjalan di background.")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logger.warning(f"Gagal drop pending updates: {e}")

    try:
        await asyncio.gather(
            dp.start_polling(bot),
            server.serve(),
        )
    finally:
        payment_poller_task.cancel()
        cleaner_task.cancel()
        subscription_task.cancel()
        stock_task.cancel()
        verify_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Aplikasi dimatikan dengan aman.")
