import math

import pya
import pytest

from kcq.geometry import router
from kcq.utils.errors import InvalidGeometryError


def _angdiff(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _heading(p_from, p_to):
    return math.degrees(math.atan2(p_to.y - p_from.y, p_to.x - p_from.x)) % 360


def _assert_valid_route(waypoints, a1, a2, max_corners=None):
    assert len(waypoints) >= 2
    dep_heading = _heading(waypoints[0], waypoints[1])
    arr_heading = _heading(waypoints[-2], waypoints[-1])
    assert _angdiff(dep_heading, a1 % 360) < 1e-6, f"departure heading {dep_heading} != {a1}"
    assert _angdiff(arr_heading, (a2 + 180) % 360) < 1e-6, f"arrival heading {arr_heading} != {a2 + 180}"
    if max_corners is not None:
        assert len(waypoints) - 2 <= max_corners


class TestSnapToAllowed:
    def test_snaps_to_nearest_octilinear_direction(self):
        assert router.snap_to_allowed(10) == 0
        assert router.snap_to_allowed(40) == 45
        assert router.snap_to_allowed(170) == 180
        assert router.snap_to_allowed(-10) == 0

    def test_snaps_to_nearest_manhattan_direction(self):
        allowed = router._MANHATTAN_DIRECTIONS_DEG
        assert router.snap_to_allowed(44, allowed) == 0
        assert router.snap_to_allowed(46, allowed) == 90


class TestRouteOctilinearStraight:
    def test_straight_line_when_ports_face_each_other(self):
        p1, p2 = pya.DPoint(0, 0), pya.DPoint(100, 0)
        wp = router.route_octilinear(p1, 0, p2, 180)
        _assert_valid_route(wp, 0, 180, max_corners=0)
        assert wp[0] == p1 and wp[-1] == p2

    def test_diagonal_straight_line(self):
        p1, p2 = pya.DPoint(10, 10), pya.DPoint(-40, 60)
        wp = router.route_octilinear(p1, 135, p2, 315)
        _assert_valid_route(wp, 135, 315, max_corners=0)


class TestRouteOctilinearL:
    def test_perpendicular_ports_route_as_l_shape(self):
        p1, p2 = pya.DPoint(0, 0), pya.DPoint(50, 50)
        wp = router.route_octilinear(p1, 0, p2, 90)
        _assert_valid_route(wp, 0, 90)

    def test_diagonal_l_shape(self):
        p1, p2 = pya.DPoint(0, 0), pya.DPoint(49.497474683, 21.213203436)
        wp = router.route_octilinear(p1, 45, p2, 135)
        _assert_valid_route(wp, 45, 135, max_corners=1)


class TestRouteOctilinearZ:
    def test_perpendicular_other_side_is_pure_l(self):
        p1, p2 = pya.DPoint(0, 0), pya.DPoint(50, -50)
        wp = router.route_octilinear(p1, 0, p2, 90)
        _assert_valid_route(wp, 0, 90, max_corners=1)

    def test_offset_ports_facing_same_direction_needs_bridge(self):
        p1, p2 = pya.DPoint(0, 0), pya.DPoint(100, 50)
        wp = router.route_octilinear(p1, 0, p2, 180)
        _assert_valid_route(wp, 0, 180)
        assert len(wp) - 2 <= 2


class TestRouteOctilinearU:
    def test_port_behind_requires_u_route(self):
        # p2 is "behind" p1 relative to a1's heading, and p2's own outward
        # direction also faces back toward p1 -- unreachable with <= 2
        # corners, needs a backtrack (U-shape, 3 corners).
        p1, p2 = pya.DPoint(0, 0), pya.DPoint(-100, 0)
        wp = router.route_octilinear(p1, 0, p2, 180)
        _assert_valid_route(wp, 0, 180)
        assert len(wp) - 2 == 2

    def test_diagonal_u_route(self):
        p1, p2 = pya.DPoint(0, 0), pya.DPoint(-50, 10)
        wp = router.route_octilinear(p1, 45, p2, 45)
        _assert_valid_route(wp, 45, 45)


class TestRouteOctilinearErrors:
    def test_same_point_raises(self):
        p = pya.DPoint(0, 0)
        with pytest.raises(InvalidGeometryError):
            router.route_octilinear(p, 0, p, 180)


class TestRouteManhattan:
    def test_only_uses_axis_aligned_headings(self):
        wp = router.route_manhattan(pya.DPoint(0, 0), 0, pya.DPoint(50, 50), 90)
        for i in range(len(wp) - 1):
            heading = round(_heading(wp[i], wp[i + 1]), 3) % 90
            assert heading in (0.0, 90.0) or heading == 0
        _assert_valid_route(wp, 0, 90)

    def test_excludes_45_degree_segments_even_for_diagonal_ports(self):
        # Ports at 45 deg get snapped down to an allowed Manhattan
        # direction before solving, so no output segment is ever 45 deg.
        wp = router.route_manhattan(pya.DPoint(0, 0), 45, pya.DPoint(100, 0), 225)
        for i in range(len(wp) - 1):
            heading = round(_heading(wp[i], wp[i + 1]), 3)
            assert heading in (0.0, 90.0, 180.0, 270.0)
