"""Bend and S-bend point generators, and waypoint-to-smooth-polyline
composition.

Generators work in local coordinates: the curve starts at (0, 0) heading
+x (0 deg) and, for bends, ends heading angle_deg away (positive = CCW).
round_polyline() places these at each corner of a router.py waypoint
list to produce the final smoothed trace centerline.
"""

import math

import pya

from kcq.utils.errors import InvalidGeometryError

_EPS = 1e-9


def _integrate_heading_curve(curvature_fn, arc_length: float, num_pts: int):
    """Integrates curvature(s) over [0, arc_length] into a point list
    (cumulative trapezoidal integration of (cos(theta), sin(theta)))."""
    s_values = [arc_length * i / (num_pts - 1) for i in range(num_pts)]
    curvatures = [curvature_fn(s) for s in s_values]

    headings = [0.0]
    for i in range(1, num_pts):
        ds = s_values[i] - s_values[i - 1]
        headings.append(headings[-1] + 0.5 * (curvatures[i] + curvatures[i - 1]) * ds)

    points = [pya.DPoint(0.0, 0.0)]
    x, y = 0.0, 0.0
    for i in range(1, num_pts):
        ds = s_values[i] - s_values[i - 1]
        x += 0.5 * (math.cos(headings[i]) + math.cos(headings[i - 1])) * ds
        y += 0.5 * (math.sin(headings[i]) + math.sin(headings[i - 1])) * ds
        points.append(pya.DPoint(x, y))
    return points


def euler_bend_points(radius: float, angle_deg: float, num_pts: int = 100):
    """Clothoid (Euler spiral) bend: curvature ramps 0 -> 1/radius over the
    first half of the arc length, then back to 0. `radius` is the minimum
    radius of curvature, reached at the midpoint. angle_deg may be
    negative for a right (CW) turn."""
    if radius <= 0:
        raise InvalidGeometryError(f"euler_bend_points: radius must be > 0, got {radius}")
    if abs(angle_deg) < _EPS:
        return [pya.DPoint(0.0, 0.0)]

    sign = 1.0 if angle_deg > 0 else -1.0
    angle_rad = math.radians(abs(angle_deg))
    k_max = 1.0 / radius
    arc_length = 2.0 * angle_rad * radius  # k_max * L / 2 = angle_rad

    def curvature(s):
        half = arc_length / 2.0
        if s <= half:
            k = k_max * (s / half) if half > 0 else 0.0
        else:
            k = k_max * ((arc_length - s) / half) if half > 0 else 0.0
        return sign * k

    return _integrate_heading_curve(curvature, arc_length, num_pts)


def arc_bend_points(radius: float, angle_deg: float, num_pts: int = 100):
    """Constant-curvature circular arc bend (same local-frame convention
    as euler_bend_points)."""
    if radius <= 0:
        raise InvalidGeometryError(f"arc_bend_points: radius must be > 0, got {radius}")
    if abs(angle_deg) < _EPS:
        return [pya.DPoint(0.0, 0.0)]

    sign = 1.0 if angle_deg > 0 else -1.0
    angle_rad = math.radians(abs(angle_deg))
    arc_length = radius * angle_rad

    def curvature(_s):
        return sign / radius

    return _integrate_heading_curve(curvature, arc_length, num_pts)


def adiabatic_sine_sbend(length: float, offset: float, num_pts: int = 100):
    """Raised-cosine lateral S-bend: y(x) = offset/2 * (1 - cos(pi*x/length)).
    Zero slope at both ends, so it splices onto straight leads with no
    tangent discontinuity."""
    if length <= 0:
        raise InvalidGeometryError(f"adiabatic_sine_sbend: length must be > 0, got {length}")
    points = []
    for i in range(num_pts):
        x = length * i / (num_pts - 1)
        y = (offset / 2.0) * (1.0 - math.cos(math.pi * x / length))
        points.append(pya.DPoint(x, y))
    return points


_BEND_GENERATORS = {
    "euler": euler_bend_points,
    "arc": arc_bend_points,
}


def _bend_tangent_length(radius: float, angle_deg: float, style: str, num_pts: int) -> float:
    """Distance from a sharp corner to where the rounded bend actually
    starts/ends (symmetric on both sides). Found by intersecting the
    incoming forward ray with the outgoing backward ray, i.e. where the
    sharp corner would have been."""
    points = _BEND_GENERATORS[style](radius, angle_deg, num_pts)
    end = points[-1]
    angle_rad = math.radians(angle_deg)
    u_in = (1.0, 0.0)
    u_out = (math.cos(angle_rad), math.sin(angle_rad))

    denom = u_in[0] * u_out[1] - u_in[1] * u_out[0]
    if abs(denom) < _EPS:
        return 0.0
    # (0,0) + t*u_in = end + s*(-u_out)  =>  t*u_in + s*u_out = end
    t = (end.x * u_out[1] - end.y * u_out[0]) / denom
    return t


