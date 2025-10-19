"""Tests for renderer."""

import json
from pathlib import Path

from ghaw_auditor.models import ActionManifest, JobMeta, WorkflowMeta
from ghaw_auditor.renderer import Renderer


def test_renderer_initialization(tmp_path: Path) -> None:
    """Test renderer initialization."""
    renderer = Renderer(tmp_path)
    assert renderer.output_dir == tmp_path
    assert renderer.output_dir.exists()


def test_render_json(tmp_path: Path) -> None:
    """Test JSON rendering."""
    renderer = Renderer(tmp_path)

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

    violations = [
        {
            "workflow": "test.yml",
            "rule": "test_rule",
            "severity": "error",
            "message": "Test violation",
        }
    ]

    renderer.render_json(workflows, actions, violations)

    # Check files exist
    assert (tmp_path / "workflows.json").exists()
    assert (tmp_path / "actions.json").exists()
    assert (tmp_path / "violations.json").exists()

    # Verify JSON content
    with open(tmp_path / "workflows.json") as f:
        data = json.load(f)
        assert "test.yml" in data
        assert data["test.yml"]["name"] == "Test"

    with open(tmp_path / "actions.json") as f:
        data = json.load(f)
        assert "actions/checkout@v4" in data

    with open(tmp_path / "violations.json") as f:
        data = json.load(f)
        assert len(data) == 1
        assert data[0]["rule"] == "test_rule"


def test_render_markdown(tmp_path: Path) -> None:
    """Test Markdown rendering."""
    renderer = Renderer(tmp_path)

    workflows = {
        "test.yml": WorkflowMeta(
            name="Test Workflow",
            path="test.yml",
            triggers=["push", "pull_request"],
            jobs={"test": JobMeta(name="test", runs_on="ubuntu-latest")},
        )
    }

    actions = {
        "actions/checkout@v4": ActionManifest(
            name="Checkout",
            description="Checkout repository",
        )
    }

    violations = [
        {
            "workflow": "test.yml",
            "rule": "require_pinned_actions",
            "severity": "error",
            "message": "Action not pinned to SHA",
        }
    ]

    analysis = {
        "total_jobs": 1,
        "reusable_workflows": 0,
        "triggers": {"push": 1, "pull_request": 1},
        "runners": {"ubuntu-latest": 1},
        "secrets": {"total_unique_secrets": 0, "secrets": []},
    }

    renderer.render_markdown(workflows, actions, violations, analysis)

    report_file = tmp_path / "report.md"
    assert report_file.exists()

    content = report_file.read_text()
    assert "# GitHub Actions & Workflows Audit Report" in content
    assert "Test Workflow" in content
    assert "Checkout" in content
    assert "require_pinned_actions" in content
    assert "push" in content
    assert "pull_request" in content


def test_render_empty_data(tmp_path: Path) -> None:
    """Test rendering with empty data."""
    renderer = Renderer(tmp_path)

    renderer.render_json({}, {}, [])

    assert (tmp_path / "workflows.json").exists()
    assert (tmp_path / "actions.json").exists()
    assert (tmp_path / "violations.json").exists()

    with open(tmp_path / "workflows.json") as f:
        assert json.load(f) == {}

    with open(tmp_path / "violations.json") as f:
        assert json.load(f) == []


def test_render_markdown_with_actions_used(tmp_path: Path) -> None:
    """Test Markdown rendering with job actions_used."""
    from ghaw_auditor.models import ActionRef, ActionType

    renderer = Renderer(tmp_path)

    # Create a job with actions_used
    action_ref = ActionRef(
        type=ActionType.GITHUB,
        owner="actions",
        repo="checkout",
        ref="v4",
        source_file="test.yml",
    )

    job = JobMeta(
        name="test",
        runs_on="ubuntu-latest",
        actions_used=[action_ref],
    )

    workflows = {
        "test.yml": WorkflowMeta(
            name="Test Workflow",
            path="test.yml",
            triggers=["push"],
            jobs={"test": job},
        )
    }

    renderer.render_markdown(workflows, {}, [], {})

    report_file = tmp_path / "report.md"
    assert report_file.exists()

    content = report_file.read_text()
    # Should render the actions used with link
    assert "Actions used:" in content
    assert "[actions/checkout](#actions-checkout)" in content


