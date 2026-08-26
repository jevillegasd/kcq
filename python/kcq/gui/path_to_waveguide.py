"""Path to Waveguide (hotkey 'W'): converts a raw, hand-drawn pya.Path
shape into a kcq.pcells.Waveguide PCell instance sized by a chosen
waveguides.xml cpw flavor. The drawn path's own width is irrelevant and
discarded -- Waveguide.produce_impl only reads path.each_point().

Before building, both end nodes are snapped onto the nearest pin in
parent_cell (if one is within range) via snap_path_endpoints -- see its
docstring for the exact rule.
"""

import math

import pya

from kcq.gui import instance_pins, snap
from kcq.utils.errors import KcqConfigError

_MIN_STANDOFF_UM = 1e-3


def _project_endpoint(anchor: pya.DPoint, required_heading_deg: float, target: pya.DPoint) -> pya.DPoint:
    """The point along the ray from `anchor` heading required_heading_deg
    that lies closest to `target` (i.e. target projected onto that ray),
    clamped to at least _MIN_STANDOFF_UM from `anchor` so the segment
    never collapses to zero/negative length."""
    rad = math.radians(required_heading_deg)
    ux, uy = math.cos(rad), math.sin(rad)
    length = max((target.x - anchor.x) * ux + (target.y - anchor.y) * uy, _MIN_STANDOFF_UM)
    return pya.DPoint(anchor.x + length * ux, anchor.y + length * uy)


def snap_path_endpoints(layout: pya.Layout, parent_cell: pya.Cell, points,
                         max_distance: float = snap.MAX_SNAP_DISTANCE_UM):
    """Snaps points[0] and points[-1] onto the nearest pin (any
    orientation, unlike kcq.gui.snap's own instance-to-instance snap)
    within max_distance among parent_cell's placed instances, treated
    independently per end.

    The connecting segment's heading is set to face the pin correctly
    (required_heading = pin.angle_deg + 180), pivoting about that end's
    own neighboring point (points[1] / points[-2], which stays fixed):
    if the pin's own angle already matched the path's existing heading
    there, this leaves the segment close to unchanged (just sliding the
    endpoint along that same heading to meet the pin); if it differs,
    the segment is swung to face the pin instead. The endpoint lands as
    close to the pin as that fixed-pivot, fixed-heading ray allows --
    generally *not* exactly on the pin unless it happens to already lie
    on that ray (a full re-route, which would hit it exactly by
    inserting a bend, is deliberately not used here).

    A no-op for either end with no pin within max_distance. The end
    snaps are also mutually exclusive of each other's pin: whichever
    pin the start end claims (if any) is excluded from the end's own
    search, so a short path near a single pin can't have both ends snap
    onto that same physical pin and collapse to a near-zero-length stub.

    Requires at least 2 points (so each end has a distinct neighboring
    point to pivot from) -- for a 2-point path, snapping both ends uses
    the other end's already-snapped position as its pivot (points[1]
    for the start is the same list slot as points[-2] for the end).
    """
    if len(points) < 2:
        raise KcqConfigError("snap_path_endpoints: path needs at least 2 points")
    new_points = list(points)

    start_pin = instance_pins.find_nearest_pin(layout, parent_cell, new_points[0], max_distance)
    if start_pin is not None:
        required_heading = (start_pin.angle_deg + 180.0) % 360.0
        new_points[0] = _project_endpoint(new_points[1], required_heading, start_pin.position)

    end_pin = instance_pins.find_nearest_pin(
        layout, parent_cell, new_points[-1], max_distance,
        exclude_position=start_pin.position if start_pin is not None else None)
    if end_pin is not None:
        required_heading = (end_pin.angle_deg + 180.0) % 360.0
        new_points[-1] = _project_endpoint(new_points[-2], required_heading, end_pin.position)

    return new_points


def convert_path(parent_cell: pya.Cell, layout: pya.Layout, dpath: pya.DPath,
                  cpw_name: str, tech_name: str = "kcq",
                  max_snap_distance: float = snap.MAX_SNAP_DISTANCE_UM) -> pya.Instance:
    """Snaps dpath's end nodes (snap_path_endpoints) then builds a
    Waveguide PCell along the resulting centerline and inserts it into
    parent_cell at identity placement -- dpath's points are already
    expressed in parent_cell's coordinate system, since they come from a
    shape selected directly in that cell."""
    points = list(dpath.each_point())
    if len(points) < 2:
        raise KcqConfigError("convert_path: path needs at least 2 points")

    snapped_points = snap_path_endpoints(layout, parent_cell, points, max_snap_distance)

    new_cell = layout.create_cell("Waveguide", tech_name, {
        "path": pya.DPath(snapped_points, dpath.width),
        "cpw_name": cpw_name,
        "tech_name": tech_name,
    })
    if new_cell is None:
        raise KcqConfigError(
            f"convert_path: layout.create_cell('Waveguide', '{tech_name}', ...) returned None -- "
            f"is the '{tech_name}' PCell library registered "
            f"(kcq.utils.pcell_loader.register_library)?"
        )
    return parent_cell.insert(pya.CellInstArray(new_cell.cell_index(), pya.Trans()))
