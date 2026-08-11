"""Tests for policy validator."""

from ghaw_auditor.models import ActionRef, ActionType, JobMeta, PermissionLevel, Permissions, Policy, WorkflowMeta
from ghaw_auditor.policy import PolicyValidator


def test_policy_validator_initialization() -> None:
    """Test validator initialization."""
    policy = Policy(min_permissions=False)
    validator = PolicyValidator(policy)
    assert validator.policy == policy


def test_pinned_actions_validation() -> None:
    """Test pinned actions policy."""
    policy = Policy(require_pinned_actions=True, min_permissions=False)
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

    violations = validator.validate({"test.yml": workflow})

    assert len(violations) > 0
    assert violations[0]["rule"] == "require_pinned_actions"
    assert violations[0]["severity"] == "error"


def test_pinned_actions_with_sha() -> None:
    """Test pinned actions with SHA pass validation.

    WorkflowMeta.actions_used must carry the ref, mirroring what Parser builds
    (the union of every job's actions). Leaving it empty made this assertion
    vacuous -- it passed without the SHA ever reaching the validator.
    """
    policy = Policy(require_pinned_actions=True, min_permissions=False)
    validator = PolicyValidator(policy)

    pinned = ActionRef(
        type=ActionType.GITHUB,
        owner="actions",
        repo="checkout",
        ref="abc123def456789012345678901234567890abcd",  # SHA
        source_file="test.yml",
    )
    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["push"],
        jobs={"test": JobMeta(name="test", runs_on="ubuntu-latest", actions_used=[pinned])},
        actions_used=[pinned],
    )

    # Guard: without this the assertion below passes on an empty input.
    assert workflow.actions_used

    violations = validator.validate({"test.yml": workflow})

    assert len(violations) == 0


def test_branch_refs_validation() -> None:
    """Test forbid branch refs policy."""
    policy = Policy(require_pinned_actions=False, forbid_branch_refs=True, min_permissions=False)
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

    violations = validator.validate({"test.yml": workflow})

    assert len(violations) > 0
    assert violations[0]["rule"] == "forbid_branch_refs"


def test_allowed_actions_validation() -> None:
    """Test allowed actions whitelist."""
    policy = Policy(require_pinned_actions=False, allowed_actions=["actions/*", "github/*"], min_permissions=False)
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

    violations = validator.validate({"test.yml": workflow})

    assert len(violations) > 0
    assert violations[0]["rule"] == "allowed_actions"


def test_denied_actions_validation() -> None:
    """Test denied actions blacklist."""
    policy = Policy(require_pinned_actions=False, denied_actions=["dangerous/*"], min_permissions=False)
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

    violations = validator.validate({"test.yml": workflow})

    assert len(violations) > 0
    assert violations[0]["rule"] == "denied_actions"


def test_pr_concurrency_validation() -> None:
    """Test PR concurrency requirement."""
    policy = Policy(require_concurrency_on_pr=True, min_permissions=False)
    validator = PolicyValidator(policy)

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["pull_request"],
        concurrency=None,
        jobs={},
    )

    violations = validator.validate({"test.yml": workflow})

    assert len(violations) > 0
    assert violations[0]["rule"] == "require_concurrency_on_pr"
    assert violations[0]["severity"] == "warning"


def test_pr_concurrency_with_group() -> None:
    """Test PR with concurrency group passes."""
    policy = Policy(require_concurrency_on_pr=True, min_permissions=False)
    validator = PolicyValidator(policy)

    workflow = WorkflowMeta(
        name="Test",
        path="test.yml",
        triggers=["pull_request"],
        concurrency={"group": "${{ github.workflow }}"},
        jobs={},
    )

    violations = validator.validate({"test.yml": workflow})

    assert len(violations) == 0


def test_matches_pattern() -> None:
    """Test pattern matching."""
    policy = Policy(min_permissions=False)
    validator = PolicyValidator(policy)

    assert validator._matches_pattern("actions/checkout", "actions/*") is True
    assert validator._matches_pattern("github/codeql-action", "github/*") is True
    assert validator._matches_pattern("thirdparty/action", "actions/*") is False


