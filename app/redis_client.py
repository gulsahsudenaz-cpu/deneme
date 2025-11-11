"""Redis client for distributed cache and rate limiting"""
import redis.asyncio as redis
from typing import Optional
from app.config import settings
from app.logger import logger

class RedisClient:
    def __init__(self):
        self.client: Optional[redis.Redis] = None
        self.enabled = bool(getattr(settings, 'REDIS_URL', None))
    
    async def connect(self):
        """Connect to Redis if URL is configured"""
        if not self.enabled:
            logger.info("Redis not configured, using in-memory fallback")
            return
        
        try:
            self.client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5
            )
            await self.client.ping()
            logger.info("Redis connected successfully")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}, using in-memory fallback")
            self.client = None
            self.enabled = False
    
    async def disconnect(self):
        """Disconnect from Redis"""
        if self.client:
            await self.client.close()
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from Redis"""
        if not self.enabled or not self.client:
            return None
        try:
            return await self.client.get(key)
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None
    
    async def set(self, key: str, value: str, ex: int = None):
        """Set value in Redis with optional expiry"""
        if not self.enabled or not self.client:
            return
        try:
            await self.client.set(key, value, ex=ex)
        except Exception as e:
            logger.error(f"Redis set error: {e}")
    
    async def delete(self, key: str):
        """Delete key from Redis"""
        if not self.enabled or not self.client:
            return
        try:
            await self.client.delete(key)
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
    
    async def incr(self, key: str) -> int:
        """Increment counter"""
        if not self.enabled or not self.client:
            return 0
        try:
            return await self.client.incr(key)
        except Exception as e:
            logger.error(f"Redis incr error: {e}")
            return 0
    
    async def expire(self, key: str, seconds: int):
        """Set expiry on key"""
        if not self.enabled or not self.client:
            return
        try:
            await self.client.expire(key, seconds)
        except Exception as e:
            logger.error(f"Redis expire error: {e}")

redis_client = RedisClient()
