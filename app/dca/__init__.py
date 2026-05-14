"""
DCA (Dollar Cost Averaging) module for recurring crypto transfers.

Provides:
- Natural language parsing for DCA commands
- PostgreSQL storage for recurring payments
- APScheduler integration for job scheduling
- Execution engine with safety checks
- Telegram command handlers
- Audit logging

Quick start:
    1. Create a DCA: "Send 10 dollars to 0x... every monday"
    2. Parser extracts: amount, token, recipient, interval
    3. Scheduler runs job on schedule
    4. Executor performs transfer with validation
    5. Execution logged for audit trail
"""

from app.dca.models import RecurringPayment, DCAExecutionLog, RecurrenceType, DCAStatus
from app.dca.parser import DCAParser, parse_dca_command, DCAParseError
from app.dca.scheduler import DCAScheduler, get_dca_scheduler
from app.dca.executor import DCAExecutor, DCAValidator
from app.dca.crud import DCAOperations
from app.dca.handlers import (
    dca_command,
    dca_callback,
)

__all__ = [
    # Models
    "RecurringPayment",
    "DCAExecutionLog",
    "RecurrenceType",
    "DCAStatus",
    # Parser
    "DCAParser",
    "parse_dca_command",
    "DCAParseError",
    # Scheduler
    "DCAScheduler",
    "get_dca_scheduler",
    # Executor
    "DCAExecutor",
    "DCAValidator",
    # CRUD
    "DCAOperations",
    # Handlers
    "dca_command",
    "dca_callback",
]