# ============================================================================
# Regression tests for defects found by the /nitpicker audit.
# Each asserts an exact count or an exact absence — `len(...) > 0` cannot
# distinguish correct behaviour from the bugs these cover.
# ============================================================================


def _workflow_with(actions: list[ActionRef], **kwargs: object) -> WorkflowMeta:
    """Build a WorkflowMeta whose single job holds the given action refs.

    Mirrors what Parser produces: WorkflowMeta.actions_used is the union of all
    job action lists, so the same refs appear at both levels.
    """
    job = JobMeta(name="build", runs_on="ubuntu-latest", actions_used=list(actions))
    return WorkflowMeta(
        name="wf",
        path="w.yml",
        jobs={"build": job},
        actions_used=list(actions),
        **kwargs,  # type: ignore[arg-type]
    )


def test_unpinned_action_reported_exactly_once() -> None:
    """One unpinned action must yield exactly one violation, not two.

    WorkflowMeta.actions_used already contains every job's actions; iterating
    both levels double-counted every violation.
    """
    ref = ActionRef(type=ActionType.GITHUB, owner="actions", repo="checkout", ref="v4", source_file="w.yml")
    violations = PolicyValidator(Policy(require_pinned_actions=True, min_permissions=False)).validate(
        {"w.yml": _workflow_with([ref])}
    )

    assert len(violations) == 1
    assert violations[0]["rule"] == "require_pinned_actions"


def test_reusable_workflow_on_branch_is_reported() -> None:
    """A reusable workflow pinned to a branch violates both pinning rules.

    Reusable workflows run in the caller's context with the caller's secrets,
    so exempting them from these checks left the highest-value target unguarded.
    """
    ref = ActionRef(
        type=ActionType.REUSABLE_WORKFLOW,
        owner="some-org",
        repo="some-repo",
        path=".github/workflows/build.yml",
        ref="main",
        source_file="w.yml",
    )
    workflows = {"w.yml": _workflow_with([ref])}

    pinned = PolicyValidator(Policy(require_pinned_actions=True, min_permissions=False)).validate(workflows)
    assert len(pinned) == 1
    assert pinned[0]["rule"] == "require_pinned_actions"

    branch = PolicyValidator(
        Policy(require_pinned_actions=False, forbid_branch_refs=True, min_permissions=False)
    ).validate(workflows)
    assert len(branch) == 1
    assert branch[0]["rule"] == "forbid_branch_refs"


def test_reusable_workflow_pinned_to_sha_is_clean() -> None:
    """A SHA-pinned reusable workflow must produce no violations."""
    ref = ActionRef(
        type=ActionType.REUSABLE_WORKFLOW,
        owner="some-org",
        repo="some-repo",
        path=".github/workflows/build.yml",
        ref="a" * 40,
        source_file="w.yml",
    )
    policy = Policy(require_pinned_actions=True, forbid_branch_refs=True, min_permissions=False)
    assert PolicyValidator(policy).validate({"w.yml": _workflow_with([ref])}) == []


def test_uppercase_and_sha256_pins_are_accepted() -> None:
    """Uppercase hex and 64-char SHA-256 object ids are valid pins."""
    refs = [
        ActionRef(type=ActionType.GITHUB, owner="a", repo="b", ref="A1B2C3D4E5" * 4, source_file="w.yml"),
        ActionRef(type=ActionType.GITHUB, owner="c", repo="d", ref="f" * 64, source_file="w.yml"),
    ]
    assert (
        PolicyValidator(Policy(require_pinned_actions=True, min_permissions=False)).validate(
            {"w.yml": _workflow_with(refs)}
        )
        == []
    )


def test_deny_pattern_dot_is_literal_not_regex_wildcard() -> None:
    """A dot in a deny pattern must match a dot, not any character."""
    matching = ActionRef(type=ActionType.GITHUB, owner="evil.org", repo="tool", ref="v1", source_file="w.yml")
    lookalike = ActionRef(type=ActionType.GITHUB, owner="evilXorg", repo="tool", ref="v1", source_file="w.yml")
    policy = Policy(require_pinned_actions=False, denied_actions=["evil.org/tool"], min_permissions=False)

    assert len(PolicyValidator(policy).validate({"w.yml": _workflow_with([matching])})) == 1
    assert PolicyValidator(policy).validate({"w.yml": _workflow_with([lookalike])}) == []


