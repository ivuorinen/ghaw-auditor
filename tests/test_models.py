"""Tests for models."""

from datetime import datetime

from ghaw_auditor.models import (
    ActionInput,
    ActionManifest,
    ActionRef,
    ActionType,
    BaselineMeta,
    PermissionLevel,
    Permissions,
)


def test_action_ref_canonical_key_github() -> None:
    """Test canonical key for GitHub action."""
    ref = ActionRef(
        type=ActionType.GITHUB,
        owner="actions",
        repo="checkout",
        ref="v4",
        resolved_sha="abc123",
        source_file="test.yml",
    )

    key = ref.canonical_key()
    assert key == "actions/checkout@abc123"


def test_action_ref_canonical_key_local() -> None:
    """Test canonical key for local action."""
    ref = ActionRef(
        type=ActionType.LOCAL,
        path="./.github/actions/custom",
        source_file="test.yml",
    )

    key = ref.canonical_key()
    assert key == "local:./.github/actions/custom"


def test_action_ref_canonical_key_reusable_workflow() -> None:
    """Test canonical key for reusable workflow."""
    ref = ActionRef(
        type=ActionType.REUSABLE_WORKFLOW,
        owner="owner",
        repo="repo",
        path=".github/workflows/reusable.yml",
        ref="v1",
        resolved_sha="abc123",
        source_file="test.yml",
    )

    key = ref.canonical_key()
    assert key == "owner/repo/.github/workflows/reusable.yml@abc123"


def test_action_ref_canonical_key_docker() -> None:
    """Test canonical key for Docker action."""
    ref = ActionRef(
        type=ActionType.DOCKER,
        path="docker://alpine:3.8",
        source_file="test.yml",
    )

    key = ref.canonical_key()
    assert key == "docker:docker://alpine:3.8"


def test_permissions_model() -> None:
    """Test permissions model."""
    perms = Permissions(
        contents=PermissionLevel.READ,
        pull_requests=PermissionLevel.WRITE,
    )

    assert perms.contents == PermissionLevel.READ
    assert perms.pull_requests == PermissionLevel.WRITE


def test_action_manifest() -> None:
    """Test action manifest model."""
    manifest = ActionManifest(
        name="Test Action",
        description="A test action",
        inputs={"test-input": ActionInput(name="test-input", required=True)},
    )

    assert manifest.name == "Test Action"
    assert "test-input" in manifest.inputs
    assert manifest.inputs["test-input"].required is True


def test_baseline_meta() -> None:
    """Test baseline metadata model."""
    meta = BaselineMeta(
        auditor_version="1.0.0",
        commit_sha="abc123",
        timestamp=datetime.now(),
    )

    assert meta.auditor_version == "1.0.0"
    assert meta.commit_sha == "abc123"
    assert meta.schema_version == "1.0"
