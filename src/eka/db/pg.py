from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from eka.config import settings

engine = create_async_engine(
    str(settings.postgres_async_url),
    echo=settings.DEBUG,
    pool_size=20,  # Сколько постоянных соединений держать открытыми
    max_overflow=10,  # Сколько дополнительных соединений можно открыть при пиках
    pool_timeout=30,  # Сколько секунд ждать свободного соединения из пула
    pool_recycle=1800,  # Сбрасывать соединения каждые 30 мин (защита от разрывов со стороны БД)
    pool_pre_ping=True,  # Проверять живое ли соединение перед каждым запросом
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Отключаем detached-state баги для асинхронности
)

sync_engine = create_engine(settings.postgres_sync_url)

SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)
