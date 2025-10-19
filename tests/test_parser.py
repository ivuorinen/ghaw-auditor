"""Tests for parser module."""

from pathlib import Path

import pytest

from ghaw_auditor.models import ActionType, PermissionLevel
from ghaw_auditor.parser import Parser

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_parser_initialization() -> None:
    """Test parser can be initialized."""
    parser = Parser(Path.cwd())
    assert parser.yaml is not None


# ============================================================================
# Workflow Parsing Tests
# ============================================================================


def test_parse_basic_workflow() -> None:
    """Test parsing a basic workflow."""
    parser = Parser(FIXTURES_DIR)
    workflow = parser.parse_workflow(FIXTURES_DIR / "basic-workflow.yml")

    assert workflow.name == "Basic Workflow"
    assert workflow.path == "basic-workflow.yml"
    assert workflow.triggers == ["push"]
    assert "test" in workflow.jobs
    assert workflow.jobs["test"].runs_on == "ubuntu-latest"
    assert len(workflow.jobs["test"].actions_used) == 1
    assert workflow.jobs["test"].actions_used[0].owner == "actions"
    assert workflow.jobs["test"].actions_used[0].repo == "checkout"


def test_parse_complex_workflow() -> None:
    """Test parsing a complex workflow with all features."""
    parser = Parser(FIXTURES_DIR)
    workflow = parser.parse_workflow(FIXTURES_DIR / "complex-workflow.yml")

    # Basic metadata
    assert workflow.name == "Complex Workflow"
    assert set(workflow.triggers) == {"push", "pull_request", "workflow_dispatch"}

    # Permissions
    assert workflow.permissions is not None
    assert workflow.permissions.contents == PermissionLevel.READ
    assert workflow.permissions.issues == PermissionLevel.WRITE
    assert workflow.permissions.pull_requests == PermissionLevel.WRITE

    # Environment variables
    assert workflow.env["NODE_ENV"] == "production"
    assert workflow.env["API_URL"] == "https://api.example.com"

    # Concurrency
    assert workflow.concurrency is not None

    # Defaults
    assert workflow.defaults["run"]["shell"] == "bash"

    # Jobs
    assert "build" in workflow.jobs
    assert "test" in workflow.jobs

    # Build job
    build = workflow.jobs["build"]
    assert build.timeout_minutes == 30
    assert build.permissions is not None
    assert build.environment == {"name": "production", "url": "https://example.com"}

    # Test job
    test = workflow.jobs["test"]
    assert test.needs == ["build"]
    assert test.if_condition == "github.event_name == 'pull_request'"
    assert test.container is not None
    assert test.container.image == "node:20-alpine"
    assert "NODE_ENV" in test.container.env
    assert test.continue_on_error is True

    # Services
    assert "postgres" in test.services
    assert test.services["postgres"].image == "postgres:15"

    # Strategy
    assert test.strategy is not None
    assert test.strategy.fail_fast is False
    assert test.strategy.max_parallel == 2

    # Secrets extraction
    assert "API_KEY" in workflow.secrets_used
    assert "GITHUB_TOKEN" in workflow.secrets_used
    assert "DATABASE_URL" in workflow.secrets_used


def test_parse_reusable_workflow() -> None:
    """Test parsing a reusable workflow."""
    parser = Parser(FIXTURES_DIR)
    workflow = parser.parse_workflow(FIXTURES_DIR / "reusable-workflow.yml")

    assert workflow.is_reusable is True
    assert workflow.reusable_contract is not None

    # Check inputs
    assert "environment" in workflow.reusable_contract.inputs
    assert workflow.reusable_contract.inputs["environment"]["required"] is True
    assert workflow.reusable_contract.inputs["debug"]["default"] is False

    # Check outputs
    assert "deployment-id" in workflow.reusable_contract.outputs

    # Check secrets
    assert "deploy-token" in workflow.reusable_contract.secrets
    assert workflow.reusable_contract.secrets["deploy-token"]["required"] is True


def test_parse_workflow_with_empty_workflow_call() -> None:
    """Test parsing workflow with empty workflow_call."""
    parser = Parser(FIXTURES_DIR)
    workflow = parser.parse_workflow(FIXTURES_DIR / "empty-workflow-call.yml")

    assert workflow.is_reusable is True
    # Empty workflow_call should result in None contract
    assert workflow.reusable_contract is None or workflow.reusable_contract.inputs == {}


