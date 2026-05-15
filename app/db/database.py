from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine
from app.config import settings

# Async engine — asyncpg uses "ssl" connect arg
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,
    connect_args={
        "ssl": "require",
        "statement_cache_size": 0,
    }
)

async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# Sync engine — psycopg2 uses "sslmode" not "ssl"
sync_db_url = settings.DATABASE_URL.replace(
    "postgresql+asyncpg://", "postgresql://"
).replace(
    "postgres://", "postgresql://"
)

sync_engine = create_engine(
    sync_db_url,
    echo=False,
    connect_args={"sslmode": "require"},  
    pool_size=5,
    max_overflow=10,
)

async def get_db():
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()