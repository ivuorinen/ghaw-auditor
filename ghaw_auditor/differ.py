"""Diff functionality for comparing baselines."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ghaw_auditor.models import (
    ActionDiff,
    ActionManifest,
    Baseline,
    BaselineMeta,
    DiffEntry,
    WorkflowDiff,
    WorkflowMeta,
)

logger = logging.getLogger(__name__)


class Differ:
    """Compares current state against baseline."""

    def __init__(self, baseline_path: Path) -> None:
        """Initialize differ."""
        self.baseline_path = baseline_path

    def load_baseline(self) -> Baseline:
        """Load baseline from disk."""
        actions_file = self.baseline_path / "actions.json"
        workflows_file = self.baseline_path / "workflows.json"
        meta_file = self.baseline_path / "meta.json"

        if not actions_file.exists() or not workflows_file.exists():
            raise FileNotFoundError(f"Baseline not found at {self.baseline_path}")

        with open(actions_file, encoding="utf-8") as f:
            actions_data = json.load(f)

        with open(workflows_file, encoding="utf-8") as f:
            workflows_data = json.load(f)

        meta = BaselineMeta(auditor_version="1.0.0", commit_sha=None, timestamp=datetime.now())
        if meta_file.exists():
            with open(meta_file, encoding="utf-8") as f:
                meta_data = json.load(f)
                meta = BaselineMeta(**meta_data)

        # Convert dicts to model instances
        actions = {k: ActionManifest(**v) for k, v in actions_data.items()}
        workflows = {k: WorkflowMeta(**v) for k, v in workflows_data.items()}

        return Baseline(meta=meta, actions=actions, workflows=workflows)

    def save_baseline(
        self, workflows: dict[str, WorkflowMeta], actions: dict[str, ActionManifest], commit_sha: str | None = None
    ) -> None:
        """Save current state as baseline."""
        self.baseline_path.mkdir(parents=True, exist_ok=True)

        # Save actions
        actions_data = {k: v.model_dump(mode="json") for k, v in actions.items()}
        with open(self.baseline_path / "actions.json", "w", encoding="utf-8") as f:
            json.dump(actions_data, f, indent=2, default=str)

        # Save workflows
        workflows_data = {k: v.model_dump(mode="json") for k, v in workflows.items()}
        with open(self.baseline_path / "workflows.json", "w", encoding="utf-8") as f:
            json.dump(workflows_data, f, indent=2, default=str)

        # Save metadata
        meta = BaselineMeta(auditor_version="1.0.0", commit_sha=commit_sha, timestamp=datetime.now())
        with open(self.baseline_path / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta.model_dump(mode="json"), f, indent=2, default=str)

        logger.info(f"Baseline saved to {self.baseline_path}")

    def diff_workflows(self, baseline: dict[str, WorkflowMeta], current: dict[str, WorkflowMeta]) -> list[WorkflowDiff]:
        """Compare workflows."""
        diffs: list[WorkflowDiff] = []

        all_paths = set(baseline.keys()) | set(current.keys())

        for path in all_paths:
            baseline_wf = baseline.get(path)
            current_wf = current.get(path)

            if baseline_wf is None:
                # `path` comes from the union of both key sets, so absent from
                # the baseline means present in current: added.
                diffs.append(WorkflowDiff(path=path, status="added", changes=[]))
            elif current_wf is None:
                # Removed
                diffs.append(WorkflowDiff(path=path, status="removed", changes=[]))
            else:
                # Present in both; both names are narrowed to non-None here.
                changes = self._compare_workflows(baseline_wf, current_wf)
                status = "modified" if changes else "unchanged"
                diffs.append(WorkflowDiff(path=path, status=status, changes=changes))

        return diffs

    def _compare_workflows(self, old: WorkflowMeta, new: WorkflowMeta) -> list[DiffEntry]:
        """Compare two workflows."""
        changes: list[DiffEntry] = []

        # Compare triggers
        if set(old.triggers) != set(new.triggers):
            changes.append(
                DiffEntry(field="triggers", old_value=old.triggers, new_value=new.triggers, change_type="modified")
            )

        # Compare permissions
        if old.permissions != new.permissions:
            changes.append(
                DiffEntry(
                    field="permissions",
                    old_value=old.permissions.model_dump() if old.permissions else None,
                    new_value=new.permissions.model_dump() if new.permissions else None,
                    change_type="modified",
                )
            )

        # Compare concurrency
        if old.concurrency != new.concurrency:
            changes.append(
                DiffEntry(
                    field="concurrency", old_value=old.concurrency, new_value=new.concurrency, change_type="modified"
                )
            )

        # Compare jobs
        if set(old.jobs.keys()) != set(new.jobs.keys()):
            changes.append(
                DiffEntry(
                    field="jobs",
                    old_value=list(old.jobs.keys()),
                    new_value=list(new.jobs.keys()),
                    change_type="modified",
                )
            )

        # Compare secrets
        if old.secrets_used != new.secrets_used:
            changes.append(
                DiffEntry(
                    field="secrets_used",
                    old_value=sorted(old.secrets_used),
                    new_value=sorted(new.secrets_used),
                    change_type="modified",
                )
            )

        return changes

    def diff_actions(self, baseline: dict[str, ActionManifest], current: dict[str, ActionManifest]) -> list[ActionDiff]:
        """Compare actions."""
        diffs: list[ActionDiff] = []

        all_keys = set(baseline.keys()) | set(current.keys())

        for key in all_keys:
            baseline_action = baseline.get(key)
            current_action = current.get(key)

            if baseline_action is None:
                # `key` comes from the union of both key sets, so absent from
                # the baseline means present in current: added.
                diffs.append(ActionDiff(key=key, status="added", changes=[]))
            elif current_action is None:
                # Removed
                diffs.append(ActionDiff(key=key, status="removed", changes=[]))
            else:
                # Present in both; both names are narrowed to non-None here.
                changes = self._compare_actions(baseline_action, current_action)
                status = "modified" if changes else "unchanged"
                diffs.append(ActionDiff(key=key, status=status, changes=changes))

        return diffs

    def _compare_actions(self, old: ActionManifest, new: ActionManifest) -> list[DiffEntry]:
        """Compare two action manifests sharing a key.

        A key can stay stable while the manifest behind it changes — a mutable
        tag repointed upstream, or a local action edited in place. That is the
        supply-chain drift a baseline diff exists to catch.
        """
        changes: list[DiffEntry] = []

        for field in ("name", "description", "author", "runs", "is_composite", "is_docker", "is_javascript"):
            old_value = getattr(old, field)
            new_value = getattr(new, field)
            if old_value != new_value:
                changes.append(DiffEntry(field=field, old_value=old_value, new_value=new_value, change_type="modified"))

        for field in ("inputs", "outputs"):
            old_items = {k: v.model_dump(mode="json") for k, v in getattr(old, field).items()}
            new_items = {k: v.model_dump(mode="json") for k, v in getattr(new, field).items()}
            if old_items != new_items:
                changes.append(
                    DiffEntry(
                        field=field,
                        old_value=sorted(old_items),
                        new_value=sorted(new_items),
                        change_type="modified",
                    )
                )

        return changes

    def _write_workflow_changes(self, f: Any, workflow_diffs: list[WorkflowDiff]) -> None:
        """Write workflow changes section to markdown file."""
        f.write("## Workflow Changes\n\n")

        added_wfs = [d for d in workflow_diffs if d.status == "added"]
        removed_wfs = [d for d in workflow_diffs if d.status == "removed"]
        modified_wfs = [d for d in workflow_diffs if d.status == "modified"]

        f.write(f"- **Added:** {len(added_wfs)}\n")
        f.write(f"- **Removed:** {len(removed_wfs)}\n")
        f.write(f"- **Modified:** {len(modified_wfs)}\n\n")

        if added_wfs:
            f.write("### Added Workflows\n\n")
            for diff in added_wfs:
                f.write(f"- `{diff.path}`\n")
            f.write("\n")

        if removed_wfs:
            f.write("### Removed Workflows\n\n")
            for diff in removed_wfs:
                f.write(f"- `{diff.path}`\n")
            f.write("\n")

        if modified_wfs:
            f.write("### Modified Workflows\n\n")
            for diff in modified_wfs:
                f.write(f"#### {diff.path}\n\n")
                for change in diff.changes:
                    f.write(f"- **{change.field}** changed\n")
                    if change.old_value is not None:
                        f.write(f"  - Old: `{change.old_value}`\n")
                    if change.new_value is not None:
                        f.write(f"  - New: `{change.new_value}`\n")
                f.write("\n")

    def _write_action_changes(self, f: Any, action_diffs: list[ActionDiff]) -> None:
        """Write action changes section to markdown file."""
        f.write("## Action Changes\n\n")

        added_actions = [d for d in action_diffs if d.status == "added"]
        removed_actions = [d for d in action_diffs if d.status == "removed"]
        modified_actions = [d for d in action_diffs if d.status == "modified"]

        f.write(f"- **Added:** {len(added_actions)}\n")
        f.write(f"- **Removed:** {len(removed_actions)}\n")
        f.write(f"- **Modified:** {len(modified_actions)}\n\n")

        if added_actions:
            f.write("### Added Actions\n\n")
            for diff in added_actions:
                f.write(f"- `{diff.key}`\n")
            f.write("\n")

        if removed_actions:
            f.write("### Removed Actions\n\n")
            for diff in removed_actions:
                f.write(f"- `{diff.key}`\n")
            f.write("\n")

        if modified_actions:
            f.write("### Modified Actions\n\n")
            for diff in modified_actions:
                f.write(f"#### {diff.key}\n\n")
                for change in diff.changes:
                    f.write(f"- **{change.field}** changed\n")
                    if change.old_value is not None:
                        f.write(f"  - Old: `{change.old_value}`\n")
                    if change.new_value is not None:
                        f.write(f"  - New: `{change.new_value}`\n")
                f.write("\n")

    def render_diff_markdown(
        self, workflow_diffs: list[WorkflowDiff], action_diffs: list[ActionDiff], output_path: Path
    ) -> None:
        """Render diff as Markdown."""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("# Audit Diff Report\n\n")
            f.write(f"**Generated:** {datetime.now().isoformat()}\n\n")

            self._write_workflow_changes(f, workflow_diffs)
            self._write_action_changes(f, action_diffs)

        logger.info(f"Diff report written to {output_path}")
