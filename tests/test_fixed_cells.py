"""Tests for fixed-cell import (kcq.utils.pcell_loader's fixed_cells/
handling) using the real launcher_15p5_7.oas asset shipped in
tech/kcq/fixed_cells/.
"""

import pya
import pytest

from kcq.geometry import cpw, pins, router
from kcq.utils import pcell_loader

GAP_LAYER = (1, 0)
GROUND_EXCLUDE_LAYER = (133, 1)
TRACE_LAYER = (1, 1)

FIXED_CELL_LIBRARY = pcell_loader.fixed_cell_library_name("kcq")


@pytest.fixture(scope="module")
def library():
    _pcell_library, fixed_cell_library = pcell_loader.register_library("kcq")
    return fixed_cell_library


def _place_launcher(layout):
    top = layout.create_cell("TOP")
    cell = layout.create_cell("launcher_15p5_7", FIXED_CELL_LIBRARY)
    top.insert(pya.CellInstArray(cell.cell_index(), pya.Trans(0, 0)))
    return cell


class TestFixedCellImport:
    def test_launcher_is_discovered_and_named_after_its_file_stem(self, library):
        assert "launcher_15p5_7" in library.imported_fixed_cells

    def test_launcher_is_creatable_via_two_arg_create_cell(self, library):
        layout = pya.Layout()
        layout.dbu = 0.001
        layout.technology_name = "kcq"
        cell = _place_launcher(layout)
        assert cell is not None

    def test_fixed_cell_library_is_separate_from_pcell_library(self, library):
        # The user's explicit direction: PCells and fixed cells live in
        # two different pya.Library instances, not merged into one.
        assert FIXED_CELL_LIBRARY != "kcq"
        layout = pya.Layout()
        layout.dbu = 0.001
        layout.technology_name = "kcq"
        assert layout.create_cell("launcher_15p5_7", "kcq") is None
        assert layout.create_cell("Transmon", FIXED_CELL_LIBRARY, {}) is None

    def test_launcher_geometry_is_present(self, library):
        layout = pya.Layout()
        layout.dbu = 0.001
        layout.technology_name = "kcq"
        cell = _place_launcher(layout)
        gap_li = layout.layer(*GAP_LAYER)
        exclude_li = layout.layer(*GROUND_EXCLUDE_LAYER)
        assert not cell.shapes(gap_li).is_empty()
        assert not cell.shapes(exclude_li).is_empty()

    def test_launcher_bbox_matches_source_asset(self, library):
        layout = pya.Layout()
        layout.dbu = 0.001
        layout.technology_name = "kcq"
        cell = _place_launcher(layout)
        bbox = cell.bbox().to_dtype(layout.dbu)
        # Body spans x=[-440, 0], y=[-240.25, 240.25]; allow slack for the
        # pin marker path, which pokes 0.5um past the port edge at x=0.
        assert bbox.left == pytest.approx(-440.0, abs=0.01)
        assert bbox.bottom == pytest.approx(-240.25, abs=0.01)
        assert bbox.top == pytest.approx(240.25, abs=0.01)


class TestFixedCellPins:
    def test_pin_loaded_from_json_sidecar(self, library):
        layout = pya.Layout()
        layout.dbu = 0.001
        layout.technology_name = "kcq"
        cell = _place_launcher(layout)
        found = pins.get_pins(cell, layout)
        assert len(found) == 1
        p = found[0]
        assert p.name == "P1"
        assert p.position.x == pytest.approx(0.0)
        assert p.position.y == pytest.approx(0.0)
        assert p.angle_deg == pytest.approx(0.0)
        assert p.width == pytest.approx(29.5)  # 15.5um core + 2*7um gap

    def test_pin_survives_instance_placement_and_transform(self, library):
        layout = pya.Layout()
        layout.dbu = 0.001
        layout.technology_name = "kcq"
        top = layout.create_cell("TOP")
        cell = layout.create_cell("launcher_15p5_7", FIXED_CELL_LIBRARY)
        inst = top.insert(pya.CellInstArray(
            cell.cell_index(), pya.Trans(pya.Trans.R90, int(1000.0 / layout.dbu), int(2000.0 / layout.dbu))))
        local_pin = pins.get_pins(inst.cell, layout)[0]
        global_position = inst.dcplx_trans * local_pin.position
        assert global_position.x == pytest.approx(1000.0)
        assert global_position.y == pytest.approx(2000.0)