def test_parse_empty_workflow() -> None:
    """Test parsing an empty workflow file raises error."""
    parser = Parser(FIXTURES_DIR)

    with pytest.raises(ValueError, match="Empty workflow file"):
        parser.parse_workflow(FIXTURES_DIR / "invalid-workflow.yml")


# ============================================================================
# Action Reference Parsing Tests
# ============================================================================


def test_parse_action_ref_github() -> None:
    """Test parsing GitHub action reference."""
    parser = Parser(Path.cwd())
    ref = parser._parse_action_ref("actions/checkout@v4", Path("test.yml"))

    assert ref.type == ActionType.GITHUB
    assert ref.owner == "actions"
    assert ref.repo == "checkout"
    assert ref.ref == "v4"


def test_parse_action_ref_github_with_path() -> None:
    """Test parsing GitHub action reference with path (monorepo)."""
    parser = Parser(Path.cwd())
    ref = parser._parse_action_ref("owner/repo/path/to/action@v1", Path("test.yml"))

    assert ref.type == ActionType.GITHUB
    assert ref.owner == "owner"
    assert ref.repo == "repo"
    assert ref.path == "path/to/action"
    assert ref.ref == "v1"


def test_parse_action_ref_local() -> None:
    """Test parsing local action reference."""
    parser = Parser(Path.cwd())
    ref = parser._parse_action_ref("./.github/actions/custom", Path("test.yml"))

    assert ref.type == ActionType.LOCAL
    assert ref.path == "./.github/actions/custom"


def test_parse_action_ref_docker() -> None:
    """Test parsing Docker action reference."""
    parser = Parser(Path.cwd())
    ref = parser._parse_action_ref("docker://alpine:3.8", Path("test.yml"))

    assert ref.type == ActionType.DOCKER
    assert ref.path == "docker://alpine:3.8"


def test_parse_action_ref_invalid() -> None:
    """Test parsing invalid action reference raises error."""
    parser = Parser(Path.cwd())

    with pytest.raises(ValueError, match="Invalid action reference"):
        parser._parse_action_ref("invalid-ref", Path("test.yml"))


def test_extract_secrets() -> None:
    """Test extracting secrets from content."""
    parser = Parser(Path.cwd())
    content = """
    env:
      TOKEN: ${{ secrets.GITHUB_TOKEN }}
      API_KEY: ${{ secrets.API_KEY }}
    """
    secrets = parser._extract_secrets(content)

    assert "GITHUB_TOKEN" in secrets
    assert "API_KEY" in secrets
    assert len(secrets) == 2


# ============================================================================
# Trigger Extraction Tests
# ============================================================================


def test_extract_triggers_string() -> None:
    """Test extracting triggers from string."""
    parser = Parser(Path.cwd())
    triggers = parser._extract_triggers("push")

    assert triggers == ["push"]


def test_extract_triggers_list() -> None:
    """Test extracting triggers from list."""
    parser = Parser(Path.cwd())
    triggers = parser._extract_triggers(["push", "pull_request"])

    assert triggers == ["push", "pull_request"]


def test_extract_triggers_dict() -> None:
    """Test extracting triggers from dict."""
    parser = Parser(Path.cwd())
    triggers = parser._extract_triggers(
        {
            "push": {"branches": ["main"]},
            "pull_request": None,
            "workflow_dispatch": None,
        }
    )

    assert set(triggers) == {"push", "pull_request", "workflow_dispatch"}


def test_extract_triggers_empty() -> None:
    """Test extracting triggers from empty value."""
    parser = Parser(Path.cwd())
    triggers = parser._extract_triggers(None)

    assert triggers == []


# ============================================================================
# Permissions Parsing Tests
# ============================================================================


def test_parse_permissions_none() -> None:
    """Test parsing None permissions."""
    parser = Parser(Path.cwd())
    perms = parser._parse_permissions(None)

    assert perms is None


def test_parse_permissions_string() -> None:
    """Test parsing string permissions (read-all/write-all)."""
    parser = Parser(Path.cwd())
    perms = parser._parse_permissions("read-all")

    # Should return an empty Permissions object
    assert perms is not None


def test_parse_permissions_dict() -> None:
    """Test parsing dict permissions."""
    parser = Parser(Path.cwd())
    perms = parser._parse_permissions(
        {
            "contents": "read",
            "issues": "write",
            "pull_requests": "write",
        }
    )

    assert perms is not None
    assert perms.contents == PermissionLevel.READ
    assert perms.issues == PermissionLevel.WRITE
    assert perms.pull_requests == PermissionLevel.WRITE


# ============================================================================
# Job Parsing Tests
# ============================================================================


def test_parse_job_with_none_data() -> None:
    """Test parsing job with None data."""
    parser = Parser(Path.cwd())
    job = parser._parse_job("test", None, Path("test.yml"), "")

    assert job.name == "test"
    assert job.runs_on == "ubuntu-latest"  # default value


def test_parse_job_needs_string_vs_list() -> None:
    """Test parsing job needs as string vs list."""
    parser = Parser(Path.cwd())

    # String needs
    job1 = parser._parse_job("test", {"needs": "build"}, Path("test.yml"), "")
    assert job1.needs == ["build"]

    # List needs
    job2 = parser._parse_job("test", {"needs": ["build", "lint"]}, Path("test.yml"), "")
    assert job2.needs == ["build", "lint"]


def test_parse_job_with_none_steps() -> None:
    """Test parsing job with None steps."""
    parser = Parser(Path.cwd())
    job = parser._parse_job(
        "test",
        {"steps": [None, {"uses": "actions/checkout@v4"}]},
        Path("test.yml"),
        "",
    )

    # Should skip None steps
    assert len(job.actions_used) == 1
    assert job.actions_used[0].repo == "checkout"


# ============================================================================
# Container/Services/Strategy Parsing Tests
# ============================================================================


def test_parse_container_none() -> None:
    """Test parsing None container."""
    parser = Parser(Path.cwd())
    container = parser._parse_container(None)

    assert container is None


def test_parse_container_string() -> None:
    """Test parsing container from string."""
    parser = Parser(Path.cwd())
    container = parser._parse_container("ubuntu:latest")

    assert container is not None
    assert container.image == "ubuntu:latest"


def test_parse_container_dict() -> None:
    """Test parsing container from dict."""
    parser = Parser(Path.cwd())
    container = parser._parse_container(
        {
            "image": "node:20",
            "credentials": {"username": "user", "password": "pass"},
            "env": {"NODE_ENV": "test"},
            "ports": [8080],
            "volumes": ["/tmp:/tmp"],
            "options": "--cpus 2",
        }
    )

    assert container is not None
    assert container.image == "node:20"
    assert container.credentials == {"username": "user", "password": "pass"}
    assert container.env["NODE_ENV"] == "test"
    assert container.ports == [8080]
    assert container.volumes == ["/tmp:/tmp"]
    assert container.options == "--cpus 2"


def test_parse_services_none() -> None:
    """Test parsing None services."""
    parser = Parser(Path.cwd())
    services = parser._parse_services(None)

    assert services == {}


def test_parse_services_string_image() -> None:
    """Test parsing service with string image."""
    parser = Parser(Path.cwd())
    services = parser._parse_services({"postgres": "postgres:15"})

    assert "postgres" in services
    assert services["postgres"].name == "postgres"
    assert services["postgres"].image == "postgres:15"


def test_parse_services_dict() -> None:
    """Test parsing service with dict config."""
    parser = Parser(Path.cwd())
    services = parser._parse_services(
        {
            "redis": {
                "image": "redis:alpine",
                "ports": [6379],
                "options": "--health-cmd 'redis-cli ping'",
            }
        }
    )

    assert "redis" in services
    assert services["redis"].image == "redis:alpine"
    assert services["redis"].ports == [6379]


def test_parse_strategy_none() -> None:
    """Test parsing None strategy."""
    parser = Parser(Path.cwd())
    strategy = parser._parse_strategy(None)

    assert strategy is None


