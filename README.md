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

### Normalize a GPX route

Removes out-and-back detour spikes from a route, keeping only the main path.

From a Strava route ID (downloads and normalizes in one step):

```bash
strava normalize-gpx <route_id> -o normalized.gpx
```

From a local GPX file:

```bash
strava normalize-gpx my_route.gpx -o normalized.gpx
```

Optional tuning flags:

| Flag | Default | Description |
|---|---|---|
| `--threshold` | 50 m | Max distance between detour start and end points |
| `--min-detour` | 100 m | Minimum round-trip length to consider a detour |
| `--max-detour` | 5000 m | Maximum round-trip length to consider a detour |
| `--max-lateral` | 30 m | Max average lateral offset (distinguishes detours from loops) |

### Web UI

Start the Django development server:

```bash
source venv/bin/activate
cd web
python manage.py runserver
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

- **Route ID tab** — paste a Strava route ID and click *Load Route* to fetch and display it on the map.
- **Upload GPX tab** — drag-and-drop or select a local `.gpx` file.
- **Normalize Route** — appears after a route is loaded; overlays the cleaned route in blue on the same map and shows a stats card (points before/after, detours removed).

## Debugging

### CLI

**Check your Strava config**

The CLI reads credentials from `~/.strava_integration/config.json` by default (or the path in `STRAVA_CONFIG`). Verify it exists and contains valid tokens:

```bash
cat ~/.strava_integration/config.json
```

Expected keys: `client_id`, `client_secret`, `access_token`, `refresh_token`, `expires_at`.
If the file is missing, run `strava setup`.

**Token expired or invalid**

The CLI refreshes tokens automatically. If a command returns a 401 error, your refresh token may have been revoked (e.g. after changing your Strava password). Re-run `strava setup` to get a fresh token pair.

**Inspect a GPX file**

Open the file in any text editor — it is plain XML. Common signs of corruption: truncated closing tags (`</el` instead of `</ele>`), stray non-ASCII characters, or a file that ends mid-element. A corrupt GPX from `download-gpx` is a Strava API issue; try downloading again.

**Step through the code with pdb**

```bash
python -c "
import pdb
from strava_integration.auth import load_config, get_valid_token
from strava_integration.routes import download_gpx
pdb.set_trace()
config = load_config()
token  = get_valid_token(config)
data   = download_gpx(3485649294818578590, token)
print(len(data), 'bytes')
"
```

Or drop `import pdb; pdb.set_trace()` directly into any source file and run the affected command.

---

### Web UI

**Enable verbose Django output**

The dev server already prints every request with status code to stdout. For more detail, set `DJANGO_DEBUG=true` (it is `true` by default) and check the terminal where `manage.py runserver` is running.

**Inspect API responses directly**

All endpoints accept plain HTTP — use `curl` to bypass the browser:

```bash
# Fetch route coordinates by ID
curl -s -X POST http://127.0.0.1:8000/api/fetch-gpx/ \
  -H "Content-Type: application/json" \
  -d '{"route_id": "3485649294818578590"}' | python3 -m json.tool | head -20

# Upload a GPX file
curl -s -X POST http://127.0.0.1:8000/api/upload-gpx/ \
  -F "gpx_file=@my_route.gpx" | python3 -m json.tool | head -5

# Normalize via upload
curl -s -X POST http://127.0.0.1:8000/api/normalize/ \
  -F "gpx_file=@my_route.gpx" | python3 -m json.tool | grep -A6 '"stats"'
```

Error responses always include an `"error"` key with a plain-English message.

**Strava config not found (HTTP 503)**

The web server reads the same config as the CLI. If you see `"Strava config not found"` in the browser, run `strava setup` from the CLI first, then reload the page.

**Port already in use**

```bash
python manage.py runserver 8080   # pick any free port
```

**Add a breakpoint in a Django view**

Insert `import pdb; pdb.set_trace()` inside any view function in `web/routes/views.py`, then trigger the relevant API call from the browser or curl. The debugger opens in the terminal where `runserver` is running. Use `python manage.py runserver --noreload` to prevent the reloader from interfering with pdb.

**Browser devtools**

Open the Network tab (F12) before clicking *Load Route* or *Normalize Route*. Each API call is a separate POST request — inspect the request payload and response body to see exactly what the server received and returned.

---

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
│   ├── __init__.py         # package version
│   ├── cli.py              # argparse CLI (setup, download-gpx, normalize-gpx)
│   ├── auth.py             # OAuth2 token management
│   ├── routes.py           # Strava routes API
│   └── gpx_normalizer.py   # detour detection and removal algorithm
├── web/                    # Django web UI
│   ├── manage.py
│   ├── config/             # Django project settings and URLs
│   └── routes/             # Django app: views, templates, static files
├── tests/
│   ├── test_main.py
│   ├── test_auth.py
│   ├── test_routes.py
│   └── test_gpx_normalizer.py
├── setup.py
├── pyproject.toml
├── requirements.txt
└── README.md
```

## License

MIT License — see the LICENSE file for details.