def test_render_markdown_with_secrets(tmp_path: Path) -> None:
    """Test Markdown rendering with secrets."""
    renderer = Renderer(tmp_path)

    workflows = {
        "test.yml": WorkflowMeta(
            name="Test Workflow",
            path="test.yml",
            triggers=["push"],
            jobs={},
        )
    }

    analysis = {
        "total_jobs": 0,
        "reusable_workflows": 0,
        "secrets": {
            "total_unique_secrets": 2,
            "secrets": ["API_KEY", "DATABASE_URL"],
        },
    }

    renderer.render_markdown(workflows, {}, [], analysis)

    report_file = tmp_path / "report.md"
    content = report_file.read_text()

    # Should render secrets
    assert "API_KEY" in content
    assert "DATABASE_URL" in content


def test_render_markdown_with_action_inputs(tmp_path: Path) -> None:
    """Test Markdown rendering with action inputs."""
    from ghaw_auditor.models import ActionInput

    renderer = Renderer(tmp_path)

    action = ActionManifest(
        name="Test Action",
        description="A test action",
        inputs={
            "token": ActionInput(
                name="token",
                description="GitHub token",
                required=True,
            ),
            "debug": ActionInput(
                name="debug",
                description="Enable debug mode",
                required=False,
            ),
        },
    )

    renderer.render_markdown({}, {"test/action@v1": action}, [], {})

    report_file = tmp_path / "report.md"
    content = report_file.read_text()

    # Should render inputs with required/optional status
    assert "token" in content
    assert "required" in content
    assert "debug" in content
    assert "optional" in content
    assert "GitHub token" in content
    assert "Enable debug mode" in content


def test_render_markdown_with_action_anchors(tmp_path: Path) -> None:
    """Test that action anchors are created for linking."""
    from ghaw_auditor.models import ActionRef, ActionType

    renderer = Renderer(tmp_path)

    action_ref = ActionRef(
        type=ActionType.GITHUB,
        owner="actions",
        repo="checkout",
        ref="v4",
        resolved_sha="abc123",
        source_file="test.yml",
    )

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={},
        actions_used=[action_ref],
    )

    action = ActionManifest(
        name="Checkout",
        description="Checkout code",
    )

    renderer.render_markdown({"test.yml": workflow}, {"actions/checkout@abc123": action}, [], {})

    report_file = tmp_path / "report.md"
    content = report_file.read_text()

    # Should have anchor tag
    assert '<a id="actions-checkout"></a>' in content


def test_render_markdown_with_repo_urls(tmp_path: Path) -> None:
    """Test that GitHub action repository URLs are included."""
    from ghaw_auditor.models import ActionRef, ActionType

    renderer = Renderer(tmp_path)

    action_ref = ActionRef(
        type=ActionType.GITHUB,
        owner="actions",
        repo="setup-node",
        ref="v4",
        resolved_sha="def456",
        source_file="test.yml",
    )

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={},
        actions_used=[action_ref],
    )

    action = ActionManifest(
        name="Setup Node",
        description="Setup Node.js",
    )

    renderer.render_markdown({"test.yml": workflow}, {"actions/setup-node@def456": action}, [], {})

    report_file = tmp_path / "report.md"
    content = report_file.read_text()

    # Should have repository link
    assert "https://github.com/actions/setup-node" in content
    assert "[actions/setup-node](https://github.com/actions/setup-node)" in content


def test_render_markdown_with_details_tags(tmp_path: Path) -> None:
    """Test that inputs are wrapped in details tags."""
    from ghaw_auditor.models import ActionInput, ActionRef, ActionType

    renderer = Renderer(tmp_path)

    action_ref = ActionRef(
        type=ActionType.GITHUB,
        owner="actions",
        repo="checkout",
        ref="v4",
        source_file="test.yml",
    )

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={},
        actions_used=[action_ref],
    )

    action = ActionManifest(
        name="Checkout",
        description="Checkout code",
        inputs={
            "token": ActionInput(
                name="token",
                description="GitHub token",
                required=False,
            ),
        },
    )

    renderer.render_markdown({"test.yml": workflow}, {"actions/checkout@v4": action}, [], {})

    report_file = tmp_path / "report.md"
    content = report_file.read_text()

    # Should have details tags
    assert "<details>" in content
    assert "<summary><b>Inputs</b></summary>" in content
    assert "</details>" in content


def test_render_markdown_with_job_action_links(tmp_path: Path) -> None:
    """Test that job actions are linked to inventory."""
    from ghaw_auditor.models import ActionRef, ActionType

    renderer = Renderer(tmp_path)

    action_ref = ActionRef(
        type=ActionType.GITHUB,
        owner="actions",
        repo="checkout",
        ref="v4",
        source_file="test.yml",
    )

    job = JobMeta(
        name="test",
        runs_on="ubuntu-latest",
        actions_used=[action_ref],
    )

    workflow = WorkflowMeta(
        name="CI",
        path="ci.yml",
        triggers=["push"],
        jobs={"test": job},
        actions_used=[action_ref],
    )

    action = ActionManifest(
        name="Checkout",
        description="Checkout code",
    )

    renderer.render_markdown({"ci.yml": workflow}, {"actions/checkout@v4": action}, [], {})

    report_file = tmp_path / "report.md"
    content = report_file.read_text()

    # Should have action link in jobs section
    assert "Actions used:" in content
    assert "[actions/checkout](#actions-checkout) (GitHub)" in content


