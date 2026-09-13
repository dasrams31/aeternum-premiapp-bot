"""
Aeternum PremiApp Bot - Main Application Entrypoint
Menjalankan Telegram Bot Polling, FastAPI Webhook Server, Invoice Janitor & Subscription Reminders.
Dilengkapi Global Error Middleware, Throttling Anti-Spam, dan Database Session Injection.
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
from bot.services.cleaner import start_expired_invoice_cleaner
from bot.services.subscription import start_subscription_reminder_task
from bot.handlers import (
    admin,
    catalog,
    history,
    order,
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

    # 3. Inisialisasi AiohttpSession dengan timeout numerik float (60s)
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
    dp.update.middleware(DatabaseMiddleware())

    # 6. Daftarkan Seluruh Routers
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(catalog.router)
    dp.include_router(wallet.router)
    dp.include_router(order.router)
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

    # 8. Mulai Background Tasks (Cleaner & Subscription Reminders)
    cleaner_task = asyncio.create_task(start_expired_invoice_cleaner(interval_seconds=120))
    subscription_task = asyncio.create_task(start_subscription_reminder_task(bot=bot, interval_seconds=1800))

    logger.info(f"FastAPI Webhook berjalan di port {settings.PORT}")
    logger.info("Bot Telegram mulai mendengarkan event polling...")

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
        cleaner_task.cancel()
        subscription_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Aplikasi dimatikan dengan aman.")
