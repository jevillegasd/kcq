"""Frame PCell: assembles Launcher instances around a die's 4 edges
(one shared position list, replicated per edge by rotation so every
pin faces inward), plus the DCS/Design Area/DRC Exception/Ground
Exclusion bookkeeping geometry and corner AlignmentMarks. Reuses kcq's
existing bookkeeping layers throughout -- no new layer numbers. See
doc/readme.html, "The component library" for the full param table.
"""

import pya

from kcq.utils import xml_parser
from kcq.utils.errors import KcqConfigError


def _default_cpw_names():
    try:
        cpws = xml_parser.load_technology("kcq")["cpws"]
        return [next(iter(cpws))]
    except Exception:
        return ["feedline"]


class Frame(pya.PCellDeclarationHelper):

    def __init__(self):
        super().__init__()
        self.set_parameters()

    def display_text_impl(self):
        n = len(self.launcher_positions) if self.launcher_positions else 0
        return f"Frame({self.die_width:.0f}x{self.die_height:.0f}um, {4 * n} launchers)"

    def coerce_parameters_impl(self):
        self.die_width = max(1.0, float(self.die_width))
        self.die_height = max(1.0, float(self.die_height))
        self.launcher_positions = ([float(v) for v in self.launcher_positions]
                                    if self.launcher_positions else [])
        self.launcher_indent = max(1.0, float(self.launcher_indent))
        self.corner_mark_inset = max(0.0, float(self.corner_mark_inset))
        self.tech_name = str(self.tech_name).strip() or "kcq"
        self.alignment_mark_layers = ([int(v) for v in self.alignment_mark_layers]
                                       if self.alignment_mark_layers else [1])
        self.cpw_name = [str(v) for v in self.cpw_name] if self.cpw_name else _default_cpw_names()

    def set_parameters(self):
        self.param("die_width", self.TypeDouble, "Die width (DCS) [um]", default=5000.0)
        self.param("die_height", self.TypeDouble, "Die height (DCS) [um]", default=5000.0)
        self.param("launcher_positions", self.TypeList,
                   "Distance from each edge's start corner, one shared list per edge [um]",
                   default=[1000.0, 2000.0, 3000.0, 4000.0])
        self.param("launcher_indent", self.TypeDouble,
                   "Inset from the DCS edge to a launcher's pin -- also defines the Design "
                   "Area boundary [um]", default=800.0)
        self.param("tech_name", self.TypeString,
                   "Technology whose waveguides.xml sizes the launchers", default="kcq")
        self.param("cpw_name", self.TypeList,
                   "Waveguide flavor(s) for the launchers: one shared, or one per "
                   "launcher_positions entry", default=_default_cpw_names())
        self.param("corner_mark_inset", self.TypeDouble,
                   "Inset from each DCS corner to its AlignmentMarks instance [um]", default=400.0)
        self.param("alignment_mark_layers", self.TypeList,
                   "Physical layers stamped by each corner's AlignmentMarks", default=[1, 2])
        self.param("chip_label", self.TypeString, "Text label near the SW corner", default="")

        self.param("dcs_layer", self.TypeLayer, "DCS (die size) layer",
                   default=pya.LayerInfo(100, 1), hidden=True)
        self.param("design_area_layer", self.TypeLayer, "Design Area layer",
                   default=pya.LayerInfo(100, 4), hidden=True)
        self.param("drc_exception_layer", self.TypeLayer, "DRC Exception layer",
                   default=pya.LayerInfo(111, 1), hidden=True)
        self.param("text_layer", self.TypeLayer, "Chip label layer",
                   default=pya.LayerInfo(103, 1), hidden=True)
        self.param("ground_exclude_layer", self.TypeLayer, "Ground exclusion layer",
                   default=pya.LayerInfo(1, 5), hidden=True)

    def produce_impl(self):
        n = len(self.launcher_positions)
        cpw_names = self._resolve_cpw_names(n)

        self._produce_boundary_layers()
        for edge in range(4):
            for i, d in enumerate(self.launcher_positions):
                self._place_launcher(edge, d, cpw_names[i])
        for corner in range(4):
            self._place_corner_mark(corner)
        self._place_label()

    def _resolve_cpw_names(self, n: int) -> list:
        if len(self.cpw_name) == 1:
            return list(self.cpw_name) * max(n, 1)
        if len(self.cpw_name) == n:
            return list(self.cpw_name)
        raise KcqConfigError(
            f"Frame: cpw_name must have 1 entry (shared) or {n} entries "
            f"(one per launcher_positions), got {len(self.cpw_name)}"
        )

    def _produce_boundary_layers(self):
        dbu = self.layout.dbu
        dcs_box = pya.DBox(0.0, 0.0, self.die_width, self.die_height)
        design_box = pya.DBox(self.launcher_indent, self.launcher_indent,
                               self.die_width - self.launcher_indent,
                               self.die_height - self.launcher_indent)

        dcs_li = self.layout.layer(self.dcs_layer)
        design_li = self.layout.layer(self.design_area_layer)
        drc_li = self.layout.layer(self.drc_exception_layer)
        exclude_li = self.layout.layer(self.ground_exclude_layer)

        self.cell.shapes(dcs_li).insert(dcs_box.to_itype(dbu))
        self.cell.shapes(design_li).insert(design_box.to_itype(dbu))

        ring = pya.Region(dcs_box.to_itype(dbu)) - pya.Region(design_box.to_itype(dbu))
        self.cell.shapes(drc_li).insert(ring)
        self.cell.shapes(exclude_li).insert(ring)

    def _edge_transform(self, edge: int, d: float) -> pya.DCplxTrans:
        """edge: 0=South, 1=East, 2=North, 3=West, walking the DCS boundary
        counter-clockwise from the origin. Rotation is chosen so the
        placed Launcher's pin (locally 180 deg) always faces inward."""
        indent = self.launcher_indent
        if edge == 0:
            return pya.DCplxTrans(1.0, 270.0, False, pya.DVector(d, indent))
        if edge == 1:
            return pya.DCplxTrans(1.0, 0.0, False, pya.DVector(self.die_width - indent, d))
        if edge == 2:
            return pya.DCplxTrans(1.0, 90.0, False,
                                   pya.DVector(self.die_width - d, self.die_height - indent))
        return pya.DCplxTrans(1.0, 180.0, False, pya.DVector(indent, self.die_height - d))

    def _place_launcher(self, edge: int, d: float, cpw_name: str):
        launcher_cell = self.layout.create_cell("Launcher", self.tech_name, {
            "cpw_name": cpw_name, "tech_name": self.tech_name,
        })
        trans = self._edge_transform(edge, d)
        self.cell.insert(pya.DCellInstArray(launcher_cell.cell_index(), trans))

    def _corner_position(self, corner: int) -> pya.DPoint:
        inset = self.corner_mark_inset
        if corner == 0:  # SW
            return pya.DPoint(inset, inset)
        if corner == 1:  # SE
            return pya.DPoint(self.die_width - inset, inset)
        if corner == 2:  # NE
            return pya.DPoint(self.die_width - inset, self.die_height - inset)
        return pya.DPoint(inset, self.die_height - inset)  # NW

    def _place_corner_mark(self, corner: int):
        mark_cell = self.layout.create_cell("AlignmentMarks", self.tech_name, {
            "layers": self.alignment_mark_layers,
        })
        position = self._corner_position(corner)
        trans = pya.DCplxTrans(1.0, corner * 90.0, False, pya.DVector(position.x, position.y))
        self.cell.insert(pya.DCellInstArray(mark_cell.cell_index(), trans))

    def _place_label(self):
        if not self.chip_label:
            return
        dbu = self.layout.dbu
        text_li = self.layout.layer(self.text_layer)
        x = self.corner_mark_inset + 200.0
        y = self.corner_mark_inset + 200.0
        self.cell.shapes(text_li).insert(pya.DText(self.chip_label, x, y).to_itype(dbu))
