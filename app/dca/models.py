"""
models.py - Database models for DCA recurring payments system.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, Boolean, Text, ForeignKey
from app.db.base import Base
from datetime import datetime
import enum



class RecurrenceType(str, enum.Enum):
    """Supported recurrence types."""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class DCAStatus(str, enum.Enum):
    """DCA recurring payment status."""
    ACTIVE = "active"
    PAUSED = "paused"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RecurringPayment(Base):
    """
    Model for recurring automated crypto transfers.
    Stores DCA configuration and execution tracking.
    """
    __tablename__ = "recurring_payments"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # User information
    user_id = Column(String(50), nullable=False, index=True)
    
    # Payment details
    recipient_address = Column(String(100), nullable=False)
    amount = Column(Float, nullable=False)  # USD amount
    token_symbol = Column(String(20), nullable=False, default="USDC")
    chain = Column(String(50), nullable=False, default="ethereum")
    
    # Scheduling
    recurrence_type = Column(String(20), nullable=False)  # e.g., "daily", "weekly", "monday"
    cron_expression = Column(String(50), nullable=False)  # e.g., "0 0 * * *"
    
    # Execution tracking
    next_execution_at = Column(DateTime, nullable=True, index=True)
    last_execution_at = Column(DateTime, nullable=True)
    execution_count = Column(Integer, default=0)
    
    # Status
    status = Column(String(20), default=DCAStatus.ACTIVE.value, index=True)
    
    # Metadata
    description = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return (
            f"<RecurringPayment("
            f"id={self.id}, "
            f"user={self.user_id}, "
            f"amount=${self.amount} {self.token_symbol}, "
            f"recipient={self.recipient_address[:10]}..., "
            f"schedule={self.recurrence_type}, "
            f"status={self.status}"
            f")>"
        )


class DCAExecutionLog(Base):
    """
    Audit log for DCA executions.
    Tracks every transaction attempt for debugging and compliance.
    """
    __tablename__ = "dca_execution_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Reference to recurring payment
    recurring_payment_id = Column(Integer, ForeignKey("recurring_payments.id"), nullable=False, index=True)
    user_id = Column(String(50), nullable=False, index=True)
    
    # Execution details
    scheduled_at = Column(DateTime, nullable=False)
    executed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    status = Column(String(20), nullable=False)  # "success", "failed", "skipped"
    
    # Transaction info
    transaction_hash = Column(String(100), nullable=True, unique=True)
    amount = Column(Float, nullable=False)
    token_symbol = Column(String(20), nullable=False)
    
    # Error tracking
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    
    # Metadata
    block_number = Column(Integer, nullable=True)
    gas_used = Column(String(50), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    def __repr__(self):
        return (
            f"<DCAExecutionLog("
            f"id={self.id}, "
            f"payment_id={self.recurring_payment_id}, "
            f"tx={self.transaction_hash[:10] if self.transaction_hash else 'N/A'}..., "
            f"status={self.status}"
            f")>"
        )
