from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import json
from functools import wraps
from .exceptions import CacheError
from .logging_config import logger

class Cache:
    def __init__(self, max_size: int = 1000, ttl: int = 300):
        self.max_size = max_size
        self.ttl = ttl  # Time to live in seconds
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.access_times: Dict[str, datetime] = {}

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            if key not in self.cache:
                return None

            # Check if entry has expired
            if self._is_expired(key):
                self._remove(key)
                return None

            # Update access time
            self.access_times[key] = datetime.utcnow()
            return self.cache[key]
        except Exception as e:
            logger.error(f"Cache get error: {str(e)}")
            return None

    def set(self, key: str, value: Any) -> bool:
        """Set value in cache"""
        try:
            # Ensure cache doesn't exceed max size
            if len(self.cache) >= self.max_size:
                self._evict_oldest()

            self.cache[key] = value
            self.access_times[key] = datetime.utcnow()
            return True
        except Exception as e:
            logger.error(f"Cache set error: {str(e)}")
            return False

    def delete(self, key: str) -> bool:
        """Delete value from cache"""
        try:
            return self._remove(key)
        except Exception as e:
            logger.error(f"Cache delete error: {str(e)}")
            return False

    def clear(self) -> bool:
        """Clear all cache entries"""
        try:
            self.cache.clear()
            self.access_times.clear()
            return True
        except Exception as e:
            logger.error(f"Cache clear error: {str(e)}")
            return False

    def _is_expired(self, key: str) -> bool:
        """Check if cache entry has expired"""
        if key not in self.access_times:
            return True
        age = datetime.utcnow() - self.access_times[key]
        return age.total_seconds() > self.ttl

    def _remove(self, key: str) -> bool:
        """Remove entry from cache"""
        try:
            if key in self.cache:
                del self.cache[key]
            if key in self.access_times:
                del self.access_times[key]
            return True
        except Exception:
            return False

    def _evict_oldest(self) -> None:
        """Evict oldest cache entry"""
        if not self.access_times:
            return
        oldest_key = min(self.access_times.items(), key=lambda x: x[1])[0]
        self._remove(oldest_key)

class CacheManager:
    def __init__(self):
        self.utxo_cache = Cache(max_size=10000, ttl=300)  # 5 minutes TTL for UTXOs
        self.token_cache = Cache(max_size=5000, ttl=600)  # 10 minutes TTL for tokens
        self.schema_cache = Cache(max_size=100, ttl=3600)  # 1 hour TTL for schemas

    def cache_utxo(self, txid: str, vout: int, utxo_data: Dict[str, Any]) -> bool:
        """Cache UTXO data"""
        try:
            key = f"utxo:{txid}:{vout}"
            return self.utxo_cache.set(key, utxo_data)
        except Exception as e:
            logger.error(f"UTXO cache error: {str(e)}")
            return False

    def get_cached_utxo(self, txid: str, vout: int) -> Optional[Dict[str, Any]]:
        """Get cached UTXO data"""
        try:
            key = f"utxo:{txid}:{vout}"
            return self.utxo_cache.get(key)
        except Exception as e:
            logger.error(f"UTXO cache retrieval error: {str(e)}")
            return None

    def cache_token(self, token_id: str, token_data: Dict[str, Any]) -> bool:
        """Cache token data"""
        try:
            key = f"token:{token_id}"
            return self.token_cache.set(key, token_data)
        except Exception as e:
            logger.error(f"Token cache error: {str(e)}")
            return False

    def get_cached_token(self, token_id: str) -> Optional[Dict[str, Any]]:
        """Get cached token data"""
        try:
            key = f"token:{token_id}"
            return self.token_cache.get(key)
        except Exception as e:
            logger.error(f"Token cache retrieval error: {str(e)}")
            return None

def cache_result(cache_key_prefix: str, ttl: int = 300):
    """Decorator for caching function results"""
    def decorator(func):
        cache = Cache(ttl=ttl)
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function arguments
            key = f"{cache_key_prefix}:{json.dumps(args)}:{json.dumps(kwargs)}"
            
            # Try to get from cache
            result = cache.get(key)
            if result is not None:
                return result
            
            # Call function and cache result
            result = func(*args, **kwargs)
            cache.set(key, result)
            return result
        
        return wrapper
    return decorator

# Create global cache manager instance
cache_manager = CacheManager() 