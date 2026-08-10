"""CLI interface for GitHub Actions & Workflows Auditor."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.logging import RichHandler
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from ghaw_auditor import __version__
from ghaw_auditor.analyzer import Analyzer
from ghaw_auditor.differ import Differ
from ghaw_auditor.factory import AuditServiceFactory
from ghaw_auditor.models import Policy
from ghaw_auditor.parser import Parser
from ghaw_auditor.policy import PolicyValidator
from ghaw_auditor.renderer import Renderer
from ghaw_auditor.scanner import Scanner
from ghaw_auditor.services import DiffService, ScanResult

app = typer.Typer(
    name="ghaw-auditor",
    help="GitHub Actions & Workflows Auditor - analyze and audit GitHub Actions ecosystem",
)
console = Console()


def setup_logging(verbose: bool = False, quiet: bool = False, log_json: bool = False) -> None:
    """Configure logging."""
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    if log_json:
        logging.basicConfig(level=level, format="%(message)s")
    else:
        logging.basicConfig(
            level=level, format="%(message)s", handlers=[RichHandler(console=console, rich_tracebacks=True)]
        )


def _load_policy(policy_file: Path | None) -> Policy | None:
    """Load a policy file into a Policy model.

    A path that was explicitly given but cannot be read is a hard error: silently
    falling back to the default policy would enforce rules the user never wrote
    while reporting success.
    """
    if policy_file is None:
        return None

    if not policy_file.exists():
        raise typer.BadParameter(f"Policy file not found: {policy_file}")

    yaml = YAML(typ="safe")
    try:
        with open(policy_file, encoding="utf-8") as f:
            data = yaml.load(f) or {}
    except YAMLError as e:
        raise typer.BadParameter(f"Invalid YAML in policy file {policy_file}: {e}") from e

    if not isinstance(data, dict):
        raise typer.BadParameter(f"Policy file {policy_file} must contain a YAML mapping")

    try:
        return Policy.model_validate(data)
    except ValidationError as e:
        raise typer.BadParameter(f"Invalid policy in {policy_file}: {e}") from e


def _render_reports(
    renderer: Renderer,
    result: ScanResult,
    format_type: str,
) -> None:
    """Render reports based on format type."""
    console.print("[cyan]Generating reports...[/cyan]")
    if format_type in ("json", "all"):
        renderer.render_json(result.workflows, result.actions, result.violations)
    if format_type in ("md", "all"):
        renderer.render_markdown(result.workflows, result.actions, result.violations, result.analysis)


def _handle_diff_mode(
    result: ScanResult,
    baseline: Path,
    output: Path,
) -> None:
    """Handle diff mode comparison."""
    console.print("[cyan]Running diff...[/cyan]")
    diff_service = DiffService(Differ(baseline))
    try:
        workflow_diffs, action_diffs = diff_service.compare(result.workflows, result.actions)

        diff_dir = output / "diff"
        diff_dir.mkdir(exist_ok=True)
        diff_service.differ.render_diff_markdown(workflow_diffs, action_diffs, diff_dir / "report.diff.md")
        console.print(f"[green]Diff report written to {diff_dir / 'report.diff.md'}[/green]")
    except FileNotFoundError as e:
        # An explicitly requested diff that cannot run is a failure. Logging and
        # continuing would report success for a comparison that never happened.
        console.print(f"[red]Baseline not found: {e}[/red]")
        raise typer.Exit(1) from e


def _write_baseline(result: ScanResult, baseline_path: Path, commit_sha: str | None = None) -> None:
    """Write baseline snapshot."""
    differ = Differ(baseline_path)
    differ.save_baseline(result.workflows, result.actions, commit_sha)
    console.print(f"[green]Baseline saved to {baseline_path}[/green]")


def _enforce_policy(violations: list[dict[str, Any]]) -> None:
    """Enforce policy and exit if errors found."""
    error_violations = [v for v in violations if v.get("severity") == "error"]
    if error_violations:
        console.print(f"[red]Policy enforcement failed: {len(error_violations)} errors[/red]")
        raise typer.Exit(1)


@app.command()
def scan(
    repo: str = typer.Option(".", help="Repository path or URL"),
    token: str | None = typer.Option(None, help="GitHub token", envvar="GITHUB_TOKEN"),
    output: Path = typer.Option(".ghaw-auditor", help="Output directory"),
    format_type: str = typer.Option("all", help="Output format: json, md, or all"),
    cache_dir: Path | None = typer.Option(None, help="Cache directory"),
    offline: bool = typer.Option(False, help="Offline mode (no API calls)"),
    concurrency: int = typer.Option(4, help="Concurrency for API calls"),
    enforce: bool = typer.Option(False, help="Enforce policy (exit non-zero on violations)"),
    policy_file: Path | None = typer.Option(None, help="Policy file path"),
    exclude: list[str] = typer.Option(  # noqa: B006
        [], "--exclude", help="Glob pattern to exclude from scanning (repeatable)"
    ),
    diff: bool = typer.Option(False, help="Run in diff mode"),
    baseline: Path | None = typer.Option(None, help="Baseline path for diff"),
    write_baseline: bool = typer.Option(False, help="Write baseline after scan"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Quiet output"),
    log_json: bool = typer.Option(False, help="JSON logging"),
) -> None:
    """Scan repository for GitHub Actions and workflows."""
    setup_logging(verbose, quiet, log_json)
    logger = logging.getLogger(__name__)

    try:
        # Validate repository path
        repo_path = Path(repo).resolve()
        if not repo_path.exists():
            console.print(f"[red]Repository not found: {repo_path}[/red]")
            raise typer.Exit(1)

        # Load policy if specified
        policy = _load_policy(policy_file)

        # Create service via factory. The `with` gives the service ownership of
        # the disk cache and HTTP pool it opened, so both are closed on exit.
        with AuditServiceFactory.create(
            repo_path=repo_path,
            token=token,
            offline=offline,
            cache_dir=cache_dir,
            concurrency=concurrency,
            policy=policy,
            exclude_patterns=exclude,
        ) as service:
            # Execute scan
            console.print("[cyan]Scanning repository...[/cyan]")
            result = service.scan(offline=offline)

            # Display summary
            console.print(f"Found {result.workflow_count} workflows and {result.action_count} actions")
            console.print(f"Found {result.unique_action_count} unique action references")

            if result.violations:
                console.print(f"Found {len(result.violations)} policy violations")

            # Render reports
            renderer = Renderer(output)
            _render_reports(renderer, result, format_type)

            # Handle diff mode
            if diff and baseline:
                _handle_diff_mode(result, baseline, output)

            # Write baseline
            if write_baseline:
                baseline_path = baseline or (output / "baseline")
                _write_baseline(result, baseline_path)

        # Enforce policy before declaring success, so an enforced failure never
        # prints the success banner.
        if enforce and result.violations:
            _enforce_policy(result.violations)

        console.print(f"[green]✓ Audit complete! Reports in {output}[/green]")

    except typer.Exit:
        # Deliberate exits (bad repo path, policy enforcement, missing baseline)
        # carry meaningful codes. typer.Exit subclasses RuntimeError, so without
        # this passthrough the handler below would rewrite every one of them to 2.
        raise
    except typer.BadParameter:
        raise
    except Exception as e:
        logger.exception(f"Scan failed: {e}")
        raise typer.Exit(2) from None


@app.command()
def inventory(
    repo: str = typer.Option(".", help="Repository path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Print deduplicated action inventory."""
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    repo_path = Path(repo).resolve()
    scanner = Scanner(repo_path)
    parser = Parser(repo_path)
    analyzer = Analyzer()

    workflow_files = scanner.find_workflows()
    all_actions = []

    for wf_file in workflow_files:
        try:
            workflow = parser.parse_workflow(wf_file)
            all_actions.extend(workflow.actions_used)
        except Exception as e:
            logger.error(f"Failed to parse {wf_file}: {e}")
            if verbose:
                logger.exception(e)

    unique_actions = analyzer.deduplicate_actions(all_actions)

    console.print(f"\n[cyan]Unique Actions: {len(unique_actions)}[/cyan]\n")
    for key, _action in sorted(unique_actions.items()):
        console.print(f"  • {key}")


