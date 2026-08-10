"""File scanner for discovering GitHub Actions and workflows."""

from __future__ import annotations

import logging
import os
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

    # Never descended into: these hold no first-party actions and contain the
    # vast majority of a checkout's directory entries.
    SKIP_DIRS = frozenset(
        {
            ".git",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".tox",
            ".nox",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "dist",
            "build",
            "site-packages",
        }
    )

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
        workflows: list[Path] = []
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
        actions: set[Path] = set()
        workflows_dir = self.repo_path / ".github" / "workflows"

        # os.walk (not rglob) so SKIP_DIRS can be pruned in place: rglob has no
        # way to avoid descending into .git / node_modules / .venv, which both
        # dominates scan time and surfaces vendored third-party action.yml files
        # as if they belonged to this repository.
        for dirpath, dirnames, filenames in os.walk(self.repo_path):
            dirnames[:] = [d for d in dirnames if d not in self.SKIP_DIRS]
            current_dir = Path(dirpath)

            if current_dir == workflows_dir:
                continue

            for name in ("action.yml", "action.yaml"):
                if name not in filenames:
                    continue
                action_file = current_dir / name
                if not self._should_exclude(action_file):
                    actions.add(action_file)
                    logger.debug(f"Found action: {action_file.relative_to(self.repo_path)}")

        logger.info(f"Found {len(actions)} action files")
        return sorted(actions)
