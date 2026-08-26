"""Extend Waveguide Length (hotkey 'Alt+L'). See doc/readme.html,
"Interactive layout tools" for the user-facing behavior. Only the
free-end case is implemented -- KLayout's scripting API exposes which
whole shape/instance is selected, not which point or edge of a guiding
shape, so detecting "an edge was selected" for an interior stretch
isn't possible here.
"""

import math

import pya

from kcq.gui import waveguide_chain
from kcq.utils.errors import InvalidGeometryError, KcqError
from kcq.utils.log import get_logger

_LOG = get_logger(__name__)


def _move_endpoint(end_point: pya.DPoint, next_point: pya.DPoint, delta: float) -> pya.DPoint:
    heading = math.atan2(end_point.y - next_point.y, end_point.x - next_point.x)
    new_length = end_point.distance(next_point) + delta
    if new_length <= 0.0:
        raise InvalidGeometryError(
            f"compute_node_extend: shrinking by {-delta:.4g} would collapse the segment "
            f"at {end_point} to zero or negative length"
        )
    return pya.DPoint(next_point.x + new_length * math.cos(heading),
                       next_point.y + new_length * math.sin(heading))


def compute_node_extend(points, extend_p1: bool, extend_p2: bool, delta: float):
    """Returns a new point list with the free end(s) moved outward along
    the heading of their own last segment, so the path's length grows by
    exactly `delta` in total (split evenly across both ends if both are
    free). No interior point is touched, so an existing bend elsewhere
    on the path is unaffected.

    Raises InvalidGeometryError if neither end is free, or if `delta`
    would shrink an end's last segment to zero or below.
    """
    if not extend_p1 and not extend_p2:
        raise InvalidGeometryError(
            "compute_node_extend: neither end is free -- both already connect to a neighbor"
        )
    if len(points) < 2:
        raise InvalidGeometryError("compute_node_extend: path needs at least 2 points")

    new_points = list(points)
    share = delta / 2.0 if (extend_p1 and extend_p2) else delta

    if extend_p1:
        new_points[0] = _move_endpoint(new_points[0], new_points[1], share)
    if extend_p2:
        new_points[-1] = _move_endpoint(new_points[-1], new_points[-2], share)
    return new_points


def extend_instance(parent_cell: pya.Cell, layout: pya.Layout, inst: pya.Instance,
                     target_total_length: float) -> float:
    """Extends inst's free end(s) so the whole connected chain it
    belongs to (kcq.gui.waveguide_chain.walk_chain) totals
    target_total_length. Returns the new own (this instance's) length.
    """
    chain = waveguide_chain.walk_chain(parent_cell, layout, inst)
    if not chain.p1_free and not chain.p2_free:
        raise InvalidGeometryError(
            "extend_instance: both ends of this waveguide already connect to a neighbor -- "
            "interior-segment stretching isn't supported yet; extend a segment with a free "
            "end instead"
        )

    chain_length_excluding_self = chain.p1_chain_length + chain.p2_chain_length
    target_own_length = target_total_length - chain_length_excluding_self
    if target_own_length <= 0.0:
        raise InvalidGeometryError(
            f"extend_instance: target_total_length={target_total_length:.4g} isn't reachable -- "
            f"the rest of the connected chain alone is already {chain_length_excluding_self:.4g}"
        )

    delta = target_own_length - chain.own_length
    params = inst.pcell_parameters_by_name()
    original_path = params["path"]
    new_points = compute_node_extend(list(original_path.each_point()), chain.p1_free, chain.p2_free, delta)

    try:
        inst.change_pcell_parameter("path", pya.DPath(new_points, original_path.width))
    except KcqError:
        raise
    except Exception as exc:
        raise InvalidGeometryError(f"extend_instance: PCell rebuild failed: {exc}") from exc

    new_length = waveguide_chain.core_length(inst, layout)
    _LOG.info("extend_instance: '%s' own length %.4g -> %.4g (target total %.4g)",
              inst.cell.name, chain.own_length, new_length, target_total_length)
    return new_length
