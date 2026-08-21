"""Octilinear (Manhattan + diagonal) waypoint routing between two ports.

A port is a position + an outward-facing orientation angle in degrees
(KLayout convention: 0 = +x, counter-clockwise positive). No obstacle
avoidance in v1.
"""

import math

import pya

from kcq.utils.errors import InvalidGeometryError
from kcq.utils.log import get_logger

_LOG = get_logger(__name__)

ALLOWED_DIRECTIONS_DEG = (0, 45, 90, 135, 180, 225, 270, 315)
_MANHATTAN_DIRECTIONS_DEG = (0, 90, 180, 270)

_EPS = 1e-9

# Minimum length for the departure/arrival segments at each port; must
# stay well above _DEDUPE_TOLERANCE so it isn't erased as a duplicate
# point. A near-zero segment here would collapse the route onto the
# wrong heading at that port.
_MIN_STANDOFF = 1e-3

_DEDUPE_TOLERANCE = 1e-9


def _norm_deg(angle_deg: float) -> float:
    return angle_deg % 360.0


def snap_to_allowed(angle_deg: float, allowed_directions_deg=ALLOWED_DIRECTIONS_DEG) -> float:
    """Returns the entry of allowed_directions_deg closest to angle_deg."""
    a = _norm_deg(angle_deg)

    def angular_distance(d):
        diff = abs(_norm_deg(d) - a)
        return min(diff, 360.0 - diff)

    return min(allowed_directions_deg, key=angular_distance)


def _dir_vector(angle_deg: float):
    rad = math.radians(angle_deg)
    return (math.cos(rad), math.sin(rad))


def _cross(u, v):
    return u[0] * v[1] - u[1] * v[0]


def _dot(u, v):
    return u[0] * v[0] + u[1] * v[1]


def _rotate(u, angle_deg):
    rad = math.radians(angle_deg)
    c, s = math.cos(rad), math.sin(rad)
    return (u[0] * c - u[1] * s, u[0] * s + u[1] * c)


def _l_route(p1: pya.DPoint, u1, p2: pya.DPoint, u2, min_standoff: float):
    """Single-corner solve: intersect the forward ray from p1 along u1
    with the forward ray from p2 along u2. None if parallel or if either
    side is shorter than min_standoff (a straight-line connection is
    parallel by construction, so it's handled by _bridge_route instead)."""
    denom = _cross(u1, u2)
    if abs(denom) < _EPS:
        return None

    dx, dy = p2.x - p1.x, p2.y - p1.y
    # p1 + t*u1 = p2 + s*u2  =>  t*u1 - s*u2 = (p2-p1)
    t = (dx * u2[1] - dy * u2[0]) / denom
    s = (dx * u1[1] - dy * u1[0]) / denom

    if t < min_standoff or s < min_standoff:
        return None
    return pya.DPoint(p1.x + t * u1[0], p1.y + t * u1[1])


def _bridge_route(p1: pya.DPoint, u1, p2: pya.DPoint, u2, min_standoff: float):
    """Two- or three-corner solve (Z- or U-shape) via a bridging segment
    perpendicular to u1, for cases _l_route can't handle. Returns the
    shortest feasible corner list (2 or 3 points), or None.

    Solves p1 + d1_eff*u1 + d_mid*u_mid = p2 + d2*u2 for the smallest
    d2 >= min_standoff with d_mid >= 0. If the resulting d1_eff (net
    displacement along u1) is >= min_standoff, that's a Z-route (2
    corners); otherwise u1 must be over-shot and backtracked, giving a
    U-route (3 corners) -- needed when p2 sits "behind" p1 along u1.
    """
    dx, dy = p2.x - p1.x, p2.y - p1.y

    best = None
    for sign in (1.0, -1.0):
        u_mid = _rotate(u1, 90.0 * sign)
        delta_par = dx * u1[0] + dy * u1[1]
        delta_perp = dx * u_mid[0] + dy * u_mid[1]
        a = _dot(u2, u1)
        b = _dot(u2, u_mid)

        # d_mid = delta_perp + b*d2 >= 0 ; d2 >= min_standoff
        lower = min_standoff
        upper = math.inf
        feasible = True
        if b > _EPS:
            lower = max(lower, -delta_perp / b)
        elif b < -_EPS:
            upper = min(upper, -delta_perp / b)
        else:
            feasible = delta_perp >= -_EPS
        if not feasible or lower > upper + _EPS:
            continue

        d2 = lower
        d1_eff = delta_par + a * d2
        d_mid = delta_perp + b * d2
        if d_mid < -_EPS or d2 < min_standoff - _EPS:
            continue

        if d1_eff >= min_standoff:
            corner1 = pya.DPoint(p1.x + d1_eff * u1[0], p1.y + d1_eff * u1[1])
            corner2 = pya.DPoint(corner1.x + d_mid * u_mid[0], corner1.y + d_mid * u_mid[1])
            corners = [corner1, corner2]
            total_length = d1_eff + d_mid + d2
        else:
            d1 = min_standoff
            d_back = d1 - d1_eff  # > 0, since d1_eff < min_standoff == d1
            corner1 = pya.DPoint(p1.x + d1 * u1[0], p1.y + d1 * u1[1])
            corner2 = pya.DPoint(corner1.x + d_mid * u_mid[0], corner1.y + d_mid * u_mid[1])
            corner3 = pya.DPoint(corner2.x - d_back * u1[0], corner2.y - d_back * u1[1])
            corners = [corner1, corner2, corner3]
            total_length = d1 + d_mid + d_back + d2

        if best is None or total_length < best[0]:
            best = (total_length, corners)

    if best is None:
        return None
    return best[1]


