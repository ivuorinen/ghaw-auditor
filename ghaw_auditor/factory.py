"""Factory for creating audit services with dependency injection."""

from __future__ import annotations

from pathlib import Path

from ghaw_auditor.analyzer import Analyzer
from ghaw_auditor.cache import Cache
from ghaw_auditor.github_client import GitHubClient
from ghaw_auditor.models import Policy
from ghaw_auditor.parser import Parser
from ghaw_auditor.policy import PolicyValidator
from ghaw_auditor.resolver import Resolver
from ghaw_auditor.scanner import Scanner
from ghaw_auditor.services import AuditService


class AuditServiceFactory:
    """Factory for creating audit services with configured dependencies."""

    @staticmethod
    def create(
        repo_path: Path,
        token: str | None = None,
        offline: bool = False,
        cache_dir: Path | None = None,
        concurrency: int = 4,
        policy: Policy | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> AuditService:
        """Create configured audit service.

        Args:
            repo_path: Path to repository
            token: GitHub API token
            offline: Disable API calls
            cache_dir: Cache directory path
            concurrency: API concurrency level
            policy: Policy configuration
            exclude_patterns: File exclusion patterns

        Returns:
            Configured AuditService instance
        """
        # Core components (always created)
        scanner = Scanner(repo_path, exclude_patterns=exclude_patterns or [])
        parser = Parser(repo_path)
        analyzer = Analyzer()
        cache = Cache(cache_dir)

        # Optional resolver (only if not offline)
        resolver = None
        if not offline:
            client = GitHubClient(token)
            resolver = Resolver(client, cache, repo_path, concurrency)

        # Optional validator (only if policy provided)
        validator = None
        if policy:
            validator = PolicyValidator(policy)

        return AuditService(scanner, parser, analyzer, resolver, validator)
