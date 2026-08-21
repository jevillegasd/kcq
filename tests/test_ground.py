import pya
import pytest

from kcq.geometry import ground


def _new_layout():
    layout = pya.Layout()
    layout.dbu = 0.001
    cell = layout.create_cell("TOP")
    return layout, cell


class TestRegionFromLayer:
    def test_reads_shapes_via_cell_shapes(self):
        layout, cell = _new_layout()
        li = layout.layer(1, 0)
        cell.shapes(li).insert(pya.Box(0, 0, 1000, 1000))
        region = ground.region_from_layer(cell, li)
        assert not region.is_empty()
        assert region.area() == 1000 * 1000

    def test_empty_layer_gives_empty_region(self):
        layout, cell = _new_layout()
        li = layout.layer(2, 0)
        region = ground.region_from_layer(cell, li)
        assert region.is_empty()


class TestBuildGroundPlane:
    def test_ground_is_outline_minus_keepouts(self):
        layout, cell = _new_layout()
        outline_li = layout.layer(0, 0)
        ground_li = layout.layer(10, 0)
        cell.shapes(outline_li).insert(pya.Box(0, 0, 2_000_000, 1_000_000))

        keepout = pya.Region(pya.Box(0, 400_000, 2_000_000, 600_000))
        ground.build_ground_plane(cell, layout, outline_li, [keepout], ground_li)

        assert not cell.shapes(ground_li).is_empty()
        result = pya.Region(cell.shapes(ground_li))
        expected_area = 2_000_000 * 1_000_000 - 2_000_000 * 200_000
        assert result.area() == expected_area

    def test_multiple_keepouts_are_all_subtracted(self):
        layout, cell = _new_layout()
        outline_li = layout.layer(0, 0)
        ground_li = layout.layer(11, 0)
        cell.shapes(outline_li).insert(pya.Box(0, 0, 1000, 1000))

        keepout_a = pya.Region(pya.Box(0, 0, 100, 100))
        keepout_b = pya.Region(pya.Box(900, 900, 1000, 1000))
        ground.build_ground_plane(cell, layout, outline_li, [keepout_a, keepout_b], ground_li)

        result = pya.Region(cell.shapes(ground_li))
        expected_area = 1000 * 1000 - 100 * 100 - 100 * 100
        assert result.area() == expected_area

    def test_no_keepouts_leaves_outline_unchanged(self):
        layout, cell = _new_layout()
        outline_li = layout.layer(0, 0)
        ground_li = layout.layer(12, 0)
        cell.shapes(outline_li).insert(pya.Box(0, 0, 500, 500))

        ground.build_ground_plane(cell, layout, outline_li, [], ground_li)

        result = pya.Region(cell.shapes(ground_li))
        assert result.area() == 500 * 500

    def test_result_is_merged(self):
        # Two abutting keepouts carved from the same outline can leave
        # coincident edges in the remaining ground region if not merged;
        # merged output should not increase polygon count from touching
        # slivers the way an unmerged boolean result would.
        layout, cell = _new_layout()
        outline_li = layout.layer(0, 0)
        ground_li = layout.layer(13, 0)
        cell.shapes(outline_li).insert(pya.Box(0, 0, 1000, 1000))

        keepout_a = pya.Region(pya.Box(0, 0, 500, 100))
        keepout_b = pya.Region(pya.Box(500, 0, 1000, 100))
        ground.build_ground_plane(cell, layout, outline_li, [keepout_a, keepout_b], ground_li)

        result = pya.Region(cell.shapes(ground_li))
        merged_copy = result.dup()
        merged_copy.merge()
        assert result.count() == merged_copy.count()

    def test_fully_covered_outline_is_empty_but_does_not_raise(self):
        layout, cell = _new_layout()
        outline_li = layout.layer(0, 0)
        ground_li = layout.layer(14, 0)
        cell.shapes(outline_li).insert(pya.Box(0, 0, 100, 100))

        full_keepout = pya.Region(pya.Box(-1000, -1000, 1000, 1000))
        ground.build_ground_plane(cell, layout, outline_li, [full_keepout], ground_li)

        assert cell.shapes(ground_li).is_empty()

    def test_empty_outline_layer_produces_empty_ground_without_raising(self):
        layout, cell = _new_layout()
        outline_li = layout.layer(0, 0)  # nothing inserted here
        ground_li = layout.layer(15, 0)

        ground.build_ground_plane(cell, layout, outline_li, [], ground_li)

        assert cell.shapes(ground_li).is_empty()
