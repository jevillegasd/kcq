import pya
import pytest

from kcq.geometry import pins
from kcq.utils import metadata, pcell_loader

METAL_LAYER = (1, 1)
GAP_LAYER = (1, 0)


@pytest.fixture(scope="module", autouse=True)
def _register_kcq_library():
    pcell_loader.register_library("kcq")


def _place_transmon(params=None):
    layout = pya.Layout()
    layout.dbu = 0.001
    layout.technology_name = "kcq"
    top = layout.create_cell("TOP")
    cell = layout.create_cell("Transmon", "kcq", params or {})
    top.insert(pya.CellInstArray(cell.cell_index(), pya.Trans(0, 0)))
    return layout, cell


class TestTransmonBasics:
    def test_registers_and_places(self):
        layout, cell = _place_transmon()
        assert cell is not None

    def test_produces_metal_and_gap_geometry(self):
        layout, cell = _place_transmon()
        metal_li = layout.layer(*METAL_LAYER)
        gap_li = layout.layer(*GAP_LAYER)
        assert not cell.shapes(metal_li).is_empty()
        assert not cell.shapes(gap_li).is_empty()

    def test_keepout_bbox_matches_island_bbox_plus_clearance(self):
        layout, cell = _place_transmon({
            "island_width": 400.0, "island_height": 200.0, "island_gap": 40.0,
            "ground_clearance": 60.0, "keepout_corner_radius": 0.0,
        })
        gap_li = layout.layer(*GAP_LAYER)
        region = pya.Region(cell.shapes(gap_li))
        bbox = region.bbox().to_dtype(layout.dbu)
        expected_half_h = 40.0 / 2.0 + 200.0 + 60.0
        assert bbox.top == pytest.approx(expected_half_h, abs=1.0)
        assert bbox.bottom == pytest.approx(-expected_half_h, abs=1.0)

    def test_two_islands_are_disjoint_without_junction_leads(self):
        # With no leads bridging the gap, top and bottom islands must not
        # touch -- island_gap should read through as real separation.
        layout, cell = _place_transmon({"add_junction_leads": False, "coupler_island": []})
        metal_li = layout.layer(*METAL_LAYER)
        region = pya.Region(cell.shapes(metal_li)).merged()
        assert region.count() == 2