def _drop_degenerate(points, tolerance=_DEDUPE_TOLERANCE):
    """Removes consecutive duplicate/near-duplicate points."""
    result = [points[0]]
    for pt in points[1:]:
        if pt.distance(result[-1]) > tolerance:
            result.append(pt)
    return result


def _collapse_collinear(points, angle_tolerance_deg=1e-6):
    """Drops interior waypoints whose incoming/outgoing headings agree,
    e.g. a near-zero bridging offset left by _bridge_route."""
    if len(points) < 3:
        return list(points)
    result = [points[0]]
    for i in range(1, len(points) - 1):
        in_heading = _heading_deg(result[-1], points[i])
        out_heading = _heading_deg(points[i], points[i + 1])
        turn = ((out_heading - in_heading + 180.0) % 360.0) - 180.0
        if abs(turn) < angle_tolerance_deg:
            continue
        result.append(points[i])
    result.append(points[-1])
    return result


def _heading_deg(p_from: pya.DPoint, p_to: pya.DPoint) -> float:
    return math.degrees(math.atan2(p_to.y - p_from.y, p_to.x - p_from.x))


def route_octilinear(p1: pya.DPoint, a1: float, p2: pya.DPoint, a2: float,
                      bend_radius: float = 0.0,
                      allowed_directions_deg=ALLOWED_DIRECTIONS_DEG):
    """Returns a waypoint list (list[pya.DPoint]) connecting port (p1, a1)
    to port (p2, a2), using only headings in allowed_directions_deg.

    The route leaves p1 heading a1 and arrives at p2 heading (a2 + 180).

    bend_radius, if > 0, is a floor on the straight-run length at each
    port/corner, reserving room for kcq.geometry.curves.round_polyline
    to inscribe a bend -- not an exact guarantee (that depends on style
    and turn angle too), so callers should still handle round_polyline
    raising InvalidGeometryError.
    """
    min_standoff = bend_radius if bend_radius > 0 else _MIN_STANDOFF
    if p1.distance(p2) < min_standoff:
        raise InvalidGeometryError(
            f"route_octilinear: p1={p1} and p2={p2} are closer than min_standoff={min_standoff}"
        )

    a1_snapped = snap_to_allowed(a1, allowed_directions_deg)
    a2_snapped = snap_to_allowed(a2, allowed_directions_deg)
    u1 = _dir_vector(a1_snapped)
    u2 = _dir_vector(a2_snapped)  # backward ray from p2, see _l_route/_bridge_route

    corner = _l_route(p1, u1, p2, u2, min_standoff)
    if corner is not None:
        waypoints = [p1, corner, p2]
    else:
        corners = _bridge_route(p1, u1, p2, u2, min_standoff)
        if corners is None:
            raise InvalidGeometryError(
                f"route_octilinear: no feasible route between p1={p1}, a1={a1} "
                f"and p2={p2}, a2={a2} using directions {allowed_directions_deg}"
            )
        waypoints = [p1, *corners, p2]

    waypoints = _drop_degenerate(waypoints)
    waypoints = _collapse_collinear(waypoints)
    if len(waypoints) < 2:
        raise InvalidGeometryError(
            f"route_octilinear: degenerate route between p1={p1} and p2={p2} (same point?)"
        )
    return waypoints


def route_manhattan(p1: pya.DPoint, a1: float, p2: pya.DPoint, a2: float,
                     bend_radius: float = 0.0):
    """route_octilinear restricted to axis-aligned headings (0/90/180/270)."""
    return route_octilinear(p1, a1, p2, a2, bend_radius, _MANHATTAN_DIRECTIONS_DEG)
