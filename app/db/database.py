from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine
from app.config import settings

# DATABASE_URL should be using the asyncpg driver
# Set statement_cache_size=0 for compatibility with PgBouncer (Supabase pooler)
engine = create_async_engine(
    settings.DATABASE_URL, 
    echo=True, 
    connect_args={
        "ssl": "require",
        "statement_cache_size": 0
    }
)

async_session_factory = async_sessionmaker(
    engine, 
    expire_on_commit=False, 
    class_=AsyncSession
)

# Synchronous engine for APScheduler (which needs synchronous DDL operations)
# Convert async URL to sync URL by replacing 'postgresql+asyncpg://' with 'postgresql://'
sync_db_url = settings.DATABASE_URL.replace(
    "postgresql+asyncpg://", "postgresql://"
) if settings.DATABASE_URL.startswith("postgresql+asyncpg://") else settings.DATABASE_URL

sync_engine = create_engine(
    sync_db_url,
    echo=False,
    connect_args={"ssl": "require"},
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
