"""Pin/port standard shared by PCells, the router, and (Phase 4) LVS.

A pin is a short pya.Path (midpoint = connection point, direction =
outward orientation angle, matching route_octilinear's port convention)
plus a co-located pya.Text naming it, both on the *same* physical
layer's reserved pin/label sublayer: datatype 4 of whichever layer
number the pin's terminal actually belongs to (e.g. (1, 4) for a metal
trace terminal, (2, 4) for a junction terminal). This is kcq's own
documented datatype convention (see doc/readme.html's "Layers and the
default technology" section) applied for real: 0=.drawing, 4=.pin/
.label, 5=.blockage, 10/20=.fill, the same meaning on every physical
layer, so a pin's layer number alone tells you which physical layer
it terminates -- and, via level_of(), which Level (contiguous block of
ten layer numbers: L1=0-9, L2=10-19, ...) it belongs to. Two pins on
different layer numbers within the same Level (e.g. a junction pin on
2/4 and a metal pin on 1/4) are electrically compatible; kcq's own
kcq.lyt <connectivity> stack unions exactly these layers for L1.
"""

import math
from dataclasses import dataclass

import pya

from kcq.utils.errors import KcqConfigError

PIN_DATATYPE = 4

_PIN_HALF_LENGTH = 0.5


@dataclass
class PinInfo:
    name: str
    position: pya.DPoint
    angle_deg: float
    width: float
    layer_num: int


def level_of(layer_num: int) -> int:
    """The physical Level a layer number belongs to: L1 is layers 0-9,
    L2 is 10-19, and so on -- level = layer_num // 10 + 1."""
    return layer_num // 10 + 1


def add_pin(cell: pya.Cell, layout: pya.Layout, name: str, point: pya.DPoint,
            angle_deg: float, width: float, layer_num: int) -> None:
    """Inserts a pin marker path (length 1, centered at point, oriented
    along angle_deg) and a co-located name label, both on
    (layer_num, PIN_DATATYPE), via cell.shapes(...)."""
    rad = math.radians(angle_deg)
    dx, dy = math.cos(rad) * _PIN_HALF_LENGTH, math.sin(rad) * _PIN_HALF_LENGTH
    path = pya.DPath([pya.DPoint(point.x - dx, point.y - dy),
                       pya.DPoint(point.x + dx, point.y + dy)], width)
    pin_li = layout.layer(layer_num, PIN_DATATYPE)
    cell.shapes(pin_li).insert(path)
    cell.shapes(pin_li).insert(pya.DText(name, point.x, point.y))


def get_pins(cell: pya.Cell, layout: pya.Layout, layer_num: int = None,
             tolerance: float = 1e-3) -> list:
    """Reads pin marker/label shapes back out into PinInfo objects.

    layer_num=None (the default) scans every layer already registered
    in `layout` whose datatype is PIN_DATATYPE, across every physical
    layer number, and aggregates pins from all of them -- callers that
    don't care which physical layer a pin belongs to (kcq.gui.snap,
    kcq.gui.instance_pins) can keep asking "every pin on this cell"
    without knowing the layer set up front. Passing layer_num restricts
    the read to that one physical layer's (layer_num, PIN_DATATYPE).

    Each marker path is matched to the label at the same point (within
    tolerance); raises KcqConfigError for an unnamed pin, since that
    means add_pin's two-shape convention was broken by hand-edited
    geometry."""
    if layer_num is not None:
        candidate_layers = [(layer_num, layout.layer(layer_num, PIN_DATATYPE))]
    else:
        candidate_layers = [
            (info.layer, li) for li, info in
            ((li, layout.get_info(li)) for li in layout.layer_indexes())
            if info.datatype == PIN_DATATYPE
        ]

    pins = []
    for found_layer_num, li in candidate_layers:
        texts = []
        for shape in cell.shapes(li).each():
            if shape.is_text():
                t = shape.dtext
                texts.append((pya.DPoint(t.x, t.y), t.string))

        for shape in cell.shapes(li).each():
            if not shape.is_path():
                continue
            points = list(shape.dpath.each_point())
            if len(points) != 2:
                continue
            p0, p1 = points
            mid = pya.DPoint((p0.x + p1.x) / 2.0, (p0.y + p1.y) / 2.0)
            angle_deg = math.degrees(math.atan2(p1.y - p0.y, p1.x - p0.x)) % 360.0

            name = None
            for text_pos, text_str in texts:
                if mid.distance(text_pos) <= tolerance:
                    name = text_str
                    break
            if name is None:
                raise KcqConfigError(
                    f"get_pins: pin path at {mid} on cell '{cell.name}' (layer "
                    f"{found_layer_num}/{PIN_DATATYPE}) has no matching name label "
                    f"within tolerance={tolerance}"
                )
            pins.append(PinInfo(name=name, position=mid, angle_deg=angle_deg,
                                 width=shape.dpath.width, layer_num=found_layer_num))

    return pins


def check_alignment(pin_a: PinInfo, pin_b: PinInfo, tolerance_deg: float = 0.1) -> bool:
    """True if pin_b's angle is pin_a's angle + 180 (within tolerance_deg)
    -- the heading convention route_octilinear requires for a direct
    connection between two ports. Does not check Level compatibility
    (see level_of()); that's a separate, not-yet-enforced concern."""
    required = (pin_a.angle_deg + 180.0) % 360.0
    diff = abs(pin_b.angle_deg - required) % 360.0
    diff = min(diff, 360.0 - diff)
    return diff <= tolerance_deg
