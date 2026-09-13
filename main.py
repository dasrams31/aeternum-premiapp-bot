"""
Aeternum PremiApp Bot - Main Application Entrypoint
"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from database.connection import init_db
from bot.middlewares.db_session import DatabaseMiddleware
from bot.handlers import admin, catalog, history, order, start


async def main() -> None:
    # Setup Logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger("aeternum_premiapp")
    logger.info("Starting Aeternum PremiApp Bot...")

    # Inisialisasi Database Schema
    await init_db()

    # Inisialisasi Bot & Dispatcher
    bot = Bot(token=settings.BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher(storage=MemoryStorage())

    # Daftarkan Database Middleware
    dp.update.middleware(DatabaseMiddleware())

    # Daftarkan Seluruh Router Handlers
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(catalog.router)
    dp.include_router(order.router)
    dp.include_router(history.router)

    # Mulai Polling Telegram
    logger.info("Bot is polling updates...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
