import pya
import pytest

from kcq.geometry import pins
from kcq.gui import path_to_waveguide, waveguide_chain
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


def _component_cell(layout, name, pin_angle_deg, pin_position=(0.0, 0.0), width=5.0):
    cell = layout.create_cell(name)
    pins.add_pin(cell, layout, "P1", pya.DPoint(*pin_position), pin_angle_deg, width, 1)
    return cell


class TestConvertPath:
    def test_converts_path_into_waveguide_instance(self):
        layout, top = _new_layout()
        dpath = pya.DPath([pya.DPoint(0, 0), pya.DPoint(300, 0)], 20.0)

        inst = path_to_waveguide.convert_path(top, layout, dpath, "feedline", "kcq")

        assert waveguide_chain.is_waveguide_instance(inst) is True
        params = inst.pcell_parameters_by_name()
        assert params["cpw_name"] == "feedline"
        assert params["tech_name"] == "kcq"
        assert waveguide_chain.core_length(inst, layout) == pytest.approx(300.0, abs=1e-2)

    def test_drawn_path_width_is_irrelevant_to_built_geometry(self):
        # The Waveguide PCell always sizes itself from waveguides.xml, not
        # from the drawn path's own width. If the built trace had instead
        # used the drawn width (999 -- wildly larger than feedline's real
        # 10um trace_width), core_length's area/trace_width computation
        # would come out far from 300, not match it.
        layout, top = _new_layout()
        dpath = pya.DPath([pya.DPoint(0, 0), pya.DPoint(300, 0)], 999.0)

        inst = path_to_waveguide.convert_path(top, layout, dpath, "feedline", "kcq")

        assert inst.pcell_parameters_by_name()["path"].width == pytest.approx(999.0)
        assert waveguide_chain.core_length(inst, layout) == pytest.approx(300.0, abs=1e-2)

    def test_multi_point_path_preserves_waypoints(self):
        layout, top = _new_layout()
        # Both legs well over feedline's ~187um bend tangent requirement
        # (100um default bend radius) so the corner actually fits.
        dpath = pya.DPath([pya.DPoint(0, 0), pya.DPoint(400, 0), pya.DPoint(400, 400)], 1.0)

        inst = path_to_waveguide.convert_path(top, layout, dpath, "feedline", "kcq")

        # Shorter than the two straight segments' sum (400+400=800) since
        # the interior corner gets rounded off by the technology's bend
        # radius -- same "core area / width" length definition as Measure.
        length = waveguide_chain.core_length(inst, layout)
        assert 0.0 < length < 800.0

    def test_raises_for_degenerate_path(self):
        layout, top = _new_layout()
        dpath = pya.DPath([pya.DPoint(0, 0)], 1.0)
        with pytest.raises(KcqConfigError):
            path_to_waveguide.convert_path(top, layout, dpath, "feedline", "kcq")

    def test_inserted_instance_is_a_direct_child_of_parent_cell(self):
        layout, top = _new_layout()
        dpath = pya.DPath([pya.DPoint(0, 0), pya.DPoint(300, 0)], 1.0)

        inst = path_to_waveguide.convert_path(top, layout, dpath, "feedline", "kcq")

        assert list(top.each_inst()) == [inst]

    def test_end_snaps_onto_nearby_pin_and_connects_for_chain_walking(self):
        # Integration check: after conversion, the new Waveguide's own P2
        # pin should coincide with the target pin closely enough for
        # kcq.gui.waveguide_chain.walk_chain to recognize the connection.
        # max_snap_distance=50 keeps the start (280um from the target) out
        # of range, so only the end (20um away) snaps.
        layout, top = _new_layout()
        target = _component_cell(layout, "Launcher", pin_angle_deg=180.0)
        target_inst = top.insert(pya.CellInstArray(target.cell_index(), _int_trans(layout, 300.0, 0.0)))

        dpath = pya.DPath([pya.DPoint(0, 0), pya.DPoint(280, 0)], 1.0)
        inst = path_to_waveguide.convert_path(top, layout, dpath, "feedline", "kcq",
                                               max_snap_distance=50.0)

        assert waveguide_chain.core_length(inst, layout) == pytest.approx(300.0, abs=1e-2)
        chain = waveguide_chain.walk_chain(top, layout, inst)
        assert chain.p2_free is False
        assert chain.p2_neighbor == target_inst


class TestProjectEndpoint:
    def test_target_already_on_ray_lands_exactly(self):
        result = path_to_waveguide._project_endpoint(pya.DPoint(0, 0), 0.0, pya.DPoint(50, 0))
        assert result.x == pytest.approx(50.0)
        assert result.y == pytest.approx(0.0)

    def test_off_ray_target_is_projected_onto_heading(self):
        result = path_to_waveguide._project_endpoint(pya.DPoint(0, 0), 0.0, pya.DPoint(50, 30))
        assert result.x == pytest.approx(50.0)
        assert result.y == pytest.approx(0.0)

    def test_perpendicular_heading(self):
        result = path_to_waveguide._project_endpoint(pya.DPoint(0, 0), 90.0, pya.DPoint(30, 80))
        assert result.x == pytest.approx(0.0)
        assert result.y == pytest.approx(80.0)

    def test_clamps_to_minimum_standoff_when_target_is_behind(self):
        result = path_to_waveguide._project_endpoint(pya.DPoint(0, 0), 0.0, pya.DPoint(-30, 0))
        assert 0.0 < result.x <= 1e-2
        assert result.y == pytest.approx(0.0)


