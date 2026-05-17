"""
parser.py - Natural language parser for DCA commands.
Extracts amount, token, recipient, and recurrence interval deterministically.

Supported commands:
- Send 10 dollars to 0x... every monday
- Send 10 dollars to 0x... every week
- Send 10 dollars to 0x... every month
- Send 10 dollars to 0x... everyday
- Send 10 dollars to 0x... every hour

NO MINUTES ALLOWED - minimum interval is hourly.
"""

import re
import logging
from typing import Tuple, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class RecurrenceInterval(str, Enum):
    """Supported recurrence intervals."""
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


class DCAParseError(Exception):
    """Exception raised when DCA parsing fails."""
    pass


class DCAParser:
    """Deterministic parser for DCA commands."""
    
    # Cron expressions for intervals
    CRON_EXPRESSIONS = {
        RecurrenceInterval.HOURLY: "0 * * * *",      # Every hour at :00
        RecurrenceInterval.DAILY: "0 0 * * *",        # Every day at 00:00 UTC
        RecurrenceInterval.WEEKLY: "0 0 * * 0",       # Every Sunday at 00:00 UTC
        RecurrenceInterval.MONTHLY: "0 0 1 * *",      # First day of month at 00:00 UTC
        RecurrenceInterval.MONDAY: "0 0 * * 1",       # Every Monday at 00:00 UTC
        RecurrenceInterval.TUESDAY: "0 0 * * 2",      # Every Tuesday at 00:00 UTC
        RecurrenceInterval.WEDNESDAY: "0 0 * * 3",    # Every Wednesday at 00:00 UTC
        RecurrenceInterval.THURSDAY: "0 0 * * 4",     # Every Thursday at 00:00 UTC
        RecurrenceInterval.FRIDAY: "0 0 * * 5",       # Every Friday at 00:00 UTC
        RecurrenceInterval.SATURDAY: "0 0 * * 6",     # Every Saturday at 00:00 UTC
        RecurrenceInterval.SUNDAY: "0 0 * * 0",       # Every Sunday at 00:00 UTC
    }
    
    # Token to symbol mapping
    CURRENCY_MAPPING = {
        "dollar": "USDC",
        "dollars": "USDC",
        "usd": "USDC",
        "usdc": "USDC",
        "usdt": "USDT",
        "eth": "ETH",
        "ethereum": "ETH",
        "btc": "BTC",
        "bitcoin": "BTC",
        "matic": "MATIC",
        "polygon": "MATIC",
        "sol": "SOL",
        "solana": "SOL",
    }
    
    @staticmethod
    def parse(text: str) -> Dict[str, Any]:
        """
        Parse a DCA command string.
        
        Args:
            text: Command text like "Send 10 dollars to 0x... every monday"
            
        Returns:
            Dict with keys: amount, token, recipient, interval, cron_expression
            
        Raises:
            DCAParseError: If parsing fails
        """
        text = text.strip()
        logger.debug(f"Parsing DCA command: {text}")
        
        # Extract amount
        amount = DCAParser._extract_amount(text)
        if amount is None:
            raise DCAParseError("Could not extract amount. Example: 'Send 10 dollars...'")
        
        # Extract token/currency
        token = DCAParser._extract_token(text)
        if token is None:
            raise DCAParseError("Could not extract token/currency. Example: '...10 dollars...'")
        
        # Extract recipient address
        recipient = DCAParser._extract_recipient(text)
        if recipient is None:
            raise DCAParseError("Could not extract recipient address. Example: '...to 0x123...'")
        
        # Extract recurrence interval
        interval = DCAParser._extract_interval(text)
        if interval is None:
            raise DCAParseError(
                "Could not extract recurrence interval. Supported: "
                "hourly, daily, weekly, monthly, monday-sunday"
            )
        
        # Get cron expression
        cron = DCAParser.CRON_EXPRESSIONS[interval]
        
        logger.info(
            f"Parsed DCA: ${amount} {token} → {recipient[:10]}... "
            f"every {interval.value} (cron: {cron})"
        )
        
        return {
            "amount": amount,
            "token": token,
            "recipient": recipient,
            "interval": interval.value,
            "cron_expression": cron,
        }
    
    @staticmethod
    def _extract_amount(text: str) -> Optional[float]:
        """Extract dollar/token amount."""
        # Pattern: optional dca/send prefix, then number and token
        pattern = r"(?:dca\s+)?(?:send\s+)?([\d.]+)\s+(?:dollars?|usd|usdc?|eth|btc|matic|pol|sol|ethereum|bitcoin|solana|arb|op|celo)"
        match = re.search(pattern, text, re.IGNORECASE)
        
        if match:
            try:
                amount = float(match.group(1))
                if amount <= 0:
                    return None
                if amount > 1_000_000:  # Sanity check
                    return None
                return amount
            except ValueError:
                return None
        
        return None
    
    @staticmethod
    def _extract_token(text: str) -> Optional[str]:
        """Extract token symbol."""
        pattern = r"(?:dca\s+)?(?:send\s+)?[\d.]+\s+(\w+)"
        match = re.search(pattern, text, re.IGNORECASE)
        
        if match:
            token_input = match.group(1).lower()
            # Map to standard symbol
            token = DCAParser.CURRENCY_MAPPING.get(token_input, token_input.upper())
            return token
        
        return None
    
    @staticmethod
    def _extract_recipient(text: str) -> Optional[str]:
        """Extract recipient wallet address."""
        # Pattern: 0x followed by 40 hex characters
        pattern = r"(?:to\s+)?(?:\@)?(0x[a-fA-F0-9]{40})"
        match = re.search(pattern, text, re.IGNORECASE)
        
        if match:
            return match.group(1)
        
        return None
    
    @staticmethod
    def _extract_interval(text: str) -> Optional[RecurrenceInterval]:
        """Extract recurrence interval."""
        text_lower = text.lower()
        
        # Patterns for each interval
        interval_patterns = {
            RecurrenceInterval.HOURLY: [r"every\s+hour", r"hourly"],
            RecurrenceInterval.DAILY: [
                r"every\s+day",
                r"everyday",
                r"daily",
                r"every\s+24\s+hours?",
            ],
            RecurrenceInterval.WEEKLY: [
                r"every\s+week",
                r"weekly",
                r"every\s+7\s+days?",
            ],
            RecurrenceInterval.MONTHLY: [
                r"every\s+month",
                r"monthly",
                r"every\s+30\s+days?",
            ],
            RecurrenceInterval.MONDAY: [
                r"every\s+monday",
                r"mondays",
                r"monday",
            ],
            RecurrenceInterval.TUESDAY: [
                r"every\s+tuesday",
                r"tuesdays",
                r"tuesday",
            ],
            RecurrenceInterval.WEDNESDAY: [
                r"every\s+wednesday",
                r"wednesdays",
                r"wednesday",
            ],
            RecurrenceInterval.THURSDAY: [
                r"every\s+thursday",
                r"thursdays",
                r"thursday",
            ],
            RecurrenceInterval.FRIDAY: [
                r"every\s+friday",
                r"fridays",
                r"friday",
            ],
            RecurrenceInterval.SATURDAY: [
                r"every\s+saturday",
                r"saturdays",
                r"saturday",
            ],
            RecurrenceInterval.SUNDAY: [
                r"every\s+sunday",
                r"sundays",
                r"sunday",
            ],
        }
        
        # Check patterns
        for interval, patterns in interval_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    return interval
        
        return None
    
    @staticmethod
    def validate_address(address: str) -> bool:
        """Validate Ethereum-style address."""
        return bool(re.match(r"^0x[a-fA-F0-9]{40}$", address))
    
    @staticmethod
    def get_cron_expression(interval: str) -> str:
        """Get cron expression for a given interval string."""
        try:
            # Try to get from enum directly
            return DCAParser.CRON_EXPRESSIONS[RecurrenceInterval(interval)]
        except ValueError:
            # If not a direct enum match, try case-insensitive lookup
            for enum_val in RecurrenceInterval:
                if enum_val.value.lower() == interval.lower():
                    return DCAParser.CRON_EXPRESSIONS[enum_val]
            raise ValueError(f"Invalid interval: {interval}")
    
    @staticmethod
    def calculate_next_execution(interval: str) -> datetime:
        """
        Calculate next execution time for an interval.
        
        All times are UTC midnight unless specified otherwise.
        """
        now = datetime.now(timezone.utc)
        
        if interval == RecurrenceInterval.HOURLY.value:
            # Next hour at :00
            return (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        
        elif interval == RecurrenceInterval.DAILY.value:
            # Tomorrow at 00:00 UTC
            return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        elif interval == RecurrenceInterval.WEEKLY.value:
            # Next Sunday at 00:00 UTC
            days_until_sunday = (6 - now.weekday()) % 7
            if days_until_sunday == 0:
                days_until_sunday = 7
            return (now + timedelta(days=days_until_sunday)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        elif interval == RecurrenceInterval.MONTHLY.value:
            # First day of next month at 00:00 UTC
            if now.month == 12:
                next_exec = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                next_exec = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
            return next_exec
        
        elif interval in [d.value for d in RecurrenceInterval if d.name.isupper()]:
            # Weekday-specific (monday, tuesday, etc.)
            weekday_map = {
                "monday": 0,
                "tuesday": 1,
                "wednesday": 2,
                "thursday": 3,
                "friday": 4,
                "saturday": 5,
                "sunday": 6,
            }
            target_weekday = weekday_map[interval]
            
            # Days until target weekday
            days_ahead = (target_weekday - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            
            return (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        return now + timedelta(hours=1)  # Fallback


def parse_dca_command(text: str) -> Dict[str, Any]:
    """
    Public interface for parsing DCA commands.
    
    Raises:
        DCAParseError: If command cannot be parsed
    """
    return DCAParser.parse(text)
