"""Pin/port standard shared by PCells, the router, and (Phase 4) LVS.

A pin is a short pya.Path on the PinRec layer (midpoint = connection
point, direction = outward orientation angle, matching route_octilinear's
port convention) with a co-located pya.Text on PinRecText naming it.

PinRec/PinRecText are fixed kcq package-level bookkeeping layers (110/1,
110/2 -- the "kcq" group, alongside MetaRef at 110/3), not a
per-technology fab layer -- unlike CPW metal/gap layers (which vary per
technology and live in waveguides.xml), every kcq technology uses the
same layers for this.
"""

import math
from dataclasses import dataclass

import pya

from kcq.utils.errors import KcqConfigError

PIN_REC_LAYER = (110, 1)
PIN_REC_TEXT_LAYER = (110, 2)

_PIN_HALF_LENGTH = 0.5


@dataclass
class PinInfo:
    name: str
    position: pya.DPoint
    angle_deg: float
    width: float


def add_pin(cell: pya.Cell, layout: pya.Layout, name: str, point: pya.DPoint,
            angle_deg: float, width: float) -> None:
    """Inserts a PinRec marker path (length 1, centered at point, oriented
    along angle_deg) and a co-located PinRecText label, via cell.shapes(...)."""
    rad = math.radians(angle_deg)
    dx, dy = math.cos(rad) * _PIN_HALF_LENGTH, math.sin(rad) * _PIN_HALF_LENGTH
    path = pya.DPath([pya.DPoint(point.x - dx, point.y - dy),
                       pya.DPoint(point.x + dx, point.y + dy)], width)
    pin_rec_li = layout.layer(*PIN_REC_LAYER)
    pin_rec_text_li = layout.layer(*PIN_REC_TEXT_LAYER)
    cell.shapes(pin_rec_li).insert(path)
    cell.shapes(pin_rec_text_li).insert(pya.DText(name, point.x, point.y))


def get_pins(cell: pya.Cell, layout: pya.Layout, tolerance: float = 1e-3) -> list:
    """Reads PinRec/PinRecText shapes back out into PinInfo objects. Each
    PinRec path is matched to the PinRecText label at the same point
    (within tolerance); raises KcqConfigError for an unnamed pin, since
    that means add_pin's two-shape convention was broken by hand-edited
    geometry."""
    pin_rec_li = layout.layer(*PIN_REC_LAYER)
    pin_rec_text_li = layout.layer(*PIN_REC_TEXT_LAYER)

    texts = []
    for shape in cell.shapes(pin_rec_text_li).each():
        if shape.is_text():
            t = shape.dtext
            texts.append((pya.DPoint(t.x, t.y), t.string))

    pins = []
    for shape in cell.shapes(pin_rec_li).each():
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
                f"get_pins: PinRec path at {mid} on cell '{cell.name}' has no matching "
                f"PinRecText label within tolerance={tolerance}"
            )
        pins.append(PinInfo(name=name, position=mid, angle_deg=angle_deg, width=shape.dpath.width))

    return pins


def check_alignment(pin_a: PinInfo, pin_b: PinInfo, tolerance_deg: float = 0.1) -> bool:
    """True if pin_b's angle is pin_a's angle + 180 (within tolerance_deg)
    -- the heading convention route_octilinear requires for a direct
    connection between two ports."""
    required = (pin_a.angle_deg + 180.0) % 360.0
    diff = abs(pin_b.angle_deg - required) % 360.0
    diff = min(diff, 360.0 - diff)
    return diff <= tolerance_deg
