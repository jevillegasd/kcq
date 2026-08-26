import pya
import pytest

from kcq.geometry import pins
from kcq.gui import snap


def _new_layout():
    layout = pya.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")
    return layout, top


def _int_trans(layout, x, y):
    # CellInstArray/Cell.insert only accept integer (database-unit) Trans --
    # a raw pya.DTrans passed to CellInstArray silently mis-scales (its
    # fields are read as already-integer database units, not converted
    # from microns), unlike Instance.transform(DTrans), which does
    # interpret its argument in microns. Same manual conversion
    # tests/test_pdk_integration.py already uses.
    return pya.Trans(int(round(x / layout.dbu)), int(round(y / layout.dbu)))


def _component_cell(layout, name, pin_angle_deg, pin_position=(0.0, 0.0), width=5.0):
    cell = layout.create_cell(name)
    pins.add_pin(cell, layout, "P1", pya.DPoint(*pin_position), pin_angle_deg, width, 1)
    return cell


class TestFindSnapDelta:
    def test_snaps_to_nearest_opposite_pin(self):
        layout, top = _new_layout()
        comp_a = _component_cell(layout, "A", pin_angle_deg=0.0)
        comp_b = _component_cell(layout, "B", pin_angle_deg=180.0)

        inst_a = top.insert(pya.CellInstArray(comp_a.cell_index(), _int_trans(layout, 0.0, 0.0)))
        inst_b = top.insert(pya.CellInstArray(comp_b.cell_index(), _int_trans(layout, 105.0, 3.0)))

        delta = snap.find_snap_delta(layout, inst_b, [inst_a])
        assert delta is not None
        assert delta.x == pytest.approx(-105.0, abs=1e-3)
        assert delta.y == pytest.approx(-3.0, abs=1e-3)

    def test_returns_none_when_no_pin_within_range(self):
        layout, top = _new_layout()
        comp_a = _component_cell(layout, "A", pin_angle_deg=0.0)
        comp_b = _component_cell(layout, "B", pin_angle_deg=180.0)

        inst_a = top.insert(pya.CellInstArray(comp_a.cell_index(), _int_trans(layout, 0.0, 0.0)))
        inst_b = top.insert(pya.CellInstArray(
            comp_b.cell_index(), _int_trans(layout, snap.MAX_SNAP_DISTANCE_UM + 100.0, 0.0)))

        assert snap.find_snap_delta(layout, inst_b, [inst_a]) is None

    def test_returns_none_when_no_pin_is_oppositely_oriented(self):
        layout, top = _new_layout()
        # Both pins face the same direction (0 deg) -- never a valid match.
        comp_a = _component_cell(layout, "A", pin_angle_deg=0.0)
        comp_b = _component_cell(layout, "B", pin_angle_deg=0.0)

        inst_a = top.insert(pya.CellInstArray(comp_a.cell_index(), _int_trans(layout, 0.0, 0.0)))
        inst_b = top.insert(pya.CellInstArray(comp_b.cell_index(), _int_trans(layout, 105.0, 0.0)))

        assert snap.find_snap_delta(layout, inst_b, [inst_a]) is None

    def test_picks_closest_among_multiple_matching_siblings(self):
        layout, top = _new_layout()
        comp_far = _component_cell(layout, "Far", pin_angle_deg=180.0)
        comp_near = _component_cell(layout, "Near", pin_angle_deg=180.0)
        comp_selected = _component_cell(layout, "Selected", pin_angle_deg=0.0)

        inst_far = top.insert(pya.CellInstArray(comp_far.cell_index(), _int_trans(layout, 400.0, 0.0)))
        inst_near = top.insert(pya.CellInstArray(comp_near.cell_index(), _int_trans(layout, 50.0, 0.0)))
        inst_selected = top.insert(
            pya.CellInstArray(comp_selected.cell_index(), _int_trans(layout, 0.0, 0.0)))

        delta = snap.find_snap_delta(layout, inst_selected, [inst_far, inst_near])
        assert delta.x == pytest.approx(50.0, abs=1e-3)
        assert delta.y == pytest.approx(0.0, abs=1e-3)

    def test_returns_none_when_selected_instance_has_no_pins(self):
        layout, top = _new_layout()
        comp_a = _component_cell(layout, "A", pin_angle_deg=0.0)
        blank = layout.create_cell("Blank")

        inst_a = top.insert(pya.CellInstArray(comp_a.cell_index(), _int_trans(layout, 0.0, 0.0)))
        inst_blank = top.insert(pya.CellInstArray(blank.cell_index(), _int_trans(layout, 5.0, 0.0)))

        assert snap.find_snap_delta(layout, inst_blank, [inst_a]) is None
