import pya
import pytest

from kcq.utils import pcell_loader

JJ_LAYER = (2, 0)
CAP_LAYER = (1, 1)
ADD_LAYER = (131, 1)


@pytest.fixture(scope="module", autouse=True)
def _register_kcq_library():
    pcell_loader.register_library("kcq")


def _new_layout():
    layout = pya.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")
    return layout, top


class TestManhattan:
    def test_registers_and_produces_junction_geometry(self):
        layout, top = _new_layout()
        cell = layout.create_cell("Manhattan", "kcq", {
            "junction_width_t": 0.1, "junction_width_b": 0.2, "angle": 0.0,
            "draw_cap": False, "patch_scratch": False,
        })
        assert cell is not None
        jj_li = layout.layer(*JJ_LAYER)
        assert not cell.shapes(jj_li).is_empty()

    def test_angle_is_clamped_to_plus_minus_60(self):
        # cell.pcell_parameters() reflects the pre-coercion input, not
        # coerce_parameters_impl's mutation (confirmed directly against
        # this project's klayout package) -- cell.pcell_declaration()
        # returns the live registered instance, so exercise the coercion
        # logic directly on it, which is what actually governs produce_impl.
        layout, top = _new_layout()
        cell = layout.create_cell("Manhattan", "kcq", {"angle": 0.0})
        decl = cell.pcell_declaration()

        decl.angle = 200.0
        decl.coerce_parameters_impl()
        assert decl.angle == pytest.approx(60.0)

        decl.angle = -200.0
        decl.coerce_parameters_impl()
        assert decl.angle == pytest.approx(-60.0)

    @pytest.mark.parametrize("negative_resist", [False, True])
    def test_test_pad_polarity_variants_do_not_raise(self, negative_resist):
        layout, top = _new_layout()
        cell = layout.create_cell("Manhattan", "kcq", {
            "junction_width_t": 0.1, "junction_width_b": 0.2, "angle": 0.0,
            "draw_cap": True, "patch_scratch": False, "negative_resist": negative_resist,
        })
        assert cell is not None
        cap_li = layout.layer(*CAP_LAYER)
        add_li = layout.layer(*ADD_LAYER)
        assert not cell.shapes(cap_li).is_empty()
        assert not cell.shapes(add_li).is_empty()

    def test_zero_size_connectors_skip_connector_geometry(self):
        layout, top = _new_layout()
        cell = layout.create_cell("Manhattan", "kcq", {"conn_width": 0.0, "conn_height": 0.0})
        assert cell is not None  # must not raise


class TestManhattanSQUID:
    def test_registers_and_creates_two_manhattan_sub_instances(self):
        layout, top = _new_layout()
        cell = layout.create_cell("ManhattanSQUID", "kcq", {
            "junction_width_t": 0.1, "junction_width_b": 0.2, "angle": 0.0,
            "squid_spacing": 20.0, "squid_asymmetry": 1.0,
            "draw_cap": True, "draw_patch": True,
        })
        assert cell is not None
        insts = list(cell.each_inst())
        manhattan_insts = [
            inst for inst in insts
            if inst.cell.pcell_declaration() is not None
            and inst.cell.pcell_declaration().name() == "Manhattan"
        ]
        assert len(manhattan_insts) == 2

    def test_junction_geometry_present_in_both_sub_instances(self):
        layout, top = _new_layout()
        cell = layout.create_cell("ManhattanSQUID", "kcq", {
            "junction_width_t": 0.1, "junction_width_b": 0.2, "angle": 0.0,
            "squid_spacing": 20.0, "draw_cap": False,
        })
        assert cell is not None
        jj_li = layout.layer(*JJ_LAYER)
        region = pya.Region(pya.RecursiveShapeIterator(layout, cell, jj_li))
        assert region.area() > 0

    def test_asymmetry_scales_junction_widths_between_sub_instances(self):
        layout, top = _new_layout()
        cell = layout.create_cell("ManhattanSQUID", "kcq", {
            "junction_width_t": 0.1, "junction_width_b": 0.1, "angle": 0.0,
            "squid_spacing": 20.0, "squid_asymmetry": 2.0, "draw_cap": False,
        })
        assert cell is not None
        insts = list(cell.each_inst())
        widths = set()
        for inst in insts:
            decl = inst.cell.pcell_declaration()
            if decl is None or decl.name() != "Manhattan":
                continue
            params = dict(zip([p.name for p in decl.get_parameters()], inst.cell.pcell_parameters()))
            widths.add(round(params["junction_width_t"], 6))
        assert widths == {0.1, 0.2}

    def test_minimum_squid_spacing_enforced(self):
        # cell.pcell_declaration() returns the one shared declaration
        # instance registered for this PCell type (register_pcell
        # registers a single object, not one per create_cell call) -- so,
        # as with the Manhattan angle-clamp test above, set every
        # attribute coerce_parameters_impl reads directly, rather than
        # relying on it having been "passed via create_cell params".
        layout, top = _new_layout()
        cell = layout.create_cell("ManhattanSQUID", "kcq", {"draw_cap": False})
        decl = cell.pcell_declaration()

        decl.angle = 0.0
        decl.squid_asymmetry = 1.0
        decl.draw_cap = False
        decl.cap_w = 240.0
        decl.conn_width = 8.0
        decl.squid_spacing = 1.0
        decl.coerce_parameters_impl()
        assert decl.squid_spacing >= decl.conn_width

    def test_reflected_junction_type_does_not_raise(self):
        layout, top = _new_layout()
        cell = layout.create_cell("ManhattanSQUID", "kcq", {"junction_type": 1, "draw_cap": False})
        assert cell is not None
