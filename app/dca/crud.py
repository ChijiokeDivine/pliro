"""
crud.py - CRUD operations for DCA recurring payments.
"""

import logging
from typing import Optional, List
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dca.models import RecurringPayment, DCAExecutionLog, DCAStatus, RecurrenceType

logger = logging.getLogger(__name__)


def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert an aware datetime to naive UTC for TIMESTAMP WITHOUT TIME ZONE columns."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class DCAOperations:
    """CRUD operations for recurring payments."""
    
    @staticmethod
    async def create_recurring_payment(
        session: AsyncSession,
        user_id: str,
        recipient_address: str,
        amount: float,
        token_symbol: str,
        chain: str,
        recurrence_type: str,
        cron_expression: str,
        next_execution_at: datetime,
        description: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> RecurringPayment:
        """
        Create a new recurring payment.
        
        Args:
            session: Database session
            user_id: Telegram user ID
            recipient_address: Recipient wallet address
            amount: USD amount
            token_symbol: Token symbol (e.g., "USDC")
            chain: Blockchain (e.g., "ethereum")
            recurrence_type: Recurrence type (e.g., "daily", "monday")
            cron_expression: Cron expression
            next_execution_at: Datetime of next execution
            description: Human-readable description
            notes: Additional notes
            
        Returns:
            Created RecurringPayment
        """
        payment = RecurringPayment(
            user_id=user_id,
            recipient_address=recipient_address,
            amount=amount,
            token_symbol=token_symbol,
            chain=chain,
            recurrence_type=recurrence_type,
            cron_expression=cron_expression,
            next_execution_at=_to_naive_utc(next_execution_at),
            status=DCAStatus.ACTIVE.value,
            description=description,
            notes=notes,
        )
        session.add(payment)
        await session.flush()
        
        logger.info(
            f"Created recurring payment {payment.id} for user {user_id}: "
            f"${amount} {token_symbol} → {recipient_address[:10]}..."
        )
        
        return payment
    
    @staticmethod
    async def get_recurring_payment(
        session: AsyncSession,
        payment_id: int
    ) -> Optional[RecurringPayment]:
        """Get recurring payment by ID."""
        return await session.get(RecurringPayment, payment_id)
    
    @staticmethod
    async def list_user_recurring_payments(
        session: AsyncSession,
        user_id: str,
        status: Optional[str] = None,
    ) -> List[RecurringPayment]:
        """
        List recurring payments for a user.
        
        Args:
            session: Database session
            user_id: Telegram user ID
            status: Optional status filter (e.g., "active", "paused")
            
        Returns:
            List of RecurringPayment
        """
        query = select(RecurringPayment).where(RecurringPayment.user_id == user_id)
        
        if status:
            query = query.where(RecurringPayment.status == status)
        
        result = await session.execute(query)
        return result.scalars().all()
    
    @staticmethod
    async def list_active_recurring_payments(
        session: AsyncSession
    ) -> List[RecurringPayment]:
        """Get all active recurring payments."""
        result = await session.execute(
            select(RecurringPayment).where(
                RecurringPayment.status == DCAStatus.ACTIVE.value
            )
        )
        return result.scalars().all()
    
    @staticmethod
    async def update_recurring_payment(
        session: AsyncSession,
        payment_id: int,
        **updates
    ) -> Optional[RecurringPayment]:
        """
        Update recurring payment fields.
        
        Args:
            session: Database session
            payment_id: ID of payment to update
            **updates: Fields to update
            
        Returns:
            Updated RecurringPayment or None if not found
        """
        payment = await session.get(RecurringPayment, payment_id)
        
        if not payment:
            return None
        
        # Update allowed fields
        allowed_fields = {
            "status", "next_execution_at", "last_execution_at",
            "execution_count", "notes", "description"
        }
        
        for field, value in updates.items():
            if field in allowed_fields:
                if field in {"next_execution_at", "last_execution_at"}:
                    value = _to_naive_utc(value)
                setattr(payment, field, value)
        
        session.add(payment)
        logger.info(f"Updated recurring payment {payment_id}: {updates}")
        
        return payment
    
    @staticmethod
    async def pause_recurring_payment(
        session: AsyncSession,
        payment_id: int
    ) -> Optional[RecurringPayment]:
        """Pause a recurring payment."""
        return await DCAOperations.update_recurring_payment(
            session,
            payment_id,
            status=DCAStatus.PAUSED.value
        )
    
    @staticmethod
    async def resume_recurring_payment(
        session: AsyncSession,
        payment_id: int
    ) -> Optional[RecurringPayment]:
        """Resume a paused recurring payment."""
        return await DCAOperations.update_recurring_payment(
            session,
            payment_id,
            status=DCAStatus.ACTIVE.value
        )
    
    @staticmethod
    async def cancel_recurring_payment(
        session: AsyncSession,
        payment_id: int
    ) -> Optional[RecurringPayment]:
        """Cancel a recurring payment."""
        return await DCAOperations.update_recurring_payment(
            session,
            payment_id,
            status=DCAStatus.CANCELLED.value
        )
    
    @staticmethod
    async def get_payment_history(
        session: AsyncSession,
        payment_id: int,
        limit: int = 20,
    ) -> List[DCAExecutionLog]:
        """Get execution history for a payment."""
        result = await session.execute(
            select(DCAExecutionLog)
            .where(DCAExecutionLog.recurring_payment_id == payment_id)
            .order_by(DCAExecutionLog.executed_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_user_execution_history(
        session: AsyncSession,
        user_id: str,
        limit: int = 50,
    ) -> List[DCAExecutionLog]:
        """Get all execution history for a user."""
        result = await session.execute(
            select(DCAExecutionLog)
            .where(DCAExecutionLog.user_id == user_id)
            .order_by(DCAExecutionLog.executed_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_recent_executions(
        session: AsyncSession,
        payment_id: int,
        hours: int = 24,
    ) -> List[DCAExecutionLog]:
        """Get executions in the last N hours."""
        from datetime import timedelta
        
        cutoff = _to_naive_utc(datetime.now(timezone.utc) - timedelta(hours=hours))
        
        result = await session.execute(
            select(DCAExecutionLog)
            .where(
                DCAExecutionLog.recurring_payment_id == payment_id,
                DCAExecutionLog.executed_at >= cutoff
            )
            .order_by(DCAExecutionLog.executed_at.desc())
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_failed_executions(
        session: AsyncSession,
        hours: int = 24,
    ) -> List[DCAExecutionLog]:
        """Get all failed executions in the last N hours."""
        from datetime import timedelta
        
        cutoff = _to_naive_utc(datetime.now(timezone.utc) - timedelta(hours=hours))
        
        result = await session.execute(
            select(DCAExecutionLog)
            .where(
                DCAExecutionLog.status == "failed",
                DCAExecutionLog.executed_at >= cutoff
            )
            .order_by(DCAExecutionLog.executed_at.desc())
        )
        return result.scalars().all()


# Convenience functions
async def create_dca(
    session: AsyncSession,
    user_id: str,
    recipient_address: str,
    amount: float,
    token_symbol: str,
    chain: str,
    recurrence_type: str,
    cron_expression: str,
    next_execution_at: datetime,
) -> RecurringPayment:
    """Create a DCA recurring payment."""
    return await DCAOperations.create_recurring_payment(
        session, user_id, recipient_address, amount, token_symbol, chain,
        recurrence_type, cron_expression, next_execution_at
    )


async def get_dca(session: AsyncSession, payment_id: int) -> Optional[RecurringPayment]:
    """Get a DCA by ID."""
    return await DCAOperations.get_recurring_payment(session, payment_id)


async def list_user_dcas(
    session: AsyncSession,
    user_id: str,
    status: Optional[str] = None,
) -> List[RecurringPayment]:
    """List user's DCAs."""
    return await DCAOperations.list_user_recurring_payments(session, user_id, status)


async def pause_dca(session: AsyncSession, payment_id: int) -> Optional[RecurringPayment]:
    """Pause a DCA."""
    return await DCAOperations.pause_recurring_payment(session, payment_id)


async def resume_dca(session: AsyncSession, payment_id: int) -> Optional[RecurringPayment]:
    """Resume a DCA."""
    return await DCAOperations.resume_recurring_payment(session, payment_id)


async def cancel_dca(session: AsyncSession, payment_id: int) -> Optional[RecurringPayment]:
    """Cancel a DCA."""
    return await DCAOperations.cancel_recurring_payment(session, payment_id)
