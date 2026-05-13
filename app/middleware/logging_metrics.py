"""
logging_metrics.py - Metrics tracking for AI reduction and cache effectiveness.
Helps monitor the impact of routing optimization.
"""

import logging
import json
from typing import Dict
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects metrics on AI calls, caching, and routing decisions."""
    
    def __init__(self):
        # Counters
        self.ai_calls_total = 0
        self.ai_calls_skipped = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.rate_limit_events = 0
        self.fallback_responses_used = 0
        
        # Per-intent tracking
        self.intent_counts: Dict[str, int] = defaultdict(int)
        self.intent_ai_calls: Dict[str, int] = defaultdict(int)
        
        # Per-user tracking (for abuse detection)
        self.user_request_counts: Dict[str, int] = defaultdict(int)
        self.user_ai_calls: Dict[str, int] = defaultdict(int)
        
        # Timing
        self.start_time = datetime.now()
        self.hourly_stats: Dict[str, dict] = defaultdict(
            lambda: {"ai_calls": 0, "ai_skipped": 0, "cache_hits": 0}
        )
    
    def record_intent(self, intent: str, user_id: str, used_ai: bool):
        """Record an intent being classified."""
        self.intent_counts[intent] += 1
        self.user_request_counts[user_id] += 1
        
        if used_ai:
            self.intent_ai_calls[intent] += 1
            self.user_ai_calls[user_id] += 1
            self.ai_calls_total += 1
        else:
            self.ai_calls_skipped += 1
        
        # Record in hourly stats
        hour_key = datetime.now().strftime("%Y-%m-%d %H:00")
        if used_ai:
            self.hourly_stats[hour_key]["ai_calls"] += 1
        else:
            self.hourly_stats[hour_key]["ai_skipped"] += 1
    
    def record_cache_hit(self, key: str):
        """Record a cache hit."""
        self.cache_hits += 1
    
    def record_cache_miss(self, key: str):
        """Record a cache miss."""
        self.cache_misses += 1
    
    def record_rate_limit(self, user_id: str, reason: str):
        """Record a rate limit event."""
        self.rate_limit_events += 1
        logger.warning(f"Rate limit: {user_id} - {reason}")
    
    def record_fallback(self, user_id: str, intent: str):
        """Record fallback response usage."""
        self.fallback_responses_used += 1
        logger.info(f"Fallback used for {user_id} (intent: {intent})")
    
    def get_summary(self) -> dict:
        """Get high-level metrics summary."""
        total_requests = self.ai_calls_total + self.ai_calls_skipped
        ai_reduction_percent = (
            (self.ai_calls_skipped / total_requests * 100) if total_requests > 0 else 0
        )
        
        uptime = datetime.now() - self.start_time
        
        return {
            "uptime_seconds": int(uptime.total_seconds()),
            "total_requests": total_requests,
            "ai_calls_made": self.ai_calls_total,
            "ai_calls_skipped": self.ai_calls_skipped,
            "ai_reduction_percent": f"{ai_reduction_percent:.1f}%",
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": f"{(self.cache_hits / (self.cache_hits + self.cache_misses) * 100) if (self.cache_hits + self.cache_misses) > 0 else 0:.1f}%",
            "rate_limit_events": self.rate_limit_events,
            "fallback_responses": self.fallback_responses_used,
        }
    
    def get_intent_stats(self) -> dict:
        """Get per-intent statistics."""
        stats = {}
        for intent, count in self.intent_counts.items():
            ai_calls = self.intent_ai_calls[intent]
            reduction = ((count - ai_calls) / count * 100) if count > 0 else 0
            stats[intent] = {
                "total_requests": count,
                "ai_calls": ai_calls,
                "ai_reduction_percent": f"{reduction:.1f}%",
            }
        return dict(sorted(stats.items(), key=lambda x: x[1]["total_requests"], reverse=True))
    
    def get_user_stats(self, user_id: str) -> dict:
        """Get statistics for a specific user."""
        total = self.user_request_counts[user_id]
        ai_calls = self.user_ai_calls[user_id]
        
        return {
            "total_requests": total,
            "ai_calls": ai_calls,
            "ai_reduction_percent": f"{((total - ai_calls) / total * 100) if total > 0 else 0:.1f}%",
        }
    
    def reset(self):
        """Reset all metrics."""
        self.ai_calls_total = 0
        self.ai_calls_skipped = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.rate_limit_events = 0
        self.fallback_responses_used = 0
        self.intent_counts.clear()
        self.intent_ai_calls.clear()
        self.user_request_counts.clear()
        self.user_ai_calls.clear()
        self.start_time = datetime.now()
        logger.info("Metrics reset")
    
    def log_summary(self):
        """Log a summary to the log file."""
        summary = self.get_summary()
        intent_stats = self.get_intent_stats()
        
        log_msg = (
            f"\n{'='*60}\n"
            f"BOT METRICS SUMMARY\n"
            f"{'='*60}\n"
            f"Uptime: {summary['uptime_seconds']}s\n"
            f"Total Requests: {summary['total_requests']}\n"
            f"AI Calls Made: {summary['ai_calls_made']}\n"
            f"AI Calls Skipped: {summary['ai_calls_skipped']}\n"
            f"AI Reduction: {summary['ai_reduction_percent']}\n"
            f"Cache Hit Rate: {summary['cache_hit_rate']}\n"
            f"Rate Limit Events: {summary['rate_limit_events']}\n"
            f"\nTop Intents:\n"
        )
        
        for intent, stats in list(intent_stats.items())[:10]:
            log_msg += (
                f"  {intent}: {stats['total_requests']} requests, "
                f"{stats['ai_calls']} AI calls ({stats['ai_reduction_percent']}% reduction)\n"
            )
        
        log_msg += f"{'='*60}\n"
        logger.info(log_msg)


# Global instance
_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    """Get global metrics collector."""
    return _metrics
