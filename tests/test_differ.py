"""Tests for differ module."""

from pathlib import Path

import pytest

from ghaw_auditor.differ import Differ
from ghaw_auditor.models import (
    ActionInput,
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


def test_diff_actions_detects_modified_manifest(tmp_path: Path) -> None:
    """Two different manifests under one key must report as modified.

    A key can stay stable while the manifest changes (a mutable tag repointed
    upstream, a local action edited in place). Hardcoding "unchanged" made that
    supply-chain drift invisible — the exact thing a baseline diff is for.
    """
    differ = Differ(tmp_path / "baseline")

    old = ActionManifest(name="Act", description="before", is_docker=False)
    new = ActionManifest(name="Act", description="after", is_docker=True)

    diffs = differ.diff_actions({"actions/x@v1": old}, {"actions/x@v1": new})

    assert len(diffs) == 1
    assert diffs[0].status == "modified"

    changed_fields = {c.field for c in diffs[0].changes}
    assert "description" in changed_fields
    assert "is_docker" in changed_fields


def test_diff_actions_detects_changed_inputs(tmp_path: Path) -> None:
    """A manifest gaining an input under a stable key is a modification."""
    differ = Differ(tmp_path / "baseline")

    old = ActionManifest(name="Act")
    new = ActionManifest(name="Act", inputs={"token": ActionInput(name="token", required=True)})

    diffs = differ.diff_actions({"actions/x@v1": old}, {"actions/x@v1": new})

    assert diffs[0].status == "modified"
    assert any(c.field == "inputs" for c in diffs[0].changes)


def test_render_diff_markdown_includes_modified_actions(tmp_path: Path) -> None:
    """Modified actions must appear in the rendered diff report.

    The renderer previously listed only added and removed, so even a correctly
    detected modification would not reach the reader.
    """
    differ = Differ(tmp_path / "baseline")
    old = ActionManifest(name="Act", description="before")
    new = ActionManifest(name="Act", description="after")

    action_diffs = differ.diff_actions({"actions/x@v1": old}, {"actions/x@v1": new})
    report = tmp_path / "report.md"
    differ.render_diff_markdown([], action_diffs, report)

    text = report.read_text()
    assert "Modified Actions" in text
    assert "actions/x@v1" in text
    assert "before" in text
    assert "after" in text


def test_diff_report_renders_changes_with_a_none_side(tmp_path: Path) -> None:
    """A field that only exists on one side renders just that side.

    permissions going from absent to declared yields old_value=None; the
    renderer must skip the Old line rather than print `None`.
    """
    differ = Differ(tmp_path / "baseline")

    old_wf = WorkflowMeta(name="W", path="w.yml", triggers=["push"], jobs={})
    new_wf = WorkflowMeta(
        name="W",
        path="w.yml",
        triggers=["push"],
        permissions=Permissions(contents=PermissionLevel.READ),
        jobs={},
    )
    workflow_diffs = differ.diff_workflows({"w.yml": old_wf}, {"w.yml": new_wf})

    old_act = ActionManifest(name="A", description="here")
    new_act = ActionManifest(name="A")  # description drops to None
    action_diffs = differ.diff_actions({"a@v1": old_act}, {"a@v1": new_act})

    report = tmp_path / "r.md"
    differ.render_diff_markdown(workflow_diffs, action_diffs, report)
    text = report.read_text()

    assert "Modified Workflows" in text
    assert "Modified Actions" in text
    assert "- New: `None`" not in text
    assert "- Old: `None`" not in text


def test_diff_report_renders_changes_with_the_opposite_none_side(tmp_path: Path) -> None:
    """The mirror of the previous test: value removed, and value added.

    Covers the remaining arms — a workflow field whose new_value is None
    (permissions removed) and an action field whose old_value is None
    (description added).
    """
    differ = Differ(tmp_path / "baseline")

    # Workflow: permissions declared -> removed, so new_value is None.
    old_wf = WorkflowMeta(
        name="W",
        path="w.yml",
        triggers=["push"],
        permissions=Permissions(contents=PermissionLevel.READ),
        jobs={},
    )
    new_wf = WorkflowMeta(name="W", path="w.yml", triggers=["push"], jobs={})
    workflow_diffs = differ.diff_workflows({"w.yml": old_wf}, {"w.yml": new_wf})

    # Action: description absent -> added, so old_value is None.
    old_act = ActionManifest(name="A")
    new_act = ActionManifest(name="A", description="now documented")
    action_diffs = differ.diff_actions({"a@v1": old_act}, {"a@v1": new_act})

    report = tmp_path / "r.md"
    differ.render_diff_markdown(workflow_diffs, action_diffs, report)
    text = report.read_text()

    assert "Modified Workflows" in text
    assert "Modified Actions" in text
    assert "now documented" in text
    assert "`None`" not in text


def test_diff_actions_detects_branding_only_change(tmp_path: Path) -> None:
    """A branding-only manifest change is a modification, not "unchanged"."""
    differ = Differ(tmp_path / "baseline")

    old = ActionManifest(name="A", branding={"icon": "check", "color": "green"})
    new = ActionManifest(name="A", branding={"icon": "x", "color": "red"})

    diffs = differ.diff_actions({"a@v1": old}, {"a@v1": new})

    assert diffs[0].status == "modified"
    assert any(c.field == "branding" for c in diffs[0].changes)


def test_diff_actions_detects_change_within_an_existing_input(tmp_path: Path) -> None:
    """Changing an existing input's definition must show distinct old and new.

    Storing only the key set left the report showing identical old and new
    values whenever the key set was unchanged.
    """
    differ = Differ(tmp_path / "baseline")

    old = ActionManifest(name="A", inputs={"token": ActionInput(name="token", required=False)})
    new = ActionManifest(name="A", inputs={"token": ActionInput(name="token", required=True)})

    diffs = differ.diff_actions({"a@v1": old}, {"a@v1": new})

    assert diffs[0].status == "modified"
    change = next(c for c in diffs[0].changes if c.field == "inputs")
    assert change.old_value != change.new_value
    assert change.old_value["token"]["required"] is False
    assert change.new_value["token"]["required"] is True
