"""Service layer for orchestrating audit operations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

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
    ) -> None:
        """Initialize audit service."""
        self.scanner = scanner
        self.parser = parser
        self.analyzer = analyzer
        self.resolver = resolver
        self.validator = validator

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
            violations = self.validator.validate(workflows, all_actions)

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
