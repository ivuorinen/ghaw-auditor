"""Policy validator for workflows and actions."""

from __future__ import annotations

import logging
import re
from typing import Any

from ghaw_auditor.models import ActionRef, ActionType, Policy, WorkflowMeta

logger = logging.getLogger(__name__)


class PolicyValidator:
    """Validates workflows against policy rules."""

    def __init__(self, policy: Policy) -> None:
        """Initialize validator."""
        self.policy = policy

    def validate(self, workflows: dict[str, WorkflowMeta], actions: list[ActionRef]) -> list[dict[str, Any]]:
        """Validate workflows and actions against policy."""
        violations: list[dict[str, Any]] = []

        for workflow_path, workflow in workflows.items():
            violations.extend(self._validate_workflow(workflow_path, workflow, actions))

        return violations

    def _validate_workflow(
        self, workflow_path: str, workflow: WorkflowMeta, actions: list[ActionRef]
    ) -> list[dict[str, Any]]:
        """Validate a single workflow."""
        violations: list[dict[str, Any]] = []

        # Check pinned actions
        if self.policy.require_pinned_actions:
            violations.extend(self._check_pinned_actions(workflow_path, workflow))

        # Check branch refs
        if self.policy.forbid_branch_refs:
            violations.extend(self._check_branch_refs(workflow_path, workflow))

        # Check allowed/denied actions
        violations.extend(self._check_action_allowlist(workflow_path, workflow))

        # Check concurrency on PR
        if self.policy.require_concurrency_on_pr:
            violations.extend(self._check_pr_concurrency(workflow_path, workflow))

        return violations

    def _check_pinned_actions(self, workflow_path: str, workflow: WorkflowMeta) -> list[dict[str, Any]]:
        """Check if actions are pinned to SHA."""
        violations: list[dict[str, Any]] = []

        # Check all actions in workflow
        all_actions = workflow.actions_used[:]
        for job in workflow.jobs.values():
            all_actions.extend(job.actions_used)

        for action in all_actions:
            # Check if ref is a SHA (40 hex chars)
            if action.type == ActionType.GITHUB and action.ref and not re.match(r"^[a-f0-9]{40}$", action.ref):
                violations.append(
                    {
                        "workflow": workflow_path,
                        "rule": "require_pinned_actions",
                        "severity": "error",
                        "message": f"Action {action.owner}/{action.repo} is not pinned to SHA: {action.ref}",
                    }
                )

        return violations

    def _check_branch_refs(self, workflow_path: str, workflow: WorkflowMeta) -> list[dict[str, Any]]:
        """Check for branch refs in actions."""
        violations: list[dict[str, Any]] = []

        # Check all actions in workflow
        all_actions = workflow.actions_used[:]
        for job in workflow.jobs.values():
            all_actions.extend(job.actions_used)

        for action in all_actions:
            # Common branch names
            if action.type == ActionType.GITHUB and action.ref and action.ref in ("main", "master", "develop", "dev"):
                violations.append(
                    {
                        "workflow": workflow_path,
                        "rule": "forbid_branch_refs",
                        "severity": "error",
                        "message": f"Action {action.owner}/{action.repo} uses branch ref: {action.ref}",
                    }
                )

        return violations

    def _check_action_allowlist(self, workflow_path: str, workflow: WorkflowMeta) -> list[dict[str, Any]]:
        """Check allowed/denied actions."""
        violations: list[dict[str, Any]] = []

        # Check all actions in workflow
        all_actions = workflow.actions_used[:]
        for job in workflow.jobs.values():
            all_actions.extend(job.actions_used)

        for action in all_actions:
            if action.type == ActionType.GITHUB:
                action_id = f"{action.owner}/{action.repo}"

                # Check denied list
                if self.policy.denied_actions:
                    for denied in self.policy.denied_actions:
                        if self._matches_pattern(action_id, denied):
                            violations.append(
                                {
                                    "workflow": workflow_path,
                                    "rule": "denied_actions",
                                    "severity": "error",
                                    "message": f"Action {action_id} is denied by policy",
                                }
                            )

                # Check allowed list (if specified)
                if self.policy.allowed_actions:
                    allowed = any(self._matches_pattern(action_id, pattern) for pattern in self.policy.allowed_actions)
                    if not allowed:
                        violations.append(
                            {
                                "workflow": workflow_path,
                                "rule": "allowed_actions",
                                "severity": "error",
                                "message": f"Action {action_id} is not in allowed list",
                            }
                        )

        return violations

    def _check_pr_concurrency(self, workflow_path: str, workflow: WorkflowMeta) -> list[dict[str, Any]]:
        """Check if PR workflows have concurrency set."""
        violations: list[dict[str, Any]] = []

        # Check if workflow is triggered by PR
        pr_triggers = {"pull_request", "pull_request_target"}
        has_pr_trigger = any(t in pr_triggers for t in workflow.triggers)

        if has_pr_trigger and not workflow.concurrency:
            violations.append(
                {
                    "workflow": workflow_path,
                    "rule": "require_concurrency_on_pr",
                    "severity": "warning",
                    "message": "PR workflow should have concurrency group to prevent resource waste",
                }
            )

        return violations

    def _matches_pattern(self, action_id: str, pattern: str) -> bool:
        """Check if action ID matches pattern (supports wildcards)."""
        regex_pattern = pattern.replace("*", ".*")
        return bool(re.match(f"^{regex_pattern}$", action_id))
