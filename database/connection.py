"""
Aeternum PremiApp Bot - Async PostgreSQL Connection Engine
"""

import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings
from .models import Base

logger = logging.getLogger(__name__)

# Buat asynchronous engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    pool_pre_ping=True,
)

# Buat sessionmaker untuk dependency injection & context manager
async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Inisialisasi tabel jika belum ada."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema verified & initialized successfully.")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency generator untuk FastAPI / Task handlers."""
    async with async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
