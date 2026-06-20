from __future__ import annotations

import time
from typing import Generator

import httpx

# Retry configuration
_MAX_RETRIES = 4          # attempts total (1 original + 3 retries)
_RETRY_BASE_DELAY = 2.0   # seconds; doubles on each retry (2, 4, 8 …)
# HTTP status codes considered transient and worth retrying
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None) -> None:
        headers: dict[str, str] = {
            # Request starred_at timestamps in star responses
            "Accept": "application/vnd.github.v3.star+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            headers=headers,
            timeout=30.0,
        )

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        """GET with exponential-backoff retry on transient errors."""
        delay = _RETRY_BASE_DELAY
        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = self._client.get(url, params=params or {})
                if response.status_code not in _RETRYABLE_STATUSES:
                    response.raise_for_status()
                    return response
                # Transient server error — honour Retry-After if present
                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else delay
            except httpx.TransportError as exc:
                # Network-level failures (connection reset, timeout, etc.)
                last_exc = exc
                wait = delay
            else:
                last_exc = httpx.HTTPStatusError(
                    f"{response.status_code}",
                    request=response.request,
                    response=response,
                )

            if attempt == _MAX_RETRIES:
                break

            print(
                f"    [retry {attempt}/{_MAX_RETRIES - 1}] "
                f"transient error, retrying in {wait:.0f}s...",
                flush=True,
            )
            time.sleep(wait)
            delay *= 2

        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # API methods
    # ------------------------------------------------------------------

    def list_org_repos(self, org: str) -> Generator[dict, None, None]:
        """Yield all repository objects for the given organization."""
        page = 1
        per_page = 100
        while True:
            response = self._get(
                f"{self.BASE_URL}/orgs/{org}/repos",
                {"per_page": per_page, "type": "all", "page": page},
            )
            data: list[dict] = response.json()
            if not data:
                break
            for repo in data:
                yield repo
            if len(data) < per_page:  # last page — no need to request again
                break
            page += 1

    def list_stargazers(self, repo_full_name: str) -> Generator[dict, None, None]:
        """Yield {username, starred_at} dicts for every stargazer of a repo."""
        page = 1
        per_page = 100
        while True:
            response = self._get(
                f"{self.BASE_URL}/repos/{repo_full_name}/stargazers",
                {"per_page": per_page, "page": page},
            )
            data: list[dict] = response.json()
            if not data:
                break
            for item in data:
                yield {
                    "username": item["user"]["login"],
                    "starred_at": item["starred_at"],
                }
            if len(data) < per_page:  # last page
                break
            page += 1
