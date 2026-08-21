"""Tests for the Waveguide core PCell (python/kcq/pcells/Waveguide.py)
-- a placeable CPW segment built from kcq.geometry.cpw.CPW, registered
into every technology's PCell library by kcq.utils.pcell_loader even
though its source lives in the package's own python/kcq/pcells/, not
any tech/<name>/pcells/.
"""

import pya
import pytest

from kcq.geometry import cpw, pins
from kcq.utils import pcell_loader, xml_parser

TRACE_LAYER = (1, 1)
GAP_LAYER = (1, 0)


@pytest.fixture(scope="module", autouse=True)
def _register_kcq_library():
    pcell_loader.register_library("kcq")


def _new_layout():
    layout = pya.Layout()
    layout.dbu = 0.001
    layout.create_cell("TOP")
    return layout


class TestWaveguideRegistration:
    def test_waveguide_is_registered_in_the_kcq_pcell_library(self):
        layout = _new_layout()
        path = pya.DPath([pya.DPoint(0.0, 0.0), pya.DPoint(500.0, 0.0)], 1.0)
        cell = layout.create_cell("Waveguide", "kcq", {"path": path, "cpw_name": "resonator"})
        assert cell is not None

    def test_default_parameters_are_instantiable(self):
        layout = _new_layout()
        cell = layout.create_cell("Waveguide", "kcq", {})
        assert cell is not None


class TestWaveguideGeometry:
    def test_produces_trace_and_gap_matching_a_direct_cpw_build(self):
        layout = _new_layout()
        waypoints = [pya.DPoint(0.0, 0.0), pya.DPoint(500.0, 0.0)]
        path = pya.DPath(waypoints, 1.0)
        cell = layout.create_cell("Waveguide", "kcq", {"path": path, "cpw_name": "resonator"})

        trace_li = layout.layer(*TRACE_LAYER)
        gap_li = layout.layer(*GAP_LAYER)
        assert not cell.shapes(trace_li).is_empty()
        assert not cell.shapes(gap_li).is_empty()

        reference_cell = layout.create_cell("ReferenceCell")
        cpw.CPW("kcq", "resonator", waypoints).build(reference_cell, layout)

        waveguide_trace = pya.Region(cell.shapes(trace_li))
        reference_trace = pya.Region(reference_cell.shapes(trace_li))
        assert waveguide_trace.area() == pytest.approx(reference_trace.area())


class TestWaveguidePins:
    def test_endpoints_are_pinned_and_face_outward(self):
        layout = _new_layout()
        waypoints = [pya.DPoint(0.0, 0.0), pya.DPoint(500.0, 0.0)]
        path = pya.DPath(waypoints, 1.0)
        cell = layout.create_cell("Waveguide", "kcq", {"path": path, "cpw_name": "resonator"})

        found = {p.name: p for p in pins.get_pins(cell, layout)}
        assert set(found) == {"P1", "P2"}

        resonator = xml_parser.get_cpw_params("kcq", "resonator")
        expected_width = resonator["trace_width"] + 2.0 * resonator["gap_width"]

        p1, p2 = found["P1"], found["P2"]
        assert p1.position.x == pytest.approx(0.0)
        assert p1.position.y == pytest.approx(0.0)
        assert p1.angle_deg == pytest.approx(180.0)  # away from the guide, backward
        assert p1.width == pytest.approx(expected_width)

        assert p2.position.x == pytest.approx(500.0)
        assert p2.position.y == pytest.approx(0.0)
        assert p2.angle_deg == pytest.approx(0.0)  # away from the guide, forward
        assert p2.width == pytest.approx(expected_width)
