"""Analyzer for workflows and actions."""

from __future__ import annotations

import logging
from typing import Any

from ghaw_auditor.models import ActionManifest, WorkflowMeta

logger = logging.getLogger(__name__)


class Analyzer:
    """Analyzes workflows and actions for patterns and risks."""

    def __init__(self) -> None:
        """Initialize analyzer."""
        pass

    def analyze_workflows(
        self, workflows: dict[str, WorkflowMeta], actions: dict[str, ActionManifest]
    ) -> dict[str, Any]:
        """Analyze workflows for patterns and issues."""
        analysis = {
            "total_workflows": len(workflows),
            "total_jobs": sum(len(w.jobs) for w in workflows.values()),
            "reusable_workflows": sum(1 for w in workflows.values() if w.is_reusable),
            "triggers": self._analyze_triggers(workflows),
            "permissions": self._analyze_permissions(workflows),
            "secrets": self._analyze_secrets(workflows),
            "runners": self._analyze_runners(workflows),
            "containers": self._analyze_containers(workflows),
        }
        return analysis

    def _analyze_triggers(self, workflows: dict[str, WorkflowMeta]) -> dict[str, int]:
        """Analyze workflow triggers."""
        triggers: dict[str, int] = {}
        for workflow in workflows.values():
            for trigger in workflow.triggers:
                triggers[trigger] = triggers.get(trigger, 0) + 1
        return triggers

    def _analyze_permissions(self, workflows: dict[str, WorkflowMeta]) -> dict[str, Any]:
        """Analyze permissions usage."""
        has_permissions = sum(1 for w in workflows.values() if w.permissions)
        job_permissions = sum(1 for w in workflows.values() for j in w.jobs.values() if j.permissions)
        return {
            "workflows_with_permissions": has_permissions,
            "jobs_with_permissions": job_permissions,
        }

    def _analyze_secrets(self, workflows: dict[str, WorkflowMeta]) -> dict[str, Any]:
        """Analyze secrets usage."""
        all_secrets: set[str] = set()
        for workflow in workflows.values():
            all_secrets.update(workflow.secrets_used)

        return {
            "total_unique_secrets": len(all_secrets),
            "secrets": sorted(all_secrets),
        }

    def _analyze_runners(self, workflows: dict[str, WorkflowMeta]) -> dict[str, int]:
        """Analyze runner usage."""
        runners: dict[str, int] = {}
        for workflow in workflows.values():
            for job in workflow.jobs.values():
                runner = str(job.runs_on) if isinstance(job.runs_on, list) else job.runs_on
                runners[runner] = runners.get(runner, 0) + 1
        return runners

    def _analyze_containers(self, workflows: dict[str, WorkflowMeta]) -> dict[str, Any]:
        """Analyze container usage."""
        jobs_with_containers = 0
        jobs_with_services = 0

        for workflow in workflows.values():
            for job in workflow.jobs.values():
                jobs_with_containers += 1 if job.container else 0
                jobs_with_services += 1 if job.services else 0

        return {
            "jobs_with_containers": jobs_with_containers,
            "jobs_with_services": jobs_with_services,
        }

    def deduplicate_actions(self, all_actions: list[Any]) -> dict[str, Any]:
        """Deduplicate actions by canonical key."""
        unique_actions: dict[str, Any] = {}
        for action in all_actions:
            key = action.canonical_key()
            if key not in unique_actions:
                unique_actions[key] = action
        return unique_actions
