"""ManhattanSQUID PCell: a SQUID built from two Manhattan Josephson
junction PCell instances.

Migrated from PDK_Qfoundry
(qfoundry/tech/pymacros/qfoundry/junctions/ManhattanSQUID.py). Geometry
unchanged; adaptations: layer renumbering (matching Manhattan.py), the
new `negative_resist` parameter forwarded to both sub-instances instead
of qfoundry's hardcoded NEGATIVE_LAYERS check, and an explicit `lib_name`
on both create_cell calls -- this project's klayout package requires it
(create_cell(pcell_name=...) alone returns None; it does not fall back
to the layout's technology_name).
"""

import pya

import _utils

# The library both this PCell and its Manhattan sub-instances are
# registered under (kcq.utils.pcell_loader.register_library's default
# tech_name). Hardcoded rather than derived, since this is kcq's own
# default PDK referencing its own sibling PCell -- a PDK forking these
# cells under a different technology name would need to update this.
_LIBRARY_NAME = "kcq"

# Single-junction parameters that are simply forwarded to each Manhattan instance.
# Each sub-instance still draws its own connectors and (optionally) its own patch
# clearance cuts - only the large test pad is shared between the two junctions,
# since two full-size pads would overlap at typical squid_spacing values.
_MANHATTAN_PARAM_NAMES = [
    "l_layer", "angle", "inner_angle", "junction_width_t", "junction_width_b",
    "junction_y_offset", "finger_overshoot", "finger_overlap", "finger_size",
    "round_pad", "pad_radius", "conn_width", "conn_height",
    "draw_patch", "patch_scratch", "patch_layer", "patch_gap", "patch_clearance",
    "cap_gap", "cap_layer", "negative_resist",
]


