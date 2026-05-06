import io
import json

import gpxpy
import requests as http_requests
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from strava_integration.auth import load_config, get_valid_token
from strava_integration.routes import download_gpx, explore_segments
from strava_integration.gpx_normalizer import Point, _parse_gpx, find_detours, remove_detours
from strava_integration.segment_snapper import snap_to_segments, build_route_from_segments


def _gpx_bytes_to_coords(data: bytes) -> list:
    parsed = gpxpy.parse(io.StringIO(data.decode("utf-8")))
    return [
        [pt.latitude, pt.longitude, pt.elevation or 0.0]
        for track in parsed.tracks
        for seg in track.segments
        for pt in seg.points
    ]


def _load_token():
    """Return (config, token) or raise with a user-friendly message."""
    try:
        config = load_config()
    except FileNotFoundError as exc:
        raise _ApiError(503, f"Strava config not found: {exc}")
    try:
        token = get_valid_token(config)
    except http_requests.RequestException as exc:
        raise _ApiError(502, f"Token refresh failed: {exc}")
    return config, token


def _fetch_gpx_bytes(route_id: int) -> bytes:
    _, token = _load_token()
    try:
        return download_gpx(route_id, token)
    except http_requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 502
        if status == 404:
            raise _ApiError(404, "Route not found on Strava")
        if status == 401:
            raise _ApiError(401, "Unauthorized — check Strava token")
        raise _ApiError(502, f"Strava API error: {exc}")
    except http_requests.RequestException as exc:
        raise _ApiError(502, f"Network error: {exc}")


class _ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message

    def response(self):
        return JsonResponse({"error": self.message}, status=self.status)


def index(request):
    return render(request, "routes/index.html")


@csrf_exempt
@require_POST
def api_fetch_gpx(request):
    try:
        body = json.loads(request.body)
        route_id = int(body.get("route_id", ""))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({"error": "Invalid or missing route_id"}, status=400)

    try:
        gpx_bytes = _fetch_gpx_bytes(route_id)
        coords = _gpx_bytes_to_coords(gpx_bytes)
    except _ApiError as exc:
        return exc.response()
    except Exception as exc:
        return JsonResponse({"error": f"Failed to parse GPX: {exc}"}, status=500)

    if not coords:
        return JsonResponse({"error": "Route contains no track points"}, status=400)

    return JsonResponse({"coordinates": coords})


@csrf_exempt
@require_POST
def api_upload_gpx(request):
    gpx_file = request.FILES.get("gpx_file")
    if not gpx_file:
        return JsonResponse({"error": "No file uploaded"}, status=400)
    if not gpx_file.name.lower().endswith(".gpx"):
        return JsonResponse({"error": "File must be a .gpx file"}, status=400)

    data = gpx_file.read()
    try:
        coords = _gpx_bytes_to_coords(data)
    except Exception as exc:
        return JsonResponse({"error": f"Failed to parse GPX: {exc}"}, status=400)

    if not coords:
        return JsonResponse({"error": "GPX file contains no track points"}, status=400)

    return JsonResponse({"coordinates": coords})


@csrf_exempt
@require_POST
def api_normalize(request):
    content_type = request.content_type or ""
    gpx_bytes = None

    if "multipart" in content_type:
        gpx_file = request.FILES.get("gpx_file")
        if not gpx_file:
            return JsonResponse({"error": "No file uploaded"}, status=400)
        gpx_bytes = gpx_file.read()
        proximity_m = float(request.POST.get("proximity_m", 50))
        min_detour_m = float(request.POST.get("min_detour_m", 100))
        max_detour_m = float(request.POST.get("max_detour_m", 5000))
        max_lateral_m = float(request.POST.get("max_lateral_m", 30))
    else:
        try:
            body = json.loads(request.body)
            route_id = int(body.get("route_id", ""))
        except (json.JSONDecodeError, ValueError, TypeError):
            return JsonResponse(
                {"error": "Provide multipart gpx_file or JSON {route_id}"}, status=400
            )
        proximity_m = float(body.get("proximity_m", 50))
        min_detour_m = float(body.get("min_detour_m", 100))
        max_detour_m = float(body.get("max_detour_m", 5000))
        max_lateral_m = float(body.get("max_lateral_m", 30))
        try:
            gpx_bytes = _fetch_gpx_bytes(route_id)
        except _ApiError as exc:
            return exc.response()

    try:
        _gpx_obj, points = _parse_gpx(gpx_bytes)
    except Exception as exc:
        return JsonResponse({"error": f"Failed to parse GPX: {exc}"}, status=400)

    if not points:
        return JsonResponse({"error": "GPX file contains no track points"}, status=400)

    detours = find_detours(
        points,
        proximity_m=proximity_m,
        min_detour_m=min_detour_m,
        max_detour_m=max_detour_m,
        max_lateral_m=max_lateral_m,
    )
    clean_points = remove_detours(points, detours)

    return JsonResponse({
        "original": [[p.lat, p.lon, p.ele] for p in points],
        "normalized": [[p.lat, p.lon, p.ele] for p in clean_points],
        "stats": {
            "original_points": len(points),
            "clean_points": len(clean_points),
            "detours_removed": len(detours),
        },
    })