class TestFixedCellAlignmentAndRouting:
    """Exercises pins.check_alignment (3.2) and the router/CPW pipeline
    (Phase 2) against the launcher's real, sidecar-driven pin -- the
    end-to-end path a real chip design uses to bring a feedline in from
    the edge launcher to an on-chip component."""

    def test_check_alignment_true_when_facing_a_matching_port(self, library):
        layout = pya.Layout()
        layout.dbu = 0.001
        layout.technology_name = "kcq"
        top = layout.create_cell("TOP")
        launcher = layout.create_cell("launcher_15p5_7", FIXED_CELL_LIBRARY)
        top.insert(pya.CellInstArray(launcher.cell_index(), pya.Trans(0, 0)))
        launcher_pin = pins.get_pins(launcher, layout)[0]  # faces +x (0 deg)

        target_pin = pins.PinInfo(name="target", position=pya.DPoint(2000.0, 0.0),
                                   angle_deg=180.0, width=22.0, layer_num=1)
        assert pins.check_alignment(launcher_pin, target_pin) is True

    def test_check_alignment_false_when_ports_do_not_face_each_other(self, library):
        layout = pya.Layout()
        layout.dbu = 0.001
        layout.technology_name = "kcq"
        top = layout.create_cell("TOP")
        launcher = layout.create_cell("launcher_15p5_7", FIXED_CELL_LIBRARY)
        top.insert(pya.CellInstArray(launcher.cell_index(), pya.Trans(0, 0)))
        launcher_pin = pins.get_pins(launcher, layout)[0]

        target_pin = pins.PinInfo(name="target", position=pya.DPoint(2000.0, 0.0),
                                   angle_deg=90.0, width=22.0, layer_num=1)
        assert pins.check_alignment(launcher_pin, target_pin) is False

    def test_route_from_launcher_to_transmon_produces_continuous_trace(self, library):
        layout = pya.Layout()
        layout.dbu = 0.001
        layout.technology_name = "kcq"
        top = layout.create_cell("TOP")

        launcher = layout.create_cell("launcher_15p5_7", FIXED_CELL_LIBRARY)
        top.insert(pya.CellInstArray(launcher.cell_index(), pya.Trans(0, 0)))
        launcher_pin = pins.get_pins(launcher, layout)[0]

        # coupler_y_offset matches the launcher's port (y=0), so the route
        # is a straight line -- no bend-radius fit-check to worry about,
        # keeping this test about routing/alignment mechanics, not bend sizing.
        transmon = layout.create_cell("Transmon", "kcq", {
            "coupler_island": ["top"], "coupler_side": ["left"], "coupler_y_offset": [0.0],
        })
        transmon_inst = top.insert(pya.CellInstArray(
            transmon.cell_index(), pya.Trans(int(3000.0 / layout.dbu), 0)))
        local_pin = pins.get_pins(transmon_inst.cell, layout)[0]
        transmon_pin = pins.PinInfo(
            name=local_pin.name,
            position=transmon_inst.dcplx_trans * local_pin.position,
            angle_deg=(local_pin.angle_deg + transmon_inst.dcplx_trans.angle) % 360.0,
            width=local_pin.width,
            layer_num=local_pin.layer_num,
        )

        assert pins.check_alignment(launcher_pin, transmon_pin) is True

        waypoints = router.route_octilinear(launcher_pin.position, launcher_pin.angle_deg,
                                             transmon_pin.position, transmon_pin.angle_deg,
                                             bend_radius=100.0)
        feedline = cpw.CPW("kcq", "resonator", waypoints)
        feedline.build(top, layout)

        trace_li = layout.layer(*TRACE_LAYER)
        trace_region = pya.Region(top.shapes(trace_li))
        assert not trace_region.is_empty()
        bbox = trace_region.bbox().to_dtype(layout.dbu)
        assert bbox.left <= launcher_pin.position.x + 1.0
        assert bbox.right >= transmon_pin.position.x - 1.0
