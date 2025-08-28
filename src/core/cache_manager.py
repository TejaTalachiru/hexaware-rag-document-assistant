from typing import Dict, Any, Optional
import time
import hashlib
import json

class SimpleCacheManager:
    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self.cache = {}
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
    
    def _get_key(self, query: str, search_mode: str) -> str:
        """Generate cache key from query and search mode"""
        content = f"{query.lower().strip()}_{search_mode}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def get(self, query: str, search_mode: str) -> Optional[Dict[str, Any]]:
        """Get cached result if available and not expired"""
        key = self._get_key(query, search_mode)
        
        if key in self.cache:
            cached_item = self.cache[key]
            if time.time() - cached_item["timestamp"] < self.ttl_seconds:
                return cached_item["data"]
            else:
                del self.cache[key]
        
        return None
    
    def set(self, query: str, search_mode: str, data: Dict[str, Any]):
        """Cache the result"""
        if len(self.cache) >= self.max_size:
            # Remove oldest item
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k]["timestamp"])
            del self.cache[oldest_key]
        
        key = self._get_key(query, search_mode)
        self.cache[key] = {
            "data": data,
            "timestamp": time.time()
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            "total_items": len(self.cache),
            "max_size": self.max_size,
            "hit_rate": getattr(self, '_hit_count', 0) / max(getattr(self, '_total_requests', 1), 1)
        }
