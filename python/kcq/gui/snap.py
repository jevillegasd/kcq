"""Snap-to-pin for a selected component instance (hotkey 'S'). See
doc/readme.html, "Interactive layout tools" for the user-facing
behavior.
"""

import pya

from kcq.geometry import pins
from kcq.gui.instance_pins import global_pins

# A GUI search radius, not a fabrication parameter -- unlike CPW trace/gap
# widths (always read from waveguides.xml), this is UX tuning, so a plain
# literal here doesn't violate the "layout-driven, not hardcoded" rule.
MAX_SNAP_DISTANCE_UM = 500.0


def find_snap_delta(layout: pya.Layout, selected_inst: pya.Instance, sibling_insts,
                     max_distance: float = MAX_SNAP_DISTANCE_UM):
    """Returns the pya.DVector translation that snaps selected_inst's
    closest matching pin onto the nearest opposite-oriented pin among
    sibling_insts' own pins, or None if no candidate is within
    max_distance. sibling_insts must not include selected_inst itself.
    """
    own_pins = global_pins(layout, selected_inst)
    if not own_pins:
        return None

    best = None
    for sibling in sibling_insts:
        for target_pin in global_pins(layout, sibling):
            for own_pin in own_pins:
                if not pins.check_alignment(own_pin, target_pin):
                    continue
                distance = own_pin.position.distance(target_pin.position)
                if distance > max_distance:
                    continue
                if best is None or distance < best[0]:
                    best = (distance, own_pin, target_pin)

    if best is None:
        return None
    _distance, own_pin, target_pin = best
    return target_pin.position - own_pin.position
