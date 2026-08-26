"""Shared helper: a placed instance's pins in its parent cell's
coordinate frame, reused by kcq.gui.snap and kcq.gui.waveguide_chain."""

import pya

from kcq.geometry import pins


def global_pins(layout: pya.Layout, inst: pya.Instance) -> list:
    """inst's own pins (kcq.geometry.pins.get_pins), transformed from the
    instance's cell-local frame into its parent cell's coordinate system
    via the instance's own placement transform -- same transform idiom as
    tests/test_pdk_integration.py's _global_pin."""
    trans = inst.dcplx_trans
    result = []
    for pin in pins.get_pins(inst.cell, layout):
        result.append(pins.PinInfo(
            name=pin.name,
            position=trans * pin.position,
            angle_deg=(pin.angle_deg + trans.angle) % 360.0,
            width=pin.width,
            layer_num=pin.layer_num,
        ))
    return result


_EXCLUDE_POSITION_TOLERANCE_UM = 1e-6


def find_nearest_pin(layout: pya.Layout, parent_cell: pya.Cell, position: pya.DPoint,
                      max_distance: float, exclude_position: pya.DPoint = None):
    """The closest pin to `position` among parent_cell's direct child
    instances, within max_distance -- not orientation-filtered (unlike
    kcq.gui.snap.find_snap_delta); a caller that cares applies
    check_alignment separately. exclude_position, if given, skips any
    pin at that exact position (lets a two-end snap avoid re-claiming
    the first end's pin). Returns a PinInfo, or None."""
    best = None
    best_distance = None
    for inst in parent_cell.each_inst():
        for pin in global_pins(layout, inst):
            if (exclude_position is not None
                    and pin.position.distance(exclude_position) <= _EXCLUDE_POSITION_TOLERANCE_UM):
                continue
            distance = position.distance(pin.position)
            if distance > max_distance:
                continue
            if best is None or distance < best_distance:
                best, best_distance = pin, distance
    return best
