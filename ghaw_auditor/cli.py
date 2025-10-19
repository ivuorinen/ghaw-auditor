"""CLI interface for GitHub Actions & Workflows Auditor."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.logging import RichHandler

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
        logger = logging.getLogger(__name__)
        logger.error(f"Baseline not found: {e}")


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
        policy = None
        if policy_file and policy_file.exists():
            # TODO: Load policy from YAML file
            policy = Policy()

        # Create service via factory
        service = AuditServiceFactory.create(
            repo_path=repo_path,
            token=token,
            offline=offline,
            cache_dir=cache_dir,
            concurrency=concurrency,
            policy=policy,
        )

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

        console.print(f"[green]✓ Audit complete! Reports in {output}[/green]")

        # Enforce policy
        if enforce and result.violations:
            _enforce_policy(result.violations)

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
    all_actions = []

    for wf_file in workflow_files:
        try:
            workflow = parser.parse_workflow(wf_file)
            rel_path = str(wf_file.relative_to(repo_path))
            workflows[rel_path] = workflow
            all_actions.extend(workflow.actions_used)
        except Exception as e:
            logger.error(f"Failed to parse {wf_file}: {e}")
            if verbose:
                logger.exception(e)

    # Load or use default policy
    policy = Policy()
    if policy_file and policy_file.exists():
        # TODO: Parse YAML policy file here
        pass

    validator = PolicyValidator(policy)
    violations = validator.validate(workflows, all_actions)

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
