# Async SQLAlchemy engine + session factory.

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings


class Base(DeclarativeBase):
    pass


def get_engine():
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=(settings.node_env == "development"),
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )


def get_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# Module-level singletons — initialized on app startup
_engine = None
_session_factory = None


async def init_db() -> None:
    global _engine, _session_factory
    _engine = get_engine()
    _session_factory = get_session_factory(_engine)

    # Create all tables
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    global _engine
    if _engine:
        await _engine.dispose()


async def get_session() -> AsyncSession:
    """FastAPI dependency — yields a DB session per request."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _session_factory() as session:
        yield session