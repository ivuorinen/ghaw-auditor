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

    service.close()


def test_factory_create_with_policy(tmp_path: Path) -> None:
    """Test factory creates service with policy."""
    policy = Policy(require_pinned_actions=True)

    service = AuditServiceFactory.create(
        repo_path=tmp_path,
        offline=True,
        policy=policy,
    )

    assert service.validator is not None

    service.close()


def test_factory_create_with_resolver(tmp_path: Path) -> None:
    """Test factory creates service with resolver."""
    service = AuditServiceFactory.create(
        repo_path=tmp_path,
        offline=False,
        token="test_token",
    )

    assert service.resolver is not None

    service.close()


def test_factory_create_with_exclude_patterns(tmp_path: Path) -> None:
    """Test factory creates service with exclusion patterns."""
    service = AuditServiceFactory.create(
        repo_path=tmp_path,
        offline=True,
        exclude_patterns=["**/node_modules/**", "**/dist/**"],
    )

    assert len(service.scanner.exclude_patterns) == 2

    service.close()


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

    service.close()


def test_factory_create_with_concurrency(tmp_path: Path) -> None:
    """Test factory creates service with custom concurrency."""
    service = AuditServiceFactory.create(
        repo_path=tmp_path,
        offline=False,
        concurrency=8,
    )

    assert service.resolver is not None
    assert service.resolver.concurrency == 8

    service.close()


def test_service_closes_cache_on_context_exit(tmp_path: Path) -> None:
    """The composition root's resources are released when the service exits.

    Nothing in production ever called Cache.close()/GitHubClient.close(), so
    every run leaked an sqlite connection and an HTTP connection pool.
    """
    cache_dir = tmp_path / "cache"
    closed: list[str] = []

    service = AuditServiceFactory.create(repo_path=tmp_path, offline=True, cache_dir=cache_dir)

    class Probe:
        def close(self) -> None:
            closed.append("closed")

    service._closeables.append(Probe())

    with service:
        pass

    assert closed == ["closed"]


def test_service_close_survives_a_failing_closeable(tmp_path: Path) -> None:
    """One failing close must not prevent the others or mask the audit result."""
    service = AuditServiceFactory.create(repo_path=tmp_path, offline=True, cache_dir=tmp_path / "c")
    closed: list[str] = []

    class Boom:
        def close(self) -> None:
            raise OSError("nope")

    class Good:
        def close(self) -> None:
            closed.append("good")

    service._closeables = [Boom(), Good()]
    service.close()

    assert closed == ["good"]
