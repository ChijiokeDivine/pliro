"""
cache_manager.py - Caching layer for AI responses and frequently accessed data.
Supports both in-memory (fast, short-lived) and Redis (distributed, persistent).
"""

import json
import hashlib
import logging
import asyncio
from typing import Optional, Any, Dict
from datetime import datetime, timedelta
import aioredis
from collections import OrderedDict

logger = logging.getLogger(__name__)


class InMemoryCache:
    """Fast in-memory cache with TTL support and LRU eviction."""
    
    def __init__(self, max_size: int = 1000):
        self.cache: OrderedDict = OrderedDict()
        self.ttl_map: Dict[str, datetime] = {}
        self.max_size = max_size
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache if exists and not expired."""
        # Check expiration
        if key in self.ttl_map:
            if datetime.now() > self.ttl_map[key]:
                # Expired, remove it
                del self.cache[key]
                del self.ttl_map[key]
                return None
        
        value = self.cache.get(key)
        if value is not None:
            # Move to end (LRU)
            self.cache.move_to_end(key)
        return value
    
    async def set(self, key: str, value: Any, ttl_seconds: int = 300):
        """Set value in cache with TTL."""
        # Remove oldest if at capacity
        if len(self.cache) >= self.max_size and key not in self.cache:
            oldest_key, _ = self.cache.popitem(last=False)
            self.ttl_map.pop(oldest_key, None)
        
        self.cache[key] = value
        self.ttl_map[key] = datetime.now() + timedelta(seconds=ttl_seconds)
        self.cache.move_to_end(key)
    
    async def delete(self, key: str):
        """Delete value from cache."""
        self.cache.pop(key, None)
        self.ttl_map.pop(key, None)
    
    async def clear(self):
        """Clear all cache."""
        self.cache.clear()
        self.ttl_map.clear()
    
    async def cleanup_expired(self):
        """Remove expired entries (called periodically)."""
        now = datetime.now()
        expired_keys = [k for k, exp_time in self.ttl_map.items() if now > exp_time]
        for key in expired_keys:
            await self.delete(key)


class CacheManager:
    """Unified cache interface supporting in-memory and Redis."""
    
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url
        self.redis = None
        self.memory_cache = InMemoryCache()
        self._init_lock = asyncio.Lock()
    
    async def initialize(self):
        """Initialize Redis connection if configured."""
        if not self.redis_url:
            logger.info("No Redis URL provided, using in-memory cache only")
            return
        
        try:
            async with self._init_lock:
                if self.redis is None:
                    self.redis = await aioredis.from_url(
                        self.redis_url,
                        encoding="utf8",
                        decode_responses=True,
                        socket_connect_timeout=5,
                        socket_keepalive=True,
                    )
                    logger.info("Connected to Redis")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis, using in-memory cache: {e}")
            self.redis = None
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache (tries memory first, then Redis).
        Returns deserialized value.
        """
        # Try in-memory first (faster)
        value = await self.memory_cache.get(key)
        if value is not None:
            logger.debug(f"Cache hit (memory): {key}")
            return value
        
        # Try Redis
        if self.redis:
            try:
                value = await self.redis.get(key)
                if value:
                    logger.debug(f"Cache hit (redis): {key}")
                    # Deserialize and store in memory
                    deserialized = json.loads(value)
                    await self.memory_cache.set(key, deserialized, ttl_seconds=300)
                    return deserialized
            except Exception as e:
                logger.warning(f"Redis get error: {e}")
        
        logger.debug(f"Cache miss: {key}")
        return None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl_seconds: int = 300,
        redis_ttl: Optional[int] = None
    ):
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
            ttl_seconds: TTL for in-memory cache
            redis_ttl: TTL for Redis (defaults to ttl_seconds if not specified)
        """
        # Store in memory
        await self.memory_cache.set(key, value, ttl_seconds)
        
        # Store in Redis if available
        if self.redis:
            try:
                redis_ttl = redis_ttl or ttl_seconds
                serialized = json.dumps(value)
                await self.redis.setex(key, redis_ttl, serialized)
                logger.debug(f"Cached to redis: {key} (ttl={redis_ttl}s)")
            except Exception as e:
                logger.warning(f"Redis set error: {e}")
    
    async def delete(self, key: str):
        """Delete value from cache."""
        await self.memory_cache.delete(key)
        if self.redis:
            try:
                await self.redis.delete(key)
            except Exception as e:
                logger.warning(f"Redis delete error: {e}")
    
    async def clear(self):
        """Clear all cache."""
        await self.memory_cache.clear()
        if self.redis:
            try:
                await self.redis.flushdb()
            except Exception as e:
                logger.warning(f"Redis flush error: {e}")
    
    @staticmethod
    def make_key(prefix: str, *parts) -> str:
        """Generate cache key from prefix and parts."""
        key_parts = [prefix] + [str(p) for p in parts]
        return ":".join(key_parts)
    
    @staticmethod
    def make_hash_key(prefix: str, data: dict) -> str:
        """Generate cache key by hashing dict data."""
        data_str = json.dumps(data, sort_keys=True)
        data_hash = hashlib.md5(data_str.encode()).hexdigest()[:8]
        return f"{prefix}:{data_hash}"


# Global cache instance
_cache_instance: Optional[CacheManager] = None


async def get_cache_manager(redis_url: Optional[str] = None) -> CacheManager:
    """Get or create global cache manager instance."""
    global _cache_instance
    
    if _cache_instance is None:
        _cache_instance = CacheManager(redis_url)
        await _cache_instance.initialize()
    
    return _cache_instance
