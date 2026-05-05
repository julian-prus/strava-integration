import io
import json

import gpxpy
import requests as http_requests
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from strava_integration.auth import load_config, get_valid_token
from strava_integration.routes import download_gpx
from strava_integration.gpx_normalizer import _parse_gpx, find_detours, remove_detours


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
    else:
        try:
            body = json.loads(request.body)
            route_id = int(body.get("route_id", ""))
        except (json.JSONDecodeError, ValueError, TypeError):
            return JsonResponse(
                {"error": "Provide multipart gpx_file or JSON {route_id}"}, status=400
            )
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

    detours = find_detours(points)
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
