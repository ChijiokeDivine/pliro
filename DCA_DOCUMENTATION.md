# DCA (Dollar Cost Averaging) System Documentation

## Overview

The DCA system enables users to set up recurring cryptocurrency transfers on a schedule. This is useful for:
- **Regular investing**: Transfer a fixed amount on a schedule (e.g., $10 every Monday)
- **Salary allocation**: Automatically move funds to different wallets
- **Dollar cost averaging**: Reduce timing risk by spreading purchases over time
- **Rebalancing**: Maintain portfolio allocations automatically

## Architecture

### Components

```
┌─────────────────────────────────────────────────────┐
│ Telegram Bot (/dca command)                         │
└────────────────┬────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────┐
│ Natural Language Parser (app/dca/parser.py)        │
│  - Deterministic regex-based extraction             │
│  - Supports: hourly, daily, weekly, monthly, days   │
│  - Example: "Send 10 dollars to 0x... every monday" │
└────────────────┬────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────┐
│ Database Models (app/dca/models.py)                │
│  - RecurringPayment: Stores DCA configuration      │
│  - DCAExecutionLog: Audit trail of executions       │
└────────────────┬────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────┐
│ APScheduler (app/dca/scheduler.py)                 │
│  - Job persistence in PostgreSQL                   │
│  - Cron-based scheduling (UTC timezone)             │
│  - Automatic recovery on restart                    │
└────────────────┬────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────┐
│ Execution Engine (app/dca/executor.py)             │
│  - Balance validation                               │
│  - Duplicate prevention                             │
│  - Transaction execution via Privy                  │
│  - Error handling and retries                       │
└────────────────┬────────────────────────────────────┘
                 │
                 ▼
        ╔═══════════════╗
        ║ Blockchain    ║
        ║ Transaction   ║
        ╚═══════════════╝
```

## File Structure

```
app/dca/
├── __init__.py          # Package exports
├── models.py            # SQLAlchemy models (RecurringPayment, DCAExecutionLog)
├── parser.py            # Natural language parser
├── scheduler.py         # APScheduler integration
├── executor.py          # Payment execution engine
├── crud.py              # Database operations
└── handlers.py          # Telegram command handlers

alembic/versions/
└── dca_v1_recurring_payments.py  # Database migration
```

## Usage

### Creating a DCA

User sends:
```
/dca create Send 10 dollars to 0xRecipient every monday
```

Parser extracts:
- Amount: 10
- Token: USDC (default)
- Recipient: 0xRecipient
- Interval: monday (weekly)
- Cron: `0 0 * * 1` (Every Monday at 00:00 UTC)

### Supported Intervals

| Interval | Example Command | Cron Expression | Frequency |
|----------|-----------------|-----------------|-----------|
| Hourly | `...every hour` | `0 * * * *` | Every hour at :00 |
| Daily | `...everyday` or `...daily` | `0 0 * * *` | Every day at 00:00 UTC |
| Weekly | `...every week` | `0 0 * * 0` | Every Sunday at 00:00 UTC |
| Monthly | `...every month` | `0 0 1 * *` | First of month at 00:00 UTC |
| Monday | `...every monday` | `0 0 * * 1` | Every Monday at 00:00 UTC |
| Tuesday | `...every tuesday` | `0 0 * * 2` | Every Tuesday at 00:00 UTC |
| ... | ... | ... | ... |
| Sunday | `...every sunday` | `0 0 * * 0` | Every Sunday at 00:00 UTC |

**Note**: Minutes and seconds are NOT supported. Minimum interval is hourly.

### Managing DCAs

**List all recurring payments:**
```
/dca list
```

**Pause a DCA:**
```
/dca pause [ID]
```

**Resume a paused DCA:**
```
/dca resume [ID]
```

**Cancel a DCA:**
```
/dca cancel [ID]
```

## Database Schema

### RecurringPayment Table

```sql
CREATE TABLE recurring_payments (
  id INTEGER PRIMARY KEY,
  user_id VARCHAR(50) NOT NULL,
  recipient_address VARCHAR(100) NOT NULL,
  amount FLOAT NOT NULL,  -- USD amount
  token_symbol VARCHAR(20) NOT NULL DEFAULT 'USDC',
  chain VARCHAR(50) NOT NULL DEFAULT 'ethereum',
  recurrence_type VARCHAR(20) NOT NULL,  -- e.g., 'daily', 'monday'
  cron_expression VARCHAR(50) NOT NULL,  -- e.g., '0 0 * * *'
  next_execution_at DATETIME,
  last_execution_at DATETIME,
  execution_count INTEGER DEFAULT 0,
  status VARCHAR(20) DEFAULT 'active',  -- 'active', 'paused', 'cancelled'
  description VARCHAR(255),
  notes TEXT,
  created_at DATETIME DEFAULT NOW(),
  updated_at DATETIME DEFAULT NOW()
);
```

### DCAExecutionLog Table

