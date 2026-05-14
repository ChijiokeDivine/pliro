"""
Pytest configuration and fixtures for tests.
"""

import pytest
import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.db.base import Base
from app.db import models as db_models
from app.dca import models as dca_models


# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_engine():
    """Create a test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def test_session(test_engine):
    """Create a test database session."""
    AsyncSessionLocal = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture
async def telegram_user(test_session):
    """Create a test Telegram user."""
    from app.db import crud
    
    user = await crud.create_or_get_user(test_session, 12345)
    await test_session.commit()
    return user


@pytest.fixture
async def user_wallet(test_session, telegram_user):
    """Create a test user wallet."""
    from app.db import crud
    
    wallet = await crud.get_or_create_user_wallet(
        test_session,
        telegram_user.id,
        evm_address="0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247",
        solana_address="4xwVVV2g2V1Jh7T1kJ2K3L4M5N6O7P8Q9R0S1T2U",
        privy_evm_wallet_id="wallet_evm_12345",
        privy_solana_wallet_id="wallet_sol_12345",
    )
    await test_session.commit()
    return wallet
