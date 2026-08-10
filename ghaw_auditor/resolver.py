"""Action resolver for GitHub actions."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

from ghaw_auditor.cache import Cache
from ghaw_auditor.github_client import GitHubClient
from ghaw_auditor.models import ActionManifest, ActionRef, ActionType
from ghaw_auditor.parser import Parser

logger = logging.getLogger(__name__)


class Resolver:
    """Resolves action references and fetches manifests."""

    def __init__(
        self,
        github_client: GitHubClient,
        cache: Cache,
        repo_path: Path,
        concurrency: int = 4,
    ) -> None:
        """Initialize resolver."""
        self.github_client = github_client
        self.cache = cache
        self.parser = Parser(repo_path)
        self.repo_path = repo_path
        self.concurrency = concurrency

    def resolve_actions(self, actions: list[ActionRef]) -> dict[str, ActionManifest]:
        """Resolve multiple action references in parallel."""
        resolved: dict[str, ActionManifest] = {}

        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            futures = {executor.submit(self._resolve_action, action): action for action in actions}

            for future in as_completed(futures):
                action = futures[future]
                try:
                    key, manifest = future.result()
                    if key and manifest:
                        resolved[key] = manifest
                except Exception as e:
                    logger.error(f"Failed to resolve {action.canonical_key()}: {e}")

        return resolved

    def _resolve_action(self, action: ActionRef) -> tuple[str, ActionManifest | None]:
        """Resolve a single action reference."""
        if action.type == ActionType.LOCAL:
            return self._resolve_local_action(action)
        elif action.type == ActionType.GITHUB:
            return self._resolve_github_action(action)
        elif action.type == ActionType.DOCKER:
            # Docker actions don't have manifests to parse
            return action.canonical_key(), None
        return "", None

    def _resolve_local_action(self, action: ActionRef) -> tuple[str, ActionManifest | None]:
        """Resolve a local action."""
        if not action.path:
            return "", None

        # Remove leading ./ prefix only
        clean_path = action.path[2:] if action.path.startswith("./") else action.path
        action_path = self.repo_path / clean_path

        # If action_path is a directory, look for action.yml/yaml inside
        # If it's a file path, look in parent directory
        if action_path.is_dir():
            for name in ("action.yml", "action.yaml"):
                manifest_path = action_path / name
                if manifest_path.exists():
                    try:
                        manifest = self.parser.parse_action(manifest_path)
                        return action.canonical_key(), manifest
                    except Exception as e:
                        logger.error(f"Failed to parse local action {manifest_path}: {e}")
                        continue
        else:
            # Try as parent directory
            parent = action_path.parent if action_path.name.startswith("action.") else action_path
            for name in ("action.yml", "action.yaml"):
                manifest_path = parent / name
                if manifest_path.exists():
                    try:
                        manifest = self.parser.parse_action(manifest_path)
                        return action.canonical_key(), manifest
                    except Exception as e:
                        logger.error(f"Failed to parse local action {manifest_path}: {e}")
                        continue

        logger.warning(f"Local action manifest not found: {action_path}")
        return "", None

    def _fetch_manifest_content(self, action: ActionRef, sha: str, manifest_path: str) -> str | None:
        """Fetch an action manifest, trying action.yml then action.yaml.

        Returns None when the manifest genuinely does not exist. Any other
        failure (5xx, rate limit, network) is logged and also returns None, but
        without pretending the next extension might work — reporting a server
        error as "manifest not found" sends users to the wrong repository.
        """
        base_path = f"{manifest_path}/" if manifest_path else ""

        for name in ("action.yml", "action.yaml"):
            file_path = f"{base_path}{name}"
            try:
                return self.github_client.get_file_content(action.owner or "", action.repo or "", file_path, sha)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    continue  # only a real 404 justifies trying the other extension
                logger.error(f"HTTP {e.response.status_code} fetching {file_path} for {action.owner}/{action.repo}")
                return None
            except Exception as e:
                logger.error(f"Failed fetching {file_path} for {action.owner}/{action.repo}: {e}")
                return None

        return None

    def _resolve_github_action(self, action: ActionRef) -> tuple[str, ActionManifest | None]:
        """Resolve a GitHub action."""
        if not action.owner or not action.repo or not action.ref:
            return "", None

        # Resolve ref to SHA
        cache_key = self.cache.make_key("ref", action.owner, action.repo, action.ref)
        sha = self.cache.get(cache_key)

        if not sha:
            try:
                sha = self.github_client.get_ref_sha(action.owner, action.repo, action.ref)
                self.cache.set(cache_key, sha)
            except Exception as e:
                logger.error(f"Failed to resolve ref {action.owner}/{action.repo}@{action.ref}: {e}")
                return "", None

        action.resolved_sha = sha

        # Fetch action manifest
        manifest_path = action.path if action.path and action.path != "action.yml" else ""
        manifest_key = self.cache.make_key("manifest", action.owner, action.repo, sha, manifest_path)
        manifest_content = self.cache.get(manifest_key)

        if not manifest_content:
            manifest_content = self._fetch_manifest_content(action, sha, manifest_path)
            if manifest_content:
                self.cache.set(manifest_key, manifest_content)

        if not manifest_content:
            location = f"{action.owner}/{action.repo}"
            if manifest_path:
                location = f"{location}/{manifest_path}"
            logger.error(f"Action manifest not found: {location} (tried action.yml and action.yaml)")
            return action.canonical_key(), None

        # Parse manifest straight from the fetched text — no temp file, so there
        # is nothing to leak when parsing fails on a malformed upstream manifest.
        try:
            manifest = self.parser.parse_action_content(
                manifest_content,
                origin=f"{action.owner}/{action.repo}/{manifest_path or 'action.yml'}@{sha}",
                default_name=action.repo,
            )
            return action.canonical_key(), manifest
        except Exception as e:
            logger.error(f"Failed to parse manifest for {action.canonical_key()}: {e}")
            return "", None
