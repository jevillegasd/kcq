"""Tests for the Launcher PCell (tech/kcq/pcells/Launcher.py) -- a
wirebond transition sized from the technology's waveguides.xml.
"""

import pya
import pytest

from kcq.geometry import pins
from kcq.utils import pcell_loader, xml_parser


@pytest.fixture(scope="module", autouse=True)
def _register_kcq_library():
    pcell_loader.register_library("kcq")


def _new_layout():
    layout = pya.Layout()
    layout.dbu = 0.001
    layout.technology_name = "kcq"
    top = layout.create_cell("TOP")
    return layout, top


def _place_launcher(layout, top, params=None):
    cell = layout.create_cell("Launcher", "kcq", params or {})
    top.insert(pya.CellInstArray(cell.cell_index(), pya.Trans()))
    return cell


class TestLauncherRegistration:
    def test_launcher_is_registered_in_the_kcq_pcell_library(self):
        layout, top = _new_layout()
        assert _place_launcher(layout, top) is not None


class TestLauncherPin:
    def test_pin_at_origin_facing_outward(self):
        layout, top = _new_layout()
        cell = _place_launcher(layout, top)
        found = pins.get_pins(cell, layout)
        assert len(found) == 1
        p = found[0]
        assert p.name == "P1"
        assert p.position.x == pytest.approx(0.0)
        assert p.position.y == pytest.approx(0.0)
        assert p.angle_deg == pytest.approx(180.0)

    def test_pin_core_width_matches_trace_width(self):
        layout, top = _new_layout()
        cell = _place_launcher(layout, top, {"cpw_name": "feedline"})
        params = xml_parser.get_cpw_params("kcq", "feedline")
        p = pins.get_pins(cell, layout)[0]
        assert p.width == pytest.approx(params["trace_width"])


class TestLauncherGeometry:
    def test_gap_does_not_overlap_trace_core(self):
        layout, top = _new_layout()
        cell = _place_launcher(layout, top)
        trace_region = pya.Region(cell.shapes(layout.layer(1, 1)))
        gap_region = pya.Region(cell.shapes(layout.layer(1, 0)))
        assert not trace_region.is_empty()
        assert not gap_region.is_empty()
        assert (trace_region & gap_region).is_empty()

    def test_probe_patch_present_only_when_requested(self):
        layout, top = _new_layout()
        with_patch = _place_launcher(layout, top, {"add_probe_patch": True})
        without_patch = _place_launcher(layout, top, {"add_probe_patch": False})
        probe_li = layout.layer(3, 0)
        assert not with_patch.shapes(probe_li).is_empty()
        assert without_patch.shapes(probe_li).is_empty()

    def test_dimensions_come_from_waveguides_xml_not_hardcoded(self):
        # feedline and resonator have different trace_width/gap_width in
        # kcq's own default technology -- if Launcher hardcoded a width,
        # both would produce identical trace area.
        layout, top = _new_layout()
        feedline_cell = _place_launcher(layout, top, {"cpw_name": "feedline"})
        resonator_cell = _place_launcher(layout, top, {"cpw_name": "resonator"})

        feedline_width = pins.get_pins(feedline_cell, layout)[0].width
        resonator_width = pins.get_pins(resonator_cell, layout)[0].width
        feedline_params = xml_parser.get_cpw_params("kcq", "feedline")
        resonator_params = xml_parser.get_cpw_params("kcq", "resonator")

        assert feedline_width == pytest.approx(feedline_params["trace_width"])
        assert resonator_width == pytest.approx(resonator_params["trace_width"])
        assert feedline_width != pytest.approx(resonator_width)
