"""OAuth2 token management for the Strava API."""

import json
import os
import time
from pathlib import Path

import requests

DEFAULT_CONFIG_PATH = Path.home() / ".strava_integration" / "config.json"
TOKEN_URL = "https://www.strava.com/oauth/token"
AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"


def _config_path(path=None) -> Path:
    if path:
        return Path(path)
    env = os.environ.get("STRAVA_CONFIG")
    if env:
        return Path(env)
    return DEFAULT_CONFIG_PATH


def load_config(path=None) -> dict:
    """Load credentials from the config file."""
    p = _config_path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Config file not found: {p}\n"
            "Create it with your Strava credentials:\n"
            "{\n"
            '  "client_id": "YOUR_CLIENT_ID",\n'
            '  "client_secret": "YOUR_CLIENT_SECRET",\n'
            '  "access_token": "YOUR_ACCESS_TOKEN",\n'
            '  "refresh_token": "YOUR_REFRESH_TOKEN",\n'
            '  "expires_at": 0\n'
            "}"
        )
    with p.open() as f:
        return json.load(f)


def save_config(config: dict, path=None) -> None:
    """Persist config (including refreshed tokens) back to disk."""
    p = _config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as f:
        json.dump(config, f, indent=2)


def refresh_token(config: dict) -> dict:
    """Exchange refresh_token for a new access_token. Returns updated config."""
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": config["refresh_token"],
        },
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    return {
        **config,
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": data["expires_at"],
    }


def exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    """Exchange an OAuth authorization code for access and refresh tokens."""
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": data["expires_at"],
    }


def get_valid_token(config: dict, path=None) -> str:
    """Return a non-expired access token, refreshing and saving if needed."""
    if int(config.get("expires_at", 0)) <= int(time.time()):
        config = refresh_token(config)
        save_config(config, path)
    return config["access_token"]
