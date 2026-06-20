"""sync.py — Daily star-data sync script.

Usage:
    uv run sync.py
    uv run sync.py --verbose

Reads config.yaml and .env from the repository root.
Requires GITHUB_TOKEN to be set (in .env or as an environment variable).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

from app.config import load_settings
from app.database import (
    get_active_star_count,
    get_active_usernames,
    get_star_history,
    init_db,
    get_db,
    mark_unstarred,
    update_last_synced,
    upsert_repo,
    upsert_stargazer,
)
from app.github_api import GitHubClient
from app.chart import render_chart


def _log(message: str, *, verbose: bool, end: str = "\n", flush: bool = False) -> None:
    """Print only when verbose mode is active."""
    if verbose:
        print(message, end=end, flush=flush)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync GitHub star data for the configured organization."
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed per-repo progress during sync.",
    )
    args = parser.parse_args()
    verbose: bool = args.verbose

    settings = load_settings()

    if not settings.github_token:
        print(
            "WARNING: GITHUB_TOKEN is not set — only public repositories will be accessible. "
            "Unauthenticated requests are rate-limited to 60/hour by GitHub.",
            file=sys.stderr,
        )

    init_db(settings.database_path)

    print(f"Syncing org: {settings.github_org}")

    # Use a single HTTP client for the entire sync to reuse the TCP connection.
    with GitHubClient(settings.github_token) as gh:

        # Stream the repo list and show a live counter so it never looks frozen.
        print("Fetching repository list...", end=" ", flush=True)
        repos: list[dict] = []
        for repo in gh.list_org_repos(settings.github_org):
            repos.append(repo)
            if verbose:
                print(f"\rFetching repository list... {len(repos)}", end="", flush=True)
        print(f"\rFound {len(repos)} repositories.              ")

        synced = 0
        skipped = 0

        for i, repo in enumerate(repos, start=1):
            repo_id: int = repo["id"]
            repo_name: str = repo["full_name"]
            created_at: str = repo.get("created_at") or ""
            remote_count: int = repo.get("stargazers_count", 0)

            prefix = f"  [{i}/{len(repos)}] {repo_name}"

            with get_db(settings.database_path) as conn:
                upsert_repo(conn, repo_id, repo_name, created_at)
                local_count = get_active_star_count(conn, repo_id)

            png_path = os.path.join(settings.cache_dir, f"{repo_id}.png")
            needs_chart = not os.path.exists(png_path)

            if local_count == remote_count and not needs_chart:
                _log(f"{prefix}: {remote_count} ★  up to date, skipping.", verbose=verbose)
                skipped += 1
                continue

            if local_count != remote_count:
                _log(
                    f"{prefix}: {local_count} → {remote_count} ★  syncing stargazers...",
                    verbose=verbose, end=" ", flush=True,
                )
            else:
                _log(
                    f"{prefix}: {remote_count} ★  chart missing, regenerating...",
                    verbose=verbose, end=" ", flush=True,
                )

            remote_stars = list(gh.list_stargazers(repo_name))

            _log(f"fetched {len(remote_stars)} stargazers...", verbose=verbose, end=" ", flush=True)

            remote_usernames = {s["username"] for s in remote_stars}
            sync_time = datetime.now(timezone.utc).isoformat()

            with get_db(settings.database_path) as conn:
                for star in remote_stars:
                    upsert_stargazer(conn, repo_id, star["username"], star["starred_at"])

                local_active = get_active_usernames(conn, repo_id)
                unstars = local_active - remote_usernames
                if unstars:
                    mark_unstarred(conn, repo_id, unstars, sync_time)
                    _log(f"{len(unstars)} unstar(s) recorded...", verbose=verbose, end=" ", flush=True)

                update_last_synced(conn, repo_id, sync_time)
                history = get_star_history(conn, repo_id)

            _log("rendering chart...", verbose=verbose, end=" ", flush=True)
            render_chart(repo_id, repo_name, created_at, history, settings.cache_dir, settings.xkcd_plot_watermark_text)

            _log("done.", verbose=verbose)
            synced += 1

    print(f"\nSync complete. {synced} updated, {skipped} skipped.")


if __name__ == "__main__":
    main()