def test_create_action_anchor() -> None:
    """Test anchor creation from action keys."""
    # GitHub action
    assert Renderer._create_action_anchor("actions/checkout@abc123") == "actions-checkout"

    # Local action
    assert Renderer._create_action_anchor("local:./sync-labels") == "local-sync-labels"

    # Docker action
    assert Renderer._create_action_anchor("docker://alpine:3.8") == "docker-alpine-3-8"

    # Long SHA
    assert (
        Renderer._create_action_anchor("actions/setup-node@1234567890abcdef1234567890abcdef12345678")
        == "actions-setup-node"
    )


def test_get_action_repo_url() -> None:
    """Test repository URL generation."""
    from ghaw_auditor.models import ActionRef, ActionType

    # GitHub action
    github_action = ActionRef(
        type=ActionType.GITHUB,
        owner="actions",
        repo="checkout",
        ref="v4",
        source_file="test.yml",
    )
    assert Renderer._get_action_repo_url(github_action) == "https://github.com/actions/checkout"

    # Local action (no URL)
    local_action = ActionRef(
        type=ActionType.LOCAL,
        path="./my-action",
        source_file="test.yml",
    )
    assert Renderer._get_action_repo_url(local_action) is None

    # Docker action (no URL)
    docker_action = ActionRef(
        type=ActionType.DOCKER,
        path="docker://alpine:3.8",
        source_file="test.yml",
    )
    assert Renderer._get_action_repo_url(docker_action) is None


def test_render_markdown_with_docker_action(tmp_path: Path) -> None:
    """Test Markdown rendering with Docker action in jobs."""
    from ghaw_auditor.models import ActionRef, ActionType

    renderer = Renderer(tmp_path)

    docker_action = ActionRef(
        type=ActionType.DOCKER,
        path="docker://alpine:3.8",
        source_file="test.yml",
    )

    job = JobMeta(
        name="test",
        runs_on="ubuntu-latest",
        actions_used=[docker_action],
    )

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={"test": job},
    )

    renderer.render_markdown({"test.yml": workflow}, {}, [], {})

    report_file = tmp_path / "report.md"
    content = report_file.read_text()

    # Should show Docker action with correct type label
    assert "Actions used:" in content
    assert "(Docker)" in content
    assert "docker://alpine:3.8" in content


def test_render_markdown_with_reusable_workflow(tmp_path: Path) -> None:
    """Test Markdown rendering with reusable workflow in jobs."""
    from ghaw_auditor.models import ActionRef, ActionType

    renderer = Renderer(tmp_path)

    reusable_wf = ActionRef(
        type=ActionType.REUSABLE_WORKFLOW,
        owner="org",
        repo="workflows",
        path=".github/workflows/reusable.yml",
        ref="main",
        source_file="test.yml",
    )

    job = JobMeta(
        name="test",
        runs_on="ubuntu-latest",
        actions_used=[reusable_wf],
    )

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={"test": job},
    )

    renderer.render_markdown({"test.yml": workflow}, {}, [], {})

    report_file = tmp_path / "report.md"
    content = report_file.read_text()

    # Should show reusable workflow with correct type label
    assert "Actions used:" in content
    assert "(Reusable Workflow)" in content
    assert ".github/workflows/reusable.yml" in content


def test_render_markdown_with_docker_action_in_inventory(tmp_path: Path) -> None:
    """Test Markdown rendering with Docker action in inventory."""
    from ghaw_auditor.models import ActionRef, ActionType

    renderer = Renderer(tmp_path)

    docker_action_ref = ActionRef(
        type=ActionType.DOCKER,
        path="docker://node:18-alpine",
        source_file="test.yml",
    )

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={},
        actions_used=[docker_action_ref],
    )

    action_manifest = ActionManifest(
        name="Node Alpine",
        description="Node.js on Alpine Linux",
    )

    renderer.render_markdown({"test.yml": workflow}, {"docker:docker://node:18-alpine": action_manifest}, [], {})

    report_file = tmp_path / "report.md"
    content = report_file.read_text()

    # Docker actions shouldn't have repository links or Local Action type
    assert "**Repository:**" not in content or "node:18-alpine" not in content
    assert "Node Alpine" in content


