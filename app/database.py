from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Generator


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS repositories (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    created_at  TEXT,
    last_synced TEXT
);

CREATE TABLE IF NOT EXISTS stargazers (
    repo_id      INTEGER NOT NULL,
    username     TEXT    NOT NULL,
    starred_at   TEXT,
    unstarred_at TEXT,
    PRIMARY KEY (repo_id, username),
    FOREIGN KEY (repo_id) REFERENCES repositories(id)
);
"""


def init_db(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

@contextmanager
def get_db(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def upsert_repo(
    conn: sqlite3.Connection,
    repo_id: int,
    name: str,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO repositories (id, name, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET name = excluded.name
        """,
        (repo_id, name, created_at),
    )


def update_last_synced(
    conn: sqlite3.Connection, repo_id: int, synced_at: str
) -> None:
    conn.execute(
        "UPDATE repositories SET last_synced = ? WHERE id = ?",
        (synced_at, repo_id),
    )


def upsert_stargazer(
    conn: sqlite3.Connection,
    repo_id: int,
    username: str,
    starred_at: str,
) -> None:
    """Insert a star event, or clear unstarred_at if the user re-starred."""
    conn.execute(
        """
        INSERT INTO stargazers (repo_id, username, starred_at)
        VALUES (?, ?, ?)
        ON CONFLICT(repo_id, username) DO UPDATE SET
            starred_at   = excluded.starred_at,
            unstarred_at = NULL
        """,
        (repo_id, username, starred_at),
    )


def mark_unstarred(
    conn: sqlite3.Connection,
    repo_id: int,
    usernames: set[str],
    sync_time: str,
) -> None:
    """Record that a set of users no longer star this repo."""
    if not usernames:
        return
    placeholders = ",".join("?" * len(usernames))
    conn.execute(
        f"""
        UPDATE stargazers
        SET unstarred_at = ?
        WHERE repo_id = ? AND username IN ({placeholders}) AND unstarred_at IS NULL
        """,
        (sync_time, repo_id, *usernames),
    )


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def get_active_star_count(conn: sqlite3.Connection, repo_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM stargazers WHERE repo_id = ? AND unstarred_at IS NULL",
        (repo_id,),
    ).fetchone()
    return row[0] if row else 0


def get_active_usernames(conn: sqlite3.Connection, repo_id: int) -> set[str]:
    rows = conn.execute(
        "SELECT username FROM stargazers WHERE repo_id = ? AND unstarred_at IS NULL",
        (repo_id,),
    ).fetchall()
    return {row[0] for row in rows}


def get_all_repos(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            r.id,
            r.name,
            r.created_at,
            r.last_synced,
            COUNT(s.username) AS star_count
        FROM repositories r
        LEFT JOIN stargazers s ON s.repo_id = r.id AND s.unstarred_at IS NULL
        GROUP BY r.id
        ORDER BY star_count DESC
        """
    ).fetchall()


def get_repo_by_name(
    conn: sqlite3.Connection, name: str
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT
            r.id,
            r.name,
            r.created_at,
            r.last_synced,
            COUNT(s.username) AS star_count
        FROM repositories r
        LEFT JOIN stargazers s ON s.repo_id = r.id AND s.unstarred_at IS NULL
        WHERE r.name = ?
        GROUP BY r.id
        """,
        (name,),
    ).fetchone()


def get_star_history(
    conn: sqlite3.Connection, repo_id: int
) -> list[tuple[str, int]]:
    """Return (event_datetime_iso, delta) rows sorted by date.

    delta = +1 for a star, -1 for an unstar.
    """
    rows = conn.execute(
        """
        SELECT starred_at   AS event_date,  1 AS delta FROM stargazers
        WHERE repo_id = ? AND starred_at IS NOT NULL
        UNION ALL
        SELECT unstarred_at AS event_date, -1 AS delta FROM stargazers
        WHERE repo_id = ? AND unstarred_at IS NOT NULL
        ORDER BY event_date
        """,
        (repo_id, repo_id),
    ).fetchall()
    return [(row[0], row[1]) for row in rows]


def search_repos(
    conn: sqlite3.Connection, query: str
) -> list[sqlite3.Row]:
    """Return repos whose short name contains `query` (case-insensitive), ordered by star count."""
    pattern = f"%{query}%"
    return conn.execute(
        """
        SELECT
            r.id,
            r.name,
            r.created_at,
            r.last_synced,
            COUNT(s.username) AS star_count
        FROM repositories r
        LEFT JOIN stargazers s ON s.repo_id = r.id AND s.unstarred_at IS NULL
        WHERE r.name LIKE ?
        GROUP BY r.id
        ORDER BY star_count DESC
        """,
        (pattern,),
    ).fetchall()


def get_last_sync_time(conn: sqlite3.Connection) -> str | None:
    """Return the most recent last_synced timestamp across all repos, or None."""
    row = conn.execute(
        "SELECT MAX(last_synced) FROM repositories"
    ).fetchone()
    return row[0] if row else None
