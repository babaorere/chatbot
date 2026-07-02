from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker, declarative_base

from config.settings import settings

_raw_url = settings.database_url


def _to_sync_url(url: str) -> str:
    """Normaliza una URL de base de datos al driver síncrono usado por SQLAlchemy."""
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _to_async_url(url: str) -> str:
    """Normaliza una URL de base de datos al driver asíncrono usado por SQLAlchemy."""
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite://") and not url.startswith("sqlite+aiosqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url


# Database pooling configuration
pool_kwargs = {}
if "postgresql" in _raw_url:
    pool_kwargs = {
        "pool_size": 20,
        "max_overflow": 40,
    }


_sync_engine = create_engine(
    _to_sync_url(_raw_url),
    echo=settings.db_echo,
    pool_pre_ping=True,
    **pool_kwargs,
)

_async_engine = create_async_engine(
    _to_async_url(_raw_url),
    echo=settings.db_echo,
    pool_pre_ping=True,
    **pool_kwargs,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_sync_engine)
AsyncSessionLocal = async_sessionmaker(
    bind=_async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


class safe_transaction:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.tx = None

    def __enter__(self) -> safe_transaction:
        if not self.db.in_transaction():
            self.tx = self.db.begin()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            if self.tx:
                self.tx.rollback()
            else:
                self.db.rollback()
        else:
            if self.tx:
                self.tx.commit()
            else:
                self.db.commit()


def get_db() -> Session:
    """Entrega una sesión SQLAlchemy síncrona con cierre garantizado al final del request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncSession:
    """Entrega una sesión SQLAlchemy asíncrona con cierre garantizado al final del request."""
    async with AsyncSessionLocal() as session:
        yield session
