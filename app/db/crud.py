import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Contact, TelegramUser, UserWallet

EVM_CHAIN_ALIASES = {
    "eth": "ethereum",
    "ethereum": "ethereum",
    "base": "base",
    "arbitrum": "arbitrum",
    "arb": "arbitrum",
    "bnb": "bnb",
    "bnb chain": "bnb",
    "bsc": "bnb",
    "polygon": "polygon",
    "matic": "polygon",
    "optimism": "optimism",
    "op": "optimism",
    "celo": "celo",
}

SOLANA_CHAIN_ALIASES = {
    "sol": "solana",
    "solana": "solana",
}


def normalize_contact_name(name: str) -> str:
    """Normalize contact names for fast, case-insensitive lookup."""
    return " ".join((name or "").strip().casefold().split())


def normalize_chain_name(chain: str | None) -> str:
    """Canonicalize chain aliases to a small set of supported names."""
    raw = " ".join((chain or "ethereum").strip().casefold().split())
    if raw in SOLANA_CHAIN_ALIASES:
        return SOLANA_CHAIN_ALIASES[raw]
    return EVM_CHAIN_ALIASES.get(raw, raw)


def normalize_contact_address(address: str, chain: str | None = None) -> str:
    """Normalize wallet addresses without breaking Solana case sensitivity."""
    raw = (address or "").strip()
    normalized_chain = normalize_chain_name(chain)
    if raw.startswith("0x") or normalized_chain in EVM_CHAIN_ALIASES.values():
        return raw.casefold()
    return raw

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


async def upsert_contact(
    session: AsyncSession,
    user_id: uuid.UUID,
    name: str,
    chain: str,
    wallet_address: str,
) -> Contact:
    """Create or update a contact keyed by normalized name."""
    normalized_name = normalize_contact_name(name)
    normalized_chain = normalize_chain_name(chain)
    normalized_wallet_address = normalize_contact_address(wallet_address, normalized_chain)

    stmt = select(Contact).where(
        Contact.user_id == user_id,
        Contact.normalized_name == normalized_name,
    )
    result = await session.execute(stmt)
    contact = result.scalar_one_or_none()

    if contact:
        contact.name = name.strip()
        contact.chain = normalized_chain
        contact.wallet_address = wallet_address.strip()
        contact.normalized_wallet_address = normalized_wallet_address
    else:
        contact = Contact(
            user_id=user_id,
            name=name.strip(),
            normalized_name=normalized_name,
            chain=normalized_chain,
            wallet_address=wallet_address.strip(),
            normalized_wallet_address=normalized_wallet_address,
        )
        session.add(contact)

    await session.flush()
    return contact


async def list_user_contacts(session: AsyncSession, user_id: uuid.UUID) -> list[Contact]:
    stmt = (
        select(Contact)
        .where(Contact.user_id == user_id)
        .order_by(Contact.name.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_contact_by_name(
    session: AsyncSession,
    user_id: uuid.UUID,
    name: str,
) -> Contact | None:
    stmt = select(Contact).where(
        Contact.user_id == user_id,
        Contact.normalized_name == normalize_contact_name(name),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_contact_by_address(
    session: AsyncSession,
    user_id: uuid.UUID,
    wallet_address: str,
    chain: str | None = None,
) -> Contact | None:
    normalized_wallet_address = normalize_contact_address(wallet_address, chain)
    stmt = select(Contact).where(
        Contact.user_id == user_id,
        Contact.normalized_wallet_address == normalized_wallet_address,
    )
    if chain:
        stmt = stmt.where(Contact.chain == normalize_chain_name(chain))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def resolve_contact_target(
    session: AsyncSession,
    user_id: uuid.UUID,
    target: str,
    chain: str | None = None,
) -> dict | None:
    """Resolve either a raw address or a contact name to contact metadata."""
    contact = await get_contact_by_name(session, user_id, target)
    if contact:
        return {
            "contact": contact,
            "address": contact.wallet_address,
            "chain": contact.chain,
            "name": contact.name,
            "resolved_from": "name",
        }

    contact = await get_contact_by_address(session, user_id, target, chain)
    if contact:
        return {
            "contact": contact,
            "address": contact.wallet_address,
            "chain": contact.chain,
            "name": contact.name,
            "resolved_from": "address",
        }

    return None