```sql
CREATE TABLE dca_execution_logs (
  id INTEGER PRIMARY KEY,
  recurring_payment_id INTEGER NOT NULL FOREIGN KEY,
  user_id VARCHAR(50) NOT NULL,
  scheduled_at DATETIME NOT NULL,
  executed_at DATETIME NOT NULL DEFAULT NOW(),
  status VARCHAR(20) NOT NULL,  -- 'success', 'failed', 'skipped'
  transaction_hash VARCHAR(100) UNIQUE,
  amount FLOAT NOT NULL,
  token_symbol VARCHAR(20) NOT NULL,
  error_message TEXT,
  retry_count INTEGER DEFAULT 0,
  block_number INTEGER,
  gas_used VARCHAR(50),
  created_at DATETIME DEFAULT NOW()
);
```

## Execution Flow

### 1. Scheduling

**Startup (app/main.py lifespan):**
1. Database initializes
2. `DCAScheduler.initialize()` called
3. APScheduler starts with PostgreSQL job store
4. All active `RecurringPayment` records loaded
5. APScheduler jobs created for each using cron expression

### 2. Scheduled Execution

**When cron time triggers:**
1. APScheduler fires the job
2. `DCAExecutor.execute_payment(payment_id)` called
3. Safety checks performed:
   - Payment exists and is active
   - Recipient address valid
   - No duplicate execution in last 60 seconds
   - Sufficient balance (with gas buffer)
4. If all checks pass:
   - `Privy.send_evm_transaction()` called
   - Transaction hash received
   - `RecurringPayment.last_execution_at` updated
   - Execution logged to `DCAExecutionLog` with status='success'
5. If checks fail:
   - Execution logged with status='failed'
   - Error message recorded
   - Payment status may be set to 'failed'

### 3. Audit Trail

Every execution is logged with:
- Execution time
- Status (success/failed/skipped)
- Transaction hash (if successful)
- Amount and token
- Error message (if failed)
- Retry count
- Block number and gas used (if successful)

## Safety Features

### Balance Validation

Before executing a payment:
1. Fetch wallet balance from Zerion API
2. Add 10% buffer for gas fees
3. Check: `balance >= (amount + gas_buffer)`
4. Fail gracefully if insufficient funds

### Duplicate Prevention

Prevents multiple transactions for same payment within 60 seconds by:
1. Querying `DCAExecutionLog` for recent successful executions
2. Skipping if found within last 60 seconds

### Rate Limiting

The executor handles:
- Per-payment execution: Only one job per `recurring_payment_id`
- APScheduler `max_instances=1`: Prevents concurrent execution
- `coalesce=True`: Skips missed runs if delayed

### Address Validation

Validates recipient:
- EVM addresses: Must match `0x[a-fA-F0-9]{40}`
- Solana addresses: 32-44 character base58
- Rejects malformed addresses

## Configuration

### Environment Variables

Set in `.env` or system:
```bash
DATABASE_URL=postgresql+asyncpg://user:password@localhost/pliro
TELEGRAM_BOT_TOKEN=your_bot_token
```

### Parser Settings

In `app/dca/parser.py`:
```python
# Supported recurrence intervals
SUPPORTED_INTERVALS = [
    "hourly", "daily", "weekly", "monthly",
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday"
]

# Token symbol mapping
CURRENCY_MAPPING = {
    "dollar": "USDC",
    "dollars": "USDC",
    "usd": "USDC",
    "usdc": "USDC",
    # ...
}
```

### Scheduler Settings

In `app/dca/scheduler.py`:
```python
# Job store configuration
jobstores = {
    "default": SQLAlchemyJobStore(url=database_url)
}

# Execution settings
job_defaults = {
    "coalesce": True,        # Skip missed runs
    "max_instances": 1,      # Prevent concurrent runs
}

# Execution configuration
misfire_grace_time = 3600,  # Allow 1 hour late execution
```

### Executor Settings

In `app/dca/executor.py`:
```python
# Balance check buffer
BALANCE_BUFFER = 1.1  # 10% extra for gas

# Duplicate check window
DUPLICATE_WINDOW = 60  # seconds
```

## Testing

### Unit Tests

```python
import pytest
from app.dca.parser import parse_dca_command, DCAParseError

def test_parse_simple_daily():
    result = parse_dca_command("Send 10 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every day")
    assert result["amount"] == 10
    assert result["token"] == "USDC"
    assert result["interval"] == "daily"

def test_parse_weekday():
    result = parse_dca_command("Send 5 USDC to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every monday")
    assert result["interval"] == "monday"

def test_invalid_interval():
    with pytest.raises(DCAParseError):
        parse_dca_command("Send 10 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every minute")

def test_invalid_address():
    with pytest.raises(DCAParseError):
        parse_dca_command("Send 10 dollars to invalid_address every day")
```

### Integration Tests

```python
async def test_create_and_execute_dca():
    # Create DCA
    payment = await DCAOperations.create_recurring_payment(...)
    
    # Schedule it
    scheduler = await get_dca_scheduler()
    await scheduler.schedule_job(payment)
    
    # Verify job exists
    status = scheduler.get_job_status(payment.id)
    assert status is not None
    assert status["next_run_time"] is not None
```

## Monitoring

