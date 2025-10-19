"""Tests for resolver with mocked API."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ghaw_auditor.cache import Cache
from ghaw_auditor.github_client import GitHubClient
from ghaw_auditor.models import ActionRef, ActionType
from ghaw_auditor.resolver import Resolver


@pytest.fixture
def mock_github_client() -> Mock:
    """Create mock GitHub client."""
    client = Mock(spec=GitHubClient)
    client.get_ref_sha.return_value = "abc123def456"
    client.get_file_content.return_value = """
name: Test Action
description: A test action
runs:
  using: node20
  main: index.js
"""
    return client


@pytest.fixture
def temp_cache(tmp_path: Path) -> Cache:
    """Create temporary cache."""
    return Cache(tmp_path / "cache")


def test_resolver_initialization(mock_github_client: Mock, temp_cache: Cache, tmp_path: Path) -> None:
    """Test resolver initialization."""
    resolver = Resolver(mock_github_client, temp_cache, tmp_path)
    assert resolver.github_client == mock_github_client
    assert resolver.cache == temp_cache
    assert resolver.repo_path == tmp_path


def test_resolve_github_action(mock_github_client: Mock, temp_cache: Cache, tmp_path: Path) -> None:
    """Test resolving GitHub action."""
    resolver = Resolver(mock_github_client, temp_cache, tmp_path)

    action = ActionRef(
        type=ActionType.GITHUB,
        owner="actions",
        repo="checkout",
        ref="v4",
        source_file="test.yml",
    )

    key, manifest = resolver._resolve_github_action(action)

    assert key == "actions/checkout@abc123def456"
    assert manifest is not None
    assert manifest.name == "Test Action"
    assert action.resolved_sha == "abc123def456"


def test_resolve_local_action(mock_github_client: Mock, temp_cache: Cache, tmp_path: Path) -> None:
    """Test resolving local action."""
    # Create local action
    action_dir = tmp_path / ".github" / "actions" / "custom"
    action_dir.mkdir(parents=True)
    action_file = action_dir / "action.yml"

    # Write valid composite action YAML
    action_file.write_text(
        """name: Custom Action
description: Local action
runs:
  using: composite
  steps:
    - name: Test step
      run: echo test
      shell: bash
