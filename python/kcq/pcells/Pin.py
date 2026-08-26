"""Pin PCell: a placeable, parametric pin/port marker.

Wraps kcq.geometry.pins.add_pin as an interactively draggable PCell --
useful for defining connection points on hand-built geometry (e.g.
authoring a fixed_cells/*.json-equivalent pin sidecar interactively)
where no other PCell already provides one at that location.

The guiding shape is a 2-point path, matching a pin marker's own
on-layout representation: its midpoint is the pin's position and its direction is
the pin's outward-facing angle, so dragging either endpoint in the GUI
moves and/or rotates the pin exactly the way the resulting marker will
look.

Core, technology-agnostic (no waveguides.xml lookup at all) -- shipped
by the kcq package itself (python/kcq/pcells/) rather than any one
PDK's tech/<name>/pcells/, merged into every technology's PCell library
by kcq.utils.pcell_loader.register_pcell_library the same way Waveguide
is.
"""

import math

import pya

from kcq.geometry import pins
from kcq.utils.errors import KcqConfigError


class Pin(pya.PCellDeclarationHelper):

    def __init__(self):
        super().__init__()
        self.param("pin_shape", self.TypeShape,
                   "Pin position/orientation (drag the endpoints to move/rotate)",
                   default=pya.DPath([pya.DPoint(-0.5, 0.0), pya.DPoint(0.5, 0.0)], 1.0))
        self.param("pin_name", self.TypeString, "Pin name", default="P1")
        self.param("width", self.TypeDouble, "Pin width [um]", default=10.0)
        self.param("layer", self.TypeLayer, "Physical layer this pin belongs to",
                   default=pya.LayerInfo(1, 1))

    def display_text_impl(self):
        return f"Pin({self.pin_name})"

    def coerce_parameters_impl(self):
        self.pin_name = str(self.pin_name).strip() or "P1"
        self.width = max(0.0, float(self.width))

    def produce_impl(self):
        points = list(self.pin_shape.each_point())
        if len(points) != 2:
            raise KcqConfigError("Pin: pin_shape needs exactly 2 points")
        p0, p1 = points
        if p0.distance(p1) < 1e-9:
            raise KcqConfigError("Pin: pin_shape's two points must not coincide (orientation is undefined)")

        position = pya.DPoint((p0.x + p1.x) / 2.0, (p0.y + p1.y) / 2.0)
        angle_deg = math.degrees(math.atan2(p1.y - p0.y, p1.x - p0.x))
        pins.add_pin(self.cell, self.layout, self.pin_name, position, angle_deg, self.width,
                     self.layer.layer)
