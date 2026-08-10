"""Service layer for orchestrating audit operations."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from ghaw_auditor.analyzer import Analyzer
from ghaw_auditor.differ import Differ
from ghaw_auditor.models import (
    ActionDiff,
    ActionManifest,
    WorkflowDiff,
    WorkflowMeta,
)
from ghaw_auditor.parser import Parser
from ghaw_auditor.policy import PolicyValidator
from ghaw_auditor.resolver import Resolver
from ghaw_auditor.scanner import Scanner

logger = logging.getLogger(__name__)


class Closeable(Protocol):
    """Anything owning an OS resource that must be released."""

    def close(self) -> None:
        """Release the underlying resource."""


@dataclass
class ScanResult:
    """Result of a scan operation."""

    workflows: dict[str, WorkflowMeta]
    actions: dict[str, ActionManifest]
    violations: list[dict[str, Any]]
    analysis: dict[str, Any]
    workflow_count: int
    action_count: int
    unique_action_count: int


class AuditService:
    """Orchestrates the audit workflow."""

    def __init__(
        self,
        scanner: Scanner,
        parser: Parser,
        analyzer: Analyzer,
        resolver: Resolver | None = None,
        validator: PolicyValidator | None = None,
        closeables: Sequence[Closeable] = (),
    ) -> None:
        """Initialize audit service.

        ``closeables`` are OS-resource owners created by the composition root
        (the disk cache's sqlite connection, the HTTP connection pool). The
        service owns closing them so the caller can use a single ``with``.
        """
        self.scanner = scanner
        self.parser = parser
        self.analyzer = analyzer
        self.resolver = resolver
        self.validator = validator
        self._closeables = list(closeables)

    def close(self) -> None:
        """Release every resource the factory opened for this service."""
        for closeable in self._closeables:
            try:
                closeable.close()
            except Exception:  # a failed close must not mask the audit result
                logger.debug("Failed to close %r", closeable, exc_info=True)
        self._closeables.clear()

    def __enter__(self) -> AuditService:
        """Context manager entry."""
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit."""
        self.close()

    def scan(self, offline: bool = False) -> ScanResult:
        """Execute scan workflow and return results."""
        # Find files
        workflow_files = self.scanner.find_workflows()
        action_files = self.scanner.find_actions()

        # Parse workflows
        workflows = {}
        all_actions = []

        for wf_file in workflow_files:
            try:
                workflow = self.parser.parse_workflow(wf_file)
                rel_path = str(wf_file.relative_to(self.scanner.repo_path))
                workflows[rel_path] = workflow
                all_actions.extend(workflow.actions_used)
            except Exception as e:
                logger.error(f"Failed to parse workflow {wf_file}: {e}")

        # Deduplicate actions
        unique_actions = self.analyzer.deduplicate_actions(all_actions)

        # Resolve actions
        actions = {}
        if not offline and self.resolver:
            actions = self.resolver.resolve_actions(list(unique_actions.values()))

        # Analyze
        analysis = self.analyzer.analyze_workflows(workflows, actions)

        # Validate
        violations = []
        if self.validator:
            violations = self.validator.validate(workflows)

        return ScanResult(
            workflows=workflows,
            actions=actions,
            violations=violations,
            analysis=analysis,
            workflow_count=len(workflow_files),
            action_count=len(action_files),
            unique_action_count=len(unique_actions),
        )


class DiffService:
    """Handles baseline comparison."""

    def __init__(self, differ: Differ) -> None:
        """Initialize diff service."""
        self.differ = differ

    def compare(
        self,
        workflows: dict[str, WorkflowMeta],
        actions: dict[str, ActionManifest],
    ) -> tuple[list[WorkflowDiff], list[ActionDiff]]:
        """Compare current state with baseline."""
        baseline = self.differ.load_baseline()
        workflow_diffs = self.differ.diff_workflows(baseline.workflows, workflows)
        action_diffs = self.differ.diff_actions(baseline.actions, actions)
        return workflow_diffs, action_diffs
