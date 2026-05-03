"""Tests for the GPX normalization module."""

import math
import os
import tempfile
from pathlib import Path

import pytest

from strava_integration.gpx_normalizer import (
    Point,
    find_detours,
    haversine,
    normalize_gpx,
    path_length,
    remove_detours,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LAT_REF = 52.0
_LON_REF = 13.0
_M_PER_DEG_LAT = 111_000.0
_M_PER_DEG_LON = 111_000.0 * math.cos(math.radians(_LAT_REF))


def _pt(north_m: float, east_m: float, ele: float = 0.0) -> Point:
    """Create a Point offset in metres from the reference coordinate."""
    return Point(
        lat=_LAT_REF + north_m / _M_PER_DEG_LAT,
        lon=_LON_REF + east_m / _M_PER_DEG_LON,
        ele=ele,
    )


# ---------------------------------------------------------------------------
# haversine
# ---------------------------------------------------------------------------

class TestHaversine:
    def test_same_point_is_zero(self):
        p = _pt(0, 0)
        assert haversine(p, p) == pytest.approx(0.0)

    def test_100m_north(self):
        p1 = _pt(0, 0)
        p2 = _pt(100, 0)
        assert haversine(p1, p2) == pytest.approx(100.0, rel=0.005)

    def test_100m_east(self):
        p1 = _pt(0, 0)
        p2 = _pt(0, 100)
        assert haversine(p1, p2) == pytest.approx(100.0, rel=0.005)

    def test_symmetry(self):
        p1 = _pt(0, 0)
        p2 = _pt(300, 400)
        assert haversine(p1, p2) == pytest.approx(haversine(p2, p1))


# ---------------------------------------------------------------------------
# path_length
# ---------------------------------------------------------------------------

class TestPathLength:
    def test_single_point_is_zero(self):
        assert path_length([_pt(0, 0)]) == pytest.approx(0.0)

    def test_two_points_100m_apart(self):
        pts = [_pt(0, 0), _pt(0, 100)]
        assert path_length(pts) == pytest.approx(100.0, rel=0.005)

    def test_three_points_l_shape(self):
        # 100 m north then 100 m east → total 200 m
        pts = [_pt(0, 0), _pt(100, 0), _pt(100, 100)]
        assert path_length(pts) == pytest.approx(200.0, rel=0.01)


# ---------------------------------------------------------------------------
# find_detours
# ---------------------------------------------------------------------------

class TestFindDetours:
    def _straight_path(self, n=20, spacing_m=50):
        """n points going north, equally spaced."""
        return [_pt(i * spacing_m, 0) for i in range(n)]

    def test_straight_path_no_detours(self):
        pts = self._straight_path()
        assert find_detours(pts) == []

    def test_single_spike_detected(self):
        """
        Main path goes north. At index 9, a detour branches east and
        returns to near index 9 at index 15 (gap of 6 > min_index_gap=5).
        Intermediate points 10–14 should be flagged as the detour.
        """
        main_before = [_pt(i * 50, 0) for i in range(10)]   # 0..9
        spike = [
            _pt(9 * 50, 0),    # 9  — anchor
            _pt(9 * 50, 70),   # 10
            _pt(9 * 50, 140),  # 11
            _pt(9 * 50, 200),  # 12 — tip
            _pt(9 * 50, 130),  # 13
            _pt(9 * 50, 60),   # 14
            _pt(9 * 50, 30),   # 15 — return: 30 m east of anchor, within 50 m
        ]
        main_after = [_pt((i + 10) * 50, 0) for i in range(1, 10)]  # 16..24
        pts = main_before + spike + main_after

        detours = find_detours(pts, proximity_m=50.0, min_detour_m=100.0)
        assert len(detours) == 1
        start, end = detours[0]
        # Intermediate points 10–14 must be inside [start, end]
        assert start <= 10 and end >= 14

    def test_loop_route_not_a_detour(self):
        """A circular route whose start and end are close must not be removed."""
        n = 200
        # Circle: n points around a ~300 m radius loop
        radius_m = 300
        pts = [
            _pt(
                radius_m * math.sin(2 * math.pi * i / n),
                radius_m * (1 - math.cos(2 * math.pi * i / n)),
            )
            for i in range(n)
        ]
        detours = find_detours(pts)
        assert detours == []

    def test_short_jitter_ignored(self):
        """A tiny out-and-back under min_detour_m is not a detour."""
        pts = [_pt(i * 50, 0) for i in range(10)]
        # Add a 20 m jitter spike after index 4
        jitter = [
            _pt(4 * 50, 0),
            _pt(4 * 50, 10),
            _pt(4 * 50, 20),
            _pt(4 * 50, 5),  # returns within 50 m but total length < 100 m
        ]
        path = pts[:4] + jitter + pts[5:]
        detours = find_detours(path, proximity_m=50.0, min_detour_m=100.0)
        assert detours == []


# ---------------------------------------------------------------------------
# remove_detours
# ---------------------------------------------------------------------------

class TestRemoveDetours:
    def test_no_detours_unchanged(self):
        pts = [_pt(i * 10, 0) for i in range(5)]
        assert remove_detours(pts, []) == pts

    def test_middle_range_removed(self):
        pts = [_pt(i * 10, 0) for i in range(7)]  # indices 0..6
        clean = remove_detours(pts, [(2, 4)])       # remove 2, 3, 4
        assert len(clean) == 4
        assert clean == [pts[0], pts[1], pts[5], pts[6]]


# ---------------------------------------------------------------------------
# normalize_gpx (integration)
# ---------------------------------------------------------------------------

SAMPLE_GPX = Path(__file__).parent.parent / "3485649294818578590.gpx"


class TestNormalizeGpx:
    @pytest.mark.skipif(not SAMPLE_GPX.exists(), reason="sample GPX not present")
    def test_sample_produces_output(self, tmp_path):
        output = tmp_path / "out.gpx"
        orig, clean, detours = normalize_gpx(SAMPLE_GPX, output)
        assert output.exists()
        assert orig > 0
        assert clean > 0
        assert clean <= orig

    @pytest.mark.skipif(not SAMPLE_GPX.exists(), reason="sample GPX not present")
    def test_output_is_valid_gpx(self, tmp_path):
        import gpxpy
        output = tmp_path / "out.gpx"
        normalize_gpx(SAMPLE_GPX, output)
        with output.open() as f:
            parsed = gpxpy.parse(f)
        assert parsed.tracks
        assert parsed.tracks[0].segments[0].points
