"""main.py — FastAPI web server entry point.

Usage:
    uv run main.py
    # or: uvicorn main:app --reload
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader

from app.config import load_settings
from app.database import (
    get_all_repos,
    get_db,
    get_last_sync_time,
    get_repo_by_name,
    get_star_history,
    init_db,
    search_repos,
)

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

settings = load_settings()
init_db(settings.database_path)

_ROOT = Path(__file__).parent

app = FastAPI(title="GitHub Star Tracker")
app.mount("/static", StaticFiles(directory=str(_ROOT / "static")), name="static")
templates = Jinja2Templates(env=Environment(
    loader=FileSystemLoader(str(_ROOT / "app" / "templates")),
    autoescape=True,
    cache_size=0,
))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_traces(
    repos: list,
    selected_ids: set[int],
    db_path: str,
) -> str:
    """Build a Plotly-compatible JSON traces array for the given repos.

    Traces for repos in `selected_ids` are visible; others are hidden.
    """
    traces = []
    for repo in repos:
        repo_id = repo["id"]
        repo_name = repo["name"]
        created_at = repo["created_at"] or ""

        with get_db(db_path) as conn:
            history = get_star_history(conn, repo_id)

        events: list[tuple[datetime, int]] = []
        for date_str, delta in history:
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                events.append((dt, delta))
            except (ValueError, AttributeError):
                continue

        try:
            start_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            start_dt = events[0][0] if events else datetime.now(timezone.utc)

        now = datetime.now(timezone.utc)

        if events:
            xs = [start_dt.isoformat()] + [e[0].isoformat() for e in events] + [now.isoformat()]
            cumulative = 0
            ys = [0]
            for _, delta in events:
                cumulative += delta
                ys.append(cumulative)
            ys.append(cumulative)
        else:
            xs = [start_dt.isoformat(), now.isoformat()]
            ys = [0, 0]

        short_name = repo_name.split("/")[-1] if "/" in repo_name else repo_name
        traces.append({
            "x": xs,
            "y": ys,
            "type": "scatter",
            "mode": "lines",
            "name": short_name,
            "visible": True if repo_id in selected_ids else False,
        })

    return json.dumps(traces)


# ---------------------------------------------------------------------------
# Routes — order matters: the doodle.png route must be registered first
# so that /repos/123/doodle.png doesn't accidentally match the repo page.
# ---------------------------------------------------------------------------

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request) -> HTMLResponse:
    """About page showing database sync status."""
    with get_db(settings.database_path) as conn:
        last_sync_raw = get_last_sync_time(conn)

    last_sync: str | None = None
    if last_sync_raw:
        try:
            dt = datetime.fromisoformat(last_sync_raw.replace("Z", "+00:00"))
            last_sync = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except (ValueError, AttributeError):
            last_sync = last_sync_raw

    return templates.TemplateResponse(
        request,
        "about.html",
        {
            "last_sync": last_sync,
            "tool_name_navbar": settings.tool_name_navbar,
        },
    )


@app.get("/search", response_class=HTMLResponse)
async def search(
    request: Request, q: str | None = None
) -> HTMLResponse:
    """Search for a repository by name and return all matching results."""
    results = []
    if q:
        with get_db(settings.database_path) as conn:
            results = search_repos(conn, q)

    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "q": q or "",
            "results": results,
            "base_url": settings.base_url,
            "tool_name_navbar": settings.tool_name_navbar,
        },
    )


@app.get("/repos/{repo_id}/doodle.png")
async def doodle_png(repo_id: int) -> FileResponse:
    """Serve the pre-rendered XKCD-style star-history PNG from the cache."""
    png_path = Path(settings.cache_dir) / f"{repo_id}.png"
    if not png_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Chart image not found. Run sync.py to generate it.",
        )
    return FileResponse(str(png_path), media_type="image/png")


@app.get("/repos/{repo_owner}/{repo_name_part}", response_class=HTMLResponse)
async def repo_page(
    request: Request, repo_owner: str, repo_name_part: str
) -> HTMLResponse:
    """Individual repository page with an interactive Plotly chart."""
    full_name = f"{repo_owner}/{repo_name_part}"

    with get_db(settings.database_path) as conn:
        repo = get_repo_by_name(conn, full_name)

    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found.")

    traces_json = _build_traces([repo], {repo["id"]}, settings.database_path)
    markdown_embed = (
        f"![Star History]({settings.base_url}/repos/{repo['id']}/doodle.png)"
    )
    doodle_url = f"{settings.base_url}/repos/{repo['id']}/doodle.png"

    return templates.TemplateResponse(
        request,
        "repo.html",
        {
            "repo": repo,
            "traces_json": traces_json,
            "markdown_embed": markdown_embed,
            "doodle_url": doodle_url,
            "tool_name_navbar": settings.tool_name_navbar,
        },
    )


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, limit: int | None = None) -> HTMLResponse:
    """Main dashboard showing star history for the top-N repositories."""
    top_n = limit if limit is not None else settings.default_top_n

    with get_db(settings.database_path) as conn:
        all_repos = get_all_repos(conn)

    selected_ids = {r["id"] for r in all_repos[:top_n]}
    traces_json = _build_traces(all_repos, selected_ids, settings.database_path)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "all_repos": all_repos,
            "selected_ids": selected_ids,
            "traces_json": traces_json,
            "top_n": top_n,
            "tool_name_navbar": settings.tool_name_navbar,
        },
    )


# ---------------------------------------------------------------------------
# Dev server entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
