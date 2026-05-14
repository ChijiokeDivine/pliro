"""
Tests for DCA parser - tests natural language command parsing.
"""

import pytest
from datetime import datetime, timedelta, timezone
from app.dca.parser import parse_dca_command, DCAParser, DCAParseError, RecurrenceInterval


class TestDCAParserBasic:
    """Basic parser functionality tests."""
    
    def test_parse_simple_daily(self):
        """Test parsing simple daily command."""
        result = parse_dca_command("Send 10 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every day")
        
        assert result["amount"] == 10.0
        assert result["token"] == "USDC"
        assert result["recipient"] == "0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247"
        assert result["interval"] == "daily"
        assert result["cron_expression"] == "0 0 * * *"
    
    def test_parse_monday_recurring(self):
        """Test parsing Monday recurring command."""
        result = parse_dca_command("Send 10 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every monday")
        
        assert result["amount"] == 10.0
        assert result["token"] == "USDC"
        assert result["interval"] == "monday"
        assert result["cron_expression"] == "0 0 * * 1"
    
    def test_parse_with_decimal_amount(self):
        """Test parsing with decimal amount."""
        result = parse_dca_command("Send 5.5 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every day")
        
        assert result["amount"] == 5.5
    
    def test_parse_usdc_token(self):
        """Test parsing USDC token."""
        result = parse_dca_command("Send 10 USDC to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every week")
        
        assert result["token"] == "USDC"
    
    def test_parse_eth_token(self):
        """Test parsing ETH token."""
        result = parse_dca_command("Send 0.5 eth to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every day")
        
        assert result["token"] == "ETH"
    
    def test_parse_usdt_token(self):
        """Test parsing USDT token."""
        result = parse_dca_command("Send 100 usdt to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every month")
        
        assert result["token"] == "USDT"


class TestDCAParserIntervals:
    """Test various recurrence intervals."""
    
    def test_parse_hourly(self):
        """Test parsing hourly interval."""
        result = parse_dca_command("Send 5 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every hour")
        assert result["interval"] == "hourly"
        assert result["cron_expression"] == "0 * * * *"
    
    def test_parse_everyday(self):
        """Test parsing 'everyday' variant."""
        result = parse_dca_command("Send 10 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 everyday")
        assert result["interval"] == "daily"
    
    def test_parse_weekly(self):
        """Test parsing weekly."""
        result = parse_dca_command("Send 10 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every week")
        assert result["interval"] == "weekly"
        assert result["cron_expression"] == "0 0 * * 0"  # Sunday
    
    def test_parse_monthly(self):
        """Test parsing monthly."""
        result = parse_dca_command("Send 100 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every month")
        assert result["interval"] == "monthly"
        assert result["cron_expression"] == "0 0 1 * *"
    
    def test_parse_all_weekdays(self):
        """Test parsing all weekdays."""
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        crons = ["0 0 * * 1", "0 0 * * 2", "0 0 * * 3", "0 0 * * 4", "0 0 * * 5", "0 0 * * 6", "0 0 * * 0"]
        
        for weekday, expected_cron in zip(weekdays, crons):
            result = parse_dca_command(f"Send 10 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every {weekday}")
            assert result["interval"] == weekday
            assert result["cron_expression"] == expected_cron


class TestDCAParserErrors:
    """Test error handling."""
    
    def test_parse_no_amount(self):
        """Test error when amount is missing."""
        with pytest.raises(DCAParseError, match="Could not extract amount"):
            parse_dca_command("Send to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every day")
    
    def test_parse_no_recipient(self):
        """Test error when recipient is missing."""
        with pytest.raises(DCAParseError, match="Could not extract recipient"):
            parse_dca_command("Send 10 dollars to invalid_address every day")
    
    def test_parse_no_interval(self):
        """Test error when interval is missing."""
        with pytest.raises(DCAParseError, match="Could not extract recurrence interval"):
            parse_dca_command("Send 10 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247")
    
    def test_parse_invalid_interval(self):
        """Test error for unsupported interval (minutes)."""
        with pytest.raises(DCAParseError, match="Could not extract recurrence interval"):
            parse_dca_command("Send 10 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every minute")
    
    def test_parse_zero_amount(self):
        """Test error for zero amount."""
        with pytest.raises(DCAParseError, match="Could not extract amount"):
            parse_dca_command("Send 0 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every day")
    
    def test_parse_negative_amount(self):
        """Test error for negative amount."""
        with pytest.raises(DCAParseError, match="Could not extract amount"):
            parse_dca_command("Send -10 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every day")
    
    def test_parse_huge_amount(self):
        """Test error for amount too large."""
        with pytest.raises(DCAParseError, match="Could not extract amount"):
            parse_dca_command("Send 10000000 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every day")


class TestDCAParserValidation:
    """Test validation functions."""
    
    def test_validate_valid_address(self):
        """Test validation of valid EVM address."""
        assert DCAParser.validate_address("0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247")
    
    def test_validate_invalid_address_short(self):
        """Test validation rejects short address."""
        assert not DCAParser.validate_address("0x50C5b228")
    
    def test_validate_invalid_address_no_prefix(self):
        """Test validation rejects address without 0x."""
        assert not DCAParser.validate_address("50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247")
    
    def test_validate_invalid_address_wrong_chars(self):
        """Test validation rejects address with invalid hex."""
        assert not DCAParser.validate_address("0xZZZZb2284D7fc3E7DE4c132D0CD5ABFD7aa11247")


class TestDCAParserNextExecution:
    """Test next execution calculation."""
    
    def test_calculate_next_hourly(self):
        """Test hourly execution calculation."""
        next_exec = DCAParser.calculate_next_execution("hourly")
        
        assert next_exec > datetime.now(timezone.utc)
        assert next_exec.minute == 0
        assert next_exec.second == 0
    
    def test_calculate_next_daily(self):
        """Test daily execution calculation."""
        next_exec = DCAParser.calculate_next_execution("daily")
        now = datetime.now(timezone.utc)
        
        assert next_exec > now
        assert next_exec.hour == 0
        assert next_exec.minute == 0
        # Should be tomorrow or later
        assert (next_exec - now).days >= 0
    
    def test_calculate_next_weekly(self):
        """Test weekly execution calculation."""
        next_exec = DCAParser.calculate_next_execution("weekly")
        now = datetime.now(timezone.utc)
        
        # Should be at next Sunday
        assert next_exec.weekday() == 6  # Sunday
        assert next_exec.hour == 0
        assert (next_exec - now).days >= 0
    
    def test_calculate_next_monday(self):
        """Test Monday-specific execution."""
        next_exec = DCAParser.calculate_next_execution("monday")
        
        assert next_exec.weekday() == 0  # Monday
        assert next_exec.hour == 0
    
    def test_calculate_next_monthly(self):
        """Test monthly execution calculation."""
        next_exec = DCAParser.calculate_next_execution("monthly")
        now = datetime.now(timezone.utc)
        
        assert next_exec.day == 1  # First day of month
        assert next_exec.hour == 0
        # Should be next month or later
        assert (next_exec - now).days >= 0
