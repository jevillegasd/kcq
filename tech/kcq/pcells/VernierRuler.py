"""VernierRuler PCell: a two-row vernier comb for verifying alignment
between two layers -- row A at tick_pitch, row B at
tick_pitch - vernier_step, both starting flush at x=0. The tick pair
that visually lines up under a microscope reveals the misalignment in
vernier_step-sized increments. See doc/readme.html, "The component
library" for the full param table.
"""

import pya


class VernierRuler(pya.PCellDeclarationHelper):

    def __init__(self):
        super().__init__()
        self.set_parameters()

    def display_text_impl(self):
        return f"VernierRuler({self.tick_count}x{self.vernier_step:.2f}um)"

    def coerce_parameters_impl(self):
        self.tick_count = max(1, int(self.tick_count))
        self.tick_pitch = max(0.01, float(self.tick_pitch))
        self.vernier_step = max(0.001, min(float(self.vernier_step), self.tick_pitch))
        self.tick_width = max(0.01, float(self.tick_width))
        self.tick_length = max(0.01, float(self.tick_length))

    def set_parameters(self):
        self.param("tick_count", self.TypeInt, "Number of ticks per row", default=10)
        self.param("tick_pitch", self.TypeDouble, "Row A tick pitch [um]", default=10.0)
        self.param("vernier_step", self.TypeDouble,
                   "Pitch difference between row A and row B [um]", default=1.0)
        self.param("tick_width", self.TypeDouble, "Tick width [um]", default=2.0)
        self.param("tick_length", self.TypeDouble, "Tick length [um]", default=20.0)
        self.param("layer_a", self.TypeLayer, "Row A layer", default=pya.LayerInfo(1, 0))
        self.param("layer_b", self.TypeLayer, "Row B layer", default=pya.LayerInfo(10, 0))

    def produce_impl(self):
        li_a = self.layout.layer(self.layer_a)
        li_b = self.layout.layer(self.layer_b)

        row_a = self._comb_region(self.tick_pitch, y_offset=0.0)
        row_b = self._comb_region(self.tick_pitch - self.vernier_step,
                                   y_offset=self.tick_length + self.tick_width)
        self.cell.shapes(li_a).insert(row_a)
        self.cell.shapes(li_b).insert(row_b)

    def _comb_region(self, pitch: float, y_offset: float) -> pya.Region:
        region = pya.Region()
        for i in range(self.tick_count):
            x = i * pitch
            box = pya.DBox(x - self.tick_width / 2.0, y_offset,
                            x + self.tick_width / 2.0, y_offset + self.tick_length)
            region += pya.Region(box.to_itype(self.layout.dbu))
        region.merge()
        return region
