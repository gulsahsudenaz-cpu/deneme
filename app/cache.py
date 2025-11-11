import time
import json
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from app.config import settings
from app.redis_client import redis_client
from app.logger import logger

class HybridCache:
    """Hybrid cache with Redis and in-memory fallback"""
    def __init__(self):
        self._memory_cache: Dict[str, tuple[Any, datetime]] = {}
        self._max_size: int = settings.CACHE_MAX_SIZE
        # Note: redis_client.client will be None until Redis is connected
        # We'll check if Redis is enabled in get/set methods
        self._use_redis = False
    
    def _check_redis(self):
        """Check if Redis is available and update flag"""
        if redis_client.enabled and redis_client.client:
            self._use_redis = True
        else:
            self._use_redis = False
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache (Redis first, then memory fallback)"""
        # Check if Redis is available
        self._check_redis()
        
        # Try Redis first if available
        if self._use_redis:
            try:
                val = await redis_client.get(key)
                if val:
                    return json.loads(val)
            except Exception as e:
                logger.warning(f"Redis get error: {e}, falling back to memory cache")
        
        # Fallback to memory cache
        if key not in self._memory_cache:
            return None
        value, expiry = self._memory_cache[key]
        if datetime.utcnow() > expiry:
            del self._memory_cache[key]
            return None
        return value
    
    def get_sync(self, key: str) -> Optional[Any]:
        """Get value from memory cache only (synchronous, for backward compatibility)"""
        if key not in self._memory_cache:
            return None
        value, expiry = self._memory_cache[key]
        if datetime.utcnow() > expiry:
            del self._memory_cache[key]
            return None
        return value
    
    async def set(self, key: str, value: Any, ttl_seconds: int = 300):
        """Set value in cache (Redis and memory)"""
        # Check if Redis is available
        self._check_redis()
        
        # Set in Redis if available
        if self._use_redis:
            try:
                await redis_client.set(key, json.dumps(value), ex=ttl_seconds)
            except Exception as e:
                logger.warning(f"Redis set error: {e}, using memory cache only")
        
        # Also set in memory (fallback)
        if len(self._memory_cache) >= self._max_size and key not in self._memory_cache:
            # Remove oldest entry
            oldest_key = min(self._memory_cache.keys(), key=lambda k: self._memory_cache[k][1])
            del self._memory_cache[oldest_key]
        
        expiry = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        self._memory_cache[key] = (value, expiry)
    
    def set_sync(self, key: str, value: Any, ttl_seconds: int = 300):
        """Set value in memory cache only (synchronous, for backward compatibility)"""
        if len(self._memory_cache) >= self._max_size and key not in self._memory_cache:
            oldest_key = min(self._memory_cache.keys(), key=lambda k: self._memory_cache[k][1])
            del self._memory_cache[oldest_key]
        expiry = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        self._memory_cache[key] = (value, expiry)
    
    async def delete(self, key: str):
        """Delete key from cache (Redis and memory)"""
        # Check if Redis is available
        self._check_redis()
        
        if self._use_redis:
            try:
                await redis_client.delete(key)
            except Exception as e:
                logger.warning(f"Redis delete error: {e}")
        self._memory_cache.pop(key, None)
    
    def delete_sync(self, key: str):
        """Delete key from memory cache only (synchronous, for backward compatibility)"""
        self._memory_cache.pop(key, None)
    
    def clear(self):
        """Clear all cache (memory only, Redis keys are not cleared)"""
        self._memory_cache.clear()
    
    def cleanup_expired(self):
        """Remove expired entries from memory cache"""
        now = datetime.utcnow()
        expired = [k for k, (_, expiry) in self._memory_cache.items() if now > expiry]
        for k in expired:
            del self._memory_cache[k]
        return len(expired)
    
    def get_keys_by_pattern(self, pattern: str) -> list[str]:
        """Get cache keys matching pattern (e.g., 'conversations:*') - memory cache only"""
        import fnmatch
        return [k for k in self._memory_cache.keys() if fnmatch.fnmatch(k, pattern)]
    
    async def delete_by_pattern(self, pattern: str) -> int:
        """Delete cache keys matching pattern (Redis and memory) and return count of deleted keys"""
        # Check if Redis is available
        self._check_redis()
        
        keys = self.get_keys_by_pattern(pattern)
        deleted_count = 0
        for key in keys:
            await self.delete(key)
            deleted_count += 1
        
        # Note: Redis doesn't support pattern deletion directly
        # We delete memory cache keys, but Redis keys will expire via TTL
        # For Redis pattern deletion, we'd need to use SCAN which is expensive
        # So we rely on TTL expiration for Redis keys
        return deleted_count
    
    def delete_by_pattern_sync(self, pattern: str) -> int:
        """Delete cache keys matching pattern (memory only, synchronous, for backward compatibility)"""
        keys = self.get_keys_by_pattern(pattern)
        for key in keys:
            self.delete_sync(key)
        return len(keys)

# Global cache instance
cache = HybridCache()

