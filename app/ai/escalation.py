"""
ai_escalation.py - Logic for deciding whether to escalate to AI.
Reduces unnecessary AI calls through intelligent routing.
"""

import logging
from typing import Tuple
from app.router.intent_classifier import IntentClassifier, Intent
from app.rate_limit.limiter import get_ai_throttler

logger = logging.getLogger(__name__)


class AIEscalationManager:
    """Manages AI escalation decisions."""
    
    def __init__(self):
        self.throttler = get_ai_throttler()
    
    async def should_call_ai(
        self,
        user_id: str,
        text: str,
        intent: Intent,
        confidence: float,
        context: dict = None
    ) -> Tuple[bool, str]:
        """
        Decide whether to call AI for this request.
        
        Args:
            user_id: User ID
            text: Message text
            intent: Classified intent
            confidence: Confidence score 0.0-1.0
            context: Optional context dict
            
        Returns:
            (should_call_ai, reason_or_error)
        """
        context = context or {}
        
        # Check if intent handler exists (can be handled deterministically)
        if IntentClassifier.should_skip_ai(intent, confidence):
            logger.debug(f"Skipping AI for user {user_id}: intent={intent}, confidence={confidence}")
            return False, f"Handled deterministically: {intent}"
        
        # Check AI rate limits
        can_call, reason = self.throttler.can_call_ai(user_id)
        if not can_call:
            logger.warning(f"AI rate limit for user {user_id}: {reason}")
            return False, reason
        
        # Check for debouncing (too similar to recent message)
        recent_messages = context.get("recent_messages", [])
        if self._is_duplicate_request(text, recent_messages):
            logger.debug(f"Debouncing duplicate request from user {user_id}")
            return False, "Similar request made recently"
        
        # This should call AI
        return True, "Conversational/ambiguous intent requires AI"
    
    @staticmethod
    def _is_duplicate_request(text: str, recent_messages: list) -> bool:
        """Check if message is too similar to recent messages."""
        if not recent_messages:
            return False
        
        # Simple similarity check: if message is shorter than 30 chars
        # and matches a recent message exactly, it's a duplicate
        if len(text) < 30:
            text_lower = text.lower().strip()
            for msg in recent_messages[-5:]:  # Check last 5 messages
                if msg.lower().strip() == text_lower:
                    return True
        
        return False
    
    def record_ai_call(self, user_id: str):
        """Record that AI was called."""
        self.throttler.record_ai_call(user_id)
    
    def get_ai_stats(self, user_id: str) -> dict:
        """Get AI usage statistics for a user."""
        return self.throttler.get_stats(user_id)


# Global instance
_escalation_manager = AIEscalationManager()


async def get_escalation_decision(
    user_id: str,
    text: str,
    context: dict = None
) -> Tuple[bool, Intent, float, str]:
    """
    Complete escalation decision pipeline.
    
    Returns:
        (should_call_ai, intent, confidence, reason)
    """
    context = context or {}
    
    # Step 1: Classify intent
    intent, confidence = IntentClassifier.classify(text, context)
    logger.debug(f"User {user_id}: intent={intent}, confidence={confidence}")
    
    # Step 2: Decide escalation
    should_escalate, reason = await _escalation_manager.should_call_ai(
        user_id, text, intent, confidence, context
    )
    
    return should_escalate, intent, confidence, reason
