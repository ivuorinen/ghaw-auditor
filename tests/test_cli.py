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
    # Pinned action AND an explicit least-privilege permissions block: both
    # default rules (require_pinned_actions, min_permissions) must be satisfied.
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(
        """
name: CI
on: push
permissions:
  contents: read
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

    # An explicitly requested diff that cannot run must fail, not report success.
    # Exit 1 (not 2) proves the deliberate exit survives the generic handler.
    assert result.exit_code == 1
    assert "Baseline not found" in result.output


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


# ============================================================================
# Regression tests for defects found by the /nitpicker audit.
# ============================================================================


def _repo_with_unpinned_action(tmp_path: Path) -> Path:
    """Create a repo whose only workflow uses an unpinned action."""
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(
        "name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - uses: actions/checkout@v4\n"
    )
    return tmp_path


def test_validate_honours_denied_actions_from_policy_file(tmp_path: Path) -> None:
    """A rule written in the policy file must actually be enforced.

    The loader was a TODO: the file was checked for existence and discarded, so
    every user-authored rule silently became the built-in default.
    """
    repo = _repo_with_unpinned_action(tmp_path)
    policy_file = tmp_path / "policy.yml"
    policy_file.write_text("require_pinned_actions: false\ndenied_actions:\n  - actions/checkout\n")

    result = runner.invoke(app, ["validate", "--repo", str(repo), "--policy-file", str(policy_file)])

    assert result.exit_code == 0
    assert "denied by policy" in result.output


def test_validate_policy_file_can_disable_a_default_rule(tmp_path: Path) -> None:
    """Setting require_pinned_actions: false must suppress the default violation."""
    repo = _repo_with_unpinned_action(tmp_path)
    policy_file = tmp_path / "policy.yml"
    policy_file.write_text("require_pinned_actions: false\nmin_permissions: false\n")

    result = runner.invoke(app, ["validate", "--repo", str(repo), "--policy-file", str(policy_file)])

    assert result.exit_code == 0
    assert "No policy violations found" in result.output


def test_missing_policy_file_is_an_error_not_a_silent_default(tmp_path: Path) -> None:
    """A --policy-file path that does not exist must fail loudly."""
    repo = _repo_with_unpinned_action(tmp_path)

    result = runner.invoke(app, ["validate", "--repo", str(repo), "--policy-file", str(tmp_path / "nope.yml")])

    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_scan_enforce_exits_1_not_2(tmp_path: Path) -> None:
    """Policy enforcement failure must exit 1, distinct from a crash (2).

    typer.Exit subclasses RuntimeError, so the blanket `except Exception`
    rewrote every deliberate exit to 2 and made --enforce unusable as a gate.
    """
    repo = _repo_with_unpinned_action(tmp_path)
    policy_file = tmp_path / "policy.yml"
    policy_file.write_text("require_pinned_actions: true\n")

    result = runner.invoke(
        app,
        [
            "scan",
            "--repo",
            str(repo),
            "--offline",
            "--enforce",
            "--policy-file",
            str(policy_file),
            "--output",
            str(tmp_path / "out"),
        ],
    )

    assert result.exit_code == 1


def test_scan_enforce_does_not_print_success_banner_on_failure(tmp_path: Path) -> None:
    """The success banner must not appear when enforcement fails."""
    repo = _repo_with_unpinned_action(tmp_path)
    policy_file = tmp_path / "policy.yml"
    policy_file.write_text("require_pinned_actions: true\n")

    result = runner.invoke(
        app,
        [
            "scan",
            "--repo",
            str(repo),
            "--offline",
            "--enforce",
            "--policy-file",
            str(policy_file),
            "--output",
            str(tmp_path / "out"),
        ],
    )

    assert "Audit complete" not in result.output


def test_policy_file_with_invalid_yaml_is_rejected(tmp_path: Path) -> None:
    """Malformed YAML in a policy file fails with a clear message."""
    repo = _repo_with_unpinned_action(tmp_path)
    policy_file = tmp_path / "policy.yml"
    policy_file.write_text("denied_actions: [unclosed\n")

    result = runner.invoke(app, ["validate", "--repo", str(repo), "--policy-file", str(policy_file)])

    assert result.exit_code != 0
    assert "Invalid YAML" in result.output


def test_policy_file_that_is_not_a_mapping_is_rejected(tmp_path: Path) -> None:
    """A policy file holding a list rather than a mapping is rejected."""
    repo = _repo_with_unpinned_action(tmp_path)
    policy_file = tmp_path / "policy.yml"
    policy_file.write_text("- just\n- a\n- list\n")

    result = runner.invoke(app, ["validate", "--repo", str(repo), "--policy-file", str(policy_file)])

    assert result.exit_code != 0
    assert "must contain a YAML mapping" in result.output


def test_policy_file_with_wrong_field_type_is_rejected(tmp_path: Path) -> None:
    """A policy whose field has the wrong type fails validation, not silently."""
    repo = _repo_with_unpinned_action(tmp_path)
    policy_file = tmp_path / "policy.yml"
    policy_file.write_text("denied_actions: 42\n")

    result = runner.invoke(app, ["validate", "--repo", str(repo), "--policy-file", str(policy_file)])

    assert result.exit_code != 0
    assert "Invalid policy" in result.output


def test_scan_rejects_bad_policy_file_with_a_specific_message(tmp_path: Path) -> None:
    """scan explains *why* a policy file was rejected rather than crashing opaquely.

    The exit code here is click's usage-error convention (2); what matters is
    that the generic handler did not swallow the reason and log an
    unexplained "Scan failed".
    """
    repo = _repo_with_unpinned_action(tmp_path)
    policy_file = tmp_path / "policy.yml"
    policy_file.write_text("- not a mapping\n")

    result = runner.invoke(
        app,
        ["scan", "--repo", str(repo), "--offline", "--policy-file", str(policy_file), "--output", str(tmp_path / "o")],
    )

    assert result.exit_code != 0
    assert "must contain a YAML mapping" in result.output
    assert "Scan failed" not in result.output


def test_enforce_policy_passes_when_only_warnings_present() -> None:
    """Warning-severity violations must not trip enforcement."""
    from ghaw_auditor.cli import _enforce_policy

    # Returns normally; a raised typer.Exit would fail the test.
    _enforce_policy([{"severity": "warning", "rule": "r", "workflow": "w", "message": "m"}])


def test_validate_enforce_exits_zero_when_violations_are_only_warnings(tmp_path: Path) -> None:
    """`validate --enforce` reports warnings but does not fail the build.

    Only error-severity violations gate; min_permissions' "nothing declared"
    signal is a warning by design.
    """
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(
        "name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"
    )
    policy_file = tmp_path / "policy.yml"
    policy_file.write_text("require_pinned_actions: false\nmin_permissions: true\n")

    result = runner.invoke(app, ["validate", "--repo", str(tmp_path), "--policy-file", str(policy_file), "--enforce"])

    assert result.exit_code == 0
    assert "WARNING" in result.output
