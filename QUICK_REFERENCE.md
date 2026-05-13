"""
QUICK_REFERENCE.md - Quick copy-paste examples for common patterns.
"""

# Quick Reference - Copy-Paste Examples

## 1. Basic Routing

### Check if user needs AI

```python
from app.bot.routing_integration import RoutingIntegration

intent, should_call_ai, reason = await RoutingIntegration.route_message(
    user_id="123456",
    text="What's my balance?"
)

print(should_call_ai)  # False - can handle deterministically
print(reason)  # "handle_balance"
```

## 2. Rate Limiting

### Check and record request

```python
from app.rate_limit.limiter import get_rate_limiter

limiter = get_rate_limiter()

# Check if limited
is_limited, reason = limiter.is_rate_limited("user123")
if is_limited:
    return f"Too many requests: {reason}"

# Record request
if not limiter.record_request("user123"):
    # Hit rate limit
    limiter.apply_cooldown("user123", "Rate limited", seconds=60)
```

## 3. Caching

### Cache and retrieve responses

```python
from app.cache.cache_manager import get_cache_manager

cache = await get_cache_manager()

# Try to get from cache
cached = await cache.get("faq:what_is_solana")
if cached:
    return cached["response"]

# Generate response
response = "Solana is a blockchain..."

# Cache for 1 hour
await cache.set("faq:what_is_solana", {"response": response}, ttl_seconds=3600)
```

## 4. Multi-Step Flows

### Send transaction flow

```python
from app.bot.routing_integration import RoutingIntegration

# Start flow
RoutingIntegration.start_send_flow(
    user_id="123456",
    to_address="0x123...",
    amount="0.01",
    token="ETH",
    chain="ethereum"
)

# Later: confirm
send_data = RoutingIntegration.confirm_send("123456")
if send_data:
    # Execute send
    tx_hash = await send_crypto(send_data)
    RoutingIntegration.end_flow("123456")
```

## 5. Metrics

### Track and report

```python
from app.middleware.logging_metrics import get_metrics

metrics = get_metrics()

# Record an interaction
metrics.record_intent(
    intent="balance",
    user_id="user123",
    used_ai=False  # Handled deterministically
)

# Get summary
summary = metrics.get_summary()
print(f"AI Reduction: {summary['ai_reduction_percent']}")
print(f"Cache Hit Rate: {summary['cache_hit_rate']}")

# Log to file
metrics.log_summary()
```

## 6. Pattern Matching

### Check if text matches a pattern

```python
from app.router.patterns import match_intent_pattern, extract_send_command

# Check pattern
if match_intent_pattern("Show my balance", "BALANCE_PATTERNS"):
    print("Balance query detected")

# Extract send command
result = extract_send_command("Send 0.01 ETH to 0xABC123...")
if result:
    amount, token, chain, address = result
    print(f"Send {amount} {token} on {chain} to {address}")
```

## 7. State Machine

### Manage conversation state

```python
from app.middleware.state_machine import get_state_machine, FlowState

sm = get_state_machine()

# Start flow
flow = sm.start_flow("user123", "swap")

# Transition
sm.transition("user123", FlowState.SWAP_INPUT_TOKEN, input_token="ETH")
sm.transition("user123", FlowState.SWAP_OUTPUT_TOKEN, output_token="USDC")

# Get context
flow_data = sm.get_swap_context("user123")

# End flow
sm.end_flow("user123")
```

## 8. Handler Template

### Create a new deterministic handler

```python
async def handle_my_feature(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Handle my_feature intent without calling AI."""
    user_id = str(update.effective_user.id)
    
    try:
        # Get data from database/API
        data = await fetch_my_feature_data(user_id)
        
        # Format response
        response = format_my_feature_response(data)
        
        # Log metrics
        get_metrics().record_intent("my_feature", user_id, used_ai=False)
        
        return response
    
    except Exception as e:
        logger.error(f"Feature error: {e}")
        return format_error(str(e))


# Register in intent classifier
class IntentClassifier:
    @staticmethod
    def classify(text):
        # ...
        if match_intent_pattern(text, "MY_FEATURE_PATTERNS"):
            scores[Intent.MY_FEATURE] = 0.85
```

## 9. Error Handling

### Graceful fallback to AI

```python
try:
    intent, should_call_ai, result = await router.route(user_id, text)
    
    if not should_call_ai:
        response = await deterministic_handler()
    else:
        response = await run_agent(text, user_id)

except Exception as e:
    logger.error(f"Routing error: {e}")
    # Fallback: call AI
    response = await run_agent(text, user_id)
```

## 10. Monitoring Query

### Get statistics

```python
from app.middleware.logging_metrics import get_metrics

metrics = get_metrics()

# Overall
print(metrics.get_summary())

# By intent
print(metrics.get_intent_stats())

# By user
print(metrics.get_user_stats("user123"))
```

## 11. Cache Key Generation

### Consistent cache keys

```python
from app.cache.cache_manager import CacheManager

cache = await get_cache_manager()

# Simple key
key1 = cache.make_key("faq", "what_is_crypto")
# Result: "faq:what_is_crypto"

# Hash-based key for large data
data = {"balance": 1000, "user": "alice"}
key2 = cache.make_hash_key("balance_summary", data)
# Result: "balance_summary:a3f5e2c1"
```