@csrf_exempt
@require_POST
def api_explore_segments(request):
    try:
        body = json.loads(request.body)
        bounds = body.get("bounds", "").strip()
        activity_type = body.get("activity_type", "riding")
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not bounds:
        return JsonResponse({"error": "Missing bounds"}, status=400)

    try:
        _, token = _load_token()
    except _ApiError as exc:
        return exc.response()

    try:
        segments = explore_segments(bounds, activity_type, token)
    except http_requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 502
        if status == 401:
            return JsonResponse({"error": "Unauthorized — check Strava token"}, status=401)
        return JsonResponse({"error": f"Strava API error: {exc}"}, status=502)
    except http_requests.RequestException as exc:
        return JsonResponse({"error": f"Network error: {exc}"}, status=502)

    return JsonResponse({"segments": segments})


def _json_coords_to_points(coords_list: list) -> list:
    return [
        Point(lat=float(c[0]), lon=float(c[1]), ele=float(c[2]) if len(c) > 2 else 0.0)
        for c in coords_list
    ]


def _raw_segments_to_point_lists(raw_segments: list) -> list:
    result = []
    for s in raw_segments:
        pts = [Point(lat=float(c[0]), lon=float(c[1]), ele=0.0) for c in s.get("coordinates", [])]
        if len(pts) >= 2:
            result.append(pts)
    return result


@csrf_exempt
@require_POST
def api_snap_to_segments(request):
    try:
        body = json.loads(request.body)
        coordinates = body.get("coordinates", [])
        raw_segments = body.get("segments", [])
        snap_radius_m = float(body.get("snap_radius_m", 30))
        min_run_length = int(body.get("min_run_length", 5))
        activity_type = body.get("activity_type", "riding")
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({"error": "Invalid request body"}, status=400)

    if not coordinates:
        return JsonResponse({"error": "Missing coordinates"}, status=400)

    try:
        gpx_points = _json_coords_to_points(coordinates)
    except (TypeError, ValueError, IndexError) as exc:
        return JsonResponse({"error": f"Invalid coordinates format: {exc}"}, status=400)

    segments = _raw_segments_to_point_lists(raw_segments)

    if not segments:
        # Auto-explore: derive bounding box from GPX coordinates
        lats = [p.lat for p in gpx_points]
        lons = [p.lon for p in gpx_points]
        bounds = f"{min(lats)},{min(lons)},{max(lats)},{max(lons)}"
        try:
            _, token = _load_token()
            raw_explored = explore_segments(bounds, activity_type, token)
        except _ApiError as exc:
            return exc.response()
        except http_requests.RequestException as exc:
            return JsonResponse({"error": f"Could not explore segments: {exc}"}, status=502)
        segments = _raw_segments_to_point_lists(raw_explored)

    if not segments:
        return JsonResponse({"error": "No segments found in the route area"}, status=404)

    snapped_points, segments_applied = snap_to_segments(
        gpx_points, segments, snap_radius_m=snap_radius_m, min_run_length=min_run_length,
    )

    return JsonResponse({
        "snapped": [[p.lat, p.lon, p.ele] for p in snapped_points],
        "stats": {
            "original_points": len(gpx_points),
            "clean_points": len(snapped_points),
            "segments_applied": segments_applied,
        },
    })


@csrf_exempt
@require_POST
def api_build_route(request):
    try:
        body = json.loads(request.body)
        raw_segments = body.get("segments", [])
        connection_radius_m = float(body.get("connection_radius_m", 100))
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({"error": "Invalid request body"}, status=400)

    segments = _raw_segments_to_point_lists(raw_segments)
    if not segments:
        return JsonResponse({"error": "No valid segments provided"}, status=400)

    route = build_route_from_segments(segments, connection_radius_m=connection_radius_m)

    return JsonResponse({
        "coordinates": [[p.lat, p.lon, 0.0] for p in route],
    })
