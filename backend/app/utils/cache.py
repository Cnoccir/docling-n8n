"""Redis caching utilities for API responses."""
import json
import redis
import os
from typing import Optional, Any
from functools import wraps
from datetime import datetime
from decimal import Decimal

# Redis client (reuse Celery's Redis)
redis_client = redis.from_url(
    os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    decode_responses=True
)

# Cache TTLs (in seconds)
CACHE_TTL_DOCUMENT_LIST = 300  # 5 minutes
CACHE_TTL_DOCUMENT_DETAIL = 3600  # 1 hour
CACHE_TTL_CHUNKS = 86400  # 24 hours (chunks don't change)
CACHE_TTL_IMAGES = 86400  # 24 hours
CACHE_TTL_TABLES = 86400  # 24 hours
CACHE_TTL_HIERARCHY = 86400  # 24 hours


def get_cache_key(prefix: str, *args) -> str:
    """Generate cache key from prefix and arguments."""
    parts = [prefix] + [str(arg) for arg in args if arg is not None]
    return ":".join(parts)


def get_cached(key: str) -> Optional[Any]:
    """Get value from cache."""
    try:
        value = redis_client.get(key)
        if value:
            return json.loads(value)
        return None
    except Exception as e:
        print(f"Cache get error: {e}")
        return None


def json_serial(obj):
    """JSON serializer for objects not serializable by default."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def set_cache(key: str, value: Any, ttl: int) -> bool:
    """Set value in cache with TTL."""
    try:
        redis_client.setex(key, ttl, json.dumps(value, default=json_serial))
        return True
    except Exception as e:
        print(f"Cache set error: {e}")
        return False


def delete_cache(pattern: str) -> int:
    """Delete all keys matching pattern."""
    try:
        keys = redis_client.keys(pattern)
        if keys:
            return redis_client.delete(*keys)
        return 0
    except Exception as e:
        print(f"Cache delete error: {e}")
        return 0


def invalidate_document_cache(doc_id: str):
    """Invalidate all cached data for a document."""
    patterns = [
        f"doc:{doc_id}:*",
        f"doc_list:*",  # Invalidate list cache too
        f"hierarchy:{doc_id}",
        f"chunks:{doc_id}:*",
        f"images:{doc_id}",
        f"tables:{doc_id}"
    ]
    for pattern in patterns:
        delete_cache(pattern)


def cache_response(ttl: int, key_prefix: str):
    """Decorator to cache API responses."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Build cache key from function arguments
            cache_key = get_cache_key(key_prefix, *args, *kwargs.values())
            
            # Try to get from cache
            cached = get_cached(cache_key)
            if cached is not None:
                return cached
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            set_cache(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator
