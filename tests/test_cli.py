"""Integration tests for CLI commands."""

from pathlib import Path
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from ghaw_auditor.cli import app

runner = CliRunner()


def test_scan_command_basic(tmp_path: Path) -> None:
    """Test basic scan command."""
    output_dir = tmp_path / "output"

    with patch("ghaw_auditor.cli.Scanner") as mock_scanner:
        mock_scanner.return_value.find_workflows.return_value = []
        mock_scanner.return_value.find_actions.return_value = []

        result = runner.invoke(app, ["scan", "--repo", str(tmp_path), "--output", str(output_dir), "--offline"])

        assert result.exit_code == 0
        assert "Scanning repository" in result.stdout


def test_scan_command_with_token(tmp_path: Path) -> None:
    """Test scan with GitHub token."""
    with patch("ghaw_auditor.cli.Scanner") as mock_scanner:
        mock_scanner.return_value.find_workflows.return_value = []
        mock_scanner.return_value.find_actions.return_value = []

        result = runner.invoke(
            app,
            ["scan", "--repo", str(tmp_path), "--token", "test_token", "--offline"],
        )

        assert result.exit_code == 0


def test_inventory_command(tmp_path: Path) -> None:
    """Test inventory command."""
    with patch("ghaw_auditor.cli.Scanner") as mock_scanner:
        mock_scanner.return_value.find_workflows.return_value = []

        result = runner.invoke(app, ["inventory", "--repo", str(tmp_path)])

        assert result.exit_code == 0
        assert "Unique Actions" in result.stdout


def test_validate_command(tmp_path: Path) -> None:
    """Test validate command."""
    with patch("ghaw_auditor.cli.Scanner") as mock_scanner:
        mock_scanner.return_value.find_workflows.return_value = []

        result = runner.invoke(app, ["validate", "--repo", str(tmp_path)])

        assert result.exit_code == 0


def test_version_command() -> None:
    """Test version command."""
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert "ghaw-auditor version" in result.stdout


def test_scan_command_verbose(tmp_path: Path) -> None:
    """Test scan with verbose flag."""
    with patch("ghaw_auditor.cli.Scanner") as mock_scanner:
        mock_scanner.return_value.find_workflows.return_value = []
        mock_scanner.return_value.find_actions.return_value = []

        result = runner.invoke(app, ["scan", "--repo", str(tmp_path), "--verbose", "--offline"])

        assert result.exit_code == 0


def test_scan_command_quiet(tmp_path: Path) -> None:
    """Test scan with quiet flag."""
    with patch("ghaw_auditor.cli.Scanner") as mock_scanner:
        mock_scanner.return_value.find_workflows.return_value = []
        mock_scanner.return_value.find_actions.return_value = []

        result = runner.invoke(app, ["scan", "--repo", str(tmp_path), "--quiet", "--offline"])

        assert result.exit_code == 0


def test_scan_command_nonexistent_repo() -> None:
    """Test scan with nonexistent repository."""
    result = runner.invoke(app, ["scan", "--repo", "/nonexistent/path"])

    assert result.exit_code in (1, 2)  # Either repo not found or other error
    assert "Repository not found" in result.stdout or result.exit_code == 2


def test_scan_command_with_log_json(tmp_path: Path) -> None:
    """Test scan with JSON logging."""
    with patch("ghaw_auditor.cli.Scanner") as mock_scanner:
        mock_scanner.return_value.find_workflows.return_value = []
        mock_scanner.return_value.find_actions.return_value = []

        result = runner.invoke(app, ["scan", "--repo", str(tmp_path), "--log-json", "--offline"])

        assert result.exit_code == 0


def test_scan_command_with_policy_file(tmp_path: Path) -> None:
    """Test scan with policy file."""
    policy_file = tmp_path / "policy.yml"
    policy_file.write_text("require_pinned_actions: true")

    with patch("ghaw_auditor.cli.Scanner") as mock_scanner:
        mock_scanner.return_value.find_workflows.return_value = []
        mock_scanner.return_value.find_actions.return_value = []

        result = runner.invoke(
            app,
            [
                "scan",
                "--repo",
                str(tmp_path),
                "--policy-file",
                str(policy_file),
                "--offline",
            ],
        )

        assert result.exit_code == 0


def test_scan_command_with_violations(tmp_path: Path) -> None:
    """Test scan with policy violations."""
    # Create workflow with unpinned action
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(
        """
name: CI
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@main
"""
    )

    policy_file = tmp_path / "policy.yml"
    policy_file.write_text("require_pinned_actions: true")

    result = runner.invoke(
        app,
        [
            "scan",
            "--repo",
            str(tmp_path),
            "--policy-file",
            str(policy_file),
            "--offline",
        ],
    )

    assert result.exit_code == 0
    assert "policy violations" in result.stdout


def test_scan_command_with_enforcement(tmp_path: Path) -> None:
    """Test scan with policy enforcement."""
    # Create workflow with unpinned action
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(
        """
name: CI
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@main
"""
    )

    policy_file = tmp_path / "policy.yml"
    policy_file.write_text("require_pinned_actions: true")

    result = runner.invoke(
        app,
        [
            "scan",
            "--repo",
            str(tmp_path),
            "--policy-file",
            str(policy_file),
            "--enforce",
            "--offline",
        ],
    )

    # Should exit with error due to violations
    assert result.exit_code in (1, 2)  # Exit code 1 from policy, or 2 from exception handling
    # Check that enforcement was triggered
    assert "policy violations" in result.stdout or "Policy enforcement failed" in result.stdout


def test_scan_command_with_diff_mode(tmp_path: Path) -> None:
    """Test scan in diff mode."""
    # Create baseline
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()

    from ghaw_auditor.differ import Differ
    from ghaw_auditor.models import WorkflowMeta

    differ = Differ(baseline_dir)
    workflow = WorkflowMeta(name="Test", path="test.yml", triggers=["push"], jobs={})
    differ.save_baseline({"test.yml": workflow}, {})

    # Create workflow
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "test.yml").write_text("name: Test\non: push\njobs: {}")

    output_dir = tmp_path / "output"

    result = runner.invoke(
        app,
        [
            "scan",
            "--repo",
            str(tmp_path),
            "--diff",
            "--baseline",
            str(baseline_dir),
            "--output",
            str(output_dir),
            "--offline",
        ],
    )

    assert result.exit_code == 0
    assert "Running diff" in result.stdout


def test_scan_command_with_write_baseline(tmp_path: Path) -> None:
    """Test scan with baseline writing."""
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text("name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest")

    baseline_dir = tmp_path / "baseline"

    result = runner.invoke(
        app,
        [
            "scan",
            "--repo",
            str(tmp_path),
            "--write-baseline",
            "--baseline",
            str(baseline_dir),
            "--offline",
        ],
    )

    assert result.exit_code == 0
    assert "Baseline saved" in result.stdout
    assert baseline_dir.exists()


def test_scan_command_with_format_json(tmp_path: Path) -> None:
    """Test scan with JSON format only."""
    with patch("ghaw_auditor.cli.Scanner") as mock_scanner:
        mock_scanner.return_value.find_workflows.return_value = []
        mock_scanner.return_value.find_actions.return_value = []

        result = runner.invoke(
            app,
            ["scan", "--repo", str(tmp_path), "--format-type", "json", "--offline"],
        )

        assert result.exit_code == 0


def test_scan_command_with_format_md(tmp_path: Path) -> None:
    """Test scan with Markdown format only."""
    with patch("ghaw_auditor.cli.Scanner") as mock_scanner:
        mock_scanner.return_value.find_workflows.return_value = []
        mock_scanner.return_value.find_actions.return_value = []

        result = runner.invoke(
            app,
            ["scan", "--repo", str(tmp_path), "--format-type", "md", "--offline"],
        )

        assert result.exit_code == 0


def test_inventory_command_with_error(tmp_path: Path) -> None:
    """Test inventory command with parse error."""
    # Create invalid workflow
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "invalid.yml").write_text("invalid: yaml: {{{")

    result = runner.invoke(app, ["inventory", "--repo", str(tmp_path)])

    assert result.exit_code == 0
    assert "Unique Actions" in result.stdout


def test_inventory_command_verbose_with_error(tmp_path: Path) -> None:
    """Test inventory command verbose mode with error."""
    # Create invalid workflow
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "invalid.yml").write_text("invalid: yaml: {{{")

    result = runner.invoke(app, ["inventory", "--repo", str(tmp_path), "--verbose"])

    assert result.exit_code == 0


def test_validate_command_with_violations(tmp_path: Path) -> None:
    """Test validate command with violations."""
    # Create workflow with unpinned action
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(
        """
name: CI
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@main
"""
    )

    result = runner.invoke(app, ["validate", "--repo", str(tmp_path)])

    assert result.exit_code == 0
    assert "policy violations" in result.stdout


def test_validate_command_with_enforcement(tmp_path: Path) -> None:
    """Test validate command with enforcement."""
    # Create workflow with unpinned action
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(
        """
name: CI
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@main
"""
    )

    result = runner.invoke(app, ["validate", "--repo", str(tmp_path), "--enforce"])

    # Should exit with error
    assert result.exit_code == 1


def test_validate_command_no_violations(tmp_path: Path) -> None:
    """Test validate command with no violations."""
    # Create workflow with pinned action (valid 40-char SHA)
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(
        """
name: CI
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@a81bbbf8298c0fa03ea29cdc473d45769f953675
"""
    )

    result = runner.invoke(app, ["validate", "--repo", str(tmp_path)])

    assert result.exit_code == 0
    assert "No policy violations found" in result.stdout


def test_validate_command_with_error(tmp_path: Path) -> None:
    """Test validate command with parse error."""
    # Create invalid workflow
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "invalid.yml").write_text("invalid: yaml: {{{")

    result = runner.invoke(app, ["validate", "--repo", str(tmp_path)])

    assert result.exit_code == 0


def test_validate_command_verbose_with_error(tmp_path: Path) -> None:
    """Test validate command verbose mode with error."""
    # Create invalid workflow
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "invalid.yml").write_text("invalid: yaml: {{{")

    result = runner.invoke(app, ["validate", "--repo", str(tmp_path), "--verbose"])

    assert result.exit_code == 0


def test_scan_command_diff_baseline_not_found(tmp_path: Path) -> None:
    """Test scan with diff mode when baseline doesn't exist."""
    # Create workflow
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text("name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest")

    # Non-existent baseline
    baseline_dir = tmp_path / "nonexistent_baseline"
    output_dir = tmp_path / "output"

    result = runner.invoke(
        app,
        [
            "scan",
            "--repo",
            str(tmp_path),
            "--diff",
            "--baseline",
            str(baseline_dir),
            "--output",
            str(output_dir),
            "--offline",
        ],
    )

    # Should complete but log error about missing baseline
    assert result.exit_code == 0
    # Diff should be attempted but baseline not found is logged


def test_scan_command_general_exception(tmp_path: Path) -> None:
    """Test scan command with general exception."""
    # Mock the factory to raise an exception
    with patch("ghaw_auditor.cli.AuditServiceFactory") as mock_factory:
        mock_factory.create.side_effect = RuntimeError("Factory failed")

        result = runner.invoke(
            app,
            ["scan", "--repo", str(tmp_path), "--offline"],
        )

        # Should exit with code 2 (exception)
        assert result.exit_code == 2


def test_inventory_command_parse_error_verbose(tmp_path: Path) -> None:
    """Test inventory command logs exceptions in verbose mode."""
    # Create workflow that will cause parse exception
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "bad.yml").write_text("!!invalid yaml!!")

    result = runner.invoke(
        app,
        ["inventory", "--repo", str(tmp_path), "--verbose"],
    )

    # Should complete (exception is caught)
    assert result.exit_code == 0
    # Check for error message in output or logs


def test_validate_command_parse_error_verbose(tmp_path: Path) -> None:
    """Test validate command logs exceptions in verbose mode."""
    # Create workflow that will cause parse exception
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "bad.yml").write_text("!!invalid yaml!!")

    result = runner.invoke(
        app,
        ["validate", "--repo", str(tmp_path), "--verbose"],
    )

    # Should complete (exception is caught)
    assert result.exit_code == 0


def test_scan_command_with_resolver_exception(tmp_path: Path) -> None:
    """Test scan with resolver that raises exception."""
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(
        """
name: CI
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""
    )

    # Mock resolver to raise exception
    with patch("ghaw_auditor.cli.AuditServiceFactory") as mock_factory:
        mock_service = Mock()
        mock_service.scan.side_effect = Exception("Resolver error")
        mock_factory.create.return_value = mock_service

        result = runner.invoke(
            app,
            ["scan", "--repo", str(tmp_path), "--offline"],
        )

        # Should exit with code 2
        assert result.exit_code == 2


def test_inventory_command_with_actions(tmp_path: Path) -> None:
    """Test inventory command with workflow that has actions."""
    # Create workflow with actions
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(
        """
name: CI
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
"""
    )

    result = runner.invoke(app, ["inventory", "--repo", str(tmp_path)])

    assert result.exit_code == 0
    assert "Unique Actions" in result.stdout
    # Should list the actions
    assert "actions/checkout" in result.stdout or "•" in result.stdout


def test_validate_command_with_policy_file(tmp_path: Path) -> None:
    """Test validate command with policy file."""
    # Create workflow
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(
        """
name: CI
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""
    )

    # Create policy file
    policy_file = tmp_path / "policy.yml"
    policy_file.write_text("require_pinned_actions: true")

    result = runner.invoke(
        app,
        ["validate", "--repo", str(tmp_path), "--policy-file", str(policy_file)],
    )

    assert result.exit_code == 0
    # Policy file exists, so TODO block executes
