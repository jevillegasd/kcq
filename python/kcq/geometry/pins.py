"""Pin/port standard shared by PCells, the router, and (Phase 4) LVS.

A pin is a rectangle + a small triangle (apex at the connection point,
the GUI-snappable part) + a name label, all on (layer_num,
PIN_DATATYPE). Full marker design and the layer/Level datatype
convention behind PIN_DATATYPE: doc/readme.html, "Pins and ports" and
"Layers and the default technology".
"""

import math
from dataclasses import dataclass

import pya

from kcq.utils.errors import KcqConfigError

PIN_DATATYPE = 4

_PIN_MARKER_LENGTH = 1.0


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
            angle_deg: float, width: float, layer_num: int,
            core_width: float = None) -> None:
    """Inserts a pin marker (rectangle + triangle + name label, see
    module docstring) on (layer_num, PIN_DATATYPE). core_width narrows
    just the triangle, defaulting to `width`. Both shapes are floored
    at 4 database units wide to avoid a degenerate, zero-area polygon."""
    if core_width is None:
        core_width = width
    rad = math.radians(angle_deg)
    forward = (math.cos(rad), math.sin(rad))
    perp = (-math.sin(rad), math.cos(rad))
    pin_li = layout.layer(layer_num, PIN_DATATYPE)

    half_width = max(width, 4.0 * layout.dbu) / 2.0
    rectangle = pya.DPolygon([
        pya.DPoint(point.x - _PIN_MARKER_LENGTH * forward[0] + half_width * perp[0],
                   point.y - _PIN_MARKER_LENGTH * forward[1] + half_width * perp[1]),
        pya.DPoint(point.x + _PIN_MARKER_LENGTH * forward[0] + half_width * perp[0],
                   point.y + _PIN_MARKER_LENGTH * forward[1] + half_width * perp[1]),
        pya.DPoint(point.x + _PIN_MARKER_LENGTH * forward[0] - half_width * perp[0],
                   point.y + _PIN_MARKER_LENGTH * forward[1] - half_width * perp[1]),
        pya.DPoint(point.x - _PIN_MARKER_LENGTH * forward[0] - half_width * perp[0],
                   point.y - _PIN_MARKER_LENGTH * forward[1] - half_width * perp[1]),
    ])
    cell.shapes(pin_li).insert(rectangle)

    base_center = pya.DPoint(point.x - _PIN_MARKER_LENGTH * forward[0],
                              point.y - _PIN_MARKER_LENGTH * forward[1])
    half_core = max(core_width, 4.0 * layout.dbu) / 2.0
    base_left = pya.DPoint(base_center.x + half_core * perp[0],
                            base_center.y + half_core * perp[1])
    base_right = pya.DPoint(base_center.x - half_core * perp[0],
                             base_center.y - half_core * perp[1])
    triangle = pya.DPolygon([point, base_left, base_right])
    cell.shapes(pin_li).insert(triangle)

    cell.shapes(pin_li).insert(pya.DText(name, point.x, point.y))


def _apex_of(points: list) -> tuple:
    """Returns (apex, base_left, base_right) from a triangle's 3
    vertices (order not preserved by KLayout on round-trip). The apex
    is the vertex whose two edges are *closest* to equal length, not an
    exact match -- dbu quantization can shift a real triangle's "equal"
    legs by a few dbu."""
    best = min(
        range(3),
        key=lambda i: abs(points[i].distance(points[(i + 1) % 3])
                           - points[i].distance(points[(i + 2) % 3])),
    )
    others = [points[j] for j in range(3) if j != best]
    return points[best], others[0], others[1]


def get_pins(cell: pya.Cell, layout: pya.Layout, layer_num: int = None,
             tolerance: float = 1e-3) -> list:
    """Reads pin markers back into PinInfo objects. layer_num=None
    (default) scans every PIN_DATATYPE layer in the cell; pass
    layer_num to restrict to one physical layer. Raises KcqConfigError
    for a marker triangle with no matching name label."""
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
            if not shape.is_polygon():
                continue
            points = list(shape.dpolygon.each_point_hull())
            if len(points) != 3:
                continue
            apex, base_left, base_right = _apex_of(points)
            base_center = pya.DPoint((base_left.x + base_right.x) / 2.0,
                                      (base_left.y + base_right.y) / 2.0)
            angle_deg = math.degrees(math.atan2(apex.y - base_center.y,
                                                 apex.x - base_center.x)) % 360.0
            width = base_left.distance(base_right)

            name = None
            for text_pos, text_str in texts:
                if apex.distance(text_pos) <= tolerance:
                    name = text_str
                    break
            if name is None:
                raise KcqConfigError(
                    f"get_pins: pin marker at {apex} on cell '{cell.name}' (layer "
                    f"{found_layer_num}/{PIN_DATATYPE}) has no matching name label "
                    f"within tolerance={tolerance}"
                )
            pins.append(PinInfo(name=name, position=apex, angle_deg=angle_deg,
                                 width=width, layer_num=found_layer_num))

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