"""
    )

    resolver = Resolver(mock_github_client, temp_cache, tmp_path)

    action = ActionRef(
        type=ActionType.LOCAL,
        path="./.github/actions/custom",  # With leading ./
        source_file="test.yml",
    )

    key, manifest = resolver._resolve_local_action(action)

    assert key == "local:./.github/actions/custom"
    assert manifest is not None
    assert manifest.name == "Custom Action"
    assert manifest.is_composite is True


def test_resolve_docker_action(mock_github_client: Mock, temp_cache: Cache, tmp_path: Path) -> None:
    """Test resolving Docker action."""
    resolver = Resolver(mock_github_client, temp_cache, tmp_path)

    action = ActionRef(
        type=ActionType.DOCKER,
        path="docker://alpine:3.8",
        source_file="test.yml",
    )

    key, manifest = resolver._resolve_action(action)

    assert key == "docker:docker://alpine:3.8"
    assert manifest is None  # Docker actions don't have manifests


def test_resolve_actions_parallel(mock_github_client: Mock, temp_cache: Cache, tmp_path: Path) -> None:
    """Test parallel action resolution."""
    resolver = Resolver(mock_github_client, temp_cache, tmp_path, concurrency=2)

    actions = [
        ActionRef(
            type=ActionType.GITHUB,
            owner="actions",
            repo="checkout",
            ref="v4",
            source_file="test.yml",
        ),
        ActionRef(
            type=ActionType.GITHUB,
            owner="actions",
            repo="setup-node",
            ref="v4",
            source_file="test.yml",
        ),
    ]

    resolved = resolver.resolve_actions(actions)

    assert len(resolved) == 2
    assert mock_github_client.get_ref_sha.call_count == 2


def test_resolve_action_with_cache(mock_github_client: Mock, temp_cache: Cache, tmp_path: Path) -> None:
    """Test action resolution with caching."""
    resolver = Resolver(mock_github_client, temp_cache, tmp_path)

    action = ActionRef(
        type=ActionType.GITHUB,
        owner="actions",
        repo="checkout",
        ref="v4",
        source_file="test.yml",
    )

    # First call
    key1, manifest1 = resolver._resolve_github_action(action)

    # Reset mock
    mock_github_client.reset_mock()

    # Second call should use cache
    key2, manifest2 = resolver._resolve_github_action(action)

    assert key1 == key2
    # Cache should reduce API calls
    assert mock_github_client.get_ref_sha.call_count <= 1


def test_resolve_action_api_error(mock_github_client: Mock, temp_cache: Cache, tmp_path: Path) -> None:
    """Test handling API errors."""
    mock_github_client.get_ref_sha.side_effect = Exception("API Error")

    resolver = Resolver(mock_github_client, temp_cache, tmp_path)

    action = ActionRef(
        type=ActionType.GITHUB,
        owner="actions",
        repo="checkout",
        ref="v4",
        source_file="test.yml",
    )

    key, manifest = resolver._resolve_github_action(action)

    assert key == ""
    assert manifest is None


def test_resolve_monorepo_action(mock_github_client: Mock, temp_cache: Cache, tmp_path: Path) -> None:
    """Test resolving monorepo action with path."""
    resolver = Resolver(mock_github_client, temp_cache, tmp_path)

    action = ActionRef(
        type=ActionType.GITHUB,
        owner="owner",
        repo="repo",
        path="subdir/action",
        ref="v1",
        source_file="test.yml",
    )

    key, manifest = resolver._resolve_github_action(action)

    # Should try to fetch subdir/action/action.yml
    mock_github_client.get_file_content.assert_called_with("owner", "repo", "subdir/action/action.yml", "abc123def456")


def test_resolve_action_unknown_type(mock_github_client: Mock, temp_cache: Cache, tmp_path: Path) -> None:
    """Test resolving action with unknown type returns empty."""
    from ghaw_auditor.models import ActionType

    resolver = Resolver(mock_github_client, temp_cache, tmp_path)

    # Create action with REUSABLE_WORKFLOW type (not handled by resolver)
    action = ActionRef(
        type=ActionType.REUSABLE_WORKFLOW,
        owner="owner",
        repo="repo",
        path=".github/workflows/test.yml",
        ref="v1",
        source_file="test.yml",
    )

    key, manifest = resolver._resolve_action(action)

    assert key == ""
    assert manifest is None


def test_resolve_local_action_no_path(mock_github_client: Mock, temp_cache: Cache, tmp_path: Path) -> None:
    """Test resolving local action without path."""
    resolver = Resolver(mock_github_client, temp_cache, tmp_path)

    action = ActionRef(
        type=ActionType.LOCAL,
        path=None,
        source_file="test.yml",
    )

    key, manifest = resolver._resolve_local_action(action)

    assert key == ""
    assert manifest is None


def test_resolve_local_action_not_found(mock_github_client: Mock, temp_cache: Cache, tmp_path: Path) -> None:
    """Test resolving local action that doesn't exist."""
    resolver = Resolver(mock_github_client, temp_cache, tmp_path)

    action = ActionRef(
        type=ActionType.LOCAL,
        path="./.github/actions/nonexistent",
        source_file="test.yml",
    )

    key, manifest = resolver._resolve_local_action(action)

    assert key == ""
    assert manifest is None


def test_resolve_local_action_invalid_yaml(mock_github_client: Mock, temp_cache: Cache, tmp_path: Path) -> None:
    """Test resolving local action with invalid YAML."""
    action_dir = tmp_path / ".github" / "actions" / "broken"
    action_dir.mkdir(parents=True)
    action_file = action_dir / "action.yml"
    action_file.write_text("invalid: yaml: content: {{{")

    resolver = Resolver(mock_github_client, temp_cache, tmp_path)

    action = ActionRef(
        type=ActionType.LOCAL,
        path="./.github/actions/broken",
        source_file="test.yml",
    )

    key, manifest = resolver._resolve_local_action(action)

    # Should handle parse error gracefully
    assert key == ""
    assert manifest is None