def test_malformed_deny_pattern_does_not_raise() -> None:
    """An unbalanced bracket in a user policy must not crash the validator."""
    ref = ActionRef(type=ActionType.GITHUB, owner="a", repo="b", ref="v1", source_file="w.yml")
    policy = Policy(require_pinned_actions=False, denied_actions=["a/[b"], min_permissions=False)

    assert PolicyValidator(policy).validate({"w.yml": _workflow_with([ref])}) == []


def test_min_permissions_flags_write_all() -> None:
    """`permissions: write-all` is the maximally permissive token grant."""
    perms = Permissions(**dict.fromkeys(Permissions.model_fields, PermissionLevel.WRITE))
    workflow = WorkflowMeta(name="wf", path="w.yml", permissions=perms, jobs={})

    violations = PolicyValidator(Policy(require_pinned_actions=False)).validate({"w.yml": workflow})

    assert len(violations) == 1
    assert violations[0]["rule"] == "min_permissions"
    assert violations[0]["severity"] == "error"
    assert "write-all" in violations[0]["message"]


def test_min_permissions_warns_when_nothing_is_declared() -> None:
    """No permissions anywhere means the token inherits the repo default."""
    workflow = WorkflowMeta(
        name="wf",
        path="w.yml",
        jobs={"build": JobMeta(name="build", runs_on="ubuntu-latest")},
    )

    violations = PolicyValidator(Policy(require_pinned_actions=False)).validate({"w.yml": workflow})

    assert len(violations) == 1
    assert violations[0]["rule"] == "min_permissions"
    assert violations[0]["severity"] == "warning"


def test_min_permissions_accepts_a_scoped_declaration() -> None:
    """An explicit least-privilege declaration is clean."""
    workflow = WorkflowMeta(
        name="wf",
        path="w.yml",
        permissions=Permissions(contents=PermissionLevel.READ),
        jobs={},
    )

    assert PolicyValidator(Policy(require_pinned_actions=False)).validate({"w.yml": workflow}) == []


def test_min_permissions_flags_a_write_all_job() -> None:
    """write-all at job level is caught even when the workflow scopes itself."""
    job_perms = Permissions(**dict.fromkeys(Permissions.model_fields, PermissionLevel.WRITE))
    workflow = WorkflowMeta(
        name="wf",
        path="w.yml",
        permissions=Permissions(contents=PermissionLevel.READ),
        jobs={"build": JobMeta(name="build", runs_on="ubuntu-latest", permissions=job_perms)},
    )

    violations = PolicyValidator(Policy(require_pinned_actions=False)).validate({"w.yml": workflow})

    assert len(violations) == 1
    assert "Job 'build'" in violations[0]["message"]


def test_min_permissions_can_be_disabled() -> None:
    """The flag genuinely gates the check."""
    workflow = WorkflowMeta(name="wf", path="w.yml", jobs={})

    policy = Policy(require_pinned_actions=False, min_permissions=False)
    assert PolicyValidator(policy).validate({"w.yml": workflow}) == []


def test_allowlist_ignores_local_and_docker_actions() -> None:
    """Only remotely-referenced actions are subject to allow/deny lists.

    A local (./path) or docker:// reference has no owner/repo to match against.
    """
    refs = [
        ActionRef(type=ActionType.LOCAL, path="./.github/actions/x", source_file="w.yml"),
        ActionRef(type=ActionType.DOCKER, path="docker://alpine:3", source_file="w.yml"),
    ]
    policy = Policy(require_pinned_actions=False, min_permissions=False, allowed_actions=["actions/*"])

    assert PolicyValidator(policy).validate({"w.yml": _workflow_with(refs)}) == []


def test_action_present_in_the_allowlist_produces_no_violation() -> None:
    """The allowed branch is exercised, not just the rejected one."""
    ref = ActionRef(type=ActionType.GITHUB, owner="actions", repo="checkout", ref="v4", source_file="w.yml")
    policy = Policy(require_pinned_actions=False, min_permissions=False, allowed_actions=["actions/*"])

    assert PolicyValidator(policy).validate({"w.yml": _workflow_with([ref])}) == []
