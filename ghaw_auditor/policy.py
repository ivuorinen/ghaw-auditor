"""Policy validator for workflows and actions."""

from __future__ import annotations

import logging
import re
from fnmatch import fnmatchcase
from typing import Any

from ghaw_auditor.models import ActionType, PermissionLevel, Permissions, Policy, WorkflowMeta

logger = logging.getLogger(__name__)

# Reusable workflows execute in the caller's context with the caller's secrets,
# so they are subject to the same pinning and ref policies as ordinary actions.
REMOTE_ACTION_TYPES = (ActionType.GITHUB, ActionType.REUSABLE_WORKFLOW)

# A full object id: SHA-1 (40) or SHA-256 (64), either case. \Z (not $) so a
# trailing newline cannot satisfy the anchor.
SHA_RE = re.compile(r"(?:[a-fA-F0-9]{40}|[a-fA-F0-9]{64})\Z")

# Branch names that are always moving targets.
MUTABLE_BRANCH_REFS = frozenset({"main", "master", "develop", "dev"})


class PolicyValidator:
    """Validates workflows against policy rules."""

    def __init__(self, policy: Policy) -> None:
        """Initialize validator."""
        self.policy = policy

    def validate(self, workflows: dict[str, WorkflowMeta]) -> list[dict[str, Any]]:
        """Validate workflows against policy.

        Every action reference reachable from a workflow already lives in
        ``WorkflowMeta.actions_used`` (the parser populates it as the union of
        all job action lists), so no separate action list is needed.
        """
        violations: list[dict[str, Any]] = []

        for workflow_path, workflow in workflows.items():
            violations.extend(self._validate_workflow(workflow_path, workflow))

        return violations

    def _validate_workflow(self, workflow_path: str, workflow: WorkflowMeta) -> list[dict[str, Any]]:
        """Validate a single workflow."""
        violations: list[dict[str, Any]] = []

        # Check least-privilege on the job token
        if self.policy.min_permissions:
            violations.extend(self._check_min_permissions(workflow_path, workflow))

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

    @staticmethod
    def _is_write_all(permissions: Permissions | None) -> bool:
        """True when every scope is set to write (the `write-all` shorthand)."""
        if permissions is None:
            return False
        values = permissions.model_dump().values()
        return bool(values) and all(v == PermissionLevel.WRITE for v in values)

    def _check_min_permissions(self, workflow_path: str, workflow: WorkflowMeta) -> list[dict[str, Any]]:
        """Check the job token follows least privilege."""
        violations: list[dict[str, Any]] = []

        if self._is_write_all(workflow.permissions):
            violations.append(
                {
                    "workflow": workflow_path,
                    "rule": "min_permissions",
                    "severity": "error",
                    "message": "Workflow grants write-all: every scope is writable by the job token",
                }
            )

        for job_name, job in workflow.jobs.items():
            if self._is_write_all(job.permissions):
                violations.append(
                    {
                        "workflow": workflow_path,
                        "rule": "min_permissions",
                        "severity": "error",
                        "message": f"Job '{job_name}' grants write-all: every scope is writable by the job token",
                    }
                )

        # Nothing declared anywhere means the token silently inherits the
        # repository default, which is read/write on contents for many repos.
        declared_anywhere = workflow.permissions is not None or any(j.permissions for j in workflow.jobs.values())
        if not declared_anywhere:
            violations.append(
                {
                    "workflow": workflow_path,
                    "rule": "min_permissions",
                    "severity": "warning",
                    "message": "No permissions declared; the job token inherits the repository default scope",
                }
            )

        return violations

    def _check_pinned_actions(self, workflow_path: str, workflow: WorkflowMeta) -> list[dict[str, Any]]:
        """Check if actions are pinned to SHA."""
        violations: list[dict[str, Any]] = []

        for action in workflow.actions_used:
            # Accept a full SHA-1 or SHA-256 object id in either case.
            if action.type in REMOTE_ACTION_TYPES and action.ref and not SHA_RE.match(action.ref):
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

        for action in workflow.actions_used:
            # Common branch names
            if action.type in REMOTE_ACTION_TYPES and action.ref and action.ref in MUTABLE_BRANCH_REFS:
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

        for action in workflow.actions_used:
            if action.type in REMOTE_ACTION_TYPES:
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
        """Check if action ID matches pattern (glob wildcards).

        Uses fnmatchcase so every character outside ``*``, ``?`` and ``[seq]``
        is literal. Building a regex from the raw pattern would let a dot match
        any character (silently widening an allowlist) and would raise re.error
        on an unbalanced bracket in a user-supplied policy.
        """
        return fnmatchcase(action_id, pattern)
