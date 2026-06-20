from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive, safe for server use
# Suppress "findfont: Font family '...' not found" noise from the xkcd style
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
import matplotlib.dates as mdates
import matplotlib.pyplot as plt


def render_chart(
    repo_id: int,
    repo_name: str,
    repo_created_at: str,
    star_history: list[tuple[str, int]],
    cache_dir: str,
    watermark_text: str = "GitHub Star Tracker",
) -> str:
    """Render a cumulative star-history chart in XKCD doodle style.

    Args:
        repo_id:        GitHub's numeric repo ID (used as the filename).
        repo_name:      Full repo name, e.g. 'your-org-name/my-repo'.
        repo_created_at: ISO-8601 creation timestamp from GitHub.
        star_history:   List of (event_datetime_iso, delta) tuples (+1 star, -1 unstar).
        cache_dir:      Directory where the PNG will be written.

    Returns:
        Absolute path to the saved PNG file.
    """
    os.makedirs(cache_dir, exist_ok=True)
    output_path = str(Path(cache_dir) / f"{repo_id}.png")

    # --- Build cumulative time series -----------------------------------------
    events: list[tuple[datetime, int]] = []
    for date_str, delta in star_history:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            events.append((dt, delta))
        except (ValueError, AttributeError):
            continue

    # Anchor the curve at the repo's creation date with 0 stars
    try:
        start_dt = datetime.fromisoformat(repo_created_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        start_dt = events[0][0] if events else datetime.now(timezone.utc)

    now = datetime.now(timezone.utc)

    if events:
        xs: list[datetime] = [start_dt] + [e[0] for e in events] + [now]
        ys: list[int] = [0]
        cumulative = 0
        for _, delta in events:
            cumulative += delta
            ys.append(cumulative)
        ys.append(cumulative)  # flat line to "now"
    else:
        xs = [start_dt, now]
        ys = [0, 0]

    # --- Draw -----------------------------------------------------------------
    with plt.xkcd():
        fig, ax = plt.subplots(figsize=(10, 5))

        ax.plot(xs, ys, linewidth=2)

        short_name = repo_name.split("/")[-1] if "/" in repo_name else repo_name
        ax.set_title(short_name)
        ax.set_xlabel("Date")
        ax.set_ylabel("Stars")

        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        fig.autofmt_xdate()

        # Watermark — lower-right corner, outside the tight-layout area
        fig.text(
            0.98, 0.01,
            watermark_text,
            ha="right",
            va="bottom",
            fontsize=8,
            color="gray",
            alpha=0.6,
            transform=fig.transFigure,
        )

        plt.tight_layout()
        plt.savefig(output_path, dpi=100, bbox_inches="tight")
        plt.close(fig)

    return output_path
