import time
from collections import defaultdict, deque
from typing import Deque, Dict
from datetime import datetime, timedelta

# Simple in-memory token bucket (single instance)
class TokenBucket:
  def __init__(self, rate_per_sec: int, burst: int):
    self.rate = rate_per_sec
    self.capacity = burst
    self.tokens = burst
    self.updated = time.monotonic()
    self.last_access = datetime.utcnow()

  def allow(self) -> bool:
    now = time.monotonic()
    elapsed = now - self.updated
    self.updated = now
    self.last_access = datetime.utcnow()
    self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
    if self.tokens >= 1:
      self.tokens -= 1
      return True
    return False

class RateLimiter:
  def __init__(self):
    self.ws_buckets: Dict[str, TokenBucket] = defaultdict(lambda: TokenBucket(1, 5))
    self.api_buckets: Dict[str, TokenBucket] = defaultdict(lambda: TokenBucket(20, 100))  # 100 req per 5 min = 20/sec

  def key(self, *parts):
    return "|".join(parts)

  def allow_ws(self, ident: str, rate: int, burst: int):
    b = self.ws_buckets.get(ident)
    if not b or b.rate != rate or b.capacity != burst:
      b = TokenBucket(rate, burst)
      self.ws_buckets[ident] = b
    return b.allow()

  def allow_api(self, ident: str, rate_per_sec: int, burst: int):
    """Rate limit for REST API endpoints"""
    b = self.api_buckets.get(ident)
    if not b or b.rate != rate_per_sec or b.capacity != burst:
      b = TokenBucket(rate_per_sec, burst)
      self.api_buckets[ident] = b
    return b.allow()

  def cleanup_stale_buckets(self, max_age_minutes: int = 60):
    """Remove buckets that haven't been accessed in max_age_minutes"""
    cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)
    # Clean WS buckets
    stale_ws = [k for k, v in self.ws_buckets.items() if v.last_access < cutoff]
    for k in stale_ws:
      del self.ws_buckets[k]
    # Clean API buckets
    stale_api = [k for k, v in self.api_buckets.items() if v.last_access < cutoff]
    for k in stale_api:
      del self.api_buckets[k]
    return len(stale_ws) + len(stale_api)

ws_rate_limiter = RateLimiter()

