from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import TelegramUser, UserWallet
import uuid

async def get_or_create_user(session: AsyncSession, telegram_id: int, username: str | None = None) -> TelegramUser:
    stmt = select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        user = TelegramUser(telegram_id=telegram_id, username=username)
        session.add(user)
        await session.flush()  # To get the ID
        
    return user

async def get_user_wallet(session: AsyncSession, user_id: uuid.UUID) -> UserWallet | None:
    stmt = select(UserWallet).where(UserWallet.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def create_user_wallet(
    session: AsyncSession, 
    user_id: uuid.UUID,
    evm_address: str,
    solana_address: str,
    privy_evm_wallet_id: str,
    privy_solana_wallet_id: str
) -> UserWallet:
    wallet = UserWallet(
        user_id=user_id,
        evm_address=evm_address,
        solana_address=solana_address,
        privy_evm_wallet_id=privy_evm_wallet_id,
        privy_solana_wallet_id=privy_solana_wallet_id
    )
    session.add(wallet)
    await session.flush()
    return wallet
