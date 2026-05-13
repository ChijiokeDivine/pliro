"""
rate_limiter.py - Rate limiting and cooldown management.
Protects against user abuse and API rate limits.
"""

import logging
from typing import Dict, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class RateLimiter:
    """In-memory rate limiter with per-user cooldowns."""
    
    def __init__(self):
        # user_id -> (last_request_time, request_count)
        self.request_history: Dict[str, Tuple[datetime, int]] = defaultdict(lambda: (None, 0))
        
        # user_id -> (reason, cooldown_until)
        self.cooldowns: Dict[str, Tuple[str, datetime]] = {}
    
    def is_rate_limited(self, user_id: str) -> Tuple[bool, str]:
        """
        Check if user is rate limited.
        
        Returns:
            (is_limited, reason)
        """
        # Check cooldown
        if user_id in self.cooldowns:
            reason, until = self.cooldowns[user_id]
            if datetime.now() < until:
                remaining = (until - datetime.now()).total_seconds()
                return True, f"Too many requests. Try again in {int(remaining)}s. Reason: {reason}"
            else:
                # Cooldown expired
                del self.cooldowns[user_id]
        
        return False, ""
    
    def record_request(self, user_id: str) -> bool:
        """
        Record a user request and check rate limit.
        
        Returns:
            True if request is allowed, False if rate limited
        """
        is_limited, reason = self.is_rate_limited(user_id)
        if is_limited:
            logger.warning(f"Rate limit hit for user {user_id}: {reason}")
            return False
        
        now = datetime.now()
        last_time, count = self.request_history[user_id]
        
        # Reset count if more than 1 minute has passed
        if last_time and (now - last_time).total_seconds() > 60:
            self.request_history[user_id] = (now, 1)
            return True
        
        # Increment count
        new_count = (count or 0) + 1
        self.request_history[user_id] = (now, new_count)
        
        # Apply progressive cooldown based on request count
        if new_count >= 10:
            self.apply_cooldown(user_id, "Too many requests", seconds=300)  # 5 min
            return False
        elif new_count >= 6:
            self.apply_cooldown(user_id, "Rate limit approaching", seconds=60)  # 1 min
            return False
        
        return True
    
    def apply_cooldown(self, user_id: str, reason: str = "Rate limited", seconds: int = 60):
        """Apply a cooldown period for a user."""
        until = datetime.now() + timedelta(seconds=seconds)
        self.cooldowns[user_id] = (reason, until)
        logger.warning(f"Cooldown applied to user {user_id} for {seconds}s: {reason}")
    
    def reset_user(self, user_id: str):
        """Reset rate limit for a user."""
        self.request_history.pop(user_id, None)
        self.cooldowns.pop(user_id, None)
    
    def cleanup(self):
        """Remove expired cooldowns."""
        now = datetime.now()
        expired = [uid for uid, (_, until) in self.cooldowns.items() if now >= until]
        for uid in expired:
            del self.cooldowns[uid]


class AICallThrottler:
    """Throttle AI calls to respect rate limits and reduce costs."""
    
    def __init__(self):
        # Track AI calls per user per minute
        self.ai_call_history: Dict[str, list] = defaultdict(list)
        self.max_ai_calls_per_minute = 5  # Configurable
        self.max_ai_calls_per_hour = 50
    
    def can_call_ai(self, user_id: str) -> Tuple[bool, str]:
        """Check if we can call AI for this user."""
        now = datetime.now()
        
        # Get recent calls
        user_calls = self.ai_call_history[user_id]
        
        # Remove old entries
        user_calls[:] = [t for t in user_calls if (now - t).total_seconds() < 3600]
        
        # Check per-minute limit
        recent_minute = [t for t in user_calls if (now - t).total_seconds() < 60]
        if len(recent_minute) >= self.max_ai_calls_per_minute:
            return False, f"AI rate limit: {len(recent_minute)}/{self.max_ai_calls_per_minute} calls/min"
        
        # Check per-hour limit
        if len(user_calls) >= self.max_ai_calls_per_hour:
            return False, f"AI daily limit: {len(user_calls)}/{self.max_ai_calls_per_hour} calls/hour"
        
        return True, ""
    
    def record_ai_call(self, user_id: str):
        """Record that AI was called for this user."""
        self.ai_call_history[user_id].append(datetime.now())
    
    def get_stats(self, user_id: str) -> dict:
        """Get AI call statistics for a user."""
        now = datetime.now()
        user_calls = self.ai_call_history[user_id]
        
        minute_calls = len([t for t in user_calls if (now - t).total_seconds() < 60])
        hour_calls = len([t for t in user_calls if (now - t).total_seconds() < 3600])
        
        return {
            "calls_this_minute": minute_calls,
            "limit_per_minute": self.max_ai_calls_per_minute,
            "calls_this_hour": hour_calls,
            "limit_per_hour": self.max_ai_calls_per_hour,
        }


# Global instances
_rate_limiter = RateLimiter()
_ai_throttler = AICallThrottler()


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance."""
    return _rate_limiter


def get_ai_throttler() -> AICallThrottler:
    """Get global AI throttler instance."""
    return _ai_throttler
