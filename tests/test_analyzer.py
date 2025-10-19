"""Tests for analyzer module."""

from ghaw_auditor.analyzer import Analyzer
from ghaw_auditor.models import ActionRef, ActionType, JobMeta, WorkflowMeta


def test_analyzer_initialization() -> None:
    """Test analyzer can be initialized."""
    analyzer = Analyzer()
    assert analyzer is not None


def test_deduplicate_actions() -> None:
    """Test action deduplication."""
    analyzer = Analyzer()

    action1 = ActionRef(
        type=ActionType.GITHUB,
        owner="actions",
        repo="checkout",
        ref="v4",
        source_file="test.yml",
    )
    action2 = ActionRef(
        type=ActionType.GITHUB,
        owner="actions",
        repo="checkout",
        ref="v4",
        source_file="test2.yml",
    )
    action3 = ActionRef(
        type=ActionType.GITHUB,
        owner="actions",
        repo="setup-node",
        ref="v4",
        source_file="test.yml",
    )

    result = analyzer.deduplicate_actions([action1, action2, action3])

    # Should have 2 unique actions (checkout appears twice)
    assert len(result) == 2


def test_analyze_workflows() -> None:
    """Test workflow analysis."""
    analyzer = Analyzer()

    job = JobMeta(
        name="test",
        runs_on="ubuntu-latest",
    )

    workflow = WorkflowMeta(
        name="Test Workflow",
        path="test.yml",
        triggers=["push", "pull_request"],
        jobs={"test": job},
        secrets_used={"SECRET1", "SECRET2"},
    )

    workflows = {"test.yml": workflow}
    analysis = analyzer.analyze_workflows(workflows, {})

    assert analysis["total_workflows"] == 1
    assert analysis["total_jobs"] == 1
    assert "push" in analysis["triggers"]
    assert analysis["triggers"]["push"] == 1
    assert analysis["secrets"]["total_unique_secrets"] == 2


def test_analyze_runners_with_list() -> None:
    """Test runner analysis with list runner."""
    from ghaw_auditor.analyzer import Analyzer
    from ghaw_auditor.models import JobMeta, WorkflowMeta

    analyzer = Analyzer()

    # Job with list runner (matrix runner)
    job = JobMeta(
        name="test",
        runs_on=["ubuntu-latest", "macos-latest"],
    )

    workflow = WorkflowMeta(
        name="Test Workflow",
        path="test.yml",
        triggers=["push"],
        jobs={"test": job},
    )

    workflows = {"test.yml": workflow}
    analysis = analyzer.analyze_workflows(workflows, {})

    # List runner should be converted to string
    assert "['ubuntu-latest', 'macos-latest']" in analysis["runners"]


def test_analyze_containers_and_services() -> None:
    """Test container and service analysis."""
    from ghaw_auditor.analyzer import Analyzer
    from ghaw_auditor.models import Container, JobMeta, Service, WorkflowMeta

    analyzer = Analyzer()

    # Job with container
    job1 = JobMeta(
        name="with-container",
        runs_on="ubuntu-latest",
        container=Container(image="node:18"),
    )

    # Job with services
    job2 = JobMeta(
        name="with-services",
        runs_on="ubuntu-latest",
        services={"postgres": Service(name="postgres", image="postgres:14")},
    )

    # Job with both
    job3 = JobMeta(
        name="with-both",
        runs_on="ubuntu-latest",
        container=Container(image="node:18"),
        services={"redis": Service(name="redis", image="redis:7")},
    )

    workflow = WorkflowMeta(
        name="Test Workflow",
        path="test.yml",
        triggers=["push"],
        jobs={
            "with-container": job1,
            "with-services": job2,
            "with-both": job3,
        },
    )

    workflows = {"test.yml": workflow}
    analysis = analyzer.analyze_workflows(workflows, {})

    # Should count containers and services
    assert analysis["containers"]["jobs_with_containers"] == 2
    assert analysis["containers"]["jobs_with_services"] == 2
