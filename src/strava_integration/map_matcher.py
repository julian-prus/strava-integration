"""Map-match a GPS trace to the OSM road network via the public OSRM cycling API."""

from typing import List

import requests

from strava_integration.gpx_normalizer import Point, haversine

OSRM_MATCH_URL = "http://router.project-osrm.org/match/v1/cycling"
_MAX_COORDS = 100


def _subsample_evenly(points: List[Point], n: int) -> List[Point]:
    """Return n evenly-spaced points from the list (inclusive of both ends)."""
    if len(points) <= n:
        return list(points)
    step = (len(points) - 1) / (n - 1)
    return [points[round(i * step)] for i in range(n)]


def _interpolate_elevation(
    matched: List[Point],
    original: List[Point],
) -> List[Point]:
    """Assign elevation to matched points by nearest-original lookup."""
    if not original:
        return matched
    result = []
    for mp in matched:
        best_ele = 0.0
        best_dist = float("inf")
        for op in original:
            d = haversine(mp, op)
            if d < best_dist:
                best_dist = d
                best_ele = op.ele
        result.append(Point(mp.lat, mp.lon, best_ele))
    return result


def match_to_roads(
    points: List[Point],
    radius_m: float = 50.0,
) -> List[Point]:
    """Map-match *points* to the OSM cycling road network using OSRM.

    Subsamples to at most 100 waypoints (OSRM limit), then returns the
    full road-snapped geometry with elevation interpolated from the
    original points.  Falls back to the original points on any error.
    """
    if len(points) < 2:
        return list(points)

    sampled = _subsample_evenly(points, _MAX_COORDS)
    coords_str = ";".join(f"{p.lon},{p.lat}" for p in sampled)
    radiuses_str = ";".join(str(int(radius_m)) for _ in sampled)

    url = (
        f"{OSRM_MATCH_URL}/{coords_str}"
        f"?radiuses={radiuses_str}&overview=full&geometries=geojson&gaps=ignore"
    )

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return list(points)

    if data.get("code") != "Ok":
        return list(points)

    matched: List[Point] = []
    for matching in data.get("matchings", []):
        for lon, lat in matching.get("geometry", {}).get("coordinates", []):
            matched.append(Point(lat=lat, lon=lon, ele=0.0))

    if not matched:
        return list(points)

    return _interpolate_elevation(matched, points)
