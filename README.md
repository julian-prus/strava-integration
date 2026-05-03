# Strava Integration

A Python CLI for interacting with the Strava API. Download routes as GPX files and manage OAuth credentials from the terminal.

## Requirements

- Python 3.8 or later
- A [Strava API application](https://www.strava.com/settings/api)

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/julian-prus/strava-integration.git
cd strava-integration
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows
```

### 3. Install the package

```bash
pip install -e .
pip install -r requirements.txt
```

The `-e` flag installs the package in editable mode so changes to the source are reflected immediately without reinstalling.

### 4. Verify the installation

```bash
strava --help
```

You should see the available commands listed.

## Configuration

Before using any commands you need to authorise the app with your Strava account.

### Create a Strava API application

1. Go to [https://www.strava.com/settings/api](https://www.strava.com/settings/api) and create an app.
2. Set the **Authorization Callback Domain** to `localhost`.
3. Copy the **Client ID** and **Client Secret** — you will need them in the next step.

### Run the setup command

```bash
strava setup
```

The command will:
1. Prompt you for your Client ID and Client Secret.
2. Open your browser to the Strava authorization page.
3. Capture the OAuth callback automatically and exchange it for tokens.
4. Save credentials to `~/.strava_integration/config.json`.

You only need to run `strava setup` once. Tokens are refreshed automatically when they expire.

### Override the config location

Set the `STRAVA_CONFIG` environment variable to use a different path:

```bash
export STRAVA_CONFIG=/path/to/my/config.json
strava setup
```

## Usage

### Download a route as GPX

```bash
strava download-gpx <route_id>
```

Save to a specific file:

```bash
strava download-gpx <route_id> -o my_route.gpx
```

The route ID is the number in the Strava route URL:
`https://www.strava.com/routes/`**123456789**

## Development

### Run tests

```bash
python -m pytest tests/
```

With coverage:

```bash
python -m pytest tests/ --cov=strava_integration
```

### Lint and format

```bash
flake8 src/ tests/
black src/ tests/
```

### Type check

```bash
mypy src/
```

## Project structure

```
strava-integration/
├── src/strava_integration/
│   ├── __init__.py       # package version
│   ├── main.py           # stub entry point
│   ├── cli.py            # argparse CLI (setup, download-gpx)
│   ├── auth.py           # OAuth2 token management
│   └── routes.py         # Strava routes API
├── tests/
│   ├── test_main.py
│   ├── test_auth.py
│   └── test_routes.py
├── setup.py
├── pyproject.toml
├── requirements.txt
└── README.md
```

## License

MIT License — see the LICENSE file for details.
