import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base



class TelegramUser(Base):
    __tablename__ = "telegram_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    wallets: Mapped[list["UserWallet"]] = relationship("UserWallet", back_populates="user", cascade="all, delete-orphan")
    contacts: Mapped[list["Contact"]] = relationship("Contact", back_populates="user", cascade="all, delete-orphan")

class UserWallet(Base):
    __tablename__ = "user_wallets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("telegram_users.id"), unique=True)
    
    evm_address: Mapped[str] = mapped_column(String)
    solana_address: Mapped[str] = mapped_column(String)
    
    privy_evm_wallet_id: Mapped[str] = mapped_column(String)
    privy_solana_wallet_id: Mapped[str] = mapped_column(String)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped["TelegramUser"] = relationship("TelegramUser", back_populates="wallets")


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("user_id", "normalized_name", name="uq_contacts_user_normalized_name"),
        UniqueConstraint("user_id", "chain", "normalized_wallet_address", name="uq_contacts_user_chain_normalized_wallet_address"),
        Index("ix_contacts_user_normalized_name", "user_id", "normalized_name"),
        Index("ix_contacts_user_normalized_wallet_address", "user_id", "normalized_wallet_address"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("telegram_users.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(120), nullable=False)
    chain: Mapped[str] = mapped_column(String(32), nullable=False)
    wallet_address: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_wallet_address: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped["TelegramUser"] = relationship("TelegramUser", back_populates="contacts")
