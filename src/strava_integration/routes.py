"""Strava Routes API interactions."""

import requests

BASE_URL = "https://www.strava.com/api/v3"


def download_gpx(route_id: int, access_token: str) -> bytes:
    """Download a Strava route as GPX bytes.

    Args:
        route_id: The Strava route ID.
        access_token: A valid OAuth2 access token with read or read_all scope.

    Returns:
        Raw GPX file contents as bytes.

    Raises:
        requests.HTTPError: On non-2xx responses (e.g. 401 unauthorized, 404 not found).
    """
    url = f"{BASE_URL}/routes/{route_id}/export_gpx"
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.content
