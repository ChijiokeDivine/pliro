"""
Tests for DCA CRUD operations.
"""

import pytest
from datetime import datetime, timedelta, timezone
from app.dca.crud import DCAOperations, create_dca, get_dca, list_user_dcas
from app.dca.models import DCAStatus


@pytest.mark.asyncio
class TestDCACRUDCreate:
    """Test creating recurring payments."""
    
    async def test_create_dca(self, test_session):
        """Test creating a DCA."""
        next_exec = datetime.now(timezone.utc) + timedelta(days=1)
        
        payment = await DCAOperations.create_recurring_payment(
            test_session,
            user_id="12345",
            recipient_address="0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247",
            amount=10.0,
            token_symbol="USDC",
            chain="ethereum",
            recurrence_type="daily",
            cron_expression="0 0 * * *",
            next_execution_at=next_exec,
        )
        await test_session.commit()
        
        assert payment.id is not None
        assert payment.user_id == "12345"
        assert payment.amount == 10.0
        assert payment.status == DCAStatus.ACTIVE.value
    
    async def test_create_dca_with_description(self, test_session):
        """Test creating DCA with description."""
        next_exec = datetime.now(timezone.utc) + timedelta(days=1)
        
        payment = await DCAOperations.create_recurring_payment(
            test_session,
            user_id="12345",
            recipient_address="0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247",
            amount=10.0,
            token_symbol="USDC",
            chain="ethereum",
            recurrence_type="daily",
            cron_expression="0 0 * * *",
            next_execution_at=next_exec,
            description="Daily USDC transfer",
        )
        await test_session.commit()
        
        assert payment.description == "Daily USDC transfer"
    
    async def test_create_multiple_dcas(self, test_session):
        """Test creating multiple DCAs for same user."""
        next_exec = datetime.now(timezone.utc) + timedelta(days=1)
        
        payment1 = await DCAOperations.create_recurring_payment(
            test_session, "12345", "0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247",
            10.0, "USDC", "ethereum", "daily", "0 0 * * *", next_exec
        )
        payment2 = await DCAOperations.create_recurring_payment(
            test_session, "12345", "0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247",
            5.0, "ETH", "ethereum", "weekly", "0 0 * * 0", next_exec
        )
        await test_session.commit()
        
        assert payment1.id != payment2.id
        assert payment1.amount == 10.0
        assert payment2.amount == 5.0


@pytest.mark.asyncio
class TestDCACRUDRead:
    """Test reading recurring payments."""
    
    async def test_get_dca_by_id(self, test_session):
        """Test getting DCA by ID."""
        next_exec = datetime.now(timezone.utc) + timedelta(days=1)
        
        created = await DCAOperations.create_recurring_payment(
            test_session, "12345", "0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247",
            10.0, "USDC", "ethereum", "daily", "0 0 * * *", next_exec
        )
        await test_session.commit()
        
        retrieved = await DCAOperations.get_recurring_payment(test_session, created.id)
        
        assert retrieved.id == created.id
        assert retrieved.amount == 10.0
    
    async def test_get_nonexistent_dca(self, test_session):
        """Test getting non-existent DCA."""
        payment = await DCAOperations.get_recurring_payment(test_session, 99999)
        assert payment is None
    
    async def test_list_user_dcas(self, test_session):
        """Test listing user's DCAs."""
        next_exec = datetime.now(timezone.utc) + timedelta(days=1)
        
        # Create 3 DCAs for user 12345
        for i in range(3):
            await DCAOperations.create_recurring_payment(
                test_session, "12345", "0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247",
                10.0 + i, "USDC", "ethereum", "daily", "0 0 * * *", next_exec
            )
        
        # Create 1 DCA for different user
        await DCAOperations.create_recurring_payment(
            test_session, "99999", "0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247",
            10.0, "USDC", "ethereum", "daily", "0 0 * * *", next_exec
        )
        
        await test_session.commit()
        
        dcas = await DCAOperations.list_user_recurring_payments(test_session, "12345")
        assert len(dcas) == 3
    
    async def test_list_user_dcas_by_status(self, test_session):
        """Test listing user's DCAs filtered by status."""
        next_exec = datetime.now(timezone.utc) + timedelta(days=1)
        
        payment1 = await DCAOperations.create_recurring_payment(
            test_session, "12345", "0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247",
            10.0, "USDC", "ethereum", "daily", "0 0 * * *", next_exec
        )
        payment2 = await DCAOperations.create_recurring_payment(
            test_session, "12345", "0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247",
            5.0, "USDC", "ethereum", "weekly", "0 0 * * 0", next_exec
        )
        
        # Pause second payment
        await DCAOperations.pause_recurring_payment(test_session, payment2.id)
        await test_session.commit()
        
        active = await DCAOperations.list_user_recurring_payments(test_session, "12345", "active")
        paused = await DCAOperations.list_user_recurring_payments(test_session, "12345", "paused")
        
        assert len(active) == 1
        assert len(paused) == 1


