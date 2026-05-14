"""
Integration tests for DCA system - parser, CRUD, and scheduler together.
"""

import pytest
from datetime import datetime, timedelta, timezone
from app.dca.parser import parse_dca_command, DCAParser
from app.dca.crud import DCAOperations
from app.dca.models import DCAStatus


@pytest.mark.asyncio
class TestDCAIntegration:
    """Integration tests for complete DCA flow."""
    
    async def test_parse_and_create_dca(self, test_session):
        """Test parsing natural language and creating DCA."""
        # Parse natural language
        parsed = parse_dca_command(
            "Send 10 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every monday"
        )
        
        # Create DCA from parsed data
        next_exec = DCAParser.calculate_next_execution(parsed["interval"])
        payment = await DCAOperations.create_recurring_payment(
            test_session,
            user_id="12345",
            recipient_address=parsed["recipient"],
            amount=parsed["amount"],
            token_symbol=parsed["token"],
            chain="ethereum",
            recurrence_type=parsed["interval"],
            cron_expression=parsed["cron_expression"],
            next_execution_at=next_exec,
        )
        await test_session.commit()
        
        # Verify
        assert payment.amount == 10.0
        assert payment.token_symbol == "USDC"
        assert payment.recurrence_type == "monday"
        assert payment.cron_expression == "0 0 * * 1"
        assert payment.status == DCAStatus.ACTIVE.value
    
    async def test_parse_and_create_multiple_dcas(self, test_session):
        """Test creating multiple different DCAs from natural language."""
        commands = [
            ("Send 10 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every monday", "monday", 10.0),
            ("Send 5.5 USDC to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every day", "daily", 5.5),
            ("Send 0.1 eth to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every hour", "hourly", 0.1),
        ]
        
        payments = []
        for command, expected_interval, expected_amount in commands:
            parsed = parse_dca_command(command)
            next_exec = DCAParser.calculate_next_execution(parsed["interval"])
            
            payment = await DCAOperations.create_recurring_payment(
                test_session,
                user_id="12345",
                recipient_address=parsed["recipient"],
                amount=parsed["amount"],
                token_symbol=parsed["token"],
                chain="ethereum",
                recurrence_type=parsed["interval"],
                cron_expression=parsed["cron_expression"],
                next_execution_at=next_exec,
            )
            payments.append(payment)
        
        await test_session.commit()
        
        # Verify all were created
        assert len(payments) == 3
        assert payments[0].recurrence_type == "monday"
        assert payments[1].recurrence_type == "daily"
        assert payments[2].recurrence_type == "hourly"
    
    async def test_parse_and_manage_dca_lifecycle(self, test_session):
        """Test full lifecycle: create, pause, resume, cancel."""
        # Create
        parsed = parse_dca_command(
            "Send 10 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every day"
        )
        next_exec = DCAParser.calculate_next_execution(parsed["interval"])
        payment = await DCAOperations.create_recurring_payment(
            test_session,
            user_id="12345",
            recipient_address=parsed["recipient"],
            amount=parsed["amount"],
            token_symbol=parsed["token"],
            chain="ethereum",
            recurrence_type=parsed["interval"],
            cron_expression=parsed["cron_expression"],
            next_execution_at=next_exec,
        )
        payment_id = payment.id
        await test_session.commit()
        
        # Verify active
        p = await DCAOperations.get_recurring_payment(test_session, payment_id)
        assert p.status == DCAStatus.ACTIVE.value
        
        # Pause
        await DCAOperations.pause_recurring_payment(test_session, payment_id)
        await test_session.commit()
        p = await DCAOperations.get_recurring_payment(test_session, payment_id)
        assert p.status == DCAStatus.PAUSED.value
        
        # Resume
        await DCAOperations.resume_recurring_payment(test_session, payment_id)
        await test_session.commit()
        p = await DCAOperations.get_recurring_payment(test_session, payment_id)
        assert p.status == DCAStatus.ACTIVE.value
        
        # Cancel
        await DCAOperations.cancel_recurring_payment(test_session, payment_id)
        await test_session.commit()
        p = await DCAOperations.get_recurring_payment(test_session, payment_id)
        assert p.status == DCAStatus.CANCELLED.value
    
    async def test_query_dcas_by_user(self, test_session):
        """Test querying DCAs by user after creating multiple."""
        # Create DCAs for user 12345
        for i, interval in enumerate(["daily", "weekly", "monthly"]):
            parsed = parse_dca_command(
                f"Send {10+i} dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every {interval}"
            )
            next_exec = DCAParser.calculate_next_execution(parsed["interval"])
            
            await DCAOperations.create_recurring_payment(
                test_session,
                user_id="12345",
                recipient_address=parsed["recipient"],
                amount=parsed["amount"],
                token_symbol=parsed["token"],
                chain="ethereum",
                recurrence_type=parsed["interval"],
                cron_expression=parsed["cron_expression"],
                next_execution_at=next_exec,
            )
        
        # Create DCAs for different user
        parsed = parse_dca_command(
            "Send 5 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every day"
        )
        next_exec = DCAParser.calculate_next_execution(parsed["interval"])
        await DCAOperations.create_recurring_payment(
            test_session,
            user_id="99999",
            recipient_address=parsed["recipient"],
            amount=parsed["amount"],
            token_symbol=parsed["token"],
            chain="ethereum",
            recurrence_type=parsed["interval"],
            cron_expression=parsed["cron_expression"],
            next_execution_at=next_exec,
        )
        
        await test_session.commit()
        
        # Query user 12345
        user_dcas = await DCAOperations.list_user_recurring_payments(test_session, "12345")
        assert len(user_dcas) == 3
        
        # Query user 99999
        other_dcas = await DCAOperations.list_user_recurring_payments(test_session, "99999")
        assert len(other_dcas) == 1
    
    async def test_execution_tracking(self, test_session):
        """Test execution tracking after payment execution."""
        from app.dca.models import DCAExecutionLog
        
        # Create DCA
        parsed = parse_dca_command(
            "Send 10 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every day"
        )
        next_exec = DCAParser.calculate_next_execution(parsed["interval"])
        payment = await DCAOperations.create_recurring_payment(
            test_session,
            user_id="12345",
            recipient_address=parsed["recipient"],
            amount=parsed["amount"],
            token_symbol=parsed["token"],
            chain="ethereum",
            recurrence_type=parsed["interval"],
            cron_expression=parsed["cron_expression"],
            next_execution_at=next_exec,
        )
        await test_session.commit()
        
        # Simulate execution
        now = datetime.now(timezone.utc)
        log = DCAExecutionLog(
            recurring_payment_id=payment.id,
            user_id="12345",
            scheduled_at=now,
            executed_at=now,
            status="success",
            transaction_hash="0x" + "a" * 64,
            amount=payment.amount,
            token_symbol=payment.token_symbol,
        )
        test_session.add(log)
        
        # Update payment
        await DCAOperations.update_recurring_payment(
            test_session,
            payment.id,
            last_execution_at=now,
            execution_count=1,
        )
        
        await test_session.commit()
        
        # Verify history
        history = await DCAOperations.get_payment_history(test_session, payment.id)
        assert len(history) == 1
        assert history[0].status == "success"
        assert history[0].transaction_hash == "0x" + "a" * 64
        
        # Verify payment updated
        updated = await DCAOperations.get_recurring_payment(test_session, payment.id)
        assert updated.execution_count == 1
        assert updated.last_execution_at is not None