def _transform(points, origin: pya.DPoint, heading_deg: float):
    rad = math.radians(heading_deg)
    c, s = math.cos(rad), math.sin(rad)
    return [pya.DPoint(origin.x + p.x * c - p.y * s, origin.y + p.x * s + p.y * c) for p in points]


def round_polyline(waypoints, radius: float, style: str = "euler", num_pts_per_bend: int = 100):
    """Replaces each interior corner of `waypoints` (a router.py output)
    with a smooth bend ('euler' or 'arc'), returning the dense point list
    (list[pya.DPoint]) as the trace centerline.

    Raises InvalidGeometryError if a corner's bend doesn't fit within its
    adjacent straight segments, or the turn is a ~180 deg hairpin (not
    supported: the tangent lines are parallel, so there's no finite
    corner to inscribe a bend at).
    """
    if style not in _BEND_GENERATORS:
        raise InvalidGeometryError(f"round_polyline: unknown bend style '{style}'")
    if len(waypoints) < 2:
        raise InvalidGeometryError("round_polyline: need at least 2 waypoints")
    if len(waypoints) == 2 or radius <= 0:
        return list(waypoints)

    segment_headings = []
    for i in range(len(waypoints) - 1):
        vec = (waypoints[i + 1].x - waypoints[i].x, waypoints[i + 1].y - waypoints[i].y)
        segment_headings.append(math.degrees(math.atan2(vec[1], vec[0])))

    # corners[i] describes the corner at waypoints[i+1] (i.e. between
    # segment i and segment i+1): (turn_deg, tangent_len), or None if
    # collinear (no bend needed there).
    corners = [None] * (len(waypoints) - 2)
    for i in range(len(corners)):
        turn = ((segment_headings[i + 1] - segment_headings[i] + 180.0) % 360.0) - 180.0
        if abs(turn) < 1e-6:
            continue
        if abs(abs(turn) - 180.0) < 1.0:
            # Parallel tangent lines -- no finite corner to inscribe a bend at.
            raise InvalidGeometryError(
                f"round_polyline: corner at {waypoints[i + 1]} is a {turn:.1f} deg "
                f"hairpin turn, which is not supported (bend tangent lines are parallel)"
            )
        tangent_len = _bend_tangent_length(radius, turn, style, num_pts_per_bend)
        corners[i] = (turn, tangent_len)

    # Each segment's bend tangent lengths (start + end) must not exceed
    # its own length -- two corners sharing a short middle segment must
    # not overlap.
    for seg_idx in range(len(segment_headings)):
        start_len = corners[seg_idx - 1][1] if seg_idx - 1 >= 0 and corners[seg_idx - 1] else 0.0
        end_len = corners[seg_idx][1] if seg_idx < len(corners) and corners[seg_idx] else 0.0
        seg_len = waypoints[seg_idx].distance(waypoints[seg_idx + 1])
        if start_len + end_len > seg_len - _EPS:
            raise InvalidGeometryError(
                f"round_polyline: bend radius {radius} (style={style}) does not fit on "
                f"segment {waypoints[seg_idx]} -> {waypoints[seg_idx + 1]} "
                f"(needs {start_len + end_len:.4g}, have {seg_len:.4g})"
            )

    result = [waypoints[0]]
    for i, corner_info in enumerate(corners):
        corner_pt = waypoints[i + 1]
        if corner_info is None:
            continue
        turn, tangent_len = corner_info
        in_heading = segment_headings[i]
        in_vec = _dir_unit(in_heading)
        bend_start = pya.DPoint(corner_pt.x - tangent_len * in_vec[0],
                                 corner_pt.y - tangent_len * in_vec[1])
        local_bend = _BEND_GENERATORS[style](radius, turn, num_pts_per_bend)
        global_bend = _transform(local_bend, bend_start, in_heading)

        result.append(bend_start)
        result.extend(global_bend[1:])

    result.append(waypoints[-1])
    return _dedupe(result)


def _dir_unit(heading_deg: float):
    rad = math.radians(heading_deg)
    return (math.cos(rad), math.sin(rad))


def _dedupe(points, tolerance=1e-9):
    result = [points[0]]
    for pt in points[1:]:
        if pt.distance(result[-1]) > tolerance:
            result.append(pt)
    return result
