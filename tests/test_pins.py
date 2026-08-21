import pya
import pytest

from kcq.geometry import pins
from kcq.utils.errors import KcqConfigError


def _new_layout():
    layout = pya.Layout()
    layout.dbu = 0.001
    cell = layout.create_cell("TOP")
    return layout, cell


class TestAddGetPins:
    def test_round_trip_single_pin(self):
        layout, cell = _new_layout()
        pins.add_pin(cell, layout, "P1", pya.DPoint(10, 20), 90.0, 5.0)

        result = pins.get_pins(cell, layout)
        assert len(result) == 1
        p = result[0]
        assert p.name == "P1"
        assert p.position.x == pytest.approx(10.0)
        assert p.position.y == pytest.approx(20.0)
        assert p.angle_deg == pytest.approx(90.0)
        assert p.width == pytest.approx(5.0)

    def test_round_trip_multiple_pins(self):
        layout, cell = _new_layout()
        pins.add_pin(cell, layout, "IN", pya.DPoint(0, 0), 0.0, 10.0)
        pins.add_pin(cell, layout, "OUT", pya.DPoint(100, 0), 180.0, 10.0)

        result = {p.name: p for p in pins.get_pins(cell, layout)}
        assert set(result) == {"IN", "OUT"}
        assert result["IN"].angle_deg == pytest.approx(0.0)
        assert result["OUT"].angle_deg == pytest.approx(180.0)

    def test_negative_angle_normalized_to_0_360(self):
        layout, cell = _new_layout()
        pins.add_pin(cell, layout, "P1", pya.DPoint(0, 0), -90.0, 5.0)
        result = pins.get_pins(cell, layout)
        assert result[0].angle_deg == pytest.approx(270.0)

    def test_uses_dedicated_pin_rec_layers(self):
        layout, cell = _new_layout()
        pins.add_pin(cell, layout, "P1", pya.DPoint(0, 0), 0.0, 5.0)
        pin_rec_li = layout.layer(*pins.PIN_REC_LAYER)
        pin_rec_text_li = layout.layer(*pins.PIN_REC_TEXT_LAYER)
        assert not cell.shapes(pin_rec_li).is_empty()
        assert not cell.shapes(pin_rec_text_li).is_empty()

    def test_unmatched_path_raises(self):
        layout, cell = _new_layout()
        # Insert a PinRec path with no matching PinRecText label.
        pin_rec_li = layout.layer(*pins.PIN_REC_LAYER)
        cell.shapes(pin_rec_li).insert(pya.DPath([pya.DPoint(-0.5, 0), pya.DPoint(0.5, 0)], 5.0))
        with pytest.raises(KcqConfigError):
            pins.get_pins(cell, layout)

    def test_empty_cell_has_no_pins(self):
        layout, cell = _new_layout()
        assert pins.get_pins(cell, layout) == []


class TestCheckAlignment:
    def test_opposite_facing_pins_are_aligned(self):
        a = pins.PinInfo(name="A", position=pya.DPoint(0, 0), angle_deg=0.0, width=10.0)
        b = pins.PinInfo(name="B", position=pya.DPoint(100, 0), angle_deg=180.0, width=10.0)
        assert pins.check_alignment(a, b) is True

    def test_same_facing_pins_are_not_aligned(self):
        a = pins.PinInfo(name="A", position=pya.DPoint(0, 0), angle_deg=0.0, width=10.0)
        b = pins.PinInfo(name="B", position=pya.DPoint(100, 0), angle_deg=0.0, width=10.0)
        assert pins.check_alignment(a, b) is False

    def test_within_tolerance(self):
        a = pins.PinInfo(name="A", position=pya.DPoint(0, 0), angle_deg=0.0, width=10.0)
        b = pins.PinInfo(name="B", position=pya.DPoint(100, 0), angle_deg=180.05, width=10.0)
        assert pins.check_alignment(a, b, tolerance_deg=0.1) is True
        assert pins.check_alignment(a, b, tolerance_deg=0.01) is False

    def test_wraparound_near_zero(self):
        a = pins.PinInfo(name="A", position=pya.DPoint(0, 0), angle_deg=350.0, width=10.0)
        b = pins.PinInfo(name="B", position=pya.DPoint(100, 0), angle_deg=170.05, width=10.0)
        assert pins.check_alignment(a, b, tolerance_deg=0.1) is True
