import pya
import pytest

from kcq.gui import waveguide_chain, waveguide_extend
from kcq.utils import pcell_loader
from kcq.utils.errors import InvalidGeometryError


class TestComputeNodeExtend:
    def test_extends_p2_free_end_along_last_segment_heading(self):
        points = [pya.DPoint(0, 0), pya.DPoint(300, 0)]
        new_points = waveguide_extend.compute_node_extend(points, extend_p1=False, extend_p2=True, delta=50.0)
        assert new_points[0] == pya.DPoint(0, 0)
        assert new_points[-1].x == pytest.approx(350.0)
        assert new_points[-1].y == pytest.approx(0.0)

    def test_extends_p1_free_end_along_last_segment_heading(self):
        points = [pya.DPoint(0, 0), pya.DPoint(300, 0)]
        new_points = waveguide_extend.compute_node_extend(points, extend_p1=True, extend_p2=False, delta=50.0)
        assert new_points[-1] == pya.DPoint(300, 0)
        assert new_points[0].x == pytest.approx(-50.0)
        assert new_points[0].y == pytest.approx(0.0)

    def test_splits_delta_evenly_when_both_ends_free(self):
        points = [pya.DPoint(0, 0), pya.DPoint(300, 0)]
        new_points = waveguide_extend.compute_node_extend(points, extend_p1=True, extend_p2=True, delta=50.0)
        assert new_points[0].x == pytest.approx(-25.0)
        assert new_points[-1].x == pytest.approx(325.0)

    def test_shrinks_when_delta_is_negative(self):
        points = [pya.DPoint(0, 0), pya.DPoint(300, 0)]
        new_points = waveguide_extend.compute_node_extend(points, extend_p1=False, extend_p2=True, delta=-50.0)
        assert new_points[-1].x == pytest.approx(250.0)

    def test_does_not_move_interior_points(self):
        points = [pya.DPoint(0, 0), pya.DPoint(200, 0), pya.DPoint(200, 150)]
        new_points = waveguide_extend.compute_node_extend(points, extend_p1=False, extend_p2=True, delta=50.0)
        assert new_points[1] == pya.DPoint(200, 0)
        assert new_points[0] == pya.DPoint(0, 0)
        assert new_points[-1].x == pytest.approx(200.0)
        assert new_points[-1].y == pytest.approx(200.0)  # heading (200,0)->(200,150) is +y, 150+50=200

    def test_raises_when_neither_end_is_free(self):
        points = [pya.DPoint(0, 0), pya.DPoint(300, 0)]
        with pytest.raises(InvalidGeometryError):
            waveguide_extend.compute_node_extend(points, extend_p1=False, extend_p2=False, delta=50.0)

    def test_raises_when_shrink_collapses_segment(self):
        points = [pya.DPoint(0, 0), pya.DPoint(300, 0)]
        with pytest.raises(InvalidGeometryError):
            waveguide_extend.compute_node_extend(points, extend_p1=False, extend_p2=True, delta=-400.0)


@pytest.fixture(scope="module", autouse=True)
def _register_kcq_library():
    pcell_loader.register_library("kcq")


def _new_layout():
    layout = pya.Layout()
    layout.dbu = 0.001
    layout.technology_name = "kcq"
    top = layout.create_cell("TOP")
    return layout, top


def _waveguide_instance(layout, top, p_start, p_end, cpw_name="feedline", tech_name="kcq"):
    cell = layout.create_cell("Waveguide", tech_name, {
        "path": pya.DPath([pya.DPoint(*p_start), pya.DPoint(*p_end)], 1.0),
        "cpw_name": cpw_name,
        "tech_name": tech_name,
    })
    return top.insert(pya.CellInstArray(cell.cell_index(), pya.Trans()))


class TestExtendInstance:
    def test_extends_standalone_waveguide_to_target_length(self):
        layout, top = _new_layout()
        inst = _waveguide_instance(layout, top, (0, 0), (300, 0))

        new_length = waveguide_extend.extend_instance(top, layout, inst, 400.0)

        assert new_length == pytest.approx(400.0, abs=1e-2)
        assert waveguide_chain.core_length(inst, layout) == pytest.approx(400.0, abs=1e-2)

    def test_extends_free_end_of_chained_waveguide_to_hit_total(self):
        layout, top = _new_layout()
        wg1 = _waveguide_instance(layout, top, (0, 0), (300, 0))    # P1 free, P2 -> wg2
        wg2 = _waveguide_instance(layout, top, (300, 0), (650, 0))  # P1 -> wg1, P2 free

        # wg1 own=300, wg2 own=350 -> chain total=650. Target the chain to
        # 900 total by editing wg2, whose P2 is the chain's only free end.
        new_own_length = waveguide_extend.extend_instance(top, layout, wg2, 900.0)

        assert new_own_length == pytest.approx(600.0, abs=1e-2)  # 900 - wg1's 300
        chain = waveguide_chain.walk_chain(top, layout, wg1)
        assert chain.extended_length == pytest.approx(900.0, abs=1e-2)

    def test_raises_when_both_ends_are_connected(self):
        layout, top = _new_layout()
        _wg1 = _waveguide_instance(layout, top, (0, 0), (300, 0))
        wg2 = _waveguide_instance(layout, top, (300, 0), (650, 0))
        _wg3 = _waveguide_instance(layout, top, (650, 0), (900, 0))

        with pytest.raises(InvalidGeometryError):
            waveguide_extend.extend_instance(top, layout, wg2, 1000.0)

    def test_raises_when_target_unreachable(self):
        layout, top = _new_layout()
        _wg1 = _waveguide_instance(layout, top, (0, 0), (300, 0))
        wg2 = _waveguide_instance(layout, top, (300, 0), (650, 0))

        # The rest of the chain (wg1, 300um) alone already exceeds this
        # target, so wg2's own contribution would have to be negative.
        with pytest.raises(InvalidGeometryError):
            waveguide_extend.extend_instance(top, layout, wg2, 100.0)
