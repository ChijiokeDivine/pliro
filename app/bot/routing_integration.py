"""
routing_integration.py - Integration layer between router and Telegram handlers.
Connects intent routing to command execution.
"""

import logging
from typing import Optional, Dict, Any
from telegram import Update
from telegram.ext import ContextTypes

from app.router.intent_router import get_router
from app.router.intent_classifier import Intent
from app.middleware.state_machine import get_state_machine, FlowState
from app.cache.cache_manager import get_cache_manager
from app.rate_limit.limiter import get_rate_limiter

logger = logging.getLogger(__name__)


class RoutingIntegration:
    """Bridges router decisions to Telegram handlers."""
    
    @staticmethod
    async def build_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Dict[str, Any]:
        """Build context dict for routing."""
        user_id = str(update.effective_user.id)
        chat_history = context.user_data.get("chat_history", [])
        
        return {
            "user_id": user_id,
            "recent_messages": [msg.get("text", "") for msg in chat_history[-5:]],
            "user_state": context.user_data,
            "has_active_flow": get_state_machine().get_flow(user_id) is not None,
        }
    
    @staticmethod
    async def route_message(
        user_id: str,
        text: str,
        context: Optional[Dict[str, Any]] = None
    ) -> tuple:
        """
        Route a message through the intent system.
        
        Returns:
            (intent, should_call_ai, handler_name_or_error)
        """
        router = get_router()
        intent, should_call_ai, reason = await router.route(user_id, text, context)
        
        return intent, should_call_ai, reason
    
    @staticmethod
    def get_active_flow(user_id: str) -> Optional[Dict[str, Any]]:
        """Get current flow context for user."""
        state_machine = get_state_machine()
        flow = state_machine.get_flow(user_id)
        return flow.to_dict() if flow else None
    
    @staticmethod
    def start_send_flow(
        user_id: str,
        to_address: str,
        amount: str,
        token: str,
        chain: str
    ) -> Dict[str, Any]:
        """Start a send transaction flow."""
        state_machine = get_state_machine()
        flow = state_machine.start_flow(user_id, "send")
        flow.state = FlowState.SEND_PREVIEW
        flow.update(
            to_address=to_address,
            amount=amount,
            token=token,
            chain=chain,
        )
        return flow.to_dict()
    
    @staticmethod
    def start_swap_flow(user_id: str) -> Dict[str, Any]:
        """Start a swap flow."""
        state_machine = get_state_machine()
        flow = state_machine.start_flow(user_id, "swap")
        flow.state = FlowState.SWAP_INPUT_TOKEN
        return flow.to_dict()
    
    @staticmethod
    def end_flow(user_id: str) -> bool:
        """End current flow for user."""
        state_machine = get_state_machine()
        flow = state_machine.end_flow(user_id)
        return flow is not None
    
    @staticmethod
    def confirm_send(user_id: str) -> Optional[Dict[str, Any]]:
        """Get send confirmation data."""
        state_machine = get_state_machine()
        return state_machine.get_send_context(user_id)
    
    @staticmethod
    def confirm_swap(user_id: str) -> Optional[Dict[str, Any]]:
        """Get swap confirmation data."""
        state_machine = get_state_machine()
        return state_machine.get_swap_context(user_id)
    
    @staticmethod
    async def check_rate_limit(user_id: str) -> tuple:
        """Check rate limit for user."""
        limiter = get_rate_limiter()
        return limiter.is_rate_limited(user_id)
    
    @staticmethod
    async def cache_ai_response(
        user_id: str,
        prompt_hash: str,
        response: str,
        ttl_seconds: int = 600
    ):
        """Cache an AI response."""
        cache = await get_cache_manager()
        cache_key = f"ai_response:{user_id}:{prompt_hash}"
        await cache.set(cache_key, {"response": response}, ttl_seconds)
    
    @staticmethod
    async def get_cached_ai_response(user_id: str, prompt_hash: str) -> Optional[str]:
        """Get cached AI response."""
        cache = await get_cache_manager()
        cache_key = f"ai_response:{user_id}:{prompt_hash}"
        cached = await cache.get(cache_key)
        return cached.get("response") if cached else None


# Convenience functions for handlers
async def should_handle_deterministically(user_id: str, text: str) -> bool:
    """Check if message can be handled without AI."""
    intent, should_call_ai, _ = await RoutingIntegration.route_message(user_id, text)
    return not should_call_ai


async def needs_ai(user_id: str, text: str) -> bool:
    """Check if message needs AI."""
    intent, should_call_ai, _ = await RoutingIntegration.route_message(user_id, text)
    return should_call_ai


def get_send_confirmation(user_id: str) -> Optional[Dict[str, Any]]:
    """Get pending send confirmation data."""
    return RoutingIntegration.confirm_send(user_id)


def get_swap_confirmation(user_id: str) -> Optional[Dict[str, Any]]:
    """Get pending swap confirmation data."""
    return RoutingIntegration.confirm_swap(user_id)
