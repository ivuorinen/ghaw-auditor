"""File scanner for discovering GitHub Actions and workflows."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class Scanner:
    """Scans repository for workflow and action files."""

    WORKFLOW_PATTERNS = [
        ".github/workflows/*.yml",
        ".github/workflows/*.yaml",
    ]

    ACTION_PATTERNS = [
        "**/action.yml",
        "**/action.yaml",
        ".github/actions/*/action.yml",
        ".github/actions/*/action.yaml",
    ]

    def __init__(self, repo_path: str | Path, exclude_patterns: list[str] | None = None) -> None:
        """Initialize scanner."""
        self.repo_path = Path(repo_path).resolve()
        self.exclude_patterns = exclude_patterns or []

    def _should_exclude(self, path: Path) -> bool:
        """Check if path should be excluded."""
        rel_path = path.relative_to(self.repo_path)
        return any(rel_path.match(pattern) for pattern in self.exclude_patterns)

    def find_workflows(self) -> list[Path]:
        """Find all workflow files."""
        workflows = []
        workflow_dir = self.repo_path / ".github" / "workflows"

        if not workflow_dir.exists():
            logger.warning(f"Workflow directory not found: {workflow_dir}")
            return workflows

        for pattern in ["*.yml", "*.yaml"]:
            for file_path in workflow_dir.glob(pattern):
                if not self._should_exclude(file_path):
                    workflows.append(file_path)

        logger.info(f"Found {len(workflows)} workflow files")
        return sorted(workflows)

    def find_actions(self) -> list[Path]:
        """Find all action manifest files.

        Supports multiple action discovery patterns:
        - .github/actions/*/action.yml (standard GitHub location)
        - ./action-name/action.yml (monorepo root-level actions)
        - Any depth: path/to/action/action.yml (recursive search)

        Excludes .github/workflows directory to avoid false positives.
        """
        actions = []

        # Check .github/actions directory
        actions_dir = self.repo_path / ".github" / "actions"
        if actions_dir.exists():
            for action_file in actions_dir.rglob("action.y*ml"):
                if action_file.name in ("action.yml", "action.yaml") and not self._should_exclude(action_file):
                    actions.append(action_file)
                    logger.debug(f"Found action: {action_file.relative_to(self.repo_path)}")

        # Check for action files in root and subdirectories (supports monorepo structure)
        for name in ("action.yml", "action.yaml"):
            for action_file in self.repo_path.rglob(name):
                # Skip if in .github/workflows
                if ".github/workflows" in str(action_file.relative_to(self.repo_path)):
                    continue
                if not self._should_exclude(action_file) and action_file not in actions:
                    actions.append(action_file)
                    logger.debug(f"Found action: {action_file.relative_to(self.repo_path)}")

        logger.info(f"Found {len(actions)} action files")
        return sorted(actions)
