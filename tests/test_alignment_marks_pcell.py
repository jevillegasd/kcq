"""Tests for the AlignmentMarks PCell (tech/kcq/pcells/AlignmentMarks.py)
-- a "+" target mark stamped across a Level's physical layers, with an
optional flip-chip counterpart.
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
    cell = layout.create_cell("AlignmentMarks", "kcq", params or {})
    top.insert(pya.CellInstArray(cell.cell_index(), pya.Trans()))
    return cell


class TestAlignmentMarksRegistration:
    def test_registered_in_the_kcq_pcell_library(self):
        layout, top = _new_layout()
        assert _place(layout, top) is not None


class TestAlignmentMarksLayers:
    def test_cross_present_on_every_listed_layer(self):
        layout, top = _new_layout()
        cell = _place(layout, top, {"layers": [1, 2, 6]})
        for layer_num in (1, 2, 6):
            region = pya.Region(cell.shapes(layout.layer(layer_num, 0)))
            assert not region.is_empty()

    def test_blockage_only_on_first_listed_layer(self):
        layout, top = _new_layout()
        cell = _place(layout, top, {"layers": [1, 2]})
        first_blockage = pya.Region(cell.shapes(layout.layer(1, 5)))
        second_blockage = pya.Region(cell.shapes(layout.layer(2, 5)))
        assert not first_blockage.is_empty()
        assert second_blockage.is_empty()

    def test_flip_chip_mark_absent_by_default(self):
        layout, top = _new_layout()
        cell = _place(layout, top, {"flip_chip_layer": 10})
        flip_region = pya.Region(cell.shapes(layout.layer(10, 0)))
        assert flip_region.is_empty()

    def test_flip_chip_mark_present_when_requested(self):
        layout, top = _new_layout()
        cell = _place(layout, top, {"include_flip_chip_mark": True, "flip_chip_layer": 10})
        flip_region = pya.Region(cell.shapes(layout.layer(10, 0)))
        assert not flip_region.is_empty()
