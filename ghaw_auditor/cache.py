"""Caching layer for GitHub API responses and parsed data."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import diskcache
from platformdirs import user_cache_dir

logger = logging.getLogger(__name__)


class Cache:
    """Disk-based cache for API responses and parsed objects."""

    def __init__(self, cache_dir: str | Path | None = None, ttl: int = 3600) -> None:
        """Initialize cache."""
        if cache_dir is None:
            cache_dir = Path(user_cache_dir("ghaw-auditor"))
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache = diskcache.Cache(str(self.cache_dir))
        self.ttl = ttl

    def get(self, key: str) -> Any:
        """Get value from cache."""
        return self.cache.get(key)

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set value in cache."""
        self.cache.set(key, value, expire=ttl or self.ttl)

    def make_key(self, *parts: str) -> str:
        """Generate cache key from parts."""
        combined = ":".join(str(p) for p in parts)
        return hashlib.sha256(combined.encode()).hexdigest()

    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()

    def close(self) -> None:
        """Close cache."""
        self.cache.close()
