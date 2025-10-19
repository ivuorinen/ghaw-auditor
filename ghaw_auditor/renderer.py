"""Renderers for JSON and Markdown reports."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ghaw_auditor.models import ActionManifest, ActionRef, ActionType, WorkflowMeta

logger = logging.getLogger(__name__)


class Renderer:
    """Renders audit reports in various formats."""

    def __init__(self, output_dir: Path) -> None:
        """Initialize renderer."""
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _create_action_anchor(key: str) -> str:
        """Create markdown-compatible anchor ID from action key.

        Examples:
            "actions/checkout@abc123" -> "actions-checkout"
            "local:./sync-labels" -> "local-sync-labels"
            "docker://alpine:3.8" -> "docker-alpine-3-8"
        """
        # For GitHub actions, remove the @ref/SHA part
        if "@" in key and not key.startswith("docker://"):
            key = key.split("@")[0]

        # Replace special characters with dashes
        anchor = key.replace("/", "-").replace(":", "-").replace(".", "-")
        # Clean up multiple consecutive dashes
        while "--" in anchor:
            anchor = anchor.replace("--", "-")
        return anchor.lower().strip("-")

    @staticmethod
    def _get_action_repo_url(action_ref: ActionRef) -> str | None:
        """Get GitHub repository URL for an action.

        Returns:
            URL string for GitHub actions, None for local/docker actions
        """
        if action_ref.type == ActionType.GITHUB and action_ref.owner and action_ref.repo:
            return f"https://github.com/{action_ref.owner}/{action_ref.repo}"
        return None

    def render_json(
        self, workflows: dict[str, WorkflowMeta], actions: dict[str, ActionManifest], violations: list[dict[str, Any]]
    ) -> None:
        """Render JSON reports."""
        # Write workflows
        workflows_data = {k: v.model_dump(mode="json") for k, v in workflows.items()}
        workflows_file = self.output_dir / "workflows.json"
        with open(workflows_file, "w", encoding="utf-8") as f:
            json.dump(workflows_data, f, indent=2, default=str)

        # Write actions
        actions_data = {k: v.model_dump(mode="json") for k, v in actions.items()}
        actions_file = self.output_dir / "actions.json"
        with open(actions_file, "w", encoding="utf-8") as f:
            json.dump(actions_data, f, indent=2, default=str)

        # Write violations
        violations_file = self.output_dir / "violations.json"
        with open(violations_file, "w", encoding="utf-8") as f:
            json.dump(violations, f, indent=2)

        logger.info(f"JSON reports written to {self.output_dir}")

    def _write_summary(
        self,
        f: Any,
        workflows: dict[str, WorkflowMeta],
        actions: dict[str, ActionManifest],
        violations: list[dict[str, Any]],
    ) -> None:
        """Write summary section to markdown file."""
        f.write("## Summary\n\n")
        f.write(f"- **Workflows:** {len(workflows)}\n")
        f.write(f"- **Actions:** {len(actions)}\n")
        f.write(f"- **Policy Violations:** {len(violations)}\n\n")

    def _write_analysis(self, f: Any, analysis: dict[str, Any]) -> None:
        """Write analysis section to markdown file."""
        if not analysis:
            return

        f.write("## Analysis\n\n")
        f.write(f"- **Total Jobs:** {analysis.get('total_jobs', 0)}\n")
        f.write(f"- **Reusable Workflows:** {analysis.get('reusable_workflows', 0)}\n")

        if "triggers" in analysis:
            f.write("\n### Triggers\n\n")
            for trigger, count in sorted(analysis["triggers"].items()):
                f.write(f"- `{trigger}`: {count}\n")
            f.write("\n")

        if "runners" in analysis:
            f.write("\n### Runners\n\n")
            for runner, count in sorted(analysis["runners"].items()):
                f.write(f"- `{runner}`: {count}\n")
            f.write("\n")

        if "secrets" in analysis:
            f.write("\n### Secrets\n\n")
            f.write(f"Total unique secrets: {analysis['secrets'].get('total_unique_secrets', 0)}\n\n")
            secrets = analysis["secrets"].get("secrets", [])
            if secrets:
                for secret in sorted(secrets):
                    f.write(f"- `{secret}`\n")
                f.write("\n")

    def _write_job_details(self, f: Any, job_name: str, job: Any) -> None:
        """Write job details to markdown file."""
        f.write(f"- **{job_name}**\n")
        f.write(f"  - Runner: `{job.runs_on}`\n")

        if job.permissions:
            active_perms = {k: v for k, v in job.permissions.model_dump(mode="json").items() if v is not None}
            if active_perms:
                f.write("  - Permissions:\n")
                for perm_name, perm_level in sorted(active_perms.items()):
                    display_name = perm_name.replace("_", "-")
                    f.write(f"    - `{display_name}`: {perm_level}\n")

        if job.actions_used:
            f.write("  - Actions used:\n")
            for action_ref in job.actions_used:
                action_key = action_ref.canonical_key()
                anchor = self._create_action_anchor(action_key)

                if action_ref.type == ActionType.GITHUB:
                    type_label = "GitHub"
                    display_name = f"{action_ref.owner}/{action_ref.repo}"
                elif action_ref.type == ActionType.LOCAL:
                    type_label = "Local"
                    display_name = action_ref.path or "local"
                elif action_ref.type == ActionType.DOCKER:
                    type_label = "Docker"
                    display_name = action_ref.path or action_key
                else:
                    type_label = "Reusable Workflow"
                    display_name = action_ref.path or action_key

                f.write(f"    - [{display_name}](#{anchor}) ({type_label})\n")

    def _write_workflows(self, f: Any, workflows: dict[str, WorkflowMeta]) -> None:
        """Write workflows section to markdown file."""
        f.write("\n## Workflows\n\n")
        for path, workflow in sorted(workflows.items()):
            f.write(f"### {workflow.name}\n\n")
            f.write(f"**Path:** `{path}`\n\n")
            f.write(f"**Triggers:** {', '.join(f'`{t}`' for t in workflow.triggers)}\n\n")
            f.write(f"**Jobs:** {len(workflow.jobs)}\n\n")

            if workflow.jobs:
                f.write("#### Jobs\n\n")
                for job_name, job in workflow.jobs.items():
                    self._write_job_details(f, job_name, job)
                f.write("\n")

    def _write_action_header(
        self, f: Any, key: str, action: ActionManifest, action_ref_map: dict[str, ActionRef]
    ) -> None:
        """Write action header with key and repository info."""
        anchor = self._create_action_anchor(key)
        f.write(f'### <a id="{anchor}"></a>{action.name}\n\n')
        f.write(f"**Key:** `{key}`\n\n")

        if key in action_ref_map:
            repo_url = self._get_action_repo_url(action_ref_map[key])
            if repo_url:
                f.write(f"**Repository:** [{action_ref_map[key].owner}/{action_ref_map[key].repo}]({repo_url})\n\n")
            elif action_ref_map[key].type == ActionType.LOCAL:
                f.write("**Type:** Local Action\n\n")

        if action.description:
            f.write(f"{action.description}\n\n")

    def _write_workflows_using_action(self, f: Any, key: str, workflows: dict[str, WorkflowMeta]) -> None:
        """Write section showing workflows that use this action."""
        workflows_using_action = []
        for workflow_path, workflow in workflows.items():
            for action_ref in workflow.actions_used:
                if action_ref.canonical_key() == key:
                    workflows_using_action.append((workflow_path, workflow.name))
                    break

        if workflows_using_action:
            f.write("<details>\n")
            f.write("<summary><b>Used in Workflows</b></summary>\n\n")
            for workflow_path, workflow_name in sorted(workflows_using_action):
                workflow_anchor = workflow_name.lower().replace(" ", "-").replace(".", "-")
                f.write(f"- [{workflow_name}](#{workflow_anchor}) (`{workflow_path}`)\n")
            f.write("\n</details>\n\n")

    def _write_action_inputs(self, f: Any, action: ActionManifest) -> None:
        """Write action inputs section."""
        if action.inputs:
            f.write("<details>\n")
            f.write("<summary><b>Inputs</b></summary>\n\n")
            for inp in action.inputs.values():
                req = "required" if inp.required else "optional"
                f.write(f"- `{inp.name}` ({req}): {inp.description or 'No description'}\n")
            f.write("\n</details>\n\n")
        else:
            f.write("\n")

    def _write_actions_inventory(
        self, f: Any, workflows: dict[str, WorkflowMeta], actions: dict[str, ActionManifest]
    ) -> None:
        """Write actions inventory section to markdown file."""
        f.write("\n## Actions Inventory\n\n")

        # Build mapping of action keys to ActionRef for repo URLs
        action_ref_map: dict[str, ActionRef] = {}
        for workflow in workflows.values():
            for action_ref in workflow.actions_used:
                key = action_ref.canonical_key()
                if key not in action_ref_map:
                    action_ref_map[key] = action_ref

        for key, action in sorted(actions.items()):
            self._write_action_header(f, key, action, action_ref_map)
            self._write_workflows_using_action(f, key, workflows)
            self._write_action_inputs(f, action)

    def _write_violations(self, f: Any, violations: list[dict[str, Any]]) -> None:
        """Write violations section to markdown file."""
        if not violations:
            return

        f.write("\n## Policy Violations\n\n")
        for violation in violations:
            severity = violation.get("severity", "warning").upper()
            f.write(f"### [{severity}] {violation['rule']}\n\n")
            f.write(f"**Workflow:** `{violation['workflow']}`\n\n")
            f.write(f"{violation['message']}\n\n")

    def render_markdown(
        self,
        workflows: dict[str, WorkflowMeta],
        actions: dict[str, ActionManifest],
        violations: list[dict[str, Any]],
        analysis: dict[str, Any],
    ) -> None:
        """Render Markdown report."""
        report_file = self.output_dir / "report.md"

        with open(report_file, "w", encoding="utf-8") as f:
            f.write("# GitHub Actions & Workflows Audit Report\n\n")
            f.write(f"**Generated:** {datetime.now().isoformat()}\n\n")

            self._write_summary(f, workflows, actions, violations)
            self._write_analysis(f, analysis)
            self._write_workflows(f, workflows)
            self._write_actions_inventory(f, workflows, actions)
            self._write_violations(f, violations)

        logger.info(f"Markdown report written to {report_file}")
