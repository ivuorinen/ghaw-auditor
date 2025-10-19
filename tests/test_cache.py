"""Tests for cache module."""

from pathlib import Path

from ghaw_auditor.cache import Cache


def test_cache_initialization(tmp_path: Path) -> None:
    """Test cache can be initialized."""
    cache = Cache(tmp_path / "cache")
    assert cache.cache_dir.exists()
    cache.close()


def test_cache_set_get(tmp_path: Path) -> None:
    """Test cache set and get."""
    cache = Cache(tmp_path / "cache")

    cache.set("test_key", "test_value")
    value = cache.get("test_key")

    assert value == "test_value"
    cache.close()


def test_cache_make_key() -> None:
    """Test cache key generation."""
    cache = Cache()

    key1 = cache.make_key("part1", "part2", "part3")
    key2 = cache.make_key("part1", "part2", "part3")
    key3 = cache.make_key("different", "parts")

    assert key1 == key2
    assert key1 != key3
    cache.close()


def test_cache_clear(tmp_path: Path) -> None:
    """Test cache clear."""
    cache = Cache(tmp_path / "cache")

    # Add some values
    cache.set("key1", "value1")
    cache.set("key2", "value2")

    # Verify they exist
    assert cache.get("key1") == "value1"
    assert cache.get("key2") == "value2"

    # Clear cache
    cache.clear()

    # Verify values are gone
    assert cache.get("key1") is None
    assert cache.get("key2") is None

    cache.close()
