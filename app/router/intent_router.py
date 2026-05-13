"""
intent_router.py - Main intent routing engine.
Routes messages to handlers based on intent classification and confidence.
Orchestrates the decision to call AI or handle deterministically.
"""

import logging
from typing import Tuple, Optional, Dict, Any
from app.router.intent_classifier import IntentClassifier, Intent
from app.ai.escalation import get_escalation_decision
from app.cache.cache_manager import CacheManager
from app.rate_limit.limiter import get_rate_limiter
from app.middleware.logging_metrics import get_metrics
from app.middleware.state_machine import get_state_machine

logger = logging.getLogger(__name__)


class IntentRouter:
    """Main routing engine that orchestrates all routing logic."""
    
    def __init__(self, cache_manager: Optional[CacheManager] = None):
        self.cache = cache_manager
        self.rate_limiter = get_rate_limiter()
        self.metrics = get_metrics()
        self.state_machine = get_state_machine()
    
    async def route(
        self,
        user_id: str,
        text: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[Intent, bool, str]:
        """
        Route a user message and determine next action.
        
        Args:
            user_id: Telegram user ID
            text: Message text
            context: Optional context dict (recent_messages, user_state, etc)
            
        Returns:
            (intent, should_call_ai, reason/handler_name)
        """
        context = context or {}
        text = text.strip()
        
        # Check rate limiting
        is_limited, reason = self.rate_limiter.is_rate_limited(user_id)
        if is_limited:
            self.metrics.record_rate_limit(user_id, reason)
            logger.warning(f"Rate limited user {user_id}: {reason}")
            return Intent.AMBIGUOUS, False, f"error:rate_limited:{reason}"
        
        # Record request
        if not self.rate_limiter.record_request(user_id):
            # Rate limit just hit
            self.metrics.record_rate_limit(user_id, "Request limit exceeded")
            return Intent.AMBIGUOUS, False, "error:rate_limited:Request limit exceeded"
        
        try:
            # Get escalation decision
            should_call_ai, intent, confidence, decision_reason = await get_escalation_decision(
                user_id, text, context
            )
            
            # Record metrics
            self.metrics.record_intent(intent.value, user_id, should_call_ai)
            
            if should_call_ai:
                logger.info(
                    f"Escalating to AI for user {user_id}: "
                    f"intent={intent}, confidence={confidence}, reason={decision_reason}"
                )
                return intent, True, f"escalate:{decision_reason}"
            else:
                # Get handler name
                handler_name = IntentClassifier.get_handler_name(intent)
                logger.info(
                    f"Routing to handler for user {user_id}: "
                    f"intent={intent}, handler={handler_name}, confidence={confidence}"
                )
                return intent, False, handler_name
        
        except Exception as e:
            logger.error(f"Error in routing for user {user_id}: {e}", exc_info=True)
            # Safe fallback: treat as conversational (call AI)
            return Intent.CONVERSATIONAL, True, f"error:routing_exception:{str(e)}"
    
    async def get_cached_response(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Try to get cached AI response."""
        if not self.cache:
            return None
        
        value = await self.cache.get(cache_key)
        if value:
            self.metrics.record_cache_hit(cache_key)
            logger.debug(f"Cache hit: {cache_key}")
        else:
            self.metrics.record_cache_miss(cache_key)
        
        return value
    
    async def cache_response(
        self,
        cache_key: str,
        response: Dict[str, Any],
        ttl_seconds: int = 300
    ):
        """Cache an AI response."""
        if self.cache:
            await self.cache.set(cache_key, response, ttl_seconds)
            logger.debug(f"Cached response: {cache_key} (ttl={ttl_seconds}s)")
    
    def get_intent_handler(self, intent: Intent) -> Optional[str]:
        """Get the handler function name for an intent."""
        return IntentClassifier.get_handler_name(intent)
    
    def get_metrics_summary(self) -> dict:
        """Get current metrics summary."""
        return self.metrics.get_summary()


# Global instance
_router: Optional[IntentRouter] = None


async def initialize_router(cache_manager: Optional[CacheManager] = None):
    """Initialize the global router."""
    global _router
    _router = IntentRouter(cache_manager)
    logger.info("Intent router initialized")


def get_router() -> IntentRouter:
    """Get the global router instance."""
    if _router is None:
        raise RuntimeError("Router not initialized. Call initialize_router() first.")
    return _router