@app.command()
def validate(
    repo: str = typer.Option(".", help="Repository path"),
    policy_file: Path | None = typer.Option(None, help="Policy file"),
    enforce: bool = typer.Option(False, help="Exit non-zero on violations"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Validate workflows against policy."""
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    repo_path = Path(repo).resolve()
    scanner = Scanner(repo_path)
    parser = Parser(repo_path)

    workflow_files = scanner.find_workflows()
    workflows = {}

    for wf_file in workflow_files:
        try:
            workflow = parser.parse_workflow(wf_file)
            rel_path = str(wf_file.relative_to(repo_path))
            workflows[rel_path] = workflow
        except Exception as e:
            logger.error(f"Failed to parse {wf_file}: {e}")
            if verbose:
                logger.exception(e)

    # An explicit --policy-file is honoured; with none given, fall back to the
    # documented defaults.
    policy = _load_policy(policy_file) or Policy()

    validator = PolicyValidator(policy)
    violations = validator.validate(workflows)

    if violations:
        console.print(f"\n[yellow]Found {len(violations)} policy violations:[/yellow]\n")
        for v in violations:
            severity = v.get("severity", "warning").upper()
            color = "red" if severity == "ERROR" else "yellow"
            console.print(f"[{color}]{severity}[/{color}] {v['workflow']}: {v['message']}")

        if enforce:
            errors = [v for v in violations if v.get("severity") == "error"]
            if errors:
                raise typer.Exit(1)
    else:
        console.print("[green]✓ No policy violations found[/green]")


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"ghaw-auditor version {__version__}")


if __name__ == "__main__":  # pragma: no cover
    app()
