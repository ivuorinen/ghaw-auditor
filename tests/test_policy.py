"""Tests for policy validator."""

from ghaw_auditor.models import ActionRef, ActionType, JobMeta, Policy, WorkflowMeta
from ghaw_auditor.policy import PolicyValidator


def test_policy_validator_initialization() -> None:
    """Test validator initialization."""
    policy = Policy()
    validator = PolicyValidator(policy)
    assert validator.policy == policy


def test_pinned_actions_validation() -> None:
    """Test pinned actions policy."""
    policy = Policy(require_pinned_actions=True)
    validator = PolicyValidator(policy)

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={
            "test": JobMeta(
                name="test",
                runs_on="ubuntu-latest",
                actions_used=[
                    ActionRef(
                        type=ActionType.GITHUB,
                        owner="actions",
                        repo="checkout",
                        ref="v4",  # Not pinned to SHA
                        source_file="test.yml",
                    )
                ],
            )
        },
        actions_used=[
            ActionRef(
                type=ActionType.GITHUB,
                owner="actions",
                repo="checkout",
                ref="v4",
                source_file="test.yml",
            )
        ],
    )

    violations = validator.validate({"test.yml": workflow}, [])

    assert len(violations) > 0
    assert violations[0]["rule"] == "require_pinned_actions"
    assert violations[0]["severity"] == "error"


def test_pinned_actions_with_sha() -> None:
    """Test pinned actions with SHA pass validation."""
    policy = Policy(require_pinned_actions=True)
    validator = PolicyValidator(policy)

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={
            "test": JobMeta(
                name="test",
                runs_on="ubuntu-latest",
                actions_used=[
                    ActionRef(
                        type=ActionType.GITHUB,
                        owner="actions",
                        repo="checkout",
                        ref="abc123def456789012345678901234567890abcd",  # SHA
                        source_file="test.yml",
                    )
                ],
            )
        },
        actions_used=[],
    )

    violations = validator.validate({"test.yml": workflow}, [])

    assert len(violations) == 0


def test_branch_refs_validation() -> None:
    """Test forbid branch refs policy."""
    policy = Policy(require_pinned_actions=False, forbid_branch_refs=True)
    validator = PolicyValidator(policy)

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={
            "test": JobMeta(
                name="test",
                runs_on="ubuntu-latest",
                actions_used=[
                    ActionRef(
                        type=ActionType.GITHUB,
                        owner="actions",
                        repo="checkout",
                        ref="main",
                        source_file="test.yml",
                    )
                ],
            )
        },
        actions_used=[
            ActionRef(
                type=ActionType.GITHUB,
                owner="actions",
                repo="checkout",
                ref="main",
                source_file="test.yml",
            )
        ],
    )

    violations = validator.validate({"test.yml": workflow}, [])

    assert len(violations) > 0
    assert violations[0]["rule"] == "forbid_branch_refs"


def test_allowed_actions_validation() -> None:
    """Test allowed actions whitelist."""
    policy = Policy(require_pinned_actions=False, allowed_actions=["actions/*", "github/*"])
    validator = PolicyValidator(policy)

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={
            "test": JobMeta(
                name="test",
                runs_on="ubuntu-latest",
                actions_used=[
                    ActionRef(
                        type=ActionType.GITHUB,
                        owner="thirdparty",
                        repo="action",
                        ref="v1",
                        source_file="test.yml",
                    )
                ],
            )
        },
        actions_used=[
            ActionRef(
                type=ActionType.GITHUB,
                owner="thirdparty",
                repo="action",
                ref="v1",
                source_file="test.yml",
            )
        ],
    )

    violations = validator.validate({"test.yml": workflow}, [])

    assert len(violations) > 0
    assert violations[0]["rule"] == "allowed_actions"


def test_denied_actions_validation() -> None:
    """Test denied actions blacklist."""
    policy = Policy(require_pinned_actions=False, denied_actions=["dangerous/*"])
    validator = PolicyValidator(policy)

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={
            "test": JobMeta(
                name="test",
                runs_on="ubuntu-latest",
                actions_used=[
                    ActionRef(
                        type=ActionType.GITHUB,
                        owner="dangerous",
                        repo="action",
                        ref="v1",
                        source_file="test.yml",
                    )
                ],
            )
        },
        actions_used=[
            ActionRef(
                type=ActionType.GITHUB,
                owner="dangerous",
                repo="action",
                ref="v1",
                source_file="test.yml",
            )
        ],
    )

    violations = validator.validate({"test.yml": workflow}, [])

    assert len(violations) > 0
    assert violations[0]["rule"] == "denied_actions"


def test_pr_concurrency_validation() -> None:
    """Test PR concurrency requirement."""
    policy = Policy(require_concurrency_on_pr=True)
    validator = PolicyValidator(policy)

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["pull_request"],
        concurrency=None,
        jobs={},
    )

    violations = validator.validate({"test.yml": workflow}, [])

    assert len(violations) > 0
    assert violations[0]["rule"] == "require_concurrency_on_pr"
    assert violations[0]["severity"] == "warning"


def test_pr_concurrency_with_group() -> None:
    """Test PR with concurrency group passes."""
    policy = Policy(require_concurrency_on_pr=True)
    validator = PolicyValidator(policy)

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["pull_request"],
        concurrency={"group": "${{ github.workflow }}"},
        jobs={},
    )

    violations = validator.validate({"test.yml": workflow}, [])

    assert len(violations) == 0


def test_matches_pattern() -> None:
    """Test pattern matching."""
    policy = Policy()
    validator = PolicyValidator(policy)

    assert validator._matches_pattern("actions/checkout", "actions/*") is True
    assert validator._matches_pattern("github/codeql-action", "github/*") is True
    assert validator._matches_pattern("thirdparty/action", "actions/*") is False
