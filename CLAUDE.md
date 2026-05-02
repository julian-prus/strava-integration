# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Early-stage Python library for integrating with the Strava API. Currently a skeleton — the actual API integration is yet to be implemented.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -e .
pip install -r requirements.txt
```

## Common Commands

```bash
# Run tests
python -m pytest tests/

# Run tests with coverage
python -m pytest tests/ --cov=strava_integration

# Run a single test
python -m pytest tests/test_main.py::TestMain::test_hello_strava

# Lint
flake8 src/ tests/

# Format
black src/ tests/

# Type check
mypy src/
```

## Architecture

Uses the `src/` layout — source lives in `src/strava_integration/`, which is installed as an editable package. Imports should use `from strava_integration import ...`.

- `src/strava_integration/main.py` — entry point; currently a stub (`hello_strava()`)
- `tests/test_main.py` — pytest tests using class-based organization (`TestMain`)

Single runtime dependency: `requests>=2.28.0` (for HTTP calls to the Strava API).
