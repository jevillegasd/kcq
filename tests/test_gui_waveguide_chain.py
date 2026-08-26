import pya
import pytest

from kcq.geometry import pins
from kcq.gui import waveguide_chain
from kcq.utils import pcell_loader
from kcq.utils.errors import KcqConfigError


@pytest.fixture(scope="module", autouse=True)
def _register_kcq_library():
    pcell_loader.register_library("kcq")


def _new_layout():
    layout = pya.Layout()
    layout.dbu = 0.001
    layout.technology_name = "kcq"
    top = layout.create_cell("TOP")
    return layout, top


def _int_trans(layout, x, y):
    # See tests/test_gui_snap.py's _int_trans for why this manual dbu
    # conversion (not a raw DTrans) is required for CellInstArray.
    return pya.Trans(int(round(x / layout.dbu)), int(round(y / layout.dbu)))


def _waveguide_instance(layout, top, p_start, p_end, cpw_name="feedline", tech_name="kcq"):
    cell = layout.create_cell("Waveguide", tech_name, {
        "path": pya.DPath([pya.DPoint(*p_start), pya.DPoint(*p_end)], 1.0),
        "cpw_name": cpw_name,
        "tech_name": tech_name,
    })
    return top.insert(pya.CellInstArray(cell.cell_index(), pya.Trans()))


class TestIsWaveguideInstance:
    def test_true_for_waveguide_pcell(self):
        layout, top = _new_layout()
        inst = _waveguide_instance(layout, top, (0, 0), (300, 0))
        assert waveguide_chain.is_waveguide_instance(inst) is True

    def test_false_for_non_pcell_instance(self):
        layout, top = _new_layout()
        other = layout.create_cell("Launcher")
        inst = top.insert(pya.CellInstArray(other.cell_index(), pya.Trans()))
        assert waveguide_chain.is_waveguide_instance(inst) is False


class TestCoreLength:
    def test_straight_waveguide_length_matches_span(self):
        layout, top = _new_layout()
        inst = _waveguide_instance(layout, top, (0, 0), (300, 0))
        assert waveguide_chain.core_length(inst, layout) == pytest.approx(300.0, abs=1e-2)

    def test_raises_for_non_waveguide_instance(self):
        layout, top = _new_layout()
        other = layout.create_cell("Launcher")
        inst = top.insert(pya.CellInstArray(other.cell_index(), pya.Trans()))
        with pytest.raises(KcqConfigError):
            waveguide_chain.core_length(inst, layout)


class TestWalkChain:
    def test_standalone_waveguide_has_no_chain(self):
        layout, top = _new_layout()
        inst = _waveguide_instance(layout, top, (0, 0), (300, 0))

        result = waveguide_chain.walk_chain(top, layout, inst)

        assert result.own_length == pytest.approx(300.0, abs=1e-2)
        assert result.p1_free is True
        assert result.p2_free is True
        assert result.p1_chain_length == 0.0
        assert result.p2_chain_length == 0.0
        assert result.is_chained is False
        assert result.extended_length == pytest.approx(300.0, abs=1e-2)

    def test_two_chained_waveguides_sum_lengths_from_either_end(self):
        layout, top = _new_layout()
        # wg1's P2 (300,0) is oriented 0deg (outward, +x); wg2's P1 (300,0)
        # is oriented 180deg (outward, -x) -- opposite, so they connect.
        wg1 = _waveguide_instance(layout, top, (0, 0), (300, 0))
        wg2 = _waveguide_instance(layout, top, (300, 0), (650, 0))

        result1 = waveguide_chain.walk_chain(top, layout, wg1)
        assert result1.p1_free is True
        assert result1.p2_free is False
        assert result1.p2_neighbor == wg2
        assert result1.p2_chain_length == pytest.approx(350.0, abs=1e-2)
        assert result1.extended_length == pytest.approx(650.0, abs=1e-2)

        result2 = waveguide_chain.walk_chain(top, layout, wg2)
        assert result2.p1_free is False
        assert result2.p1_neighbor == wg1
        assert result2.p2_free is True
        assert result2.p1_chain_length == pytest.approx(300.0, abs=1e-2)
        assert result2.extended_length == pytest.approx(650.0, abs=1e-2)

    def test_chain_stops_at_non_waveguide_neighbor(self):
        layout, top = _new_layout()
        wg1 = _waveguide_instance(layout, top, (0, 0), (300, 0))
        wg2 = _waveguide_instance(layout, top, (300, 0), (650, 0))

        launcher = layout.create_cell("Launcher")
        pins.add_pin(launcher, layout, "P1", pya.DPoint(0, 0), 180.0, 10.0, 1)
        launcher_inst = top.insert(pya.CellInstArray(launcher.cell_index(), _int_trans(layout, 650.0, 0.0)))

        result = waveguide_chain.walk_chain(top, layout, wg2)
        assert result.p2_free is False
        assert result.p2_neighbor == launcher_inst
        # The launcher isn't a Waveguide, so the chain doesn't extend
        # through it -- only wg1's length (via P1) counts.
        assert result.p2_chain_length == 0.0
        assert result.p1_chain_length == pytest.approx(300.0, abs=1e-2)
        assert result.extended_length == pytest.approx(650.0, abs=1e-2)

    def test_three_chained_waveguides_sum_across_whole_chain(self):
        layout, top = _new_layout()
        wg1 = _waveguide_instance(layout, top, (0, 0), (200, 0))
        wg2 = _waveguide_instance(layout, top, (200, 0), (500, 0))
        wg3 = _waveguide_instance(layout, top, (500, 0), (900, 0))

        result = waveguide_chain.walk_chain(top, layout, wg2)
        assert result.p1_chain_length == pytest.approx(200.0, abs=1e-2)
        assert result.p2_chain_length == pytest.approx(400.0, abs=1e-2)
        assert result.extended_length == pytest.approx(900.0, abs=1e-2)
        assert wg1 is not None and wg3 is not None  # sanity: both ends participate
