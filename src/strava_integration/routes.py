"""Strava Routes API interactions."""

from typing import List, Tuple

import requests

BASE_URL = "https://www.strava.com/api/v3"


def _decode_polyline(encoded: str) -> List[Tuple[float, float]]:
    """Decode a Google Encoded Polyline string to a list of (lat, lng) pairs."""
    coords: List[Tuple[float, float]] = []
    index = 0
    lat = lng = 0
    length = len(encoded)
    while index < length:
        for is_lng in (False, True):
            result = shift = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 32:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if is_lng:
                lng += delta
                coords.append((lat / 1e5, lng / 1e5))
            else:
                lat += delta
    return coords


def explore_segments(bounds: str, activity_type: str, access_token: str) -> list:
    """Return top segments within a bounding box from the Strava explore endpoint.

    Args:
        bounds: "sw_lat,sw_lng,ne_lat,ne_lng"
        activity_type: "riding" or "running"
        access_token: valid OAuth2 access token

    Returns:
        List of segment dicts with decoded polyline in "coordinates" key.

    Raises:
        requests.HTTPError: On non-2xx responses.
    """
    url = f"{BASE_URL}/segments/explore"
    response = requests.get(
        url,
        params={"bounds": bounds, "activity_type": activity_type},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()

    segments = response.json().get("segments", [])
    result = []
    for seg in segments:
        coords = _decode_polyline(seg.get("points") or "")
        result.append({
            "id": seg.get("id"),
            "name": seg.get("name"),
            "distance": seg.get("distance"),
            "avg_grade": seg.get("avg_grade"),
            "coordinates": coords,
        })
    return result


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
