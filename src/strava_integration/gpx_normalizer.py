"""GPX route normalization — detects and removes out-and-back detour spikes."""

import io
import math
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

import gpxpy
import gpxpy.gpx


class Point(NamedTuple):
    lat: float
    lon: float
    ele: float


def haversine(p1: Point, p2: Point) -> float:
    """Great-circle distance in metres between two lat/lon points."""
    R = 6_371_000
    lat1, lat2 = math.radians(p1.lat), math.radians(p2.lat)
    dlat = lat2 - lat1
    dlon = math.radians(p2.lon - p1.lon)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def path_length(points: List[Point]) -> float:
    """Cumulative haversine length of a sequence of Points in metres."""
    return sum(haversine(points[i], points[i + 1]) for i in range(len(points) - 1))


def _parse_gpx(source) -> Tuple[gpxpy.gpx.GPX, List[Point]]:
    if isinstance(source, (str, Path)):
        with Path(source).open(encoding="utf-8") as f:
            parsed = gpxpy.parse(f)
    else:
        parsed = gpxpy.parse(io.StringIO(source.decode("utf-8")))

    points: List[Point] = []
    for track in parsed.tracks:
        for segment in track.segments:
            for tp in segment.points:
                points.append(Point(tp.latitude, tp.longitude, tp.elevation or 0.0))
    return parsed, points


def _is_out_and_back(segment: List[Point], max_lateral_m: float = 30.0) -> bool:
    """
    Return True only if segment is a genuine out-and-back path (retraces itself).

    Splits at the apex (point of maximum distance from the start), then
    measures the average lateral distance between evenly-sampled points on the
    outward leg and their counterparts on the return leg reversed.  A small
    average means the two legs share the same physical road → true detour.
    A large average means the route takes a different road back → loop closure,
    not a detour.
    """
    n = len(segment)
    if n < 4:
        return True

    anchor = segment[0]
    apex_idx = max(range(n), key=lambda k: haversine(anchor, segment[k]))
    if apex_idx == 0 or apex_idx == n - 1:
        return True

    outward = segment[: apex_idx + 1]
    return_leg = list(reversed(segment[apex_idx:]))

    # Sample from the shorter leg; for each sample find its nearest point
    # on the longer leg.  This is robust to uneven point density and handles
    # the case where the two paths are offset (same road, opposite lanes) or
    # a duplicate anchor point at segment[0].
    shorter = outward if len(outward) <= len(return_leg) else return_leg
    longer = return_leg if len(outward) <= len(return_leg) else outward

    samples = min(len(shorter), 10)
    if samples < 2:
        return True

    total = 0.0
    for k in range(samples):
        pt = shorter[int(k * (len(shorter) - 1) / (samples - 1))]
        total += min(haversine(pt, q) for q in longer)

    return (total / samples) < max_lateral_m


def find_detours(
    points: List[Point],
    proximity_m: float = 50.0,
    min_detour_m: float = 100.0,
    max_detour_m: float = 5000.0,
    min_index_gap: int = 5,
    max_lateral_m: float = 30.0,
) -> List[Tuple[int, int]]:
    """
    Return list of (start_idx, end_idx) inclusive index ranges that are detours.

    A detour is a sub-path that starts near point i, travels between
    min_detour_m and max_detour_m in total, then returns within proximity_m
    of point i, AND physically retraces itself (outward and return legs share
    the same road within max_lateral_m metres on average).

    The max_lateral_m check prevents loop closures — where two different roads
    happen to come near each other — from being falsely removed.

    The first and last 1% of the route are excluded from being matched as a
    pair so that circular routes whose ends nearly coincide are not falsely
    removed.
    """
    n = len(points)
    if n < min_index_gap + 1:
        return []

    loop_guard = max(1, n // 100)
    detours: List[Tuple[int, int]] = []
    i = 0

    while i < n:
        for j in range(i + min_index_gap, n):
            # Don't match the very start against the very end (loop route)
            if i < loop_guard and j >= n - loop_guard:
                continue
            if haversine(points[i], points[j]) < proximity_m:
                seg_len = path_length(points[i : j + 1])
                if min_detour_m <= seg_len <= max_detour_m:
                    segment = points[i : j + 1]
                    if _is_out_and_back(segment, max_lateral_m=max_lateral_m):
                        detours.append((i + 1, j - 1))
                        i = j  # skip to the return point
                break  # take the first (nearest) return regardless
        else:
            i += 1
            continue
        i += 1  # advance past the matched return point

    return detours


def remove_detours(points: List[Point], detours: List[Tuple[int, int]]) -> List[Point]:
    """Return a copy of points with all detour index ranges removed."""
    if not detours:
        return list(points)
    drop = set()
    for start, end in detours:
        drop.update(range(start, end + 1))
    return [p for idx, p in enumerate(points) if idx not in drop]


def _write_gpx(original: gpxpy.gpx.GPX, clean_points: List[Point], output: Path) -> int:
    """Replace track segment points in original GPX and write to output."""
    for track in original.tracks:
        for segment in track.segments:
            segment.points.clear()

    if not original.tracks:
        original.tracks.append(gpxpy.gpx.GPXTrack())
    if not original.tracks[0].segments:
        original.tracks[0].segments.append(gpxpy.gpx.GPXTrackSegment())

    target = original.tracks[0].segments[0]
    for p in clean_points:
        target.points.append(gpxpy.gpx.GPXTrackPoint(p.lat, p.lon, elevation=p.ele))

    output.write_text(original.to_xml(), encoding="utf-8")
    return len(clean_points)


def normalize_gpx(
    input_path: Path,
    output_path: Path,
    proximity_m: float = 50.0,
    min_detour_m: float = 100.0,
    max_detour_m: float = 5000.0,
    max_lateral_m: float = 30.0,
) -> Tuple[int, int, int]:
    """
    Load, normalize, and save a GPX file.

    Returns (original_point_count, clean_point_count, detour_segment_count).
    """
    original, points = _parse_gpx(input_path)
    detours = find_detours(
        points,
        proximity_m=proximity_m,
        min_detour_m=min_detour_m,
        max_detour_m=max_detour_m,
        max_lateral_m=max_lateral_m,
    )
    clean = remove_detours(points, detours)
    _write_gpx(original, clean, output_path)
    return len(points), len(clean), len(detours)


def normalize_gpx_bytes(
    data: bytes,
    output_path: Path,
    proximity_m: float = 50.0,
    min_detour_m: float = 100.0,
    max_detour_m: float = 5000.0,
    max_lateral_m: float = 30.0,
) -> Tuple[int, int, int]:
    """Same as normalize_gpx but accepts raw GPX bytes instead of a file path."""
    original, points = _parse_gpx(data)
    detours = find_detours(
        points,
        proximity_m=proximity_m,
        min_detour_m=min_detour_m,
        max_detour_m=max_detour_m,
        max_lateral_m=max_lateral_m,
    )
    clean = remove_detours(points, detours)
    _write_gpx(original, clean, output_path)
    return len(points), len(clean), len(detours)
