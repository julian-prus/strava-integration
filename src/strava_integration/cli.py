"""Command-line interface for the Strava integration tool."""

import argparse
import getpass
import http.server
import socket
import sys
import urllib.parse
import webbrowser
from pathlib import Path

import requests

from strava_integration.auth import (
    AUTHORIZE_URL,
    _config_path,
    exchange_code,
    get_valid_token,
    load_config,
    save_config,
)
from strava_integration.routes import download_gpx


def cmd_download_gpx(args) -> int:
    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    try:
        token = get_valid_token(config)
    except requests.HTTPError as e:
        print(f"Token refresh failed: {e}", file=sys.stderr)
        return 1

    try:
        gpx_bytes = download_gpx(args.route_id, token)
    except requests.HTTPError as e:
        print(f"Failed to download GPX: {e}", file=sys.stderr)
        return 1

    output_path = Path(args.output) if args.output else Path(f"{args.route_id}.gpx")
    output_path.write_bytes(gpx_bytes)
    print(f"Saved {len(gpx_bytes)} bytes to {output_path}")
    return 0


def cmd_setup(args) -> int:
    print("Strava API Setup")
    print("=" * 40)
    print("You'll need a Strava API application.")
    print("Create one at: https://www.strava.com/settings/api")
    print()

    client_id = input("Client ID: ").strip()
    if not client_id:
        print("Error: Client ID is required.", file=sys.stderr)
        return 1

    client_secret = getpass.getpass("Client Secret: ").strip()
    if not client_secret:
        print("Error: Client Secret is required.", file=sys.stderr)
        return 1

    with socket.socket() as s:
        s.bind(("", 0))
        port = s.getsockname()[1]

    redirect_uri = f"http://localhost:{port}/callback"
    auth_url = (
        f"{AUTHORIZE_URL}"
        f"?client_id={urllib.parse.quote(client_id)}"
        f"&redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
        f"&response_type=code"
        f"&scope=read,activity:read_all"
    )

    auth_code: list = []
    error_msg: list = []

    class _CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            if "code" in params:
                auth_code.append(params["code"][0])
                self._respond("Authorization successful! You can close this tab.")
            else:
                error_msg.append(params.get("error", ["unknown"])[0])
                self._respond("Authorization failed. You can close this tab.")

        def _respond(self, message):
            body = f"<html><body><p>{message}</p></body></html>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *a):
            pass

    server = http.server.HTTPServer(("localhost", port), _CallbackHandler)
    server.timeout = 120

    print(f"\nOpening browser to authorize the app...")
    webbrowser.open(auth_url)
    print("Waiting for authorization (2-minute timeout)...")
    print(f"If the browser did not open, visit:\n  {auth_url}\n")

    server.handle_request()
    server.server_close()

    if error_msg:
        print(f"Error: Authorization denied: {error_msg[0]}", file=sys.stderr)
        return 1

    if not auth_code:
        print("Error: Timed out waiting for authorization.", file=sys.stderr)
        return 1

    print("Authorization received. Exchanging code for tokens...")

    try:
        config = exchange_code(client_id, client_secret, auth_code[0], redirect_uri)
    except requests.HTTPError as e:
        print(f"Error: Token exchange failed: {e}", file=sys.stderr)
        return 1

    save_config(config)
    print(f"Credentials saved to {_config_path()}")
    print("Setup complete! You can now use the Strava CLI.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="strava",
        description="Strava CLI — interact with the Strava API",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    subparsers.required = True

    setup_parser = subparsers.add_parser(
        "setup",
        help="Configure Strava API credentials",
    )
    setup_parser.set_defaults(func=cmd_setup)

    gpx_parser = subparsers.add_parser(
        "download-gpx",
        help="Download a route as a GPX file",
    )
    gpx_parser.add_argument("route_id", type=int, help="Strava route ID")
    gpx_parser.add_argument(
        "-o", "--output",
        metavar="FILE",
        default=None,
        help="Output file path (default: <route_id>.gpx)",
    )
    gpx_parser.set_defaults(func=cmd_download_gpx)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
