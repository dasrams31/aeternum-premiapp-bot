"""
Aeternum PremiApp Bot - Main Application Entrypoint
Menjalankan Telegram Bot Polling & FastAPI Webhook Server secara asinkronus bersamaan.
"""

import asyncio
import logging
import sys
import uvicorn

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from database.connection import init_db
from bot.middlewares.db_session import DatabaseMiddleware
from bot.handlers import admin, catalog, history, order, start, wallet
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

    # 3. Inisialisasi Bot & Dispatcher
    bot = Bot(token=settings.BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher(storage=MemoryStorage())

    # Berikan instance bot ke webhook server untuk notifikasi pengiriman otomatis
    set_bot_instance(bot)

    # 4. Daftarkan Middleware & Routers
    dp.update.middleware(DatabaseMiddleware())
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(catalog.router)
    dp.include_router(wallet.router)
    dp.include_router(order.router)
    dp.include_router(history.router)

    # 5. Konfigurasi Webhook Server (FastAPI + Uvicorn)
    config = uvicorn.Config(
        app=webhook_app,
        host="0.0.0.0",
        port=settings.PORT,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)

    # 6. Jalankan Bot Polling & Webhook Server Bersamaan
    logger.info(f"FastAPI Webhook berjalan di port {settings.PORT}")
    logger.info("Bot Telegram mulai mendengarkan event polling...")

    await bot.delete_webhook(drop_pending_updates=True)

    try:
        await asyncio.gather(
            dp.start_polling(bot),
            server.serve(),
        )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Aplikasi dimatikan dengan aman.")
