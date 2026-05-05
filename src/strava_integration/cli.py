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
from strava_integration.gpx_normalizer import normalize_gpx, normalize_gpx_bytes
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


def cmd_normalize_gpx(args) -> int:
    source: str = args.source
    output_arg = Path(args.output) if args.output else None

    # Decide whether the source is a Strava route ID or a local file path.
    try:
        route_id = int(source)
        is_route_id = True
    except ValueError:
        is_route_id = False

    if is_route_id:
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
            gpx_bytes = download_gpx(route_id, token)
        except requests.HTTPError as e:
            print(f"Failed to download GPX: {e}", file=sys.stderr)
            return 1
        output_path = output_arg or Path(f"{route_id}_normalized.gpx")
        try:
            orig, clean, n_detours = normalize_gpx_bytes(
                gpx_bytes, output_path,
                proximity_m=args.threshold,
                min_detour_m=args.min_detour,
                max_detour_m=args.max_detour,
                max_lateral_m=args.max_lateral,
            )
        except Exception as e:
            print(f"Error normalizing GPX: {e}", file=sys.stderr)
            return 1
    else:
        input_path = Path(source)
        if not input_path.exists():
            print(f"Error: File not found: {input_path}", file=sys.stderr)
            return 1
        default_out = input_path.parent / (input_path.stem + "_normalized" + input_path.suffix)
        output_path = output_arg or default_out
        try:
            orig, clean, n_detours = normalize_gpx(
                input_path, output_path,
                proximity_m=args.threshold,
                min_detour_m=args.min_detour,
                max_detour_m=args.max_detour,
                max_lateral_m=args.max_lateral,
            )
        except Exception as e:
            print(f"Error normalizing GPX: {e}", file=sys.stderr)
            return 1

    removed = orig - clean
    print(f"Loaded {orig} trackpoints")
    print(f"Removed {n_detours} detour segment(s) ({removed} points)")
    print(f"Saved {clean} trackpoints to {output_path}")
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

    norm_parser = subparsers.add_parser(
        "normalize-gpx",
        help="Remove out-and-back detours from a GPX route",
    )
    norm_parser.add_argument(
        "source",
        help="Strava route ID (downloads first) or path to a local .gpx file",
    )
    norm_parser.add_argument(
        "-o", "--output",
        metavar="FILE",
        default=None,
        help="Output file path (default: <stem>_normalized.gpx or <route_id>_normalized.gpx)",
    )
    norm_parser.add_argument(
        "--threshold",
        type=float,
        default=50.0,
        metavar="METERS",
        help="Max distance in metres between departure and return point to count as a detour (default: 50)",
    )
    norm_parser.add_argument(
        "--min-detour",
        type=float,
        default=100.0,
        metavar="METERS",
        help="Minimum round-trip path length in metres to count as a detour (default: 100)",
    )
    norm_parser.add_argument(
        "--max-detour",
        type=float,
        default=5000.0,
        metavar="METERS",
        help="Maximum round-trip path length in metres to count as a detour (default: 5000)",
    )
    norm_parser.add_argument(
        "--max-lateral",
        type=float,
        default=30.0,
        metavar="METERS",
        help="Max average lateral distance in metres between outward and return legs; "
             "segments exceeding this are treated as loops, not detours (default: 30)",
    )
    norm_parser.set_defaults(func=cmd_normalize_gpx)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
