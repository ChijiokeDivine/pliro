"""
executor.py - DCA payment execution engine with safety checks and validation.
Handles actual crypto transfers with error handling and audit logging.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.db.database import async_session_factory
from app.db import crud
from app.wallet.privy import PrivyClient
from app.wallet.zerion import ZerionClient
from app.dca.models import RecurringPayment, DCAExecutionLog, DCAStatus
from sqlalchemy import select, update

logger = logging.getLogger(__name__)


def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert an aware datetime to naive UTC for DCA DB timestamp columns."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class DCAValidator:
    """Validates DCA execution conditions."""
    
    def __init__(self):
        self.zerion = ZerionClient()
        self.privy = PrivyClient()
    
    @staticmethod
    async def validate_recipient_address(address: str) -> bool:
        """Validate recipient wallet address format."""
        import re
        # EVM address validation
        if re.match(r"^0x[a-fA-F0-9]{40}$", address):
            return True
        # Solana address validation (base58, ~32-44 chars)
        if len(address) >= 32 and len(address) <= 44:
            return True
        return False
    
    async def check_wallet_balance(
        self,
        wallet_address: str,
        required_amount_usd: float,
        token_symbol: str,
        chain: str
    ) -> Dict[str, Any]:
        """
        Check if wallet has sufficient balance.
        
        Returns:
            {
                "sufficient": bool,
                "balance_usd": float,
                "required_usd": float,
                "token_symbol": str,
                "message": str
            }
        """
        try:
            # Get portfolio
            portfolio = await self.zerion.get_portfolio(wallet_address)
            balance_usd = portfolio.get("total_value", 0)
            
            # Add buffer for gas fees
            required_with_buffer = required_amount_usd * 1.1  # 10% buffer
            
            sufficient = balance_usd >= required_with_buffer
            
            return {
                "sufficient": sufficient,
                "balance_usd": balance_usd,
                "required_usd": required_amount_usd,
                "buffer_usd": required_amount_usd * 0.1,
                "token_symbol": token_symbol,
                "message": (
                    f"Balance sufficient: ${balance_usd:.2f} >= ${required_with_buffer:.2f}"
                    if sufficient else
                    f"Insufficient balance: ${balance_usd:.2f} < ${required_with_buffer:.2f}"
                ),
            }
        
        except Exception as e:
            logger.error(f"Failed to check balance for {wallet_address}: {e}")
            return {
                "sufficient": False,
                "error": str(e),
                "message": f"Failed to check balance: {str(e)}",
            }
    
    async def check_execution_safety(
        self,
        user_id: str,
        payment_id: int,
        recipient: str
    ) -> Dict[str, Any]:
        """
        Check safety conditions before execution.
        
        Returns:
            {
                "safe": bool,
                "checks": {
                    "no_duplicate": bool,
                    "valid_recipient": bool,
                    "user_exists": bool,
                    "payment_active": bool,
                },
                "message": str
            }
        """
        checks = {
            "no_duplicate": True,
            "valid_recipient": True,
            "user_exists": True,
            "payment_active": True,
        }
        issues = []
        
        # Validate recipient
        if not await self.validate_recipient_address(recipient):
            checks["valid_recipient"] = False
            issues.append("Invalid recipient address format")
        
        try:
            async with async_session_factory() as session:
                # Check user exists
                user = await crud.get_or_create_user(session, int(user_id))
                if not user:
                    checks["user_exists"] = False
                    issues.append("User not found")
                
                # Check payment exists and is active
                payment = await session.get(RecurringPayment, payment_id)
                if not payment:
                    checks["payment_active"] = False
                    issues.append("Payment not found")
                elif payment.status != DCAStatus.ACTIVE.value:
                    checks["payment_active"] = False
                    issues.append(f"Payment is {payment.status}, not active")
                
                # Check for duplicate execution in last 60 seconds
                last_60s = _to_naive_utc(datetime.now(timezone.utc) - timedelta(seconds=60))
                result = await session.execute(
                    select(DCAExecutionLog).where(
                        DCAExecutionLog.recurring_payment_id == payment_id,
                        DCAExecutionLog.executed_at >= last_60s,
                        DCAExecutionLog.status == "success",
                    )
                )
                recent_executions = result.scalars().all()
                if recent_executions:
                    checks["no_duplicate"] = False
                    issues.append(f"Duplicate execution detected (executed {len(recent_executions)} times in last 60s)")
        
        except Exception as e:
            logger.error(f"Safety check error: {e}")
            return {
                "safe": False,
                "checks": checks,
                "message": f"Safety check failed: {str(e)}",
            }
        
        safe = all(checks.values())
        
        return {
            "safe": safe,
            "checks": checks,
            "message": "All checks passed" if safe else ", ".join(issues),
        }


class DCAExecutor:
    """Executes DCA recurring payments with comprehensive error handling."""
    
    def __init__(self):
        self.validator = DCAValidator()
        self.privy = PrivyClient()
        self.zerion = ZerionClient()
        self.max_retries = 3
    
    async def execute_payment(self, payment_id: int):
        """
        Execute a single DCA payment.
        
        This is called by the scheduler. Handles all error cases gracefully.
        """
        start_time = datetime.now(timezone.utc)
        execution_log = None
        
        try:
            async with async_session_factory() as session:
                # Get payment
                payment = await session.get(RecurringPayment, payment_id)
                if not payment:
                    logger.error(f"Payment {payment_id} not found")
                    return
                
                logger.info(
                    f"Executing DCA payment {payment_id}: "
                    f"${payment.amount} {payment.token_symbol} → {payment.recipient_address[:10]}..."
                )
                
                # Validate execution safety
                safety = await self.validator.check_execution_safety(
                    payment.user_id,
                    payment_id,
                    payment.recipient_address
                )
                
                if not safety["safe"]:
                    logger.warning(f"Payment {payment_id} failed safety check: {safety['message']}")
                    await self._log_execution(
                        session, payment_id, payment.user_id, payment.amount,
                        payment.token_symbol, "failed", error_message=safety["message"]
                    )
                    return
                
                # Check wallet balance
                user = await crud.get_or_create_user(session, int(payment.user_id))
                wallet = await crud.get_user_wallet(session, user.id)
                
                if not wallet:
                    logger.error(f"No wallet found for user {payment.user_id}")
                    await self._log_execution(
                        session, payment_id, payment.user_id, payment.amount,
                        payment.token_symbol, "failed", error_message="No wallet found"
                    )
                    return
                
                balance_check = await self.validator.check_wallet_balance(
                    wallet.evm_address,
                    payment.amount,
                    payment.token_symbol,
                    payment.chain
                )
                
                if not balance_check["sufficient"]:
                    logger.warning(f"Payment {payment_id} insufficient balance: {balance_check['message']}")
                    await self._log_execution(
                        session, payment_id, payment.user_id, payment.amount,
                        payment.token_symbol, "failed", error_message=balance_check["message"]
                    )
                    return
                
                # Execute transaction
                try:
                    amount_wei = int(float(payment.amount) * 10 ** 18)
                    tx_hash = await self.privy.send_evm_transaction(
                        wallet_id=wallet.privy_evm_wallet_id,
                        to_address=payment.recipient_address,
                        value_hex=hex(amount_wei),
                        chain=payment.chain,
                    )
                    
                    # Success!
                    logger.info(f"Payment {payment_id} executed: TX {tx_hash}")
                    
                    # Update payment
                    payment.last_execution_at = _to_naive_utc(datetime.now(timezone.utc))
                    payment.execution_count = (payment.execution_count or 0) + 1
                    payment.next_execution_at = _to_naive_utc(self._calculate_next_execution(payment))
                    session.add(payment)
                    
                    # Log execution
                    await self._log_execution(
                        session, payment_id, payment.user_id, payment.amount,
                        payment.token_symbol, "success", tx_hash
                    )
                    
                    await session.commit()
                
                except Exception as tx_error:
                    logger.error(f"Transaction failed for payment {payment_id}: {tx_error}", exc_info=True)
                    await self._log_execution(
                        session, payment_id, payment.user_id, payment.amount,
                        payment.token_symbol, "failed", error_message=str(tx_error), retry_count=1
                    )
                    await session.commit()
        
        except Exception as e:
            logger.error(f"Unexpected error executing payment {payment_id}: {e}", exc_info=True)
    
    async def _log_execution(
        self,
        session,
        payment_id: int,
        user_id: str,
        amount: float,
        token_symbol: str,
        status: str,
        tx_hash: Optional[str] = None,
        error_message: Optional[str] = None,
        retry_count: int = 0
    ):
        """Create an execution log entry."""
        try:
            log = DCAExecutionLog(
                recurring_payment_id=payment_id,
                user_id=user_id,
                scheduled_at=_to_naive_utc(datetime.now(timezone.utc)),
                executed_at=_to_naive_utc(datetime.now(timezone.utc)),
                status=status,
                transaction_hash=tx_hash,
                amount=amount,
                token_symbol=token_symbol,
                error_message=error_message,
                retry_count=retry_count,
            )
            session.add(log)
            logger.debug(f"Logged execution for payment {payment_id}: {status}")
        except Exception as e:
            logger.warning(f"Failed to log execution: {e}")
    
    @staticmethod
    def _calculate_next_execution(payment: RecurringPayment) -> datetime:
        """Calculate next execution time."""
        from app.dca.parser import DCAParser
        
        try:
            next_exec = DCAParser.calculate_next_execution(payment.recurrence_type)
            return next_exec
        except Exception as e:
            logger.warning(f"Failed to calculate next execution: {e}")
            return _to_naive_utc(datetime.now(timezone.utc) + timedelta(hours=1))
