"""Coplanar waveguide (CPW) synthesis.

Turns a waypoint list into trace metal, gap-keepout, and ground-clearance
Region geometry, sized entirely from the named cpw type's parameters in
the active technology's waveguides.xml (kcq.utils.xml_parser) -- no
trace width, gap width, clearance, or bend radius is ever a Python
literal here.
"""

import pya

from kcq.geometry import curves
from kcq.utils import xml_parser
from kcq.utils.errors import KcqConfigError
from kcq.utils.log import get_logger

_LOG = get_logger(__name__)


def parse_layer_spec(spec: str):
    """Parses a 'layer/datatype' string (e.g. "1/0", from waveguides.xml)
    into a (layer, datatype) int pair."""
    try:
        layer_str, datatype_str = spec.split("/")
        return int(layer_str), int(datatype_str)
    except (ValueError, AttributeError) as exc:
        raise KcqConfigError(
            f"invalid layer spec '{spec}', expected 'layer/datatype' (e.g. '1/0')"
        ) from exc


class CPW:
    """A coplanar waveguide routed along `waypoints`, synthesized entirely
    from cpw_name's parameters in tech_name's waveguides.xml.
    """

    def __init__(self, tech_name: str, cpw_name: str, waypoints):
        if len(waypoints) < 2:
            raise KcqConfigError("CPW requires at least 2 waypoints")
        self.tech_name = tech_name
        self.cpw_name = cpw_name
        self.waypoints = list(waypoints)
        self.params = xml_parser.get_cpw_params(tech_name, cpw_name)

    def smoothed_centerline(self):
        """The trace centerline as a dense point list, with bends applied
        per the technology's bend_radius_default/bend_style."""
        return curves.round_polyline(
            self.waypoints,
            self.params["bend_radius_default"],
            style=self.params["bend_style"],
        )

    def build(self, cell: pya.Cell, layout: pya.Layout) -> None:
        """Builds the trace metal Region, the gap keepout Region
        (width=trace_width + 2*gap_width), and the ground-clearance
        Region (width=trace_width + 2*(gap_width + ground_clearance),
        the "Ground Exclusion Area" a later ground-plane fill pass must
        avoid), and inserts all three via cell.shapes(layer_index).
        Regions that land on the same layer index (e.g. a technology
        that points clearance_layer at gap_layer) are merged together
        first, so the layer's total area isn't double-counted."""
        centerline = self.smoothed_centerline()

        trace_width = self.params["trace_width"]
        gap_width = self.params["gap_width"]
        ground_clearance = self.params["ground_clearance"]

        trace_region = self._path_region(centerline, trace_width, layout.dbu)
        keepout_region = self._path_region(centerline, trace_width + 2.0 * gap_width, layout.dbu)
        clearance_region = self._path_region(
            centerline, trace_width + 2.0 * (gap_width + ground_clearance), layout.dbu)

        trace_layer, trace_datatype = parse_layer_spec(self.params["layer"])
        gap_layer, gap_datatype = parse_layer_spec(self.params["gap_layer"])
        clearance_layer, clearance_datatype = parse_layer_spec(self.params["clearance_layer"])
        trace_li = layout.layer(trace_layer, trace_datatype)
        gap_li = layout.layer(gap_layer, gap_datatype)
        clearance_li = layout.layer(clearance_layer, clearance_datatype)

        regions_by_layer = {}
        for li, region in ((trace_li, trace_region), (gap_li, keepout_region),
                            (clearance_li, clearance_region)):
            regions_by_layer[li] = regions_by_layer[li] + region if li in regions_by_layer else region
        for li, region in regions_by_layer.items():
            region.merge()
            cell.shapes(li).insert(region)

        _LOG.info(
            "CPW '%s' (tech='%s'): %d waypoints, trace_width=%.3f, gap_width=%.3f, "
            "ground_clearance=%.3f",
            self.cpw_name, self.tech_name, len(self.waypoints), trace_width, gap_width,
            ground_clearance,
        )

    @staticmethod
    def _path_region(centerline, width: float, dbu: float) -> pya.Region:
        dpath = pya.DPath(centerline, width)
        region = pya.Region(dpath.to_itype(dbu))
        region.merge()
        return region
