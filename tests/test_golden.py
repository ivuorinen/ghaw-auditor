"""Golden file tests for reports."""

import json
from pathlib import Path

from ghaw_auditor.models import (
    ActionInput,
    ActionManifest,
    JobMeta,
    WorkflowMeta,
)
from ghaw_auditor.renderer import Renderer


def test_json_workflow_output(tmp_path: Path) -> None:
    """Test workflow JSON matches golden file."""
    renderer = Renderer(tmp_path)

    workflows = {
        "test.yml": WorkflowMeta(
            name="Test Workflow",
            path="test.yml",
            triggers=["push", "pull_request"],
            jobs={
                "test": JobMeta(
                    name="test",
                    runs_on="ubuntu-latest",
                    secrets_used={"GITHUB_TOKEN"},
                )
            },
            secrets_used={"GITHUB_TOKEN"},
        )
    }

    renderer.render_json(workflows, {}, [])

    # Load generated and golden files
    with open(tmp_path / "workflows.json") as f:
        generated = json.load(f)

    golden_path = Path(__file__).parent / "golden" / "workflows.json"
    with open(golden_path) as f:
        golden = json.load(f)

    # Compare structure (ignoring list order differences)
    assert generated["test.yml"]["name"] == golden["test.yml"]["name"]
    assert set(generated["test.yml"]["triggers"]) == set(golden["test.yml"]["triggers"])
    assert generated["test.yml"]["jobs"]["test"]["runs_on"] == golden["test.yml"]["jobs"]["test"]["runs_on"]


def test_json_action_output(tmp_path: Path) -> None:
    """Test action JSON matches golden file."""
    renderer = Renderer(tmp_path)

    actions = {
        "actions/checkout@abc123": ActionManifest(
            name="Checkout",
            description="Checkout a Git repository",
            author="GitHub",
            inputs={
                "repository": ActionInput(
                    name="repository",
                    description="Repository name with owner",
                    required=False,
                ),
                "ref": ActionInput(
                    name="ref",
                    description="The branch, tag or SHA to checkout",
                    required=False,
                ),
            },
            runs={"using": "node20", "main": "dist/index.js"},
            is_javascript=True,
        )
    }

    renderer.render_json({}, actions, [])

    with open(tmp_path / "actions.json") as f:
        generated = json.load(f)

    golden_path = Path(__file__).parent / "golden" / "actions.json"
    with open(golden_path) as f:
        golden = json.load(f)

    assert generated["actions/checkout@abc123"]["name"] == golden["actions/checkout@abc123"]["name"]
    assert generated["actions/checkout@abc123"]["is_javascript"] is True


def test_markdown_report_structure(tmp_path: Path) -> None:
    """Test markdown report structure."""
    renderer = Renderer(tmp_path)

    workflows = {
        "test.yml": WorkflowMeta(
            name="Test Workflow",
            path="test.yml",
            triggers=["push", "pull_request"],
            jobs={
                "test": JobMeta(
                    name="test",
                    runs_on="ubuntu-latest",
                    secrets_used={"GITHUB_TOKEN"},
                )
            },
            secrets_used={"GITHUB_TOKEN"},
        )
    }

    actions = {
        "actions/checkout@abc123": ActionManifest(
            name="Checkout",
            description="Checkout a Git repository",
            inputs={
                "repository": ActionInput(
                    name="repository",
                    description="Repository name with owner",
                ),
                "ref": ActionInput(
                    name="ref",
                    description="The branch, tag or SHA to checkout",
                ),
            },
        )
    }

    analysis = {
        "total_jobs": 1,
        "reusable_workflows": 0,
        "triggers": {"push": 1, "pull_request": 1},
        "runners": {"ubuntu-latest": 1},
        "secrets": {"total_unique_secrets": 1, "secrets": ["GITHUB_TOKEN"]},
    }

    renderer.render_markdown(workflows, actions, [], analysis)

    with open(tmp_path / "report.md") as f:
        content = f.read()

    # Check key sections exist
    assert "# GitHub Actions & Workflows Audit Report" in content
    assert "## Summary" in content
    assert "## Analysis" in content
    assert "## Workflows" in content
    assert "## Actions Inventory" in content

    # Check specific content
    assert "Test Workflow" in content
    assert "Checkout" in content
    assert "GITHUB_TOKEN" in content
    assert "`ubuntu-latest`" in content


def test_empty_report_generation(tmp_path: Path) -> None:
    """Test report generation with empty data."""
    renderer = Renderer(tmp_path)

    renderer.render_json({}, {}, [])
    renderer.render_markdown({}, {}, [], {})

    # Files should exist even with empty data
    assert (tmp_path / "workflows.json").exists()
    assert (tmp_path / "actions.json").exists()
    assert (tmp_path / "violations.json").exists()
    assert (tmp_path / "report.md").exists()

    with open(tmp_path / "workflows.json") as f:
        assert json.load(f) == {}
