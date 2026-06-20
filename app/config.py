from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Resolve the repository root (one level above this file's directory)
_REPO_ROOT = Path(__file__).parent.parent

# Load .env from the repo root before reading env vars
load_dotenv(_REPO_ROOT / ".env")

_CONFIG_PATH = _REPO_ROOT / "config.yaml"


@dataclass
class Settings:
    github_org: str
    tool_name_navbar: str
    xkcd_plot_watermark_text: str
    base_url: str
    host: str
    port: int
    database_path: str
    cache_dir: str
    default_top_n: int
    github_token: str | None


def _resolve(raw: str) -> str:
    """Resolve a path that may be relative (to repo root) or absolute."""
    p = Path(raw)
    return str(p if p.is_absolute() else _REPO_ROOT / p)


def load_settings() -> Settings:
    with open(_CONFIG_PATH) as f:
        data = yaml.safe_load(f)

    return Settings(
        github_org=data["github_org"],
        tool_name_navbar=data.get("tool_name_navbar", "GitHub Star Tracker"),
        xkcd_plot_watermark_text=data.get("xkcd_plot_watermark_text", "GitHub Star Tracker"),
        base_url=data["base_url"].rstrip("/"),
        host=data.get("host", "0.0.0.0"),
        port=int(data.get("port", 8000)),
        database_path=_resolve(data.get("database_path", "./stars.db")),
        cache_dir=_resolve(data.get("cache_dir", "./cache")),
        default_top_n=int(data.get("default_top_n", 25)),
        github_token=os.environ.get("GITHUB_TOKEN") or None,
    )
