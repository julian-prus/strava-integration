# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python CLI and Django web UI for interacting with the Strava API. Core features: OAuth2 setup, GPX route download, and GPX normalization (out-and-back detour removal).

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -e .
pip install -r requirements.txt
```

The `strava` CLI entry point is registered via `pyproject.toml` and maps to `strava_integration.cli:main`.

## Common Commands

```bash
# Run tests
python -m pytest tests/

# Run tests with coverage
python -m pytest tests/ --cov=strava_integration

# Run a single test
python -m pytest tests/test_gpx_normalizer.py::TestGpxNormalizer::test_name

# Lint / format / type check
flake8 src/ tests/
black src/ tests/
mypy src/

# Start the Django web UI (from the web/ directory)
cd web && python manage.py runserver
```

## Architecture

### Library (`src/strava_integration/`)

Uses the `src/` layout — installed as an editable package. Imports use `from strava_integration import ...`.

- **`auth.py`** — OAuth2 token management. Credentials live at `~/.strava_integration/config.json` (overridable via `STRAVA_CONFIG` env var). `get_valid_token()` auto-refreshes expired tokens and persists them back to disk.
- **`routes.py`** — Strava API calls (currently `download_gpx`).
- **`gpx_normalizer.py`** — Detour detection and removal algorithm. `find_detours()` scans a point list for out-and-back spikes using proximity + path-length + `_is_out_and_back()` (lateral distance check to avoid falsely removing loop closures). `normalize_gpx()` and `normalize_gpx_bytes()` are the public entry points.
- **`cli.py`** — `argparse` CLI with three subcommands: `setup` (OAuth flow with a local callback server), `download-gpx`, and `normalize-gpx` (accepts either a route ID or a local file path).

### Web UI (`web/`)

A Django project that wraps the same library code.

- **`config/`** — Django project settings and root URL conf (delegates everything to `routes.urls`).
- **`routes/views.py`** — Three JSON API endpoints (all `@csrf_exempt @require_POST`) plus the `index` view:
  - `POST /api/fetch-gpx/` — fetches a Strava route by ID, returns `{coordinates}`.
  - `POST /api/upload-gpx/` — accepts a multipart GPX file upload, returns `{coordinates}`.
  - `POST /api/normalize/` — accepts either `multipart gpx_file` or JSON `{route_id}`; returns `{original, normalized, stats}`.
- **`routes/templates/routes/index.html`** + **`routes/static/routes/style.css`** — single-page UI with Leaflet map, route ID tab, GPX upload tab, and normalize overlay.

The web layer imports directly from `strava_integration` — there is no separate API client layer. The Django dev server reads the same `~/.strava_integration/config.json` as the CLI.