def test_parse_strategy_matrix() -> None:
    """Test parsing strategy with matrix."""
    parser = Parser(Path.cwd())
    strategy = parser._parse_strategy(
        {
            "matrix": {"node-version": [18, 20], "os": ["ubuntu-latest", "windows-latest"]},
            "fail-fast": False,
            "max-parallel": 4,
        }
    )

    assert strategy is not None
    assert strategy.matrix == {"node-version": [18, 20], "os": ["ubuntu-latest", "windows-latest"]}
    assert strategy.fail_fast is False
    assert strategy.max_parallel == 4


# ============================================================================
# Action Manifest Parsing Tests
# ============================================================================


def test_parse_composite_action() -> None:
    """Test parsing a composite action."""
    parser = Parser(FIXTURES_DIR)
    action = parser.parse_action(FIXTURES_DIR / "composite-action.yml")

    assert action.name == "Composite Action"
    assert action.description == "A composite action example"
    assert action.author == "Test Author"
    assert action.is_composite is True
    assert action.is_docker is False
    assert action.is_javascript is False

    # Check inputs
    assert "message" in action.inputs
    assert action.inputs["message"].required is True
    assert "debug" in action.inputs
    assert action.inputs["debug"].required is False
    assert action.inputs["debug"].default == "false"

    # Check outputs
    assert "result" in action.outputs
    assert action.outputs["result"].description == "Action result"

    # Check branding
    assert action.branding is not None


def test_parse_docker_action() -> None:
    """Test parsing a Docker action."""
    parser = Parser(FIXTURES_DIR)
    action = parser.parse_action(FIXTURES_DIR / "docker-action.yml")

    assert action.name == "Docker Action"
    assert action.is_docker is True
    assert action.is_composite is False
    assert action.is_javascript is False

    # Check inputs
    assert "dockerfile" in action.inputs
    assert action.inputs["dockerfile"].default == "Dockerfile"

    # Check outputs
    assert "image-id" in action.outputs


def test_parse_javascript_action() -> None:
    """Test parsing a JavaScript action."""
    parser = Parser(FIXTURES_DIR)
    action = parser.parse_action(FIXTURES_DIR / "javascript-action.yml")

    assert action.name == "JavaScript Action"
    assert action.is_javascript is True
    assert action.is_composite is False
    assert action.is_docker is False

    # Check runs config
    assert action.runs["using"] == "node20"
    assert action.runs["main"] == "dist/index.js"


def test_parse_action_with_various_defaults() -> None:
    """Test parsing action with different input default types."""
    parser = Parser(FIXTURES_DIR)
    action = parser.parse_action(FIXTURES_DIR / "action-with-defaults.yml")

    assert action.name == "Action with Various Defaults"

    # String default
    assert action.inputs["string-input"].default == "hello"

    # Boolean default
    assert action.inputs["boolean-input"].default is True

    # Number default
    assert action.inputs["number-input"].default == 42

    # No default
    assert action.inputs["no-default"].required is True


def test_parse_action_empty_inputs_outputs() -> None:
    """Test parsing action with empty inputs/outputs."""
    parser = Parser(FIXTURES_DIR)
    action = parser.parse_action(FIXTURES_DIR / "composite-action.yml")

    # Even if action has inputs/outputs, the parser should handle missing ones
    assert action.inputs is not None
    assert action.outputs is not None


def test_parse_empty_action() -> None:
    """Test parsing an empty action file raises error."""
    parser = Parser(FIXTURES_DIR)

    with pytest.raises(ValueError, match="Empty action file"):
        parser.parse_action(FIXTURES_DIR / "invalid-action.yml")


# ============================================================================
# Reusable Workflow Tests
# ============================================================================