class TestSnapPathEndpoints:
    def test_matching_angle_end_slides_to_meet_pin_without_reorienting(self):
        layout, top = _new_layout()
        # Pin faces -x (180deg) -> required heading for the path's end is
        # 0deg (+x), which already matches this path's own end heading.
        # max_distance=80 keeps the start (150um away) out of range while
        # the end (50um away) stays in range, isolating this to one end.
        target = _component_cell(layout, "A", pin_angle_deg=180.0)
        top.insert(pya.CellInstArray(target.cell_index(), _int_trans(layout, 150.0, 0.0)))
        points = [pya.DPoint(0, 0), pya.DPoint(100, 0)]

        result = path_to_waveguide.snap_path_endpoints(layout, top, points, max_distance=80.0)

        assert result[0] == pya.DPoint(0, 0)
        assert result[-1].x == pytest.approx(150.0)
        assert result[-1].y == pytest.approx(0.0)

    def test_differing_angle_end_is_reoriented_toward_pin(self):
        layout, top = _new_layout()
        # Pin faces -y (270deg) -> required heading is 90deg (+y), which
        # differs from this path's own end heading of 0deg (+x).
        # max_distance=100 keeps the start (~136um away) out of range
        # while the end (~80.6um away) stays in range.
        target = _component_cell(layout, "B", pin_angle_deg=270.0)
        top.insert(pya.CellInstArray(target.cell_index(), _int_trans(layout, 110.0, 80.0)))
        points = [pya.DPoint(0, 0), pya.DPoint(100, 0)]

        result = path_to_waveguide.snap_path_endpoints(layout, top, points, max_distance=100.0)

        assert result[0] == pya.DPoint(0, 0)
        assert result[-1].x == pytest.approx(0.0, abs=1e-6)
        assert result[-1].y == pytest.approx(80.0)

    def test_both_ends_near_a_single_pin_only_one_claims_it(self):
        # Without the mutual-exclusion, both ends would independently snap
        # onto this one pin and collapse the path to a near-zero stub.
        layout, top = _new_layout()
        target = _component_cell(layout, "A", pin_angle_deg=180.0)
        top.insert(pya.CellInstArray(target.cell_index(), _int_trans(layout, 200.0, 0.0)))
        points = [pya.DPoint(0, 0), pya.DPoint(100, 0)]

        result = path_to_waveguide.snap_path_endpoints(layout, top, points)

        # Start (closer to its own pivot-free original position) claims
        # the pin; the end's search excludes it and finds nothing, so it
        # stays at its original position.
        assert result[0].x == pytest.approx(200.0)
        assert result[0].y == pytest.approx(0.0)
        assert result[-1] == pya.DPoint(100, 0)
        assert result[0].distance(result[-1]) > 1.0

    def test_no_pin_in_range_is_a_no_op(self):
        layout, top = _new_layout()
        points = [pya.DPoint(0, 0), pya.DPoint(100, 0)]

        result = path_to_waveguide.snap_path_endpoints(layout, top, points)

        assert result == points

    def test_both_ends_snap_independently_on_a_multi_point_path(self):
        layout, top = _new_layout()
        start_target = _component_cell(layout, "Start", pin_angle_deg=0.0)
        end_target = _component_cell(layout, "End", pin_angle_deg=180.0)
        top.insert(pya.CellInstArray(start_target.cell_index(), _int_trans(layout, -200.0, 0.0)))
        top.insert(pya.CellInstArray(end_target.cell_index(), _int_trans(layout, 500.0, 200.0)))
        points = [pya.DPoint(0, 0), pya.DPoint(200, 0), pya.DPoint(200, 200), pya.DPoint(400, 200)]

        result = path_to_waveguide.snap_path_endpoints(layout, top, points)

        # Start end: required heading 180deg, pivoting about points[1]=(200,0).
        assert result[0].x == pytest.approx(-200.0)
        assert result[0].y == pytest.approx(0.0)
        # End: required heading 0deg, pivoting about points[-2]=(200,200)
        # (unaffected by the start snap, since this path has 4 distinct points).
        assert result[-1].x == pytest.approx(500.0)
        assert result[-1].y == pytest.approx(200.0)
        # Interior points untouched.
        assert result[1] == pya.DPoint(200, 0)
        assert result[2] == pya.DPoint(200, 200)

    def test_raises_for_degenerate_path(self):
        layout, top = _new_layout()
        with pytest.raises(KcqConfigError):
            path_to_waveguide.snap_path_endpoints(layout, top, [pya.DPoint(0, 0)])
