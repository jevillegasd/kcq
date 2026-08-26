"""Path to Waveguide (hotkey 'W'). See doc/readme.html, "Interactive
layout tools" for the user-facing behavior. The drawn path's own width
is irrelevant and discarded -- Waveguide.produce_impl only reads
path.each_point().
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
    orientation) within max_distance, each pivoting about its own
    neighboring point (points[1] / points[-2]) -- see doc/readme.html,
    "Interactive layout tools" for the rule. A no-op for either end
    with no pin in range; the two ends exclude each other's claimed pin
    so a short path near one pin can't collapse to a near-zero-length
    stub. Requires at least 2 points."""
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
