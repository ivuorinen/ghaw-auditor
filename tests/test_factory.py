"""Tests for factory module."""

from pathlib import Path

from ghaw_auditor.factory import AuditServiceFactory
from ghaw_auditor.models import Policy


def test_factory_create_basic(tmp_path: Path) -> None:
    """Test factory creates service with basic configuration."""
    service = AuditServiceFactory.create(
        repo_path=tmp_path,
        offline=True,
    )

    assert service.scanner is not None
    assert service.parser is not None
    assert service.analyzer is not None
    assert service.resolver is None  # Offline mode
    assert service.validator is None  # No policy


def test_factory_create_with_policy(tmp_path: Path) -> None:
    """Test factory creates service with policy."""
    policy = Policy(require_pinned_actions=True)

    service = AuditServiceFactory.create(
        repo_path=tmp_path,
        offline=True,
        policy=policy,
    )

    assert service.validator is not None


def test_factory_create_with_resolver(tmp_path: Path) -> None:
    """Test factory creates service with resolver."""
    service = AuditServiceFactory.create(
        repo_path=tmp_path,
        offline=False,
        token="test_token",
    )

    assert service.resolver is not None


def test_factory_create_with_exclude_patterns(tmp_path: Path) -> None:
    """Test factory creates service with exclusion patterns."""
    service = AuditServiceFactory.create(
        repo_path=tmp_path,
        offline=True,
        exclude_patterns=["**/node_modules/**", "**/dist/**"],
    )

    assert len(service.scanner.exclude_patterns) == 2


def test_factory_create_with_cache_dir(tmp_path: Path) -> None:
    """Test factory creates service with custom cache directory."""
    cache_dir = tmp_path / "custom_cache"

    service = AuditServiceFactory.create(
        repo_path=tmp_path,
        offline=True,
        cache_dir=cache_dir,
    )

    # Service created successfully
    assert service is not None


def test_factory_create_with_concurrency(tmp_path: Path) -> None:
    """Test factory creates service with custom concurrency."""
    service = AuditServiceFactory.create(
        repo_path=tmp_path,
        offline=False,
        concurrency=8,
    )

    assert service.resolver is not None
    assert service.resolver.concurrency == 8
