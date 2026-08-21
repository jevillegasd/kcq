import math

import pya
import pytest

from kcq.geometry import curves, router
from kcq.utils.errors import InvalidGeometryError


def _heading(p_from, p_to):
    return math.degrees(math.atan2(p_to.y - p_from.y, p_to.x - p_from.x))


def _angdiff(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


class TestEulerBendPoints:
    def test_starts_at_origin_heading_zero(self):
        pts = curves.euler_bend_points(50, 90, num_pts=400)
        assert pts[0].x == pytest.approx(0.0, abs=1e-9)
        assert pts[0].y == pytest.approx(0.0, abs=1e-9)
        start_heading = _heading(pts[0], pts[1])
        assert start_heading == pytest.approx(0.0, abs=0.1)

    def test_ends_heading_at_turn_angle(self):
        pts = curves.euler_bend_points(50, 90, num_pts=400)
        end_heading = _heading(pts[-2], pts[-1])
        assert end_heading == pytest.approx(90.0, abs=0.1)

    def test_negative_angle_turns_right(self):
        pts = curves.euler_bend_points(50, -90, num_pts=400)
        end_heading = _heading(pts[-2], pts[-1])
        assert end_heading == pytest.approx(-90.0, abs=0.1)
        assert pts[-1].y < 0  # right turn from heading 0 dips into y<0

    def test_finer_discretization_reduces_endpoint_heading_error(self):
        coarse = curves.euler_bend_points(50, 90, num_pts=10)
        fine = curves.euler_bend_points(50, 90, num_pts=1000)
        coarse_err = abs(_heading(coarse[0], coarse[1]) - 0.0)
        fine_err = abs(_heading(fine[0], fine[1]) - 0.0)
        assert fine_err < coarse_err

    def test_invalid_radius_raises(self):
        with pytest.raises(InvalidGeometryError):
            curves.euler_bend_points(0, 90)
        with pytest.raises(InvalidGeometryError):
            curves.euler_bend_points(-10, 90)

    def test_zero_angle_is_a_single_point(self):
        pts = curves.euler_bend_points(50, 0)
        assert len(pts) == 1


class TestArcBendPoints:
    def test_matches_closed_form_tangent_length(self):
        # For a circular arc, the sharp-corner-to-bend-start distance has
        # the well-known closed form R * tan(turn/2); cross-check the
        # generic numeric _bend_tangent_length against it as a
        # correctness regression test.
        radius, angle = 50.0, 90.0
        numeric = curves._bend_tangent_length(radius, angle, "arc", 400)
        closed_form = radius * math.tan(math.radians(angle) / 2.0)
        assert numeric == pytest.approx(closed_form, abs=1e-2)

    def test_endpoint_lies_on_circle_of_given_radius(self):
        radius, angle = 30.0, 60.0
        pts = curves.arc_bend_points(radius, angle, num_pts=400)
        center = pya.DPoint(0.0, radius)  # left turn -> center at +y
        # Numeric (cumulative-trapezoid) integration, not exact trig, so
        # this is a "close to the true circle" check, not bit-exact.
        assert pts[-1].distance(center) == pytest.approx(radius, abs=1e-2)
        assert pts[0].distance(center) == pytest.approx(radius, abs=1e-2)


class TestAdiabaticSineSbend:
    def test_endpoints_match_length_and_offset(self):
        pts = curves.adiabatic_sine_sbend(100, 20, num_pts=200)
        assert pts[0].x == pytest.approx(0.0, abs=1e-9)
        assert pts[0].y == pytest.approx(0.0, abs=1e-9)
        assert pts[-1].x == pytest.approx(100.0, abs=1e-9)
        assert pts[-1].y == pytest.approx(20.0, abs=1e-9)

    def test_zero_slope_at_both_ends(self):
        pts = curves.adiabatic_sine_sbend(100, 20, num_pts=400)
        start_slope_deg = _heading(pts[0], pts[1])
        end_slope_deg = _heading(pts[-2], pts[-1])
        assert start_slope_deg == pytest.approx(0.0, abs=0.5)
        assert end_slope_deg == pytest.approx(0.0, abs=0.5)

    def test_invalid_length_raises(self):
        with pytest.raises(InvalidGeometryError):
            curves.adiabatic_sine_sbend(0, 20)


class TestRoundPolyline:
    def test_two_waypoints_passthrough_unchanged(self):
        wp = [pya.DPoint(0, 0), pya.DPoint(100, 0)]
        result = curves.round_polyline(wp, 10.0, style="euler")
        assert result == wp

    def test_zero_radius_passthrough_unchanged(self):
        wp = [pya.DPoint(0, 0), pya.DPoint(50, 0), pya.DPoint(50, 50)]
        result = curves.round_polyline(wp, 0.0, style="euler")
        assert result == wp

    @pytest.mark.parametrize("style", ["euler", "arc"])
    def test_l_route_smoothing_preserves_endpoints_and_headings(self, style):
        p1, p2 = pya.DPoint(0, 0), pya.DPoint(49.497474683, 21.213203436)
        wp = router.route_octilinear(p1, 45, p2, 135)
        assert len(wp) - 2 == 1  # confirm this is the single-corner L case
        smoothed = curves.round_polyline(wp, 10.0, style=style, num_pts_per_bend=64)
        assert smoothed[0] == wp[0]
        assert smoothed[-1] == wp[-1]
        assert len(smoothed) > len(wp)
        start_heading = _heading(smoothed[0], smoothed[1])
        end_heading = _heading(smoothed[-2], smoothed[-1])
        assert _angdiff(start_heading, 45.0) < 0.5
        assert _angdiff(end_heading, 315.0) < 0.5

    def test_u_route_smoothing_handles_shared_middle_segment(self):
        # A U-route where the bridging (perpendicular) segment has real
        # length -- as opposed to the exactly-colinear backtrack case
        # below, this has two ordinary 90 deg corners, not hairpins.
        # bend_radius passed to the router is a floor on straight-run
        # length, not an exact guarantee for every style/angle (an Euler
        # bend's tangent trim is longer than a circular arc's of the same
        # nominal radius) -- pad it generously here since this test is
        # about the shared-segment bookkeeping, not edge-of-fit behavior
        # (see test_raises_when_two_corners_overlap_on_shared_segment).
        wp = router.route_octilinear(pya.DPoint(0, 0), 45, pya.DPoint(-50, 10), 45, bend_radius=15.0)
        assert len(wp) - 2 == 2  # confirm this is the 2-corner U case
        smoothed = curves.round_polyline(wp, 5.0, style="euler", num_pts_per_bend=32)
        assert smoothed[0] == wp[0]
        assert smoothed[-1] == wp[-1]

    def test_colinear_backtrack_u_route_is_a_double_hairpin(self):
        # p1/p2 sit on the same line, each requiring the route to depart
        # in the direction it must also arrive from -- resolvable as
        # waypoints (router.py handles it, see test_router.py), but only
        # as two literal 180 deg reversals, which round_polyline correctly
        # refuses rather than mis-rendering.
        wp = router.route_octilinear(pya.DPoint(0, 0), 0, pya.DPoint(-100, 0), 180)
        with pytest.raises(InvalidGeometryError, match="hairpin"):
            curves.round_polyline(wp, 5.0, style="euler")

    def test_hairpin_corner_raises_clear_error(self):
        # route_octilinear can legitimately produce a route whose bridge
        # segment must overshoot and reverse (e.g. perpendicular ports
        # where p2 can only be approached from "above") -- a genuine 180
        # deg interior turn. That can't be expressed as an inscribed
        # corner bend (the tangent lines are parallel), so it must raise
        # a clear, specific error rather than emit wrong geometry.
        wp = router.route_octilinear(pya.DPoint(0, 0), 0, pya.DPoint(50, 50), 90)
        with pytest.raises(InvalidGeometryError, match="hairpin"):
            curves.round_polyline(wp, 10.0, style="arc")

    def test_raises_when_bend_does_not_fit(self):
        wp = [pya.DPoint(0, 0), pya.DPoint(5, 0), pya.DPoint(5, 5)]
        with pytest.raises(InvalidGeometryError):
            curves.round_polyline(wp, 50.0, style="arc")

    def test_raises_when_two_corners_overlap_on_shared_segment(self):
        # A short middle segment where both adjacent corners' bends want
        # more of it than it has combined, even though each bend fits
        # individually against the segment's full length.
        wp = [pya.DPoint(0, 0), pya.DPoint(20, 0), pya.DPoint(20, 4), pya.DPoint(0, 4)]
        with pytest.raises(InvalidGeometryError):
            curves.round_polyline(wp, 10.0, style="arc")

    def test_unknown_style_raises(self):
        wp = [pya.DPoint(0, 0), pya.DPoint(50, 0), pya.DPoint(50, 50)]
        with pytest.raises(InvalidGeometryError):
            curves.round_polyline(wp, 10.0, style="bogus")
