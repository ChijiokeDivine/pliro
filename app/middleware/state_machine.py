"""
state_machine.py - Conversation state machine for multi-step flows.
Handles stateful interactions like sending crypto, swapping, etc.
WITHOUT using AI for state management.
"""

import logging
import json
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class FlowState(str, Enum):
    """States in multi-step flows."""
    
    # Send flow
    SEND_INITIAL = "send_initial"
    SEND_PREVIEW = "send_preview"
    SEND_CONFIRM = "send_confirm"
    
    # Swap flow
    SWAP_INPUT_TOKEN = "swap_input_token"
    SWAP_OUTPUT_TOKEN = "swap_output_token"
    SWAP_AMOUNT = "swap_amount"
    SWAP_PREVIEW = "swap_preview"
    SWAP_CONFIRM = "swap_confirm"
    
    # Receive flow
    RECEIVE_CHAIN_SELECT = "receive_chain_select"
    RECEIVE_DISPLAY = "receive_display"
    
    # General
    IDLE = "idle"


class FlowContext:
    """Holds context for a multi-step flow."""
    
    def __init__(self, user_id: str, flow_type: str):
        self.user_id = user_id
        self.flow_type = flow_type  # 'send', 'swap', 'receive'
        self.state = FlowState.IDLE
        self.data: Dict[str, Any] = {}
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.timeout_seconds = 300  # 5 minutes
    
    def update(self, **kwargs):
        """Update flow data."""
        self.data.update(kwargs)
        self.last_activity = datetime.now()
    
    def is_expired(self) -> bool:
        """Check if flow session has expired."""
        age = (datetime.now() - self.last_activity).total_seconds()
        return age > self.timeout_seconds
    
    def to_dict(self) -> dict:
        """Serialize to dict for Redis storage."""
        return {
            "user_id": self.user_id,
            "flow_type": self.flow_type,
            "state": self.state.value if isinstance(self.state, FlowState) else self.state,
            "data": self.data,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "FlowContext":
        """Deserialize from dict."""
        ctx = cls(data["user_id"], data["flow_type"])
        ctx.state = FlowState(data["state"])
        ctx.data = data["data"]
        ctx.created_at = datetime.fromisoformat(data["created_at"])
        ctx.last_activity = datetime.fromisoformat(data["last_activity"])
        return ctx


class StateMachine:
    """Manages conversation state for multi-step flows."""
    
    def __init__(self):
        # user_id -> FlowContext
        self.flows: Dict[str, FlowContext] = {}
    
    def get_flow(self, user_id: str) -> Optional[FlowContext]:
        """Get user's current flow context."""
        ctx = self.flows.get(user_id)
        
        # Check expiration
        if ctx and ctx.is_expired():
            logger.warning(f"Flow expired for user {user_id}: {ctx.flow_type}")
            del self.flows[user_id]
            return None
        
        return ctx
    
    def start_flow(self, user_id: str, flow_type: str) -> FlowContext:
        """Start a new flow."""
        # End previous flow if exists
        if user_id in self.flows:
            logger.info(f"Ending previous flow for user {user_id}")
        
        ctx = FlowContext(user_id, flow_type)
        self.flows[user_id] = ctx
        logger.info(f"Flow started for user {user_id}: {flow_type}")
        return ctx
    
    def transition(self, user_id: str, new_state: FlowState, **data) -> FlowContext:
        """Transition to a new state."""
        ctx = self.get_flow(user_id)
        if not ctx:
            raise ValueError(f"No active flow for user {user_id}")
        
        old_state = ctx.state
        ctx.state = new_state
        ctx.update(**data)
        
        logger.debug(
            f"Flow transition for user {user_id}: "
            f"{old_state.value if isinstance(old_state, FlowState) else old_state} "
            f"-> {new_state.value}"
        )
        
        return ctx
    
    def end_flow(self, user_id: str) -> Optional[FlowContext]:
        """End a flow."""
        ctx = self.flows.pop(user_id, None)
        if ctx:
            logger.info(f"Flow ended for user {user_id}: {ctx.flow_type}")
        return ctx
    
    def get_send_context(self, user_id: str) -> Optional[dict]:
        """Get send confirmation data."""
        ctx = self.get_flow(user_id)
        if ctx and ctx.flow_type == "send" and ctx.state == FlowState.SEND_PREVIEW:
            return ctx.data
        return None
    
    def get_swap_context(self, user_id: str) -> Optional[dict]:
        """Get swap confirmation data."""
        ctx = self.get_flow(user_id)
        if ctx and ctx.flow_type == "swap" and ctx.state == FlowState.SWAP_PREVIEW:
            return ctx.data
        return None
    
    def cleanup_expired(self):
        """Remove expired flows."""
        expired_users = [
            uid for uid, ctx in self.flows.items()
            if ctx.is_expired()
        ]
        for uid in expired_users:
            self.end_flow(uid)
        
        if expired_users:
            logger.info(f"Cleaned up {len(expired_users)} expired flows")


# Global instance
_state_machine = StateMachine()


def get_state_machine() -> StateMachine:
    """Get global state machine."""
    return _state_machine
