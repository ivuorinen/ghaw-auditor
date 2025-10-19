"""Tests for service layer."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from ghaw_auditor.analyzer import Analyzer
from ghaw_auditor.differ import Differ
from ghaw_auditor.models import (
    ActionManifest,
    Policy,
    WorkflowMeta,
)
from ghaw_auditor.parser import Parser
from ghaw_auditor.policy import PolicyValidator
from ghaw_auditor.scanner import Scanner
from ghaw_auditor.services import AuditService, DiffService


def test_audit_service_scan_basic(tmp_path: Path) -> None:
    """Test basic scan without workflows."""
    scanner = Scanner(tmp_path)
    parser = Parser(tmp_path)
    analyzer = Analyzer()

    service = AuditService(scanner, parser, analyzer)
    result = service.scan(offline=True)

    assert result.workflow_count == 0
    assert result.action_count == 0
    assert result.unique_action_count == 0
    assert len(result.workflows) == 0
    assert len(result.actions) == 0
    assert len(result.violations) == 0


def test_audit_service_scan_with_workflow(tmp_path: Path) -> None:
    """Test scan with a simple workflow."""
    # Create test workflow
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

    scanner = Scanner(tmp_path)
    parser = Parser(tmp_path)
    analyzer = Analyzer()

    service = AuditService(scanner, parser, analyzer)
    result = service.scan(offline=True)

    assert result.workflow_count == 1
    assert len(result.workflows) == 1
    assert ".github/workflows/ci.yml" in result.workflows
    assert result.unique_action_count == 1


def test_audit_service_scan_with_policy_violations(tmp_path: Path) -> None:
    """Test scan with policy violations."""
    # Create workflow with branch ref (violates pinning policy)
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

    scanner = Scanner(tmp_path)
    parser = Parser(tmp_path)
    analyzer = Analyzer()
    policy = Policy(require_pinned_actions=True)
    validator = PolicyValidator(policy)

    service = AuditService(scanner, parser, analyzer, validator=validator)
    result = service.scan(offline=True)

    assert len(result.violations) > 0
    assert any("pinned" in v["message"].lower() for v in result.violations)


def test_audit_service_scan_parse_error(tmp_path: Path) -> None:
    """Test scan handles parse errors gracefully."""
    # Create invalid workflow
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "invalid.yml").write_text("invalid: yaml: {{{")

    scanner = Scanner(tmp_path)
    parser = Parser(tmp_path)
    analyzer = Analyzer()

    service = AuditService(scanner, parser, analyzer)
    result = service.scan(offline=True)

    # Should continue despite parse error
    assert result.workflow_count == 1
    assert len(result.workflows) == 0  # Workflow not parsed


def test_audit_service_scan_with_resolver(tmp_path: Path) -> None:
    """Test scan with resolver (mocked)."""
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

    scanner = Scanner(tmp_path)
    parser = Parser(tmp_path)
    analyzer = Analyzer()

    # Mock resolver
    mock_resolver = Mock()
    mock_resolver.resolve_actions.return_value = {
        "actions/checkout@abc123": ActionManifest(
            name="Checkout",
            description="Checkout code",
        )
    }

    service = AuditService(scanner, parser, analyzer, resolver=mock_resolver)
    result = service.scan(offline=False)

    # Should call resolver
    assert mock_resolver.resolve_actions.called
    assert len(result.actions) == 1


def test_audit_service_scan_analysis(tmp_path: Path) -> None:
    """Test that scan includes analysis."""
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text(
        """
name: CI
on:
  - push
  - pull_request
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo test
"""
    )

    scanner = Scanner(tmp_path)
    parser = Parser(tmp_path)
    analyzer = Analyzer()

    service = AuditService(scanner, parser, analyzer)
    result = service.scan(offline=True)

    # Check analysis
    assert "total_workflows" in result.analysis
    assert result.analysis["total_workflows"] == 1
    assert "triggers" in result.analysis
    assert "push" in result.analysis["triggers"]
    assert "pull_request" in result.analysis["triggers"]


def test_diff_service_compare(tmp_path: Path) -> None:
    """Test diff service comparison."""
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()

    # Create baseline
    differ = Differ(baseline_dir)
    old_workflow = WorkflowMeta(
        name="Old",
        path="test.yml",
        triggers=["push"],
        jobs={},
    )
    differ.save_baseline({"test.yml": old_workflow}, {})

    # Create diff service
    diff_service = DiffService(differ)

    # New workflow
    new_workflow = WorkflowMeta(
        name="New",
        path="test.yml",
        triggers=["push", "pull_request"],
        jobs={},
    )

    workflow_diffs, action_diffs = diff_service.compare({"test.yml": new_workflow}, {})

    assert len(workflow_diffs) == 1
    assert workflow_diffs[0].status == "modified"


def test_diff_service_compare_no_baseline(tmp_path: Path) -> None:
    """Test diff service with missing baseline."""
    baseline_dir = tmp_path / "nonexistent"

    differ = Differ(baseline_dir)
    diff_service = DiffService(differ)

    with pytest.raises(FileNotFoundError):
        diff_service.compare({}, {})