def test_resolve_github_action_missing_fields(mock_github_client: Mock, temp_cache: Cache, tmp_path: Path) -> None:
    """Test resolving GitHub action with missing required fields."""
    resolver = Resolver(mock_github_client, temp_cache, tmp_path)

    # Missing owner
    action = ActionRef(
        type=ActionType.GITHUB,
        owner=None,
        repo="checkout",
        ref="v4",
        source_file="test.yml",
    )

    key, manifest = resolver._resolve_github_action(action)

    assert key == ""
    assert manifest is None


def test_resolve_github_action_manifest_not_found(mock_github_client: Mock, temp_cache: Cache, tmp_path: Path) -> None:
    """Test resolving GitHub action when manifest cannot be fetched."""
    # Setup mock to fail fetching manifest
    mock_github_client.get_ref_sha.return_value = "abc123"
    mock_github_client.get_file_content.side_effect = Exception("404 Not Found")

    resolver = Resolver(mock_github_client, temp_cache, tmp_path)

    action = ActionRef(
        type=ActionType.GITHUB,
        owner="actions",
        repo="missing",
        ref="v1",
        source_file="test.yml",
    )

    key, manifest = resolver._resolve_github_action(action)

    # Should return key but no manifest
    assert "actions/missing@abc123" in key
    assert manifest is None