@pytest.mark.asyncio
class TestDCACRUDUpdate:
    """Test updating recurring payments."""
    
    async def test_pause_dca(self, test_session):
        """Test pausing a DCA."""
        next_exec = datetime.now(timezone.utc) + timedelta(days=1)
        
        payment = await DCAOperations.create_recurring_payment(
            test_session, "12345", "0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247",
            10.0, "USDC", "ethereum", "daily", "0 0 * * *", next_exec
        )
        payment_id = payment.id
        await test_session.commit()
        
        updated = await DCAOperations.pause_recurring_payment(test_session, payment_id)
        await test_session.commit()
        
        assert updated.status == DCAStatus.PAUSED.value
    
    async def test_resume_dca(self, test_session):
        """Test resuming a paused DCA."""
        next_exec = datetime.now(timezone.utc) + timedelta(days=1)
        
        payment = await DCAOperations.create_recurring_payment(
            test_session, "12345", "0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247",
            10.0, "USDC", "ethereum", "daily", "0 0 * * *", next_exec
        )
        payment_id = payment.id
        await test_session.commit()
        
        await DCAOperations.pause_recurring_payment(test_session, payment_id)
        await test_session.commit()
        
        resumed = await DCAOperations.resume_recurring_payment(test_session, payment_id)
        await test_session.commit()
        
        assert resumed.status == DCAStatus.ACTIVE.value
    
    async def test_cancel_dca(self, test_session):
        """Test cancelling a DCA."""
        next_exec = datetime.now(timezone.utc) + timedelta(days=1)
        
        payment = await DCAOperations.create_recurring_payment(
            test_session, "12345", "0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247",
            10.0, "USDC", "ethereum", "daily", "0 0 * * *", next_exec
        )
        payment_id = payment.id
        await test_session.commit()
        
        cancelled = await DCAOperations.cancel_recurring_payment(test_session, payment_id)
        await test_session.commit()
        
        assert cancelled.status == DCAStatus.CANCELLED.value
    
    async def test_update_execution_tracking(self, test_session):
        """Test updating execution tracking fields."""
        next_exec = datetime.now(timezone.utc) + timedelta(days=1)
        
        payment = await DCAOperations.create_recurring_payment(
            test_session, "12345", "0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247",
            10.0, "USDC", "ethereum", "daily", "0 0 * * *", next_exec
        )
        payment_id = payment.id
        await test_session.commit()
        
        now = datetime.now(timezone.utc)
        updated = await DCAOperations.update_recurring_payment(
            test_session,
            payment_id,
            last_execution_at=now,
            execution_count=1,
        )
        await test_session.commit()
        
        assert updated.execution_count == 1
        assert updated.last_execution_at is not None


@pytest.mark.asyncio
class TestDCACRUDExecutionHistory:
    """Test execution history tracking."""
    
    async def test_get_payment_history(self, test_session):
        """Test getting payment execution history."""
        from app.dca.models import DCAExecutionLog
        
        next_exec = datetime.now(timezone.utc) + timedelta(days=1)
        payment = await DCAOperations.create_recurring_payment(
            test_session, "12345", "0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247",
            10.0, "USDC", "ethereum", "daily", "0 0 * * *", next_exec
        )
        await test_session.commit()
        
        # Create execution logs
        for i in range(3):
            log = DCAExecutionLog(
                recurring_payment_id=payment.id,
                user_id="12345",
                scheduled_at=datetime.now(timezone.utc),
                executed_at=datetime.now(timezone.utc),
                status="success",
                amount=10.0,
                token_symbol="USDC",
                transaction_hash=f"0x{i:064d}",
            )
            test_session.add(log)
        
        await test_session.commit()
        
        history = await DCAOperations.get_payment_history(test_session, payment.id)
        assert len(history) == 3
    
    async def test_get_user_execution_history(self, test_session):
        """Test getting user's execution history."""
        from app.dca.models import DCAExecutionLog
        
        next_exec = datetime.now(timezone.utc) + timedelta(days=1)
        payment = await DCAOperations.create_recurring_payment(
            test_session, "12345", "0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247",
            10.0, "USDC", "ethereum", "daily", "0 0 * * *", next_exec
        )
        await test_session.commit()
        
        # Create execution logs
        for i in range(2):
            log = DCAExecutionLog(
                recurring_payment_id=payment.id,
                user_id="12345",
                scheduled_at=datetime.now(timezone.utc),
                executed_at=datetime.now(timezone.utc),
                status="success",
                amount=10.0,
                token_symbol="USDC",
                transaction_hash=f"0x{i:064d}",
            )
            test_session.add(log)
        
        await test_session.commit()
        
        history = await DCAOperations.get_user_execution_history(test_session, "12345")
        assert len(history) >= 2
