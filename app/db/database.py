from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
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
