"""
patterns.py - Regex patterns and keyword matching for intent classification.
These patterns are used to identify user intent WITHOUT calling the AI agent.
"""

import re
from enum import Enum
from typing import List, Tuple

class Intent(str, Enum):
    """All possible intents that don't require AI."""
    
    # Navigation
    START = "start"
    MENU = "menu"
    HELP = "help"
    SETTINGS = "settings"
    
    # Wallet queries
    BALANCE = "balance"
    PORTFOLIO = "portfolio"
    ADDRESSES = "addresses"
    TOKENS = "tokens"
    TRANSACTIONS = "transactions"
    HISTORY = "history"
    
    # Actions
    SEND = "send"
    RECEIVE = "receive"
    SWAP = "swap"
    
    # Confirmations
    CONFIRM = "confirm"
    CANCEL = "cancel"
    
    # Generic fallback
    CONVERSATIONAL = "conversational"  # Needs AI
    AMBIGUOUS = "ambiguous"            # Needs AI


class IntentPatterns:
    """Regex patterns for intent matching."""
    
    # Balance/Portfolio queries
    BALANCE_PATTERNS = [
        r"balance",
        r"portfolio",
        r"worth",
        r"value",
        r"how much",
        r"total.*holdings",
        r"net worth",
        r"💼",
    ]
    
    # Token/Holdings queries
    TOKENS_PATTERNS = [
        r"tokens",
        r"holdings",
        r"(?:show|list).*tokens",
        r"what.*(?:holding|own)",
        r"coin balance",
        r"asset",
        r"🪙",
        r"get_tokens",
    ]
    
    # Address queries
    ADDRESSES_PATTERNS = [
        r"address(?:es)?",
        r"wallet.*address",
        r"my.*wallet",
        r"receive.*address",
        r"where.*send",
        r"📬",
        r"public.*key",
    ]
    
    # Transaction history
    HISTORY_PATTERNS = [
        r"transaction",
        r"history",
        r"recent.*(?:tx|transactions)",
        r"past.*(?:activity|transaction)",
        r"📜",
    ]
    
    # Send crypto
    SEND_PATTERNS = [
        r"send\s+([\d.]+)\s+(\w+)(?:\s+(?:on|to|@))?\s+(0x[a-fA-F0-9]{40})",
        r"send.*to.*address",
        r"📤",
    ]
    
    # Receive
    RECEIVE_PATTERNS = [
        r"receive",
        r"deposit",
        r"fund.*(?:address|wallet)",
        r"how.*(?:send|receive)",
        r"📥",
    ]
    
    # Swap
    SWAP_PATTERNS = [
        r"swap",
        r"exchange",
        r"trade",
        r"convert",
        r"💱",
    ]
    
    # Help/FAQ
    HELP_PATTERNS = [
        r"help",
        r"how.*(?:do|to|does)",
        r"(?:what|where|when|why|which).*(?:is|are|can)",
        r"explain",
        r"guide",
        r"faq",
        r"(?:don't|do not|can't|cannot).*(?:understand|work)",
    ]
    
    # Settings
    SETTINGS_PATTERNS = [
        r"setting",
        r"preference",
        r"configure",
        r"language",
        r"notification",
    ]
    
    # Confirmations
    CONFIRM_PATTERNS = [
        r"^(?:yes|✅|confirm|ok|okay|sure|go|proceed)$",
        r"^✅\s",
    ]
    
    CANCEL_PATTERNS = [
        r"^(?:no|❌|cancel|abort|stop|dont|nope)$",
        r"^❌\s",
    ]
    
    # Greetings
    GREETING_PATTERNS = [
        r"^(?:hi|hello|hey|greetings|sup|wassup)(?:\s|$|!|\?)",
        r"^👋",
    ]
    
    @classmethod
    def compile_patterns(cls) -> dict:
        """Compile all patterns into regex objects for faster matching."""
        patterns = {}
        for attr_name in dir(cls):
            if attr_name.endswith("_PATTERNS") and not attr_name.startswith("_"):
                pattern_list = getattr(cls, attr_name)
                if isinstance(pattern_list, list):
                    # Combine patterns with OR, make case-insensitive
                    combined = "|".join(f"(?:{p})" for p in pattern_list)
                    patterns[attr_name] = re.compile(combined, re.IGNORECASE)
        return patterns


# Pre-compiled patterns for performance
COMPILED_PATTERNS = IntentPatterns.compile_patterns()


def match_intent_pattern(text: str, pattern_name: str) -> bool:
    """Check if text matches a specific pattern."""
    pattern = COMPILED_PATTERNS.get(pattern_name)
    if pattern:
        return bool(pattern.search(text))
    return False


def extract_send_command(text: str) -> Tuple[str, str, str, str] | None:
    """Extract send command components: amount, token, chain, address."""
    pattern = re.compile(
        r"send\s+([\d.]+)\s+(\w+)(?:\s+on\s+(\w+))?\s+to\s+(0x[a-fA-F0-9]{40})",
        re.IGNORECASE
    )
    match = pattern.search(text)
    if match:
        amount, token, chain, address = match.groups()
        return amount, token, chain or "ethereum", address
    return None


def keyword_search(text: str, keywords: List[str]) -> bool:
    """Check if text contains any keywords."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)
