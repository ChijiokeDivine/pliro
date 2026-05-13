"""
intent_classifier.py - Intent classification with confidence scoring.
Determines whether to handle request deterministically or escalate to AI.
"""

import logging
from typing import Tuple, Optional
from app.router.patterns import (
    Intent, 
    COMPILED_PATTERNS, 
    match_intent_pattern, 
    extract_send_command,
    keyword_search
)

logger = logging.getLogger(__name__)


class IntentClassifier:
    """Classifies user messages into intents with confidence scores."""
    
    # Confidence thresholds
    MIN_CONFIDENCE_FOR_DETERMINISTIC = 0.7  # Must be ≥ this to skip AI
    MIN_MESSAGE_LENGTH_FOR_CONVERSATIONAL = 15  # Shorter messages are likely simple commands
    
    # High-confidence intent mappings
    COMMAND_TO_INTENT = {
        "start": Intent.START,
        "menu": Intent.MENU,
        "help": Intent.HELP,
        "settings": Intent.SETTINGS,
        "balance": Intent.BALANCE,
        "addresses": Intent.ADDRESSES,
        "get_tokens": Intent.TOKENS,
        "transactions": Intent.TRANSACTIONS,
        "send": Intent.SEND,
        "receive": Intent.RECEIVE,
        "swap": Intent.SWAP,
    }
    
    # Button text to intent
    BUTTON_TO_INTENT = {
        "💼 balance": Intent.BALANCE,
        "🪙 tokens": Intent.TOKENS,
        "📬 addresses": Intent.ADDRESSES,
        "📜 history": Intent.HISTORY,
        "📤 send": Intent.SEND,
        "📥 receive": Intent.RECEIVE,
        "💱 swap": Intent.SWAP,
        "⛽ gas": Intent.BALANCE,  # Gas is related to portfolio
        "🏠 main menu": Intent.MENU,
    }
    
    @staticmethod
    def classify(text: str, context: dict = None) -> Tuple[Intent, float]:
        """
        Classify user message and return intent with confidence score.
        
        Args:
            text: User message text
            context: Optional context dict with user_state, chat_history, etc
            
        Returns:
            Tuple of (Intent, confidence_score 0.0-1.0)
        """
        context = context or {}
        text = text.strip()
        
        # Empty message
        if not text:
            return Intent.AMBIGUOUS, 0.0
        
        # Check for slash commands first (highest priority)
        if text.startswith("/"):
            command = text[1:].split()[0].lower()
            if command in IntentClassifier.COMMAND_TO_INTENT:
                return IntentClassifier.COMMAND_TO_INTENT[command], 1.0
        
        # Check for button presses (text matches button emojis)
        text_lower = text.lower().strip()
        if text_lower in IntentClassifier.BUTTON_TO_INTENT:
            return IntentClassifier.BUTTON_TO_INTENT[text_lower], 1.0
        
        # Check for confirmations (very high confidence)
        if match_intent_pattern(text, "CONFIRM_PATTERNS"):
            return Intent.CONFIRM, 0.95
        if match_intent_pattern(text, "CANCEL_PATTERNS"):
            return Intent.CANCEL, 0.95
        
        # Check for send command pattern (0x address is very specific)
        if extract_send_command(text):
            return Intent.SEND, 0.95
        
        # Check for greetings (high confidence, but low importance)
        if match_intent_pattern(text, "GREETING_PATTERNS"):
            return Intent.CONVERSATIONAL, 0.5  # Allow AI to be friendly
        
        # Check other intent patterns with confidence scoring
        scores = {}
        
        if match_intent_pattern(text, "BALANCE_PATTERNS"):
            scores[Intent.BALANCE] = 0.8
        
        if match_intent_pattern(text, "TOKENS_PATTERNS"):
            scores[Intent.TOKENS] = 0.8
        
        if match_intent_pattern(text, "ADDRESSES_PATTERNS"):
            scores[Intent.ADDRESSES] = 0.8
        
        if match_intent_pattern(text, "HISTORY_PATTERNS"):
            scores[Intent.HISTORY] = 0.8
        
        if match_intent_pattern(text, "RECEIVE_PATTERNS"):
            scores[Intent.RECEIVE] = 0.8
        
        if match_intent_pattern(text, "SWAP_PATTERNS"):
            scores[Intent.SWAP] = 0.75  # Lower confidence, might be conversational
        
        if match_intent_pattern(text, "HELP_PATTERNS"):
            scores[Intent.HELP] = 0.7
        
        if match_intent_pattern(text, "SETTINGS_PATTERNS"):
            scores[Intent.SETTINGS] = 0.8
        
        # Return highest scoring intent
        if scores:
            best_intent = max(scores, key=scores.get)
            best_score = scores[best_intent]
            
            # If multiple high-confidence matches, escalate to AI
            high_confidence_intents = [i for i, s in scores.items() if s >= 0.75]
            if len(high_confidence_intents) > 1:
                # Multiple matching intents = ambiguous
                return Intent.AMBIGUOUS, max(scores.values()) - 0.2
            
            return best_intent, best_score
        
        # Default: treat as conversational (needs AI)
        # But short messages are usually simple requests
        if len(text) < IntentClassifier.MIN_MESSAGE_LENGTH_FOR_CONVERSATIONAL:
            # Short message with no pattern match = likely a command we don't recognize
            return Intent.AMBIGUOUS, 0.3
        
        return Intent.CONVERSATIONAL, 0.4
    
    @staticmethod
    def should_skip_ai(intent: Intent, confidence: float) -> bool:
        """
        Determine if we should handle this intent WITHOUT calling AI.
        
        Args:
            intent: Classified intent
            confidence: Confidence score 0.0-1.0
            
        Returns:
            True if we can handle deterministically, False if we should call AI
        """
        # Always skip AI for these high-confidence intents
        deterministic_intents = {
            Intent.START,
            Intent.MENU,
            Intent.BALANCE,
            Intent.ADDRESSES,
            Intent.TOKENS,
            Intent.HISTORY,
            Intent.TRANSACTIONS,
            Intent.SEND,
            Intent.RECEIVE,
            Intent.SWAP,
            Intent.CONFIRM,
            Intent.CANCEL,
            Intent.SETTINGS,
        }
        
        if intent in deterministic_intents:
            return confidence >= IntentClassifier.MIN_CONFIDENCE_FOR_DETERMINISTIC
        
        # For conversational/ambiguous, always call AI
        return False
    
    @staticmethod
    def get_handler_name(intent: Intent) -> str:
        """Get the handler function name for an intent."""
        handler_map = {
            Intent.START: "handle_start",
            Intent.MENU: "handle_menu",
            Intent.HELP: "handle_help",
            Intent.SETTINGS: "handle_settings",
            Intent.BALANCE: "handle_balance",
            Intent.ADDRESSES: "handle_addresses",
            Intent.TOKENS: "handle_tokens",
            Intent.HISTORY: "handle_history",
            Intent.TRANSACTIONS: "handle_transactions",
            Intent.SEND: "handle_send",
            Intent.RECEIVE: "handle_receive",
            Intent.SWAP: "handle_swap",
            Intent.CONFIRM: "handle_confirm",
            Intent.CANCEL: "handle_cancel",
            Intent.CONVERSATIONAL: "handle_conversational",
            Intent.AMBIGUOUS: "handle_conversational",  # Fallback to AI
        }
        return handler_map.get(intent, "handle_conversational")
