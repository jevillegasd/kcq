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
        pins.add_pin(cell, layout, "P1", pya.DPoint(10, 20), 90.0, 5.0, 1)

        result = pins.get_pins(cell, layout)
        assert len(result) == 1
        p = result[0]
        assert p.name == "P1"
        assert p.position.x == pytest.approx(10.0)
        assert p.position.y == pytest.approx(20.0)
        assert p.angle_deg == pytest.approx(90.0)
        assert p.width == pytest.approx(5.0)
        assert p.layer_num == 1

    def test_round_trip_multiple_pins(self):
        layout, cell = _new_layout()
        pins.add_pin(cell, layout, "IN", pya.DPoint(0, 0), 0.0, 10.0, 1)
        pins.add_pin(cell, layout, "OUT", pya.DPoint(100, 0), 180.0, 10.0, 1)

        result = {p.name: p for p in pins.get_pins(cell, layout)}
        assert set(result) == {"IN", "OUT"}
        assert result["IN"].angle_deg == pytest.approx(0.0)
        assert result["OUT"].angle_deg == pytest.approx(180.0)

    def test_round_trip_across_different_physical_layers(self):
        layout, cell = _new_layout()
        pins.add_pin(cell, layout, "M1", pya.DPoint(0, 0), 0.0, 10.0, 1)
        pins.add_pin(cell, layout, "JJ", pya.DPoint(50, 0), 0.0, 5.0, 2)

        result = {p.name: p for p in pins.get_pins(cell, layout)}
        assert set(result) == {"M1", "JJ"}
        assert result["M1"].layer_num == 1
        assert result["JJ"].layer_num == 2

        assert [p.name for p in pins.get_pins(cell, layout, layer_num=2)] == ["JJ"]

    def test_negative_angle_normalized_to_0_360(self):
        layout, cell = _new_layout()
        pins.add_pin(cell, layout, "P1", pya.DPoint(0, 0), -90.0, 5.0, 1)
        result = pins.get_pins(cell, layout)
        assert result[0].angle_deg == pytest.approx(270.0)

    def test_uses_layer_specific_pin_datatype(self):
        layout, cell = _new_layout()
        pins.add_pin(cell, layout, "P1", pya.DPoint(0, 0), 0.0, 5.0, 1)
        pin_li = layout.layer(1, pins.PIN_DATATYPE)
        assert not cell.shapes(pin_li).is_empty()

    def test_draws_both_a_rectangle_and_a_triangle(self):
        layout, cell = _new_layout()
        pins.add_pin(cell, layout, "P1", pya.DPoint(0, 0), 0.0, 20.0, 1)
        pin_li = layout.layer(1, pins.PIN_DATATYPE)

        polygon_point_counts = sorted(
            len(list(shape.dpolygon.each_point_hull()))
            for shape in cell.shapes(pin_li).each() if shape.is_polygon()
        )
        # One 3-point triangle (parsed by get_pins) and one 4-point
        # rectangle (decorative -- get_pins skips anything that isn't
        # exactly 3 points).
        assert polygon_point_counts == [3, 4]
        # get_pins only ever returns the triangle -- the rectangle isn't
        # double-counted as a second pin.
        assert len(pins.get_pins(cell, layout)) == 1

    def test_core_width_narrows_only_the_triangle(self):
        layout, cell = _new_layout()
        pins.add_pin(cell, layout, "P1", pya.DPoint(0, 0), 0.0, 20.0, 1, core_width=6.0)

        # get_pins reads the triangle, so PinInfo.width reflects
        # core_width, not the (wider) rectangle's width.
        assert pins.get_pins(cell, layout)[0].width == pytest.approx(6.0)

        pin_li = layout.layer(1, pins.PIN_DATATYPE)
        rectangle_width = next(
            pya.Region(shape.dpolygon.to_itype(layout.dbu)).bbox().to_dtype(layout.dbu).height()
            for shape in cell.shapes(pin_li).each()
            if shape.is_polygon() and len(list(shape.dpolygon.each_point_hull())) == 4
        )
        assert rectangle_width == pytest.approx(20.0)

    def test_unmatched_triangle_raises(self):
        layout, cell = _new_layout()
        # Insert a pin marker triangle with no matching name label.
        pin_li = layout.layer(1, pins.PIN_DATATYPE)
        cell.shapes(pin_li).insert(pya.DPolygon(
            [pya.DPoint(0, 0), pya.DPoint(-1, 2.5), pya.DPoint(-1, -2.5)]))
        with pytest.raises(KcqConfigError):
            pins.get_pins(cell, layout)

    def test_empty_cell_has_no_pins(self):
        layout, cell = _new_layout()
        assert pins.get_pins(cell, layout) == []


class TestLevelOf:
    def test_layer_1_is_level_1(self):
        assert pins.level_of(1) == 1

    def test_layer_9_is_level_1(self):
        assert pins.level_of(9) == 1

    def test_layer_10_is_level_2(self):
        assert pins.level_of(10) == 2

    def test_layer_19_is_level_2(self):
        assert pins.level_of(19) == 2


class TestCheckAlignment:
    def test_opposite_facing_pins_are_aligned(self):
        a = pins.PinInfo(name="A", position=pya.DPoint(0, 0), angle_deg=0.0, width=10.0, layer_num=1)
        b = pins.PinInfo(name="B", position=pya.DPoint(100, 0), angle_deg=180.0, width=10.0, layer_num=1)
        assert pins.check_alignment(a, b) is True

    def test_same_facing_pins_are_not_aligned(self):
        a = pins.PinInfo(name="A", position=pya.DPoint(0, 0), angle_deg=0.0, width=10.0, layer_num=1)
        b = pins.PinInfo(name="B", position=pya.DPoint(100, 0), angle_deg=0.0, width=10.0, layer_num=1)
        assert pins.check_alignment(a, b) is False

    def test_within_tolerance(self):
        a = pins.PinInfo(name="A", position=pya.DPoint(0, 0), angle_deg=0.0, width=10.0, layer_num=1)
        b = pins.PinInfo(name="B", position=pya.DPoint(100, 0), angle_deg=180.05, width=10.0, layer_num=1)
        assert pins.check_alignment(a, b, tolerance_deg=0.1) is True
        assert pins.check_alignment(a, b, tolerance_deg=0.01) is False

    def test_wraparound_near_zero(self):
        a = pins.PinInfo(name="A", position=pya.DPoint(0, 0), angle_deg=350.0, width=10.0, layer_num=1)
        b = pins.PinInfo(name="B", position=pya.DPoint(100, 0), angle_deg=170.05, width=10.0, layer_num=1)
        assert pins.check_alignment(a, b, tolerance_deg=0.1) is True