def test_parse_reusable_workflow_caller() -> None:
    """Test parsing workflow that calls reusable workflows."""
    parser = Parser(FIXTURES_DIR)
    workflow = parser.parse_workflow(FIXTURES_DIR / "reusable-workflow-caller.yml")

    assert workflow.name == "Reusable Workflow Caller"
    assert "call-workflow" in workflow.jobs
    assert "call-workflow-inherit" in workflow.jobs
    assert "call-local-workflow" in workflow.jobs

    # Test job with explicit secrets
    call_job = workflow.jobs["call-workflow"]
    assert call_job.uses == "owner/repo/.github/workflows/deploy.yml@v1"
    assert call_job.with_inputs["environment"] == "production"
    assert call_job.with_inputs["debug"] is False
    assert call_job.with_inputs["version"] == "1.2.3"
    assert call_job.secrets_passed is not None
    assert "deploy-token" in call_job.secrets_passed
    assert call_job.inherit_secrets is False

    # Verify reusable workflow tracked as action
    assert len(call_job.actions_used) == 1
    assert call_job.actions_used[0].type == ActionType.REUSABLE_WORKFLOW
    assert call_job.actions_used[0].owner == "owner"
    assert call_job.actions_used[0].repo == "repo"
    assert call_job.actions_used[0].path == ".github/workflows/deploy.yml"
    assert call_job.actions_used[0].ref == "v1"

    # Test job with inherited secrets
    inherit_job = workflow.jobs["call-workflow-inherit"]
    assert inherit_job.uses == "owner/repo/.github/workflows/test.yml@main"
    assert inherit_job.inherit_secrets is True
    assert inherit_job.secrets_passed is None

    # Test local reusable workflow
    local_job = workflow.jobs["call-local-workflow"]
    assert local_job.uses == "./.github/workflows/shared.yml"
    assert local_job.actions_used[0].type == ActionType.REUSABLE_WORKFLOW
    assert local_job.actions_used[0].path == "./.github/workflows/shared.yml"


def test_parse_job_with_outputs() -> None:
    """Test parsing job with outputs."""
    parser = Parser(FIXTURES_DIR)
    workflow = parser.parse_workflow(FIXTURES_DIR / "job-with-outputs.yml")

    assert "build" in workflow.jobs
    build_job = workflow.jobs["build"]

    assert build_job.outputs is not None
    assert "version" in build_job.outputs
    assert "artifact-url" in build_job.outputs
    assert "status" in build_job.outputs
    assert build_job.outputs["status"] == "success"


def test_parse_reusable_workflow_ref_local() -> None:
    """Test parsing local reusable workflow reference."""
    parser = Parser(Path.cwd())
    ref = parser._parse_reusable_workflow_ref("./.github/workflows/deploy.yml", Path("test.yml"))

    assert ref.type == ActionType.REUSABLE_WORKFLOW
    assert ref.path == "./.github/workflows/deploy.yml"


def test_parse_reusable_workflow_ref_github() -> None:
    """Test parsing GitHub reusable workflow reference."""
    parser = Parser(Path.cwd())
    ref = parser._parse_reusable_workflow_ref("actions/reusable/.github/workflows/build.yml@v1", Path("test.yml"))

    assert ref.type == ActionType.REUSABLE_WORKFLOW
    assert ref.owner == "actions"
    assert ref.repo == "reusable"
    assert ref.path == ".github/workflows/build.yml"
    assert ref.ref == "v1"


def test_parse_reusable_workflow_ref_invalid() -> None:
    """Test parsing invalid reusable workflow reference raises error."""
    parser = Parser(Path.cwd())

    with pytest.raises(ValueError, match="Invalid reusable workflow reference"):
        parser._parse_reusable_workflow_ref("invalid-workflow-ref", Path("test.yml"))


def test_parse_permissions_invalid_type(tmp_path: Path) -> None:
    """Test parsing permissions with invalid type."""
    parser = Parser(tmp_path)

    # Test with boolean (invalid type)
    result = parser._parse_permissions(True)
    assert result is None

    # Test with int (invalid type)
    result = parser._parse_permissions(123)
    assert result is None

    # Test with list (invalid type)
    result = parser._parse_permissions(["read", "write"])
    assert result is None


def test_parse_workflow_with_boolean_and_number_env(tmp_path: Path) -> None:
    """Test parsing workflow with boolean and number values in env."""
    workflow_file = tmp_path / "test.yml"
    workflow_file.write_text(
        """
name: Test
on: push
env:
  STRING_VAR: "hello"
  BOOL_VAR: true
  NUMBER_VAR: 42
  FLOAT_VAR: 3.14
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo test
"""
    )

    parser = Parser(tmp_path)
    workflow = parser.parse_workflow(workflow_file)

    assert workflow.env["STRING_VAR"] == "hello"
    assert workflow.env["BOOL_VAR"] is True
    assert workflow.env["NUMBER_VAR"] == 42
    assert workflow.env["FLOAT_VAR"] == 3.14
