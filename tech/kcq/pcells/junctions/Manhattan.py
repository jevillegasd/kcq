"""Manhattan PCell: a parametric Manhattan-style (double-angle-evaporation)
Josephson junction.

Migrated from PDK_Qfoundry (qfoundry/tech/pymacros/qfoundry/junctions/Manhattan.py).
Geometry unchanged; two adaptations for kcq:
- The `kqcircuits.util.symmetric_polygons.polygon_with_vsym` dependency
  (via junctions/utils.py) is gone -- `_utils.py` reimplements it locally
  and this file's own (unused in the original) import of it is dropped.
- The original picked positive- vs. negative-resist behavior by comparing
  `cap_layer` against a hardcoded qfoundry-specific layer list; that's now
  an explicit `negative_resist` parameter, technology-agnostic.
"""

import pya
from math import radians, cos, sin

import _utils


class Manhattan(pya.PCellDeclarationHelper):

    def __init__(self):
        super(Manhattan, self).__init__()
        self.set_paramters()

    def display_text_impl(self):
        return "Manhattan: A parameteric manhattan josephson junction"

    def coerce_parameters_impl(self):
        if (self.angle < -60):
            self.angle = -60
        elif (self.angle > 60):
            self.angle = 60

    def produce_impl(self):
        self.produceManhattan()

    def set_paramters(self):
        self.param("l_layer", self.TypeLayer, "Layer", default=pya.LayerInfo(2, 0))
        self.param("angle", self.TypeDouble, "Junction angle", default=0.0)

        self.param("inner_angle", self.TypeDouble, "Angle between junction pads", default=90.0)
        self.param("junction_width_t", self.TypeDouble, "Top junction width", default=0.3, unit="μm", hidden=False)
        self.param("junction_width_b", self.TypeDouble, "Bottom junction width", default=0.3, unit="μm", hidden=False)
        self.param("junction_y_offset", self.TypeDouble, "Vertical Offset of the junction position", default=0.0, unit="μm", hidden=False)
        self.param("finger_overshoot", self.TypeDouble, "Length of fingers after the junction.", default=2.0, unit="μm", hidden=False)
        self.param("finger_overlap", self.TypeDouble, "Length of fingers inside the arms.", default=1.0, unit="μm", hidden=True)
        self.param("finger_size", self.TypeDouble, "Length of fingers (without overshoot).", default=10.0, unit="μm")

        self.param("round_pad", self.TypeBoolean, "Arm has round edges", default=True, hidden=True)
        self.param("pad_radius", self.TypeDouble, "Arm edge radius", default=2.0, hidden=True)
        self.param("conn_width", self.TypeDouble, "Connector arm width", default=5.0, hidden=False)
        self.param("conn_height", self.TypeDouble, "Connector arm height", default=20.0, hidden=False)

        # add separator
        self.param("draw_cap", self.TypeBoolean, "Include test pad", default=False)
        self.param("cap_gap", self.TypeDouble, "Capacitor gap", default=40.0)
        self.param("cap_w", self.TypeDouble, "Capacitor width", default=200.0, hidden=False)
        self.param("cap_h", self.TypeDouble, "Capacitor height", default=200.0, hidden=False)
        self.param("draw_patch", self.TypeBoolean, "Include patches", default=True)
        self.param("patch_scratch", self.TypeBoolean, "Draw 45 deg scratches as patch", default=False)
        self.param("patch_layer", self.TypeLayer, "Patch Layer", default=pya.LayerInfo(4, 0))
        self.param("patch_gap", self.TypeDouble, "Patch gap", default=2.0, hidden=False)
        self.param("patch_clearance", self.TypeDouble, "Patch clearance", default=5.0)

        self.param("cap_layer", self.TypeLayer, "Layer", default=pya.LayerInfo(1, 1))
        self.param("negative_resist", self.TypeBoolean,
                   "Litho polarity: True draws the label directly and puts junction "
                   "leads/patches on a separate additive layer; False subtracts the "
                   "label from the positive region instead", default=False)
        self.param("offset_compensation", self.TypeDouble, "Compensation for top junction.", default=0.0, unit="μm", hidden=True)
        self.param("mirror_offset", self.TypeDouble, "Length of fingers (without overshoot).", default=False, unit="μm", hidden=True)
        self.param("label", self.TypeString, "Label", default="kcq_manhattan", hidden=True)

    def produceManhattan(self):
            """Draws the Manhattan junction"""
            dbu = self.layout.dbu
            has_connectors = (self.conn_height != 0) and (self.conn_width != 0)

            #Junction
            finger_shapes = _utils.draw_junction(angle=self.angle,
                                          inner_angle=self.inner_angle,
                                          junction_width_b=self.junction_width_b,
                                          junction_width_t=self.junction_width_t,
                                          finger_size=self.finger_size,
                                          mirror_offset=self.mirror_offset,
                                          offset_compensation=self.offset_compensation,
                                          finger_overshoot=self.finger_overshoot,
                                          finger_overlap=self.finger_overlap,
                                          bottom_lead_comp=0, center=pya.DPoint(0, 0), dbu=dbu)
            layer_jj = self.layout.layer(self.l_layer)
            _utils.add_shapes(self.cell, finger_shapes, layer_jj)
            if has_connectors:
                conn_shapes = self.draw_connectors(pya.DPoint(0, 0))
                _utils.add_shapes(self.cell, conn_shapes, layer_jj)

            # Capacitor
            if self.draw_cap:
                cap_shape = _utils.draw_pad(self.cap_w, self.cap_h, self.cap_gap, dbu=dbu)
                patch_open_shape = []
                patch_shape = []

                metal_neg = pya.Box(-(self.cap_w + 80) / dbu / 2, -(self.cap_h + 40 + self.cap_gap / 2) / dbu,
                                    (self.cap_w + 80) / dbu / 2, (self.cap_h + 40 + self.cap_gap / 2) / dbu)

                region_pos = pya.Region(cap_shape).merged()
                region_neg = pya.Region(metal_neg).merged() - pya.Region(cap_shape).merged()
            else:
                # Regions must be defined even when no capacitor is drawn.
                region_pos = pya.Region()
                region_neg = pya.Region()

            if has_connectors:
                # Patches (maybe not drawn, but always calculated so it can be used for the region logic)
                patch_shape = _utils.draw_patch(
                    self.finger_size,
                    self.cap_gap,
                    self.conn_width,
                    self.conn_height,
                    self.angle,
                    self.inner_angle,
                    self.patch_scratch,
                    self.patch_clearance,
                    finger_overlap=self.finger_overlap,
                    center=pya.DPoint(0, 0),
                    dbu=dbu
                )

                # Patch opening in base metal layer
                center = pya.DPoint(0, 0)
                _angle = radians(self.angle)
                top_height = self.conn_height + self.cap_gap / 2 - self.finger_size * sin(_angle)
                patch_top = _utils.draw_patch_openning(
                    self.finger_size,
                    self.conn_width,
                    top_height,
                    self.angle,
                    self.inner_angle,
                    gap=self.patch_gap,
                    finger_overlap=self.finger_overlap,
                    round_radius=self.pad_radius + self.patch_clearance - self.patch_gap,
                )

                bottom_angle = self.angle - self.inner_angle
                bot_height = self.conn_height + self.cap_gap / 2 + self.finger_size * sin(radians(bottom_angle))
                patch_bot = _utils.draw_patch_openning(
                    self.finger_size,
                    self.conn_width,
                    bot_height,
                    angle=bottom_angle,
                    inner_angle=self.inner_angle,
                    gap=self.patch_gap,
                    finger_overlap=self.finger_overlap,
                    round_radius=self.pad_radius + self.patch_clearance - self.patch_gap,
                    direction=-1,
                )

                patch_open_shape = [
                    (pya.DTrans(0, False, center.x, center.y) * patch_top).to_itype(dbu),
                    (pya.DTrans(0, False, center.x, center.y) * patch_bot).to_itype(dbu)
                ]
                region_pos = region_pos - pya.Region(patch_open_shape).merged()
                region_neg = region_neg + pya.Region(patch_open_shape).merged()

                if self.draw_patch:
                  layer_patch = self.layout.layer(self.patch_layer)
                  _utils.add_shapes(self.cell, patch_shape, layer_patch)

            # Drawing and label handling
            layer_cap = self.layout.layer(self.cap_layer)
            layer_add = self.layout.layer(pya.LayerInfo(131, 1))

            if self.draw_cap:
                trans = pya.Trans(pya.Trans.R0, (-self.cap_w / 2 + 10) / dbu, (self.cap_h - 10) / dbu)

                if self.negative_resist:
                    # Negative lithography: use separate layers for positive and negative regions
                    cell_label = self.layout.create_cell("TEXT", "Basic", {"text": self.label, "mag": 20, "layer": layer_cap})
                    cell_instance_lbl = pya.CellInstArray(cell_label.cell_index(), trans)
                    self.cell.insert(cell_instance_lbl)
                else:
                    # Positive lithography: insert label and subtract from positive region
                    cell_label = self.layout.create_cell("TEXT", "Basic", {"text": self.label, "mag": 20, "layer": layer_add})
                    cell_instance_lbl = pya.CellInstArray(cell_label.cell_index(), trans)
                    self.cell.insert(cell_instance_lbl)
                    # Flatten and subtract the label region from region_pos if needed
                    layer_label = self.layout.layer(pya.LayerInfo(103, 1))  # Texts
                    region_pos = region_pos - pya.Region(cell_label.shapes(layer_label)).merged()

            self.cell.shapes(layer_add).insert(region_pos)
            self.cell.shapes(layer_cap).insert(region_neg)

    def draw_connectors(self, center=pya.DPoint(0, 0)):
        dbu = self.layout.dbu
        size = self.finger_size
        _angle = radians(self.angle)
        conn_width = self.conn_width
        conn_height = self.conn_height
        _inner_angle = radians(self.inner_angle)

        def connector_points(tip_w, width, angle, rot=0, conn_height=20.0):
            end_x = size * cos(angle)
            end_y = size * sin(angle)

            polygon = pya.DTrans(0, False, end_x, end_y) * pya.DTrans(rot, False, 0, 0) * pya.DPolygon([
                pya.DPoint(tip_w / 2, 0),
                pya.DPoint(conn_width / 2, conn_width),
                pya.DPoint(conn_width / 2, conn_height),
                pya.DPoint(-conn_width / 2, conn_height),
                pya.DPoint(-conn_width / 2, conn_width),
                pya.DPoint(-tip_w / 2, 0)
            ])
            if self.round_pad:
              polygon = polygon.round_corners(self.pad_radius, self.pad_radius, 16)
            return polygon

        conn_top = pya.DTrans(0, False, 0, -1) * (connector_points(tip_w=2.0, width=conn_width, angle=_angle, conn_height=conn_height + self.cap_gap / 2.0 - self.finger_size * sin(_angle)))
        conn_bot = pya.DTrans(0, False, 0, 1) * (connector_points(tip_w=2.0, width=conn_width, angle=_angle - _inner_angle, rot=2, conn_height=conn_height + self.cap_gap / 2.0 + self.finger_size * sin(_angle - _inner_angle)))

        connector_shapes = [(pya.DTrans(0, False, center.x, center.y) * conn_top).to_itype(dbu),
                            (pya.DTrans(0, False, center.x, center.y) * conn_bot).to_itype(dbu)]

        return connector_shapes
