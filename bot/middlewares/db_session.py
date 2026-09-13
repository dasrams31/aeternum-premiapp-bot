"""
Aeternum PremiApp Bot - Database Session Middleware
"""

from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import async_session


class DatabaseMiddleware(BaseMiddleware):
    """Menyisipkan AsyncSession SQLAlchemy ke dalam data handler event."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        async with async_session() as session:
            data["session"] = session
            return await handler(event, data)
