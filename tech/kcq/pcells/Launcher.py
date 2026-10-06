"""Launcher PCell: wirebond transition from a routable CPW pin to a
wide bond pad, sized from the technology's waveguides.xml (matching
python/kcq/pcells/Waveguide.py's own pattern) rather than raw literals.
See doc/readme.html, "The component library" for the full param table.
"""

import pya

from kcq.geometry import cpw, pins
from kcq.utils import xml_parser
from kcq.utils.errors import KcqConfigError


class Launcher(pya.PCellDeclarationHelper):

    def __init__(self):
        super().__init__()
        self.set_parameters()

    def display_text_impl(self):
        return f"Launcher({self.cpw_name}, {self.total_length:.0f}x{self.pad_width:.0f}um)"

    def coerce_parameters_impl(self):
        self.cpw_name = str(self.cpw_name).strip() or "feedline"
        self.tech_name = str(self.tech_name).strip() or "kcq"
        self.pad_width = max(1.0, float(self.pad_width))
        self.total_length = max(1.0, float(self.total_length))
        self.pad_length = max(0.0, min(float(self.pad_length), self.total_length))
        self.pad_gap = max(0.0, float(self.pad_gap))

    def set_parameters(self):
        self.param("cpw_name", self.TypeString,
                   "Waveguide flavor (waveguides.xml <cpw name=...>)", default="feedline")
        self.param("tech_name", self.TypeString,
                   "Technology whose waveguides.xml sizes this launcher", default="kcq")
        self.param("pad_width", self.TypeDouble, "Bond pad width [um]", default=200.0)
        self.param("total_length", self.TypeDouble,
                   "Length from the waveguide port to the pad tip [um]", default=450.0)
        self.param("pad_length", self.TypeDouble,
                   "Flat section length at full pad width [um]", default=200.0)
        self.param("pad_gap", self.TypeDouble, "Gap width at the pad end [um]", default=100.0)
        self.param("add_probe_patch", self.TypeBoolean,
                   "Add a metal probe patch on the pad", default=True)
        self.param("probe_patch_layer", self.TypeLayer,
                   "Probe patch layer", default=pya.LayerInfo(3, 0))

    def produce_impl(self):
        params = xml_parser.get_cpw_params(self.tech_name, self.cpw_name)
        trace_width = params["trace_width"]
        gap_width = params["gap_width"]
        ground_clearance = params["ground_clearance"]
        trace_layer, trace_datatype = cpw.parse_layer_spec(params["layer"])
        gap_layer, gap_datatype = cpw.parse_layer_spec(params["gap_layer"])
        clearance_layer, clearance_datatype = cpw.parse_layer_spec(params["clearance_layer"])

        taper_length = self.total_length - self.pad_length

        core_region = self._tapered_region(trace_width, self.pad_width, taper_length)
        gap_envelope = self._tapered_region(
            trace_width + 2.0 * gap_width, self.pad_width + 2.0 * self.pad_gap, taper_length)
        clearance_region = self._tapered_region(
            trace_width + 2.0 * (gap_width + ground_clearance),
            self.pad_width + 2.0 * (self.pad_gap + ground_clearance), taper_length)
        gap_region = gap_envelope - core_region

        dbu = self.layout.dbu
        trace_li = self.layout.layer(trace_layer, trace_datatype)
        gap_li = self.layout.layer(gap_layer, gap_datatype)
        clearance_li = self.layout.layer(clearance_layer, clearance_datatype)
        self.cell.shapes(trace_li).insert(core_region)
        self.cell.shapes(gap_li).insert(gap_region)
        self.cell.shapes(clearance_li).insert(clearance_region)

        if self.add_probe_patch:
            patch_size = min(self.pad_width, self.pad_length) * 0.6
            patch_center_x = taper_length + self.pad_length / 2.0
            patch_box = pya.DBox(patch_center_x - patch_size / 2.0, -patch_size / 2.0,
                                  patch_center_x + patch_size / 2.0, patch_size / 2.0)
            probe_li = self.layout.layer(self.probe_patch_layer)
            self.cell.shapes(probe_li).insert(patch_box.to_itype(dbu))

        width_at_port = trace_width + 2.0 * gap_width
        pins.add_pin(self.cell, self.layout, "P1", pya.DPoint(0.0, 0.0), 180.0,
                     width_at_port, trace_layer, core_width=trace_width)

    def _tapered_region(self, width_at_origin: float, width_at_pad: float,
                         taper_length: float) -> pya.Region:
        """A hexagonal polygon: half-width `width_at_origin`/2 at x=0,
        tapering linearly to half-width `width_at_pad`/2 at x=taper_length,
        then flat out to x=total_length."""
        h0 = width_at_origin / 2.0
        h1 = width_at_pad / 2.0
        x_end = self.total_length
        points = [
            pya.DPoint(0.0, -h0),
            pya.DPoint(0.0, h0),
            pya.DPoint(taper_length, h1),
            pya.DPoint(x_end, h1),
            pya.DPoint(x_end, -h1),
            pya.DPoint(taper_length, -h1),
        ]
        region = pya.Region(pya.DPolygon(points).to_itype(self.layout.dbu))
        region.merge()
        return region
