"""Waveguide PCell: a placeable CPW segment, built entirely from
kcq.geometry.cpw.CPW so its trace/gap widths and bend behavior stay
technology-driven rather than duplicated here.

This is a *core* PCell -- technology-agnostic (its own tech_name param
just picks which technology's waveguides.xml sizes it), shipped by the
kcq package itself (python/kcq/pcells/) rather than any one PDK's
tech/<name>/pcells/. It still needs to resolve as
layout.create_cell("Waveguide", tech_name, params) like any PDK-specific
PCell, so kcq.utils.pcell_loader's register_pcell_library() merges
every core PCell under this directory into each technology's own PCell
library.
"""

import math

import pya

from kcq.geometry import cpw, pins
from kcq.utils.errors import KcqConfigError
from kcq.utils.log import get_logger

_LOG = get_logger(__name__)


class Waveguide(pya.PCellDeclarationHelper):

    def __init__(self):
        super().__init__()
        self.param("path", self.TypeShape, "Path",
                   default=pya.DPath([pya.DPoint(0.0, 0.0), pya.DPoint(200.0, 0.0)], 1.0))
        self.param("cpw_name", self.TypeString,
                   "Waveguide flavor (waveguides.xml <cpw name=...>)", default="feedline")
        self.param("tech_name", self.TypeString,
                   "Technology whose waveguides.xml sizes this waveguide", default="kcq")

    def display_text_impl(self):
        return f"Waveguide({self.cpw_name})"

    def coerce_parameters_impl(self):
        self.cpw_name = str(self.cpw_name).strip() or "feedline"
        self.tech_name = str(self.tech_name).strip() or "kcq"

    def produce_impl(self):
        waypoints = list(self.path.each_point())
        if len(waypoints) < 2:
            raise KcqConfigError("Waveguide: path needs at least 2 points")

        waveguide = cpw.CPW(self.tech_name, self.cpw_name, waypoints)
        waveguide.build(self.cell, self.layout)

        centerline = waveguide.smoothed_centerline()
        width = waveguide.params["trace_width"] + 2.0 * waveguide.params["gap_width"]
        trace_layer, _ = cpw.parse_layer_spec(waveguide.params["layer"])
        self._add_end_pin("P1", centerline[0], centerline[1], width, trace_layer)
        self._add_end_pin("P2", centerline[-1], centerline[-2], width, trace_layer)

    def _add_end_pin(self, name, end_point, next_point, width, layer_num):
        angle_deg = math.degrees(math.atan2(end_point.y - next_point.y, end_point.x - next_point.x))
        pins.add_pin(self.cell, self.layout, name, end_point, angle_deg, width, layer_num)