## 12. Add New Intent

### Complete example

```python
# 1. Add pattern (app/router/patterns.py)
class IntentPatterns:
    CUSTOM_PATTERNS = [
        r"custom command",
        r"(?:show|list).*custom",
        r"🎯",
    ]

# 2. Add intent (app/router/patterns.py)
class Intent(str, Enum):
    CUSTOM = "custom"

# 3. Update classifier (app/router/intent_classifier.py)
class IntentClassifier:
    COMMAND_TO_INTENT = {
        ...
        "custom": Intent.CUSTOM,
    }
    
    @staticmethod
    def classify(text):
        if match_intent_pattern(text, "CUSTOM_PATTERNS"):
            scores[Intent.CUSTOM] = 0.85

# 4. Create handler (app/bot/handlers.py)
async def handle_custom(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Handle custom intent."""
    return "Custom response"

# 5. Register in handler map
handler_map = {
    ...
    "handle_custom": handle_custom,
}

# Done! No AI needed.
```

## 13. Debug Intent Classification

### Test intent detection

```python
from app.router.intent_classifier import IntentClassifier, Intent

test_messages = [
    "What's my balance?",
    "Show portfolio",
    "Send 0.01 ETH to 0x...",
    "Tell me a joke",
    "How do I swap tokens?",
]

for msg in test_messages:
    intent, conf = IntentClassifier.classify(msg)
    skip_ai = IntentClassifier.should_skip_ai(intent, conf)
    
    print(f"'{msg}'")
    print(f"  Intent: {intent}, Confidence: {conf}")
    print(f"  Skip AI: {skip_ai}")
    print()
```

## 14. Rate Limit Testing

### Simulate rate limit

```python
from app.rate_limit.limiter import get_rate_limiter

limiter = get_rate_limiter()
user = "test_user"

# Generate 15 requests
for i in range(15):
    allowed = limiter.record_request(user)
    is_limited, reason = limiter.is_rate_limited(user)
    
    print(f"Request {i+1}: {'✅' if allowed else '❌'}")
    if is_limited:
        print(f"  Limited: {reason}")
```

## 15. Cache Performance Test

### Measure cache effectiveness

```python
import time
from app.cache.cache_manager import get_cache_manager

cache = await get_cache_manager()

# Warm up cache
for i in range(100):
    await cache.set(f"key_{i % 10}", {"data": f"value_{i}"}, ttl_seconds=60)

# Measure hit rate
start = time.time()
for i in range(1000):
    await cache.get(f"key_{i % 10}")
elapsed = time.time() - start

metrics = get_metrics()
hit_rate = metrics.cache_hits / (metrics.cache_hits + metrics.cache_misses)

print(f"1000 cache accesses in {elapsed:.2f}s")
print(f"Cache hit rate: {hit_rate*100:.1f}%")
```

---

## Common Issues & Solutions

### Issue: Pattern not matching

```python
# Debug
from app.router.patterns import COMPILED_PATTERNS

text = "show my tokens"
for pattern_name, pattern_obj in COMPILED_PATTERNS.items():
    if pattern_obj.search(text):
        print(f"Matched: {pattern_name}")
```

### Issue: AI being called too much

```python
# Find problematic intents
metrics = get_metrics()
for intent, stat in metrics.get_intent_stats().items():
    reduction = float(stat['ai_reduction_percent'].rstrip('%'))
    if reduction < 70:
        print(f"⚠️ Add pattern for: {intent}")
```

### Issue: Cache not working

```python
# Check cache availability
cache = await get_cache_manager()
print(f"Redis available: {cache.redis is not None}")

# Test manual set/get
await cache.set("test", {"data": "test"})
result = await cache.get("test")
print(f"Cache working: {result is not None}")
```

---

## Performance Tips

1. **Set realistic TTLs**
   - FAQ: 3600s (1 hour)
   - Portfolio: 300s (5 min)
   - AI responses: 600s (10 min)

2. **Use in-memory cache for hot data**
   - Frequently accessed FAQs
   - Recent user queries
   - Session state

3. **Monitor metrics regularly**
   - Target: 80-90% AI reduction
   - Target: 40-60% cache hit rate
   - Low target: <1% rate limit events

4. **Add patterns aggressively**
   - Every new query type → add pattern
   - Avoid AI for predictable requests

5. **Set reasonable rate limits**
   - 5 AI calls/min is reasonable
   - 10 general requests/min is generous
   - Adjust based on user behavior

---

## Quick Deployment Checklist

- [ ] `pip install aioredis`
- [ ] Update config.py with settings
- [ ] Initialize router in main.py
- [ ] Update handle_message() with routing
- [ ] Create deterministic handlers
- [ ] Test: `/balance`, `/send`, `/swap`
- [ ] Check metrics: `/api/v1/metrics`
- [ ] Verify AI reduction ≥ 80%
- [ ] Deploy to production
- [ ] Monitor metrics every hour

**Time to deploy: ~2 hours**
**Expected AI reduction: 80-90%**
**Expected cost reduction: 80-90%**