def test_render_markdown_with_local_action_without_path(tmp_path: Path) -> None:
    """Test Markdown rendering with LOCAL action that has no path."""
    from ghaw_auditor.models import ActionRef, ActionType

    renderer = Renderer(tmp_path)

    local_action = ActionRef(
        type=ActionType.LOCAL,
        path=None,
        source_file="test.yml",
    )

    job = JobMeta(
        name="test",
        runs_on="ubuntu-latest",
        actions_used=[local_action],
    )

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={"test": job},
    )

    renderer.render_markdown({"test.yml": workflow}, {}, [], {})

    report_file = tmp_path / "report.md"
    content = report_file.read_text()

    # Should show "local" as display name when path is None
    assert "Actions used:" in content
    assert "[local](#local-none) (Local)" in content


def test_render_markdown_with_local_action_in_inventory(tmp_path: Path) -> None:
    """Test Markdown rendering with LOCAL action in inventory showing Type label."""
    from ghaw_auditor.models import ActionRef, ActionType

    renderer = Renderer(tmp_path)

    local_action_ref = ActionRef(
        type=ActionType.LOCAL,
        path="./my-custom-action",
        source_file="test.yml",
    )

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={},
        actions_used=[local_action_ref],
    )

    action_manifest = ActionManifest(
        name="My Custom Action",
        description="A custom local action",
    )

    renderer.render_markdown({"test.yml": workflow}, {"local:./my-custom-action": action_manifest}, [], {})

    report_file = tmp_path / "report.md"
    content = report_file.read_text()

    # Local actions should have "Type: Local Action" label
    assert "**Type:** Local Action" in content
    assert "My Custom Action" in content


def test_render_markdown_with_job_permissions(tmp_path: Path) -> None:
    """Test Markdown rendering with job permissions."""
    from ghaw_auditor.models import PermissionLevel, Permissions

    renderer = Renderer(tmp_path)

    job = JobMeta(
        name="test",
        runs_on="ubuntu-latest",
        permissions=Permissions(
            contents=PermissionLevel.READ,
            issues=PermissionLevel.WRITE,
            security_events=PermissionLevel.WRITE,
        ),
    )

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={"test": job},
    )

    renderer.render_markdown({"test.yml": workflow}, {}, [], {})

    report_file = tmp_path / "report.md"
    content = report_file.read_text()

    # Should show permissions
    assert "Permissions:" in content
    assert "`contents`: read" in content
    assert "`issues`: write" in content
    assert "`security-events`: write" in content


def test_render_markdown_without_job_permissions(tmp_path: Path) -> None:
    """Test Markdown rendering with job that has no permissions set."""
    renderer = Renderer(tmp_path)

    job = JobMeta(
        name="test",
        runs_on="ubuntu-latest",
        permissions=None,
    )

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={"test": job},
    )

    renderer.render_markdown({"test.yml": workflow}, {}, [], {})

    report_file = tmp_path / "report.md"
    content = report_file.read_text()

    # Should not show permissions section
    assert "Permissions:" not in content


def test_render_markdown_with_workflows_using_action(tmp_path: Path) -> None:
    """Test that actions show which workflows use them."""
    from ghaw_auditor.models import ActionRef, ActionType

    renderer = Renderer(tmp_path)

    # Create an action reference
    action_ref = ActionRef(
        type=ActionType.GITHUB,
        owner="actions",
        repo="checkout",
        ref="v4",
        source_file=".github/workflows/ci.yml",
    )

    # Create two workflows that use the same action
    workflow1 = WorkflowMeta(
        name="CI Workflow",
        path=".github/workflows/ci.yml",
        triggers=["push"],
        actions_used=[action_ref],
    )

    workflow2 = WorkflowMeta(
        name="Deploy Workflow",
        path=".github/workflows/deploy.yml",
        triggers=["push"],
        actions_used=[action_ref],
    )

    # Create the action manifest
    action = ActionManifest(
        name="Checkout",
        description="Checkout repository",
    )

    workflows = {
        ".github/workflows/ci.yml": workflow1,
        ".github/workflows/deploy.yml": workflow2,
    }
    actions = {"actions/checkout@v4": action}

    renderer.render_markdown(workflows, actions, [], {})

    report_file = tmp_path / "report.md"
    content = report_file.read_text()

    # Should show "Used in Workflows" section
    assert "Used in Workflows" in content
    assert "CI Workflow" in content
    assert "Deploy Workflow" in content
    assert ".github/workflows/ci.yml" in content
    assert ".github/workflows/deploy.yml" in content
    # Should have links to workflow sections
    assert "[CI Workflow](#ci-workflow)" in content
    assert "[Deploy Workflow](#deploy-workflow)" in content
