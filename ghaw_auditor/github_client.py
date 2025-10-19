"""GitHub API client for resolving actions and refs."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Suppress httpx INFO logging (we handle logging ourselves)
logging.getLogger("httpx").setLevel(logging.WARNING)


def should_retry_http_error(exception: BaseException) -> bool:
    """Determine if an HTTP error should be retried.

    Retry on:
    - Network errors (RequestError)
    - Server errors (5xx)
    - Rate limiting (429)

    Don't retry on:
    - 404 (not found - won't change on retry)
    - 401/403 (auth errors - won't change on retry)
    - 400 (bad request - won't change on retry)
    """
    if isinstance(exception, httpx.RequestError):
        # Network errors - retry
        return True

    if isinstance(exception, httpx.HTTPStatusError):
        status_code = exception.response.status_code
        # Retry on 5xx server errors and 429 rate limiting
        # Don't retry on 4xx client errors (except 429)
        if status_code == 429:
            return True
        return 500 <= status_code < 600

    return False


class GitHubClient:
    """GitHub API client with rate limiting and retries."""

    def __init__(self, token: str | None = None, base_url: str = "https://api.github.com") -> None:
        """Initialize GitHub client."""
        self.base_url = base_url
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

        self.client = httpx.Client(headers=self.headers, timeout=30.0, follow_redirects=True)

    @retry(
        retry=retry_if_exception(should_retry_http_error),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
    )
    def get_ref_sha(self, owner: str, repo: str, ref: str) -> str:
        """Resolve a ref (tag/branch) to a SHA."""
        url = f"{self.base_url}/repos/{owner}/{repo}/commits/{ref}"
        logger.debug(f"Fetching ref SHA: {owner}/{repo}@{ref}")

        try:
            response = self.client.get(url)
            response.raise_for_status()
            sha = response.json()["sha"]
            logger.debug(f"Resolved {owner}/{repo}@{ref} -> {sha}")
            return sha
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code == 404:
                logger.error(f"Action not found: {owner}/{repo}@{ref}")
            elif status_code == 403:
                logger.error(f"Access denied (check token permissions): {owner}/{repo}@{ref}")
            elif status_code == 401:
                logger.error(f"Authentication required: {owner}/{repo}@{ref}")
            elif 400 <= status_code < 600:
                logger.warning(f"HTTP {status_code} fetching {url}")
            raise

    @retry(
        retry=retry_if_exception(should_retry_http_error),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
    )
    def get_file_content(self, owner: str, repo: str, path: str, ref: str) -> str:
        """Fetch raw file content at a specific ref."""
        # Use raw.githubusercontent.com for files
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
        logger.debug(f"Fetching file: {owner}/{repo}/{path}@{ref}")

        try:
            response = self.client.get(raw_url)
            response.raise_for_status()
            content = response.text
            logger.debug(f"Downloaded {path} ({len(content)} bytes)")
            return content
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            # Don't log 404 as warning - it's expected when trying action.yml before action.yaml
            if status_code == 404:
                logger.debug(f"File not found: {path}")
            elif status_code == 403:
                logger.error(f"Access denied (check token permissions): {owner}/{repo}/{path}")
            elif status_code == 401:
                logger.error(f"Authentication required: {owner}/{repo}/{path}")
            elif 400 <= status_code < 600:
                logger.warning(f"HTTP {status_code} fetching {raw_url}")
            raise

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self) -> GitHubClient:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()