### Metrics to Track

1. **Execution Success Rate**
   ```
   SELECT 
     status, 
     COUNT(*) as count,
     100 * COUNT(*) / (SELECT COUNT(*) FROM dca_execution_logs) as percentage
   FROM dca_execution_logs
   WHERE executed_at > NOW() - INTERVAL '7 days'
   GROUP BY status;
   ```

2. **Failed Executions**
   ```
   SELECT recurring_payment_id, error_message, COUNT(*) as count
   FROM dca_execution_logs
   WHERE status = 'failed'
   GROUP BY recurring_payment_id, error_message
   ORDER BY count DESC;
   ```

3. **Total Value Transferred**
   ```
   SELECT 
     token_symbol,
     SUM(amount) as total_amount,
     COUNT(*) as transactions
   FROM dca_execution_logs
   WHERE status = 'success'
   GROUP BY token_symbol;
   ```

### Logging

DCA events are logged to file and console:

```
2024-01-15 10:00:00 - app.dca.scheduler - INFO - Scheduled DCA job dca_42: $10.00 USDC → 0x50C5b228... (cron: 0 0 * * 1)
2024-01-15 12:00:00 - app.dca.executor - INFO - Executing DCA payment 42: $10.00 USDC → 0x50C5b228...
2024-01-15 12:00:05 - app.dca.executor - INFO - Payment 42 executed: TX 0xabc123...
```

## Troubleshooting

### Payment not executing

1. **Check if active**: `SELECT status FROM recurring_payments WHERE id = 42;`
2. **Check next execution**: `SELECT next_execution_at FROM recurring_payments WHERE id = 42;`
3. **Check scheduler job**: Verify job exists in APScheduler
4. **Check logs**: Look for error messages in execution logs

### Insufficient balance error

1. **Check wallet balance**: Use `/balance` command
2. **Reduce amount** or **pause other DCAs**
3. **Check gas prices**: May need more buffer

### Invalid address error

1. **Verify format**: EVM addresses must be `0x` + 40 hex characters
2. **Test address**: Try a known working address first

### Duplicate execution detected

This is a safety feature. If triggered:
1. Check execution logs for recent successful runs
2. Verify APScheduler isn't running multiple instances
3. Check system clock synchronization

## API Reference

### Parser

```python
from app.dca.parser import parse_dca_command, DCAParser

# Parse a command
result = parse_dca_command("Send 10 dollars to 0x... every monday")
# Returns: {
#     "amount": 10.0,
#     "token": "USDC",
#     "recipient": "0x...",
#     "interval": "monday",
#     "cron_expression": "0 0 * * 1"
# }

# Validate address
is_valid = DCAParser.validate_address("0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247")

# Calculate next execution
next_exec = DCAParser.calculate_next_execution("daily")
```

### CRUD

```python
from app.dca.crud import DCAOperations

# Create
payment = await DCAOperations.create_recurring_payment(
    session, user_id, recipient, amount, token, chain,
    recurrence_type, cron_expression, next_execution_at
)

# Read
payment = await DCAOperations.get_recurring_payment(session, payment_id)
payments = await DCAOperations.list_user_recurring_payments(session, user_id)

# Update
payment = await DCAOperations.pause_recurring_payment(session, payment_id)
payment = await DCAOperations.resume_recurring_payment(session, payment_id)
payment = await DCAOperations.cancel_recurring_payment(session, payment_id)

# Audit
logs = await DCAOperations.get_payment_history(session, payment_id)
```

### Scheduler

```python
from app.dca.scheduler import get_dca_scheduler

# Initialize
scheduler = await get_dca_scheduler(database_url)

# Schedule job
await scheduler.schedule_job(payment)

# Manage
await scheduler.pause_job(payment_id)
await scheduler.resume_job(payment_id)
await scheduler.unschedule_job(payment_id)

# Query
status = scheduler.get_job_status(payment_id)
```

### Executor

```python
from app.dca.executor import DCAExecutor, DCAValidator

executor = DCAExecutor()

# Execute (called by scheduler)
await executor.execute_payment(payment_id)

# Validate
validator = DCAValidator()
safety = await validator.check_execution_safety(user_id, payment_id, recipient)
balance = await validator.check_wallet_balance(wallet_address, amount, token, chain)
```

## Future Enhancements

1. **Multiple chains**: Currently ethereum only, could support Solana, Polygon, etc.
2. **Advanced intervals**: Cron expression builder UI
3. **Price alerts**: Notification before execution
4. **Gas optimization**: Bundle multiple small DCAs
5. **Portfolio rebalancing**: Auto-calculate amounts to maintain target allocations
6. **Slippage protection**: For DEX swaps as part of DCA
7. **Calendar view**: Visual schedule of upcoming executions
8. **Analytics**: Charts of total transferred, frequency, etc.

## Support

For issues or questions:
1. Check execution logs: `SELECT * FROM dca_execution_logs WHERE status = 'failed' ORDER BY executed_at DESC;`
2. Review Telegram bot logs for parser errors
3. Verify database connection and migrations
4. Check APScheduler job store health
