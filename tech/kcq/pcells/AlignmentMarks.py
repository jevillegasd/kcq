"""AlignmentMarks PCell: a "+" target mark stamped on every physical
layer listed, plus an optional flip-chip counterpart on a second Level's
layer. See doc/readme.html, "The component library" for the full param
table and doc/readme.html's "Layers and the default technology" for the
Level/datatype convention (.drawing=0, .blockage=5) this reuses.
"""

import pya


class AlignmentMarks(pya.PCellDeclarationHelper):

    def __init__(self):
        super().__init__()
        self.set_parameters()

    def display_text_impl(self):
        return f"AlignmentMarks({len(self.layers)} layer(s))"

    def coerce_parameters_impl(self):
        self.layers = [int(v) for v in self.layers] if self.layers else [1]
        self.cross_size = max(1.0, float(self.cross_size))
        self.cross_width = max(0.1, min(float(self.cross_width), self.cross_size))
        self.keepout_margin = max(0.0, float(self.keepout_margin))
        self.flip_chip_layer = int(self.flip_chip_layer)

    def set_parameters(self):
        self.param("layers", self.TypeList,
                   "Physical layer numbers to stamp the mark on", default=[1, 2])
        self.param("cross_size", self.TypeDouble, "Overall mark size [um]", default=100.0)
        self.param("cross_width", self.TypeDouble, "Cross arm width [um]", default=10.0)
        self.param("keepout_margin", self.TypeDouble,
                   "Blockage margin beyond the mark [um]", default=20.0)
        self.param("include_flip_chip_mark", self.TypeBoolean,
                   "Also stamp the mark on the flip-chip layer", default=False)
        self.param("flip_chip_layer", self.TypeInt,
                   "Flip-chip (L2) layer number", default=10)

    def produce_impl(self):
        dbu = self.layout.dbu
        cross = self._cross_region()
        keepout = pya.DBox(-self.cross_size / 2.0 - self.keepout_margin,
                            -self.cross_size / 2.0 - self.keepout_margin,
                            self.cross_size / 2.0 + self.keepout_margin,
                            self.cross_size / 2.0 + self.keepout_margin).to_itype(dbu)

        for i, layer_num in enumerate(self.layers):
            drawing_li = self.layout.layer(layer_num, 0)
            self.cell.shapes(drawing_li).insert(cross)
            if i == 0:
                blockage_li = self.layout.layer(layer_num, 5)
                self.cell.shapes(blockage_li).insert(keepout)

        if self.include_flip_chip_mark:
            flip_li = self.layout.layer(self.flip_chip_layer, 0)
            self.cell.shapes(flip_li).insert(cross)

    def _cross_region(self) -> pya.Region:
        dbu = self.layout.dbu
        half = self.cross_size / 2.0
        half_w = self.cross_width / 2.0
        horizontal = pya.DBox(-half, -half_w, half, half_w)
        vertical = pya.DBox(-half_w, -half, half_w, half)
        region = pya.Region(horizontal.to_itype(dbu)) + pya.Region(vertical.to_itype(dbu))
        region.merge()
        return region
