"""Tests for the VernierRuler PCell (tech/kcq/pcells/VernierRuler.py)
-- a two-row vernier comb for verifying alignment between two layers.
"""

import pya
import pytest

from kcq.utils import pcell_loader


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
    cell = layout.create_cell("VernierRuler", "kcq", params or {})
    top.insert(pya.CellInstArray(cell.cell_index(), pya.Trans()))
    return cell


class TestVernierRulerRegistration:
    def test_registered_in_the_kcq_pcell_library(self):
        layout, top = _new_layout()
        assert _place(layout, top) is not None


class TestVernierRulerGeometry:
    def test_tick_count_matches_on_both_rows(self):
        layout, top = _new_layout()
        cell = _place(layout, top, {"tick_count": 7})
        region_a = pya.Region(cell.shapes(layout.layer(1, 0)))
        region_b = pya.Region(cell.shapes(layout.layer(10, 0)))
        assert region_a.count() == 7
        assert region_b.count() == 7

    def test_cumulative_offset_at_last_tick_matches_vernier_step(self):
        layout, top = _new_layout()
        tick_count = 10
        tick_pitch = 10.0
        vernier_step = 1.0
        cell = _place(layout, top, {
            "tick_count": tick_count, "tick_pitch": tick_pitch, "vernier_step": vernier_step,
        })
        region_a = pya.Region(cell.shapes(layout.layer(1, 0)))
        region_b = pya.Region(cell.shapes(layout.layer(10, 0)))

        last_a_center = region_a.bbox().to_dtype(layout.dbu).right - 1.0  # tick_width/2
        last_b_center = region_b.bbox().to_dtype(layout.dbu).right - 1.0
        expected_offset = (tick_count - 1) * vernier_step
        assert (last_a_center - last_b_center) == pytest.approx(expected_offset, abs=0.01)

    def test_layers_are_configurable(self):
        layout, top = _new_layout()
        cell = _place(layout, top, {"layer_a": pya.LayerInfo(3, 0), "layer_b": pya.LayerInfo(4, 0)})
        region_a = pya.Region(cell.shapes(layout.layer(3, 0)))
        region_b = pya.Region(cell.shapes(layout.layer(4, 0)))
        assert not region_a.is_empty()
        assert not region_b.is_empty()
