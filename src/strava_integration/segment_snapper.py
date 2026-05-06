"""Snap a GPX route to Strava segments and build routes from segment chains."""

from typing import List, Tuple

from strava_integration.gpx_normalizer import Point, haversine


def _nearest_on_segment(pt: Point, seg: List[Point]) -> Tuple[int, float]:
    """Return (index_of_nearest_point_on_seg, distance_metres)."""
    best_idx = 0
    best_dist = float("inf")
    for i, sp in enumerate(seg):
        d = haversine(pt, sp)
        if d < best_dist:
            best_dist = d
            best_idx = i
    return best_idx, best_dist


def snap_to_segments(
    gpx_points: List[Point],
    segments: List[List[Point]],
    snap_radius_m: float = 30.0,
    min_run_length: int = 5,
) -> Tuple[List[Point], int]:
    """Replace stretches of gpx_points that closely follow a Strava segment.

    For each GPX point, finds the nearest segment point across all segments.
    Consecutive GPX points assigned to the same segment that form a run of
    at least min_run_length are replaced with the exact segment coordinates
    for the covered range.  Elevation is linearly interpolated from the
    original GPX end-points of the run.

    Returns (snapped_points, number_of_runs_replaced).
    """
    if not segments or not gpx_points:
        return list(gpx_points), 0

    n = len(gpx_points)

    # assignment[i] = (seg_idx, seg_pt_idx) or None if outside snap_radius
    assignment: List[Tuple[int, int] | None] = [None] * n
    for i, gpt in enumerate(gpx_points):
        best_dist = float("inf")
        best_seg = -1
        best_pt = -1
        for si, seg in enumerate(segments):
            idx, dist = _nearest_on_segment(gpt, seg)
            if dist < best_dist:
                best_dist = dist
                best_seg = si
                best_pt = idx
        if best_dist <= snap_radius_m:
            assignment[i] = (best_seg, best_pt)

    # Collect replacement ranges: (gpx_start, gpx_end_exclusive, replacement_points)
    replacements: List[Tuple[int, int, List[Point]]] = []
    i = 0
    while i < n:
        if assignment[i] is None:
            i += 1
            continue

        seg_idx = assignment[i][0]
        j = i
        while j < n and assignment[j] is not None and assignment[j][0] == seg_idx:
            j += 1

        run_len = j - i
        if run_len >= min_run_length:
            seg_pt_indices = [assignment[k][1] for k in range(i, j)]
            s_min = min(seg_pt_indices)
            s_max = max(seg_pt_indices)

            if s_min < s_max:
                forward = seg_pt_indices[0] <= seg_pt_indices[-1]
                seg_slice = segments[seg_idx][s_min: s_max + 1]
                if not forward:
                    seg_slice = list(reversed(seg_slice))

                ele_start = gpx_points[i].ele
                ele_end = gpx_points[j - 1].ele
                m = len(seg_slice) - 1
                snapped_pts = [
                    Point(
                        p.lat,
                        p.lon,
                        ele_start + (ele_end - ele_start) * k / max(m, 1),
                    )
                    for k, p in enumerate(seg_slice)
                ]
                replacements.append((i, j, snapped_pts))

        i = j

    # Apply replacements right-to-left so earlier indices stay valid
    result = list(gpx_points)
    for start, end, new_pts in sorted(replacements, key=lambda x: -x[0]):
        result[start:end] = new_pts

    return result, len(replacements)


def build_route_from_segments(
    segments: List[List[Point]],
    connection_radius_m: float = 100.0,
) -> List[Point]:
    """Chain segments into a route by greedily connecting nearby endpoints.

    Tries every segment as a starting point in both directions and returns the
    longest chain found.  Two segments connect when one's end endpoint is within
    connection_radius_m of the other's start endpoint.
    """
    if not segments:
        return []
    if len(segments) == 1:
        return list(segments[0])

    best_chain: List[Point] = []

    for start_idx in range(len(segments)):
        for start_reversed in (False, True):
            used = {start_idx}
            current = list(reversed(segments[start_idx])) if start_reversed else list(segments[start_idx])
            chain = list(current)

            while True:
                tail = chain[-1]
                best_next = -1
                best_dist = float("inf")
                best_rev = False

                for si in range(len(segments)):
                    if si in used:
                        continue
                    seg = segments[si]
                    d_fwd = haversine(tail, seg[0])
                    d_rev = haversine(tail, seg[-1])
                    if d_fwd <= connection_radius_m and d_fwd < best_dist:
                        best_dist = d_fwd
                        best_next = si
                        best_rev = False
                    if d_rev <= connection_radius_m and d_rev < best_dist:
                        best_dist = d_rev
                        best_next = si
                        best_rev = True

                if best_next == -1:
                    break

                next_seg = segments[best_next]
                if best_rev:
                    next_seg = list(reversed(next_seg))
                # Skip duplicate junction point
                chain.extend(next_seg[1:] if next_seg else [])
                used.add(best_next)

            if len(chain) > len(best_chain):
                best_chain = list(chain)

    return best_chain
