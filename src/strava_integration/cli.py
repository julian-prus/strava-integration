"""Command-line interface for the Strava integration tool."""

import argparse
import sys
from pathlib import Path

import requests

from strava_integration.auth import get_valid_token, load_config
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


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="strava",
        description="Strava CLI — interact with the Strava API",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    subparsers.required = True

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
