# GitHub Star History

Internal tool to track and visualize the star history for all repositories in a GitHub organization. A daily sync script fetches star data from the GitHub API; a FastAPI web server displays interactive charts and serves embeddable static images.

---

## Prerequisites

- **Python 3.11+**
- A GitHub **Personal Access Token (classic)** with `repo` and `read:org` scopes, authorized for SSO — **required for private org repos; optional for fully public orgs**

### Public organizations (no token required)

If the target organization's repositories are all public you can skip token setup entirely. Leave `GITHUB_TOKEN` unset (or leave `.env` as the example) and the sync will proceed using unauthenticated requests.

> **Rate limit:** Unauthenticated GitHub API requests are capped at **60 requests/hour**. Each paginated page of repos or stargazers costs one request, so large orgs or repos with many stargazers may hit this limit during the initial sync. Subsequent incremental syncs are cheaper because unchanged repos are skipped. A token (even a read-only one with no special scopes) raises this to 5,000 requests/hour.

### Private organizations — Creating and authorizing a PAT

1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)**
2. Click **Generate new token (classic)**
3. Set an expiration and check these top-level scopes:
   - `repo` — full control of private repositories
   - `read:org` — discover all repositories in the organization
4. Click **Generate token** and copy it immediately
5. On the token list page, click **Configure SSO** next to your new token, then click **Authorize** next to your organization

> Without the SSO authorization step, all API requests to private org repos will return **403 Forbidden**.

---

## Setup

**1. Install dependencies**

1. Install `uv` if you don't have it installed already
2. `uv sync` to install set up virtual environment

Note: `scripts/setup.bat` does complete setup for Windows users.

**2. Configure your token** *(skip for fully public organizations)*

Copy `.env.example` to `.env` and paste your PAT (read access token):

```
GITHUB_TOKEN=ghp_your_token_here
```

If `GITHUB_TOKEN` is absent or empty the sync will proceed with unauthenticated requests (public repos only, 60 req/hour limit).

**3. Edit `config.yaml`**

| Key | Default | Description |
|---|---|---|
| `github_org` | `your-org-name` | Organization to sync |
| `tool_name_navbar` | `WelkinU's Github Star Tracker` | Navbar tool name displayed |
| `xkcd_plot_watermark_text` | `WelkinU's Github Star Tracker` | Watermark added to the xkcd style plot |
| `base_url` | `http://localhost:8000` | Public URL — used in README embed links |
| `host` / `port` | `0.0.0.0` / `8000` | Server bind address |
| `default_top_n` | `25` | Repos shown by default on the dashboard |

---

## Quickstart

**Sync star data** (run once to populate the database, then on a schedule):

```
uv run sync.py
```

**Start the web server:**

```
uv run main.py
```

Open [http://localhost:8000](http://localhost:8000).

---

## Scheduling the sync

To keep data fresh, run `uv run sync.py` daily via Task Scheduler (Windows), cron (Linux/macOS), or a GitHub Actions workflow. The script is incremental — it skips repositories whose star count has not changed since the last run.
