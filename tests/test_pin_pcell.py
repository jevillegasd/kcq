"""Tests for the Pin core PCell (python/kcq/pcells/Pin.py) -- a
placeable, parametric pin/port marker, registered into every
technology's PCell library by kcq.utils.pcell_loader even though its
source lives in the package's own python/kcq/pcells/, not any
tech/<name>/pcells/.
"""

import pya
import pytest

from kcq.geometry import pins
from kcq.utils import pcell_loader


@pytest.fixture(scope="module", autouse=True)
def _register_kcq_library():
    pcell_loader.register_library("kcq")


def _new_layout():
    layout = pya.Layout()
    layout.dbu = 0.001
    layout.technology_name = "kcq"
    layout.create_cell("TOP")
    return layout


class TestPinRegistration:
    def test_pin_is_registered_in_the_kcq_pcell_library(self):
        layout = _new_layout()
        cell = layout.create_cell("Pin", "kcq", {})
        assert cell is not None

    def test_default_parameters_are_instantiable(self):
        layout = _new_layout()
        cell = layout.create_cell("Pin", "kcq", {})
        found = pins.get_pins(cell, layout)
        assert len(found) == 1
        assert found[0].name == "P1"
        assert found[0].width == pytest.approx(10.0)


class TestPinGeometry:
    def test_produces_a_named_pin_at_the_shape_midpoint_and_angle(self):
        layout = _new_layout()
        pin_shape = pya.DPath([pya.DPoint(0.0, 0.0), pya.DPoint(10.0, 0.0)], 1.0)
        cell = layout.create_cell("Pin", "kcq", {
            "pin_shape": pin_shape, "pin_name": "IN", "width": 8.0,
        })

        found = pins.get_pins(cell, layout)
        assert len(found) == 1
        p = found[0]
        assert p.name == "IN"
        assert p.position.x == pytest.approx(5.0)
        assert p.position.y == pytest.approx(0.0)
        assert p.angle_deg == pytest.approx(0.0)
        assert p.width == pytest.approx(8.0)

    def test_angle_derived_from_diagonal_shape(self):
        layout = _new_layout()
        pin_shape = pya.DPath([pya.DPoint(0.0, 0.0), pya.DPoint(10.0, 10.0)], 1.0)
        cell = layout.create_cell("Pin", "kcq", {"pin_shape": pin_shape})

        p = pins.get_pins(cell, layout)[0]
        assert p.angle_deg == pytest.approx(45.0)

    def test_reversed_shape_faces_the_opposite_direction(self):
        layout = _new_layout()
        pin_shape = pya.DPath([pya.DPoint(10.0, 0.0), pya.DPoint(0.0, 0.0)], 1.0)
        cell = layout.create_cell("Pin", "kcq", {"pin_shape": pin_shape})

        p = pins.get_pins(cell, layout)[0]
        assert p.position.x == pytest.approx(5.0)
        assert p.angle_deg == pytest.approx(180.0)

    def test_name_is_trimmed_and_falls_back_to_default_when_blank(self):
        layout = _new_layout()
        cell = layout.create_cell("Pin", "kcq", {"pin_name": "  OUT  "})
        assert pins.get_pins(cell, layout)[0].name == "OUT"

        cell2 = layout.create_cell("Pin", "kcq", {"pin_name": "   "})
        assert pins.get_pins(cell2, layout)[0].name == "P1"

    def test_negative_width_is_clamped_to_zero(self):
        layout = _new_layout()
        cell = layout.create_cell("Pin", "kcq", {"width": -5.0})
        # Not exactly 0.0: add_pin floors the marker's own geometric
        # footprint at a few dbu so a ~zero-width pin still has a real,
        # non-degenerate triangle to snap to (a true zero-area polygon
        # has no vertices at all -- nothing for get_pins to read back).
        assert pins.get_pins(cell, layout)[0].width == pytest.approx(0.0, abs=0.01)

    def test_coincident_endpoints_produce_no_pin(self):
        # PCell production errors are caught internally by KLayout (logged,
        # not raised to the caller), so the observable effect is an empty
        # cell rather than a propagated exception.
        layout = _new_layout()
        pin_shape = pya.DPath([pya.DPoint(3.0, 3.0), pya.DPoint(3.0, 3.0)], 1.0)
        cell = layout.create_cell("Pin", "kcq", {"pin_shape": pin_shape})
        assert pins.get_pins(cell, layout) == []
