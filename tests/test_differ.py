"""Tests for differ module."""

from pathlib import Path

import pytest

from ghaw_auditor.differ import Differ
from ghaw_auditor.models import (
    ActionManifest,
    JobMeta,
    PermissionLevel,
    Permissions,
    WorkflowMeta,
)


def test_save_and_load_baseline(tmp_path: Path) -> None:
    """Test saving and loading baseline."""
    baseline_path = tmp_path / "baseline"
    differ = Differ(baseline_path)

    # Create sample data
    workflows = {
        "test.yml": WorkflowMeta(
            name="Test",
            path="test.yml",
            triggers=["push"],
            jobs={"test": JobMeta(name="test", runs_on="ubuntu-latest")},
        )
    }
    actions = {
        "actions/checkout@v4": ActionManifest(
            name="Checkout",
            description="Checkout code",
        )
    }

    # Save baseline
    differ.save_baseline(workflows, actions, "abc123")
    assert (baseline_path / "workflows.json").exists()
    assert (baseline_path / "actions.json").exists()
    assert (baseline_path / "meta.json").exists()

    # Load baseline
    baseline = differ.load_baseline()
    assert baseline.meta.commit_sha == "abc123"
    assert len(baseline.workflows) == 1
    assert len(baseline.actions) == 1


def test_diff_workflows(tmp_path: Path) -> None:
    """Test workflow diff."""
    baseline_path = tmp_path / "baseline"
    differ = Differ(baseline_path)

    old_workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={},
    )

    new_workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push", "pull_request"],
        jobs={},
    )

    diffs = differ.diff_workflows({"test.yml": old_workflow}, {"test.yml": new_workflow})

    assert len(diffs) == 1
    assert diffs[0].status == "modified"
    assert len(diffs[0].changes) > 0


def test_diff_added_workflow(tmp_path: Path) -> None:
    """Test added workflow detection."""
    baseline_path = tmp_path / "baseline"
    differ = Differ(baseline_path)

    new_workflow = WorkflowMeta(
        name="New",
        path="new.yml",
        triggers=["push"],
        jobs={},
    )

    diffs = differ.diff_workflows({}, {"new.yml": new_workflow})

    assert len(diffs) == 1
    assert diffs[0].status == "added"
    assert diffs[0].path == "new.yml"


def test_diff_removed_workflow(tmp_path: Path) -> None:
    """Test removed workflow detection."""
    baseline_path = tmp_path / "baseline"
    differ = Differ(baseline_path)

    old_workflow = WorkflowMeta(
        name="Old",
        path="old.yml",
        triggers=["push"],
        jobs={},
    )

    diffs = differ.diff_workflows({"old.yml": old_workflow}, {})

    assert len(diffs) == 1
    assert diffs[0].status == "removed"
    assert diffs[0].path == "old.yml"


def test_load_baseline_not_found(tmp_path: Path) -> None:
    """Test loading baseline when it doesn't exist."""
    baseline_path = tmp_path / "nonexistent"
    differ = Differ(baseline_path)

    with pytest.raises(FileNotFoundError, match="Baseline not found"):
        differ.load_baseline()


def test_load_baseline_without_meta(tmp_path: Path) -> None:
    """Test loading baseline when meta.json doesn't exist."""
    baseline_path = tmp_path / "baseline"
    baseline_path.mkdir()

    # Create only workflows.json and actions.json
    (baseline_path / "workflows.json").write_text("{}")
    (baseline_path / "actions.json").write_text("{}")

    differ = Differ(baseline_path)
    baseline = differ.load_baseline()

    # Should still load with default meta
    assert baseline.meta is not None
    assert baseline.workflows == {}
    assert baseline.actions == {}


def test_diff_workflows_permissions_change(tmp_path: Path) -> None:
    """Test workflow diff with permissions changes."""
    baseline_path = tmp_path / "baseline"
    differ = Differ(baseline_path)

    old_workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        permissions=Permissions(contents=PermissionLevel.READ),
        jobs={},
    )

    new_workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        permissions=Permissions(contents=PermissionLevel.WRITE),
        jobs={},
    )

    diffs = differ.diff_workflows({"test.yml": old_workflow}, {"test.yml": new_workflow})

    assert len(diffs) == 1
    assert diffs[0].status == "modified"
    assert any(c.field == "permissions" for c in diffs[0].changes)


def test_diff_workflows_concurrency_change(tmp_path: Path) -> None:
    """Test workflow diff with concurrency changes."""
    baseline_path = tmp_path / "baseline"
    differ = Differ(baseline_path)

    old_workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        concurrency="group1",
        jobs={},
    )

    new_workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        concurrency="group2",
        jobs={},
    )

    diffs = differ.diff_workflows({"test.yml": old_workflow}, {"test.yml": new_workflow})

    assert len(diffs) == 1
    assert diffs[0].status == "modified"
    assert any(c.field == "concurrency" for c in diffs[0].changes)


