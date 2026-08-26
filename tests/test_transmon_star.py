import pya
import pytest

from kcq.geometry import pins
from kcq.utils import pcell_loader

METAL_LAYER = (1, 1)
METAL_N_LAYER = (1, 0)


@pytest.fixture(scope="module", autouse=True)
def _register_kcq_library():
    pcell_loader.register_library("kcq")


def _place_transmon_star(params=None):
    layout = pya.Layout()
    layout.dbu = 0.001
    layout.technology_name = "kcq"
    top = layout.create_cell("TOP")
    cell = layout.create_cell("TransmonStar", "kcq", params or {})
    top.insert(pya.CellInstArray(cell.cell_index(), pya.Trans(0, 0)))
    return layout, cell


class TestTransmonStar:
    def test_registers_and_places(self):
        layout, cell = _place_transmon_star()
        assert cell is not None

    def test_produces_metal_and_gap_geometry(self):
        layout, cell = _place_transmon_star()
        metal_li = layout.layer(*METAL_LAYER)
        gap_li = layout.layer(*METAL_N_LAYER)
        assert not cell.shapes(metal_li).is_empty()
        assert not cell.shapes(gap_li).is_empty()

    def test_default_five_couplers_produce_five_pins(self):
        layout, cell = _place_transmon_star()
        found = pins.get_pins(cell, layout)
        assert len(found) == 5
        assert {p.name for p in found} == {"C0", "C1", "C2", "C3", "C4"}

    def test_coupler_count_matches_angle_list(self):
        layout, cell = _place_transmon_star({"coupler_angles": [0.0, 90.0, 180.0]})
        found = pins.get_pins(cell, layout)
        assert len(found) == 3

    def test_pin_angle_matches_coupler_angle(self):
        layout, cell = _place_transmon_star({"coupler_angles": [0.0, 90.0]})
        found = {p.name: p for p in pins.get_pins(cell, layout)}
        assert found["C0"].angle_deg == pytest.approx(0.0, abs=0.1)
        assert found["C1"].angle_deg == pytest.approx(90.0, abs=0.1)

    def test_no_couplers_still_produces_metal_circle(self):
        layout, cell = _place_transmon_star({"coupler_angles": []})
        metal_li = layout.layer(*METAL_LAYER)
        assert not cell.shapes(metal_li).is_empty()
        assert pins.get_pins(cell, layout) == []
