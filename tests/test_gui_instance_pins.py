import pya
import pytest

from kcq.geometry import pins
from kcq.gui import instance_pins


def _new_layout():
    layout = pya.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")
    return layout, top


def _int_trans(layout, x, y):
    # See tests/test_gui_snap.py's _int_trans for why this manual dbu
    # conversion (not a raw DTrans) is required for CellInstArray.
    return pya.Trans(int(round(x / layout.dbu)), int(round(y / layout.dbu)))


def _component_cell(layout, name, pin_angle_deg, pin_position=(0.0, 0.0), width=5.0):
    cell = layout.create_cell(name)
    pins.add_pin(cell, layout, "P1", pya.DPoint(*pin_position), pin_angle_deg, width, 1)
    return cell


class TestGlobalPins:
    def test_transforms_local_pin_by_instance_placement(self):
        layout, top = _new_layout()
        comp = _component_cell(layout, "A", pin_angle_deg=0.0)
        inst = top.insert(pya.CellInstArray(comp.cell_index(), _int_trans(layout, 10.0, 20.0)))

        result = instance_pins.global_pins(layout, inst)

        assert len(result) == 1
        assert result[0].position.x == pytest.approx(10.0)
        assert result[0].position.y == pytest.approx(20.0)
        assert result[0].angle_deg == pytest.approx(0.0)


class TestFindNearestPin:
    def test_finds_pin_regardless_of_orientation(self):
        # Unlike kcq.gui.snap.find_snap_delta, find_nearest_pin does not
        # filter by opposite orientation -- a same-facing pin still counts.
        layout, top = _new_layout()
        comp = _component_cell(layout, "A", pin_angle_deg=0.0)
        inst = top.insert(pya.CellInstArray(comp.cell_index(), _int_trans(layout, 50.0, 0.0)))

        result = instance_pins.find_nearest_pin(layout, top, pya.DPoint(0, 0), max_distance=500.0)

        assert result is not None
        assert result.position.x == pytest.approx(50.0)

    def test_picks_closest_among_multiple(self):
        layout, top = _new_layout()
        far = _component_cell(layout, "Far", pin_angle_deg=0.0)
        near = _component_cell(layout, "Near", pin_angle_deg=180.0)
        top.insert(pya.CellInstArray(far.cell_index(), _int_trans(layout, 400.0, 0.0)))
        top.insert(pya.CellInstArray(near.cell_index(), _int_trans(layout, 40.0, 0.0)))

        result = instance_pins.find_nearest_pin(layout, top, pya.DPoint(0, 0), max_distance=500.0)

        assert result.position.x == pytest.approx(40.0)

    def test_returns_none_outside_max_distance(self):
        layout, top = _new_layout()
        comp = _component_cell(layout, "A", pin_angle_deg=0.0)
        top.insert(pya.CellInstArray(comp.cell_index(), _int_trans(layout, 600.0, 0.0)))

        result = instance_pins.find_nearest_pin(layout, top, pya.DPoint(0, 0), max_distance=500.0)

        assert result is None

    def test_returns_none_for_empty_cell(self):
        layout, top = _new_layout()
        assert instance_pins.find_nearest_pin(layout, top, pya.DPoint(0, 0), max_distance=500.0) is None