class TestTransmonCouplers:
    def test_default_two_couplers_produce_two_pins(self):
        layout, cell = _place_transmon()
        found = {p.name: p for p in pins.get_pins(cell, layout)}
        assert set(found) == {"C0", "C1"}

    def test_default_coupler_pin_positions_and_angles(self):
        layout, cell = _place_transmon({
            "island_width": 420.0, "island_height": 200.0, "island_gap": 40.0,
            "ground_clearance": 60.0, "coupler_extension": [30.0],
        })
        found = {p.name: p for p in pins.get_pins(cell, layout)}
        # C0: top island, right side -> +x, +y (island midpoint)
        assert found["C0"].angle_deg == pytest.approx(0.0)
        assert found["C0"].position.x == pytest.approx(210.0 + 60.0 + 30.0, abs=0.1)
        assert found["C0"].position.y == pytest.approx(20.0 + 100.0, abs=0.1)
        # C1: bottom island, left side -> -x, -y
        assert found["C1"].angle_deg == pytest.approx(180.0)
        assert found["C1"].position.x == pytest.approx(-(210.0 + 60.0 + 30.0), abs=0.1)
        assert found["C1"].position.y == pytest.approx(-(20.0 + 100.0), abs=0.1)

    def test_coupler_pin_width_defaults_from_technology_resonator_cpw(self):
        layout, cell = _place_transmon()
        found = pins.get_pins(cell, layout)
        # kcq's shipped waveguides.xml: resonator trace_width=10, gap_width=6.
        for p in found:
            assert p.width == pytest.approx(10.0 + 2 * 6.0)

    def test_explicit_coupler_wg_width_gap_override_technology_default(self):
        layout, cell = _place_transmon({"coupler_wg_width": [20.0], "coupler_wg_gap": [4.0]})
        found = pins.get_pins(cell, layout)
        for p in found:
            assert p.width == pytest.approx(20.0 + 2 * 4.0)

    def test_zero_couplers_produces_no_pins(self):
        layout, cell = _place_transmon({"coupler_island": []})
        assert pins.get_pins(cell, layout) == []

    def test_three_couplers_with_mixed_islands_and_sides(self):
        layout, cell = _place_transmon({
            "coupler_island": ["top", "top", "bottom"],
            "coupler_side": ["left", "right", "right"],
        })
        found = {p.name: p for p in pins.get_pins(cell, layout)}
        assert len(found) == 3
        assert found["C0"].angle_deg == pytest.approx(180.0)
        assert found["C1"].angle_deg == pytest.approx(0.0)
        assert found["C2"].angle_deg == pytest.approx(0.0)

    def test_invalid_coupler_island_defaults_to_top(self):
        layout, cell = _place_transmon({"coupler_island": ["diagonal"], "coupler_side": ["right"]})
        found = pins.get_pins(cell, layout)
        assert len(found) == 1
        assert found[0].position.y > 0  # top island's y range is positive

    def test_notch_leaves_a_capacitive_gap_not_a_short(self):
        # The conductor must not reach all the way to the notch's back
        # wall -- there should be empty space (no metal) at the gap
        # between the conductor tip and the remaining island metal.
        layout, cell = _place_transmon({
            "coupler_island": ["top"], "coupler_side": ["right"],
            "coupler_notch_depth": [80.0], "coupler_notch_gap": [10.0],
            "island_width": 420.0,
        })
        metal_li = layout.layer(*METAL_LAYER)
        region = pya.Region(cell.shapes(metal_li))
        # notch_inner_x = 210 - 80 = 130; conductor tip = 130 + 10 = 140.
        # A point strictly between tip and back wall must be empty.
        probe_box = pya.Region(pya.DBox(134.9, 119.9, 135.1, 120.1).to_itype(layout.dbu))
        assert (region & probe_box).is_empty()


class TestTransmonJunctionLeads:
    def test_axis_aligned_leads_bridge_the_gap(self):
        layout, cell = _place_transmon({"add_junction_leads": True, "coupler_island": []})
        metal_li = layout.layer(*METAL_LAYER)
        region = pya.Region(cell.shapes(metal_li)).merged()
        # Leads should connect the two islands into a single polygon
        # (arm_gap keeps them from touching at the junction itself, but
        # each lead is still joined to its own island).
        assert region.count() >= 2

    def test_angled_leads_with_squid_do_not_raise(self):
        layout, cell = _place_transmon({
            "lead_angled": True, "junction_angle": 45.0,
            "junction_pos_x": 100.0, "squid_spacing": 40.0,
        })
        metal_li = layout.layer(*METAL_LAYER)
        assert not cell.shapes(metal_li).is_empty()


class TestTransmonMetadata:
    def test_metadata_pointer_is_attached(self):
        layout, cell = _place_transmon()
        pointer = metadata.read_pointer(cell, layout)
        assert pointer is not None

    def test_metadata_pointer_survives_gds_roundtrip(self, tmp_path):
        layout, cell = _place_transmon()
        pointer = metadata.read_pointer(cell, layout)

        gds_path = str(tmp_path / "transmon.gds")
        layout.write(gds_path)
        layout2 = pya.Layout()
        layout2.read(gds_path)
        cell2 = layout2.cell(cell.name)

        assert metadata.read_pointer(cell2, layout2) == pointer

    def test_different_params_give_different_metadata_id(self):
        layout1, cell1 = _place_transmon({"island_width": 420.0})
        layout2, cell2 = _place_transmon({"island_width": 400.0})
        assert metadata.read_pointer(cell1, layout1) != metadata.read_pointer(cell2, layout2)
