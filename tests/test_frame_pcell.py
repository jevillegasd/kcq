"""Tests for the Frame PCell (tech/kcq/pcells/Frame.py) -- assembles
Launcher instances around a die's 4 edges plus DCS/Design Area/DRC
Exception/Ground Exclusion bookkeeping geometry and corner
AlignmentMarks.
"""

import pya
import pytest

from kcq.gui import instance_pins
from kcq.utils import pcell_loader
from kcq.utils.errors import KcqConfigError


@pytest.fixture(scope="module", autouse=True)
def _register_kcq_library():
    pcell_loader.register_library("kcq")


def _new_layout():
    layout = pya.Layout()
    layout.dbu = 0.001
    layout.technology_name = "kcq"
    top = layout.create_cell("TOP")
    return layout, top


def _place(layout, top, params=None):
    cell = layout.create_cell("Frame", "kcq", params or {})
    top.insert(pya.CellInstArray(cell.cell_index(), pya.Trans()))
    return cell


def _sub_instances(frame_cell, cell_name):
    # KLayout auto-suffixes a PCell's variant cell name ("Launcher$1",
    # "Launcher$2", ...) once more than one distinct parameter
    # combination of it is in use, so match by prefix, not equality.
    return [inst for inst in frame_cell.each_inst()
            if inst.cell.name == cell_name or inst.cell.name.startswith(cell_name + "$")]


class TestFrameRegistration:
    def test_registered_in_the_kcq_pcell_library(self):
        layout, top = _new_layout()
        assert _place(layout, top) is not None


class TestFrameBoundaryLayers:
    def test_dcs_and_design_area_match_params(self):
        layout, top = _new_layout()
        frame = _place(layout, top, {
            "die_width": 5000.0, "die_height": 5000.0, "launcher_indent": 800.0,
        })
        dcs = pya.Region(frame.shapes(layout.layer(100, 1))).bbox().to_dtype(layout.dbu)
        design = pya.Region(frame.shapes(layout.layer(100, 4))).bbox().to_dtype(layout.dbu)
        assert dcs.left == pytest.approx(0.0)
        assert dcs.right == pytest.approx(5000.0)
        assert design.left == pytest.approx(800.0)
        assert design.right == pytest.approx(5000.0 - 800.0)

    def test_drc_and_ground_exclusion_ring_area_matches_dcs_minus_design_area(self):
        layout, top = _new_layout()
        frame = _place(layout, top, {
            "die_width": 5000.0, "die_height": 5000.0, "launcher_indent": 800.0,
        })
        dcs_area = 5000.0 * 5000.0
        design_area = (5000.0 - 2 * 800.0) ** 2
        expected_ring = dcs_area - design_area

        drc_area = pya.Region(frame.shapes(layout.layer(111, 1))).area() * layout.dbu ** 2
        excl_area = pya.Region(frame.shapes(layout.layer(1, 5))).area() * layout.dbu ** 2
        assert drc_area == pytest.approx(expected_ring)
        assert excl_area == pytest.approx(expected_ring)


class TestFrameLaunchers:
    def test_launcher_count_matches_four_times_positions(self):
        layout, top = _new_layout()
        frame = _place(layout, top, {"launcher_positions": [1000.0, 2000.0, 3000.0]})
        assert len(_sub_instances(frame, "Launcher")) == 12

    def test_every_launcher_pin_lands_on_the_design_area_boundary_facing_inward(self):
        layout, top = _new_layout()
        die = 5000.0
        indent = 800.0
        frame = _place(layout, top, {
            "die_width": die, "die_height": die, "launcher_indent": indent,
            "launcher_positions": [1000.0, 2000.0, 3000.0, 4000.0],
        })
        for inst in _sub_instances(frame, "Launcher"):
            pin = instance_pins.global_pins(layout, inst)[0]
            on_boundary = (
                pin.position.x == pytest.approx(indent, abs=1e-3)
                or pin.position.x == pytest.approx(die - indent, abs=1e-3)
                or pin.position.y == pytest.approx(indent, abs=1e-3)
                or pin.position.y == pytest.approx(die - indent, abs=1e-3)
            )
            assert on_boundary
            # Inward-facing: south=90, east=180, north=270, west=0.
            closest_diff = min(abs(pin.angle_deg - a) for a in (0.0, 90.0, 180.0, 270.0))
            assert closest_diff < 0.5

    def test_single_cpw_name_broadcasts_to_every_launcher(self):
        layout, top = _new_layout()
        frame = _place(layout, top, {
            "launcher_positions": [1000.0, 2000.0], "cpw_name": ["resonator"],
        })
        for inst in _sub_instances(frame, "Launcher"):
            assert inst.cell.pcell_parameters_by_name()["cpw_name"] == "resonator"

    def test_per_position_cpw_name_list_assigns_one_to_one(self):
        layout, top = _new_layout()
        frame = _place(layout, top, {
            "launcher_positions": [1000.0, 2000.0], "cpw_name": ["feedline", "resonator"],
        })
        south_edge = [inst for inst in _sub_instances(frame, "Launcher")
                      if instance_pins.global_pins(layout, inst)[0].position.y == pytest.approx(800.0)]
        south_edge.sort(key=lambda inst: instance_pins.global_pins(layout, inst)[0].position.x)
        names = [inst.cell.pcell_parameters_by_name()["cpw_name"] for inst in south_edge]
        assert names == ["feedline", "resonator"]

    def test_mismatched_cpw_name_length_raises(self):
        layout, top = _new_layout()
        with pytest.raises(KcqConfigError):
            _place(layout, top, {
                "launcher_positions": [1000.0, 2000.0, 3000.0], "cpw_name": ["feedline", "resonator"],
            })

    def test_default_cpw_name_matches_waveguides_xml_first_entry(self):
        from kcq.utils import xml_parser
        layout, top = _new_layout()
        frame = _place(layout, top, {"launcher_positions": [1000.0]})
        expected = next(iter(xml_parser.load_technology("kcq")["cpws"]))
        inst = _sub_instances(frame, "Launcher")[0]
        assert inst.cell.pcell_parameters_by_name()["cpw_name"] == expected


class TestFrameCornerMarksAndLabel:
    def test_four_corner_alignment_marks(self):
        layout, top = _new_layout()
        frame = _place(layout, top)
        assert len(_sub_instances(frame, "AlignmentMarks")) == 4

    def test_chip_label_placed_near_sw_corner(self):
        layout, top = _new_layout()
        frame = _place(layout, top, {"chip_label": "TEST_CHIP"})
        texts = [shape.dtext for li in layout.layer_indexes()
                 for shape in frame.shapes(li).each() if shape.is_text()]
        assert len(texts) == 1
        assert texts[0].string == "TEST_CHIP"
        assert texts[0].x < 2000.0
        assert texts[0].y < 2000.0

    def test_no_label_when_chip_label_empty(self):
        layout, top = _new_layout()
        frame = _place(layout, top, {"chip_label": ""})
        texts = [shape for li in layout.layer_indexes()
                 for shape in frame.shapes(li).each() if shape.is_text()]
        assert texts == []