class ManhattanSQUID(pya.PCellDeclarationHelper):

    def __init__(self):
        super(ManhattanSQUID, self).__init__()
        self.set_paramters()

    def display_text_impl(self):
        return "ManhattanSQUID: A SQUID built from two Manhattan junctions"

    def coerce_parameters_impl(self):
        if self.angle < -90:
            self.angle = -90
        elif self.angle > 90:
            self.angle = 90

        # Junctions must be spaced enough apart that their connector leads don't overlap.
        min_spacing = self.conn_width
        if self.squid_spacing < min_spacing:
            self.squid_spacing = min_spacing

        if self.squid_asymmetry < 0.1:
            self.squid_asymmetry = 0.1
        elif self.squid_asymmetry > 10.0:
            self.squid_asymmetry = 10.0

        # Keep the shared test pad wide enough to enclose both junctions.
        min_cap_w = self.squid_spacing + 2 * self.conn_width + 40.0
        if self.draw_cap and self.cap_w < min_cap_w:
            self.cap_w = min_cap_w

    def produce_impl(self):
        self.produceManhattanSQUID()

    def set_paramters(self):
        self.param("l_layer", self.TypeLayer, "Layer", default=pya.LayerInfo(2, 0))
        self.param("angle", self.TypeDouble, "Junction angle", default=0.0)

        self.param("inner_angle", self.TypeDouble, "Angle between junction pads", default=90.0)
        self.param("junction_width_t", self.TypeDouble, "Top junction width", default=0.3, unit="μm", hidden=False)
        self.param("junction_width_b", self.TypeDouble, "Bottom junction width", default=0.3, unit="μm", hidden=False)
        self.param("junction_y_offset", self.TypeDouble, "Vertical Offset of the junction position", default=0.0, unit="μm", hidden=False)
        self.param("finger_overshoot", self.TypeDouble, "Length of fingers after the junction.", default=2.0, unit="μm", hidden=False)
        self.param("finger_overlap", self.TypeDouble, "Length of fingers inside the pads.", default=1.0, unit="μm", hidden=True)
        self.param("finger_size", self.TypeDouble, "Length of fingers (without overshoot).", default=10.0, unit="μm")

        self.param("round_pad", self.TypeBoolean, "Pad has round edges", default=True, hidden=True)
        self.param("pad_radius", self.TypeDouble, "Pad edge radius", default=2.0, hidden=True)
        self.param("conn_width", self.TypeDouble, "Connector pad width", default=5.0, hidden=False)
        self.param("conn_height", self.TypeDouble, "Connector pad height", default=20.0, hidden=False)

        # SQUID-specific parameters
        choices = [("SQUID Pair", 0), ("SQUID Reflected", 1)]
        self.param("junction_type", self.TypeList, "Junction Type", choices=choices, default=0)
        self.param("squid_spacing", self.TypeDouble, "Spacing between SQUID junctions", default=20.0, unit="μm")
        self.param("squid_asymmetry", self.TypeDouble, "Asymmetry of the SQUID junctions", default=1.0)

        # add separator
        self.param("draw_cap", self.TypeBoolean, "Include test pad", default=True)
        self.param("cap_gap", self.TypeDouble, "Capacitor gap", default=20.0)
        self.param("cap_w", self.TypeDouble, "Capacitor width", default=240.0, hidden=False)
        self.param("cap_h", self.TypeDouble, "Capacitor height", default=200.0, hidden=False)
        self.param("draw_patch", self.TypeBoolean, "Include patches", default=True)
        self.param("patch_scratch", self.TypeBoolean, "Draw 45 deg scratches as patch", default=False)
        self.param("patch_layer", self.TypeLayer, "Patch Layer", default=pya.LayerInfo(4, 0))
        self.param("patch_gap", self.TypeDouble, "Patch gap", default=2.0, hidden=True)
        self.param("patch_clearance", self.TypeDouble, "Patch clearance", default=5.0)

        self.param("cap_layer", self.TypeLayer, "Layer", default=pya.LayerInfo(1, 1))
        self.param("negative_resist", self.TypeBoolean,
                   "Litho polarity, forwarded to both Manhattan sub-instances", default=False)
        self.param("label", self.TypeString, "Label", default="kcq_SQUID", hidden=True)

    def _junction_params(self, asymmetry=1.0):
        """Build the parameter dict forwarded to one Manhattan sub-instance.

        Each sub-instance draws its own fingers, connectors and (if enabled)
        patch clearance cuts. Only the large test pad is suppressed here, since
        the SQUID cell draws a single shared one spanning both junctions.
        """
        params = {name: getattr(self, name) for name in _MANHATTAN_PARAM_NAMES}
        params["junction_width_t"] = self.junction_width_t * asymmetry
        params["junction_width_b"] = self.junction_width_b * asymmetry
        params["draw_cap"] = False
        params["label"] = ""
        return params

    def produceManhattanSQUID(self):
        """Draws the SQUID using two instances of the Manhattan PCell."""
        dbu = self.layout.dbu
        reflected = self.junction_type == 1

        params1 = self._junction_params(asymmetry=1.0)
        params2 = self._junction_params(asymmetry=self.squid_asymmetry)

        cell1 = self.layout.create_cell("Manhattan", _LIBRARY_NAME, params1)
        cell2 = self.layout.create_cell("Manhattan", _LIBRARY_NAME, params2)
        if cell1 is None or cell2 is None:
            raise RuntimeError("Manhattan PCell not found - cannot build SQUID")

        center1 = pya.DPoint(0, 0)
        center2 = pya.DPoint(self.squid_spacing, 0)

        trans1 = pya.DTrans(0, False, center1.x / dbu, center1.y / dbu)
        trans2 = pya.DTrans(0, reflected, center2.x / dbu, center2.y / dbu)

        self.cell.insert(pya.CellInstArray(cell1.cell_index(), trans1))
        self.cell.insert(pya.CellInstArray(cell2.cell_index(), trans2))

        if not self.draw_cap:
            return

        # Shared test pad spanning both junctions
        midpoint = pya.DPoint((center1.x + center2.x) / 2.0, 0)

        cap_shape = _utils.draw_pad(self.cap_w, self.cap_h, self.cap_gap, dbu=dbu)
        mid_trans = pya.Trans(int(round(midpoint.x / dbu)), int(round(midpoint.y / dbu)))
        cap_shape = [mid_trans * shape for shape in cap_shape]

        metal_neg = pya.Box(
            (midpoint.x - (self.cap_w + 80) / 2) / dbu,
            (midpoint.y - (self.cap_h + 40 + self.cap_gap / 2)) / dbu,
            (midpoint.x + (self.cap_w + 80) / 2) / dbu,
            (midpoint.y + (self.cap_h + 40 + self.cap_gap / 2)) / dbu,
        )

        region_pos = pya.Region(cap_shape).merged()
        region_neg = pya.Region(metal_neg).merged() - region_pos

        layer_cap = self.layout.layer(self.cap_layer)

        trans = pya.Trans(
            pya.Trans.R0,
            int(round((midpoint.x - self.cap_w / 2 + 10) / dbu)),
            int(round((midpoint.y + self.cap_h - 10) / dbu)),
        )
        cell_label = self.layout.create_cell("TEXT", "Basic", {"text": self.label, "mag": 20, "layer": pya.LayerInfo(103, 1)})
        cell_instance_lbl = pya.CellInstArray(cell_label.cell_index(), trans)

        if self.negative_resist:
            # Negative lithography: use separate layers for positive and negative regions
            layer_add = self.layout.layer(pya.LayerInfo(131, 1))
            self.cell.shapes(layer_add).insert(region_pos)
            self.cell.shapes(layer_cap).insert(region_neg)
            self.cell.insert(cell_instance_lbl)
        else:
            # Positive lithography
            self.cell.insert(cell_instance_lbl)
            self.cell.shapes(layer_cap).insert(region_pos)