def test_diff_workflows_jobs_change(tmp_path: Path) -> None:
    """Test workflow diff with job changes."""
    baseline_path = tmp_path / "baseline"
    differ = Differ(baseline_path)

    old_workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={"build": JobMeta(name="build", runs_on="ubuntu-latest")},
    )

    new_workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={
            "build": JobMeta(name="build", runs_on="ubuntu-latest"),
            "test": JobMeta(name="test", runs_on="ubuntu-latest"),
        },
    )

    diffs = differ.diff_workflows({"test.yml": old_workflow}, {"test.yml": new_workflow})

    assert len(diffs) == 1
    assert diffs[0].status == "modified"
    assert any(c.field == "jobs" for c in diffs[0].changes)


def test_diff_workflows_secrets_change(tmp_path: Path) -> None:
    """Test workflow diff with secrets changes."""
    baseline_path = tmp_path / "baseline"
    differ = Differ(baseline_path)

    old_workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={},
        secrets_used={"API_KEY"},
    )

    new_workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={},
        secrets_used={"API_KEY", "DATABASE_URL"},
    )

    diffs = differ.diff_workflows({"test.yml": old_workflow}, {"test.yml": new_workflow})

    assert len(diffs) == 1
    assert diffs[0].status == "modified"
    assert any(c.field == "secrets_used" for c in diffs[0].changes)


def test_diff_workflows_unchanged(tmp_path: Path) -> None:
    """Test workflow diff when unchanged."""
    baseline_path = tmp_path / "baseline"
    differ = Differ(baseline_path)

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={},
    )

    diffs = differ.diff_workflows({"test.yml": workflow}, {"test.yml": workflow})

    assert len(diffs) == 1
    assert diffs[0].status == "unchanged"
    assert len(diffs[0].changes) == 0


def test_diff_actions_added(tmp_path: Path) -> None:
    """Test action diff with added action."""
    baseline_path = tmp_path / "baseline"
    differ = Differ(baseline_path)

    new_action = ActionManifest(name="New Action", description="Test")

    diffs = differ.diff_actions({}, {"actions/new@v1": new_action})

    assert len(diffs) == 1
    assert diffs[0].status == "added"
    assert diffs[0].key == "actions/new@v1"


def test_diff_actions_removed(tmp_path: Path) -> None:
    """Test action diff with removed action."""
    baseline_path = tmp_path / "baseline"
    differ = Differ(baseline_path)

    old_action = ActionManifest(name="Old Action", description="Test")

    diffs = differ.diff_actions({"actions/old@v1": old_action}, {})

    assert len(diffs) == 1
    assert diffs[0].status == "removed"
    assert diffs[0].key == "actions/old@v1"


def test_diff_actions_unchanged(tmp_path: Path) -> None:
    """Test action diff when unchanged."""
    baseline_path = tmp_path / "baseline"
    differ = Differ(baseline_path)

    action = ActionManifest(name="Test Action", description="Test")

    diffs = differ.diff_actions({"actions/test@v1": action}, {"actions/test@v1": action})

    assert len(diffs) == 1
    assert diffs[0].status == "unchanged"
    assert len(diffs[0].changes) == 0


def test_render_diff_markdown(tmp_path: Path) -> None:
    """Test rendering diff as Markdown."""
    from ghaw_auditor.models import ActionDiff, DiffEntry, WorkflowDiff

    baseline_path = tmp_path / "baseline"
    differ = Differ(baseline_path)

    workflow_diffs = [
        WorkflowDiff(path="added.yml", status="added", changes=[]),
        WorkflowDiff(path="removed.yml", status="removed", changes=[]),
        WorkflowDiff(
            path="modified.yml",
            status="modified",
            changes=[
                DiffEntry(
                    field="triggers",
                    old_value=["push"],
                    new_value=["push", "pull_request"],
                    change_type="modified",
                )
            ],
        ),
    ]

    action_diffs = [
        ActionDiff(key="actions/new@v1", status="added", changes=[]),
        ActionDiff(key="actions/old@v1", status="removed", changes=[]),
    ]

    output_path = tmp_path / "diff.md"
    differ.render_diff_markdown(workflow_diffs, action_diffs, output_path)

    assert output_path.exists()
    content = output_path.read_text()

    # Check content
    assert "# Audit Diff Report" in content
    assert "## Workflow Changes" in content
    assert "## Action Changes" in content
    assert "added.yml" in content
    assert "removed.yml" in content
    assert "modified.yml" in content
    assert "actions/new@v1" in content
    assert "actions/old@v1" in content
    assert "triggers" in content


def test_render_diff_markdown_empty(tmp_path: Path) -> None:
    """Test rendering empty diff."""
    baseline_path = tmp_path / "baseline"
    differ = Differ(baseline_path)

    output_path = tmp_path / "diff.md"
    differ.render_diff_markdown([], [], output_path)

    assert output_path.exists()
    content = output_path.read_text()

    assert "# Audit Diff Report" in content
    assert "**Added:** 0" in content
    assert "**Removed:** 0" in content
