"""Tests for scanner module."""

from pathlib import Path

from ghaw_auditor.scanner import Scanner


def test_scanner_initialization() -> None:
    """Test scanner can be initialized."""
    scanner = Scanner(".")
    assert scanner.repo_path.exists()


def test_scanner_initialization_with_exclusions() -> None:
    """Test scanner initialization with exclusion patterns."""
    scanner = Scanner(".", exclude_patterns=["**/node_modules/**", "**/dist/**"])
    assert len(scanner.exclude_patterns) == 2
    assert "**/node_modules/**" in scanner.exclude_patterns


def test_scanner_should_exclude(tmp_path: Path) -> None:
    """Test exclusion pattern matching."""
    # Note: glob patterns need to match the full path including files
    scanner = Scanner(tmp_path, exclude_patterns=["node_modules/**/*", ".git/**/*"])

    # Create test directories and files
    node_modules_path = tmp_path / "node_modules" / "test" / "action.yml"
    node_modules_path.parent.mkdir(parents=True)
    node_modules_path.touch()

    git_path = tmp_path / ".git" / "hooks" / "pre-commit"
    git_path.parent.mkdir(parents=True)
    git_path.touch()

    valid_path = tmp_path / ".github" / "actions" / "test" / "action.yml"
    valid_path.parent.mkdir(parents=True)
    valid_path.touch()

    # Test exclusions
    assert scanner._should_exclude(node_modules_path) is True
    assert scanner._should_exclude(git_path) is True
    assert scanner._should_exclude(valid_path) is False


def test_find_workflows_empty_dir(tmp_path: Path) -> None:
    """Test finding workflows in empty directory."""
    scanner = Scanner(tmp_path)
    workflows = scanner.find_workflows()
    assert len(workflows) == 0


def test_find_workflows_with_files(tmp_path: Path) -> None:
    """Test finding workflow files."""
    # Create workflow directory
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)

    # Create workflow files
    (workflows_dir / "ci.yml").write_text("name: CI\non: push")
    (workflows_dir / "release.yaml").write_text("name: Release\non: push")
    (workflows_dir / "README.md").write_text("# Workflows")  # Should be ignored

    scanner = Scanner(tmp_path)
    workflows = scanner.find_workflows()

    assert len(workflows) == 2
    assert workflows[0].name == "ci.yml"
    assert workflows[1].name == "release.yaml"


def test_find_workflows_with_exclusions(tmp_path: Path) -> None:
    """Test finding workflows with exclusion patterns."""
    # Create workflow directory
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)

    # Create workflow files
    (workflows_dir / "ci.yml").write_text("name: CI")
    (workflows_dir / "test.yml").write_text("name: Test")

    scanner = Scanner(tmp_path, exclude_patterns=["**test.yml"])
    workflows = scanner.find_workflows()

    assert len(workflows) == 1
    assert workflows[0].name == "ci.yml"


def test_find_actions_empty_dir(tmp_path: Path) -> None:
    """Test finding actions in empty directory."""
    scanner = Scanner(tmp_path)
    actions = scanner.find_actions()
    assert len(actions) == 0


def test_find_actions_in_github_directory(tmp_path: Path) -> None:
    """Test finding actions in .github/actions directory."""
    # Create actions directory
    actions_dir = tmp_path / ".github" / "actions"

    # Create multiple actions
    action1_dir = actions_dir / "action1"
    action1_dir.mkdir(parents=True)
    (action1_dir / "action.yml").write_text("name: Action 1")

    action2_dir = actions_dir / "action2"
    action2_dir.mkdir(parents=True)
    (action2_dir / "action.yaml").write_text("name: Action 2")

    # Create nested action
    nested_dir = actions_dir / "group" / "nested"
    nested_dir.mkdir(parents=True)
    (nested_dir / "action.yml").write_text("name: Nested Action")

    scanner = Scanner(tmp_path)
    actions = scanner.find_actions()

    assert len(actions) == 3
    assert any("action1" in str(a) for a in actions)
    assert any("action2" in str(a) for a in actions)
    assert any("nested" in str(a) for a in actions)


def test_find_actions_in_root(tmp_path: Path) -> None:
    """Test finding action in root directory."""
    # Create action in root
    (tmp_path / "action.yml").write_text("name: Root Action")

    scanner = Scanner(tmp_path)
    actions = scanner.find_actions()

    assert len(actions) == 1
    assert actions[0].name == "action.yml"


def test_find_actions_excludes_workflows_dir(tmp_path: Path) -> None:
    """Test that actions in workflows directory are excluded."""
    # Create workflow directory with action file (should be ignored)
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "action.yml").write_text("name: Not an action")

    # Create real action
    actions_dir = tmp_path / ".github" / "actions" / "real"
    actions_dir.mkdir(parents=True)
    (actions_dir / "action.yml").write_text("name: Real Action")

    scanner = Scanner(tmp_path)
    actions = scanner.find_actions()

    # Should only find the action in .github/actions, not in workflows
    assert len(actions) == 1
    assert "actions/real" in str(actions[0])


def test_find_actions_with_exclusions(tmp_path: Path) -> None:
    """Test finding actions with exclusion patterns."""
    # Create actions
    actions_dir = tmp_path / ".github" / "actions"

    action1_dir = actions_dir / "include-me"
    action1_dir.mkdir(parents=True)
    (action1_dir / "action.yml").write_text("name: Include")

    action2_dir = actions_dir / "exclude-me"
    action2_dir.mkdir(parents=True)
    (action2_dir / "action.yml").write_text("name: Exclude")

    scanner = Scanner(tmp_path, exclude_patterns=["**/exclude-me/**"])
    actions = scanner.find_actions()

    assert len(actions) == 1
    assert "include-me" in str(actions[0])


def test_find_actions_deduplication(tmp_path: Path) -> None:
    """Test that duplicate actions are not included."""
    # Create action in .github/actions
    actions_dir = tmp_path / ".github" / "actions" / "my-action"
    actions_dir.mkdir(parents=True)
    action_file = actions_dir / "action.yml"
    action_file.write_text("name: My Action")

    scanner = Scanner(tmp_path)
    actions = scanner.find_actions()

    # Should find it exactly once
    assert len(actions) == 1
    assert actions[0] == action_file


def test_find_actions_monorepo_structure(tmp_path: Path) -> None:
    """Test finding actions in monorepo with multiple root-level action directories."""
    # Create monorepo structure: ./action1/, ./action2/, etc.
    for name in ["sync-labels", "deploy-action", "test-action"]:
        action_dir = tmp_path / name
        action_dir.mkdir()
        (action_dir / "action.yml").write_text(f"name: {name}\ndescription: Test action")

    scanner = Scanner(tmp_path)
    actions = scanner.find_actions()

    assert len(actions) == 3
    assert any("sync-labels" in str(a) for a in actions)
    assert any("deploy-action" in str(a) for a in actions)
    assert any("test-action" in str(a) for a in actions)