@pytest.mark.asyncio
class TestDCAEdgeCases:
    """Test edge cases and boundary conditions."""
    
    async def test_create_dca_with_max_amount(self, test_session):
        """Test creating DCA with maximum allowed amount."""
        parsed = parse_dca_command(
            "Send 999999.99 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every day"
        )
        next_exec = DCAParser.calculate_next_execution(parsed["interval"])
        
        payment = await DCAOperations.create_recurring_payment(
            test_session,
            user_id="12345",
            recipient_address=parsed["recipient"],
            amount=parsed["amount"],
            token_symbol=parsed["token"],
            chain="ethereum",
            recurrence_type=parsed["interval"],
            cron_expression=parsed["cron_expression"],
            next_execution_at=next_exec,
        )
        await test_session.commit()
        
        assert payment.amount == 999999.99
    
    async def test_create_dca_with_small_amount(self, test_session):
        """Test creating DCA with small amount."""
        parsed = parse_dca_command(
            "Send 0.01 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every hour"
        )
        next_exec = DCAParser.calculate_next_execution(parsed["interval"])
        
        payment = await DCAOperations.create_recurring_payment(
            test_session,
            user_id="12345",
            recipient_address=parsed["recipient"],
            amount=parsed["amount"],
            token_symbol=parsed["token"],
            chain="ethereum",
            recurrence_type=parsed["interval"],
            cron_expression=parsed["cron_expression"],
            next_execution_at=next_exec,
        )
        await test_session.commit()
        
        assert payment.amount == 0.01
    
    async def test_list_empty_user_dcas(self, test_session):
        """Test listing DCAs for user with none."""
        dcas = await DCAOperations.list_user_recurring_payments(test_session, "nonexistent")
        assert len(dcas) == 0
    
    async def test_case_insensitive_parsing(self, test_session):
        """Test that parser handles case variations."""
        # Test uppercase
        parsed1 = parse_dca_command(
            "SEND 10 DOLLARS TO 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 EVERY DAY"
        )
        
        # Test lowercase
        parsed2 = parse_dca_command(
            "send 10 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every day"
        )
        
        # Test mixed case
        parsed3 = parse_dca_command(
            "Send 10 Dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 Every Day"
        )
        
        # All should parse to same values
        assert parsed1["amount"] == parsed2["amount"] == parsed3["amount"] == 10.0
        assert parsed1["interval"] == parsed2["interval"] == parsed3["interval"] == "daily"