def test_resolve_monorepo_action_manifest_not_found(
    mock_github_client: Mock, temp_cache: Cache, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test resolving monorepo action when manifest cannot be fetched."""
    import logging

    # Setup mock to fail fetching manifest for both .yml and .yaml
    mock_github_client.get_ref_sha.return_value = "abc123"
    mock_github_client.get_file_content.side_effect = Exception("404 Not Found")

    resolver = Resolver(mock_github_client, temp_cache, tmp_path)

    action = ActionRef(
        type=ActionType.GITHUB,
        owner="owner",
        repo="repo",
        path="subdir/action",
        ref="v1",
        source_file="test.yml",
    )

    with caplog.at_level(logging.ERROR):
        key, manifest = resolver._resolve_github_action(action)

    # Should return key but no manifest
    assert "owner/repo@abc123" in key
    assert manifest is None
    # Should log error with path
    assert "owner/repo/subdir/action" in caplog.text
    assert "(tried action.yml and action.yaml)" in caplog.text


def test_resolve_github_action_invalid_manifest(mock_github_client: Mock, temp_cache: Cache, tmp_path: Path) -> None:
    """Test resolving GitHub action with invalid manifest content."""
    # Setup mock to return invalid YAML
    mock_github_client.get_ref_sha.return_value = "abc123"
    mock_github_client.get_file_content.return_value = "invalid: yaml: {{{: bad"

    resolver = Resolver(mock_github_client, temp_cache, tmp_path)

    action = ActionRef(
        type=ActionType.GITHUB,
        owner="actions",
        repo="broken",
        ref="v1",
        source_file="test.yml",
    )

    key, manifest = resolver._resolve_github_action(action)

    # Should handle parse error gracefully
    assert key == ""
    assert manifest is None


def test_resolve_actions_with_exception(mock_github_client: Mock, temp_cache: Cache, tmp_path: Path) -> None:
    """Test parallel resolution handles exceptions gracefully."""

    # Setup one action to succeed, one to fail
    def side_effect_get_ref(owner: str, repo: str, ref: str) -> str:
        if repo == "fail":
            raise Exception("API Error")
        return "abc123"

    mock_github_client.get_ref_sha.side_effect = side_effect_get_ref

    resolver = Resolver(mock_github_client, temp_cache, tmp_path, concurrency=2)

    actions = [
        ActionRef(
            type=ActionType.GITHUB,
            owner="actions",
            repo="checkout",
            ref="v4",
            source_file="test.yml",
        ),
        ActionRef(
            type=ActionType.GITHUB,
            owner="actions",
            repo="fail",
            ref="v1",
            source_file="test.yml",
        ),
    ]

    resolved = resolver.resolve_actions(actions)

    # Should only resolve the successful one
    assert len(resolved) == 1
    assert "actions/checkout" in list(resolved.keys())[0]


def test_resolve_actions_logs_exception(mock_github_client: Mock, temp_cache: Cache, tmp_path: Path) -> None:
    """Test that exceptions during resolution are logged."""
    resolver = Resolver(mock_github_client, temp_cache, tmp_path)

    # Patch _resolve_action to raise an exception directly
    # This will propagate to future.result() and trigger the exception handler
    with patch.object(resolver, "_resolve_action", side_effect=RuntimeError("Unexpected error")):
        actions = [
            ActionRef(
                type=ActionType.GITHUB,
                owner="actions",
                repo="broken",
                ref="v1",
                source_file="test.yml",
            ),
        ]

        resolved = resolver.resolve_actions(actions)

        # Should handle exception gracefully and log error
        assert len(resolved) == 0


def test_resolve_local_action_file_path_parse_error(
    mock_github_client: Mock, temp_cache: Cache, tmp_path: Path
) -> None:
    """Test resolving local action when file path parsing fails."""
    # Create a directory with invalid action.yml
    action_dir = tmp_path / "my-action"
    action_dir.mkdir()
    action_file = action_dir / "action.yml"
    action_file.write_text("invalid: yaml: content: {{{")

    resolver = Resolver(mock_github_client, temp_cache, tmp_path)

    # Reference a file that starts with "action." so parent = action_path.parent
    # This triggers the else branch where we look in parent directory
    action = ActionRef(
        type=ActionType.LOCAL,
        path="./my-action/action.custom.yml",
        source_file="test.yml",
    )

    key, manifest = resolver._resolve_local_action(action)

    # Should handle parse error in file path branch (else branch)
    # The code will look in parent (my-action/) for action.yml and fail to parse
    assert key == ""
    assert manifest is None


def test_resolve_action_local_type(mock_github_client: Mock, temp_cache: Cache, tmp_path: Path) -> None:
    """Test _resolve_action with LOCAL action type."""
    # Create valid local action
    action_dir = tmp_path / "my-action"
    action_dir.mkdir()
    action_file = action_dir / "action.yml"
    action_file.write_text("""
name: My Action
description: Test action
runs:
  using: composite
  steps:
    - run: echo test
      shell: bash
""")

    resolver = Resolver(mock_github_client, temp_cache, tmp_path)

    action = ActionRef(
        type=ActionType.LOCAL,
        path="./my-action",
        source_file="test.yml",
    )

    # Call _resolve_action to hit the LOCAL branch
    key, manifest = resolver._resolve_action(action)

    assert key == "local:./my-action"
    assert manifest is not None
    assert manifest.name == "My Action"


def test_resolve_local_action_file_path_success(mock_github_client: Mock, temp_cache: Cache, tmp_path: Path) -> None:
    """Test resolving local action via file path (else branch) with valid YAML."""
    # Create a directory with valid action.yml
    action_dir = tmp_path / "my-action"
    action_dir.mkdir()
    action_file = action_dir / "action.yml"
    action_file.write_text("""
name: File Path Action
description: Test action via file path
runs:
  using: composite
  steps:
    - run: echo test
      shell: bash
""")

    resolver = Resolver(mock_github_client, temp_cache, tmp_path)

    # Reference a file that starts with "action." to trigger else branch
    # with parent = action_path.parent
    action = ActionRef(
        type=ActionType.LOCAL,
        path="./my-action/action.yml",
        source_file="test.yml",
    )

    key, manifest = resolver._resolve_local_action(action)

    # Should successfully parse from parent directory
    assert key == "local:./my-action/action.yml"
    assert manifest is not None
    assert manifest.name == "File Path Action"
