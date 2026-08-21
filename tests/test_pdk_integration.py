"""End-to-end Phase 3 smoke test: place two Transmon PCell instances and
route between their pins using Phase 2's router + CPW, confirming the
whole default-PDK pipeline (PCells -> pins -> router -> CPW synthesis)
works together, not just each piece in isolation.
"""

import pya
import pytest

from kcq.geometry import cpw, pins, router
from kcq.utils import pcell_loader

TRACE_LAYER = (1, 1)
GAP_LAYER = (1, 0)


@pytest.fixture(scope="module", autouse=True)
def _register_kcq_library():
    pcell_loader.register_library("kcq")


def _global_pin(layout, inst, pin_name):
    """Returns the PinInfo for `pin_name` on `inst`'s cell, transformed
    into the parent cell's coordinate system via the instance's own
    placement transform."""
    local_pins = {p.name: p for p in pins.get_pins(inst.cell, layout)}
    local = local_pins[pin_name]
    trans = inst.dcplx_trans
    global_position = trans * local.position
    global_angle = (local.angle_deg + trans.angle) % 360.0
    return pins.PinInfo(name=local.name, position=global_position,
                         angle_deg=global_angle, width=local.width)


def test_route_between_two_transmons_produces_continuous_cpw():
    layout = pya.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")

    transmon_a = layout.create_cell("Transmon", "kcq", {
        "coupler_island": ["top"], "coupler_side": ["right"],
    })
    transmon_b = layout.create_cell("Transmon", "kcq", {
        "coupler_island": ["top"], "coupler_side": ["left"],
    })

    inst_a = top.insert(pya.CellInstArray(transmon_a.cell_index(), pya.Trans(0, 0)))
    inst_b = top.insert(pya.CellInstArray(
        transmon_b.cell_index(), pya.Trans(int(2000.0 / layout.dbu), 0)))

    pin_a = _global_pin(layout, inst_a, "C0")
    pin_b = _global_pin(layout, inst_b, "C0")

    # The two ports face each other (a's coupler exits right/0deg, b's
    # exits left/180deg, and b sits to a's right), so route_octilinear
    # should resolve a direct straight connection.
    waypoints = router.route_octilinear(pin_a.position, pin_a.angle_deg,
                                         pin_b.position, pin_b.angle_deg,
                                         bend_radius=100.0)
    assert waypoints[0] == pin_a.position
    assert waypoints[-1] == pin_b.position

    resonator = cpw.CPW("kcq", "resonator", waypoints)
    resonator.build(top, layout)

    trace_li = layout.layer(*TRACE_LAYER)
    gap_li = layout.layer(*GAP_LAYER)
    trace_region = pya.Region(top.shapes(trace_li))
    assert not trace_region.is_empty()
    assert not top.shapes(gap_li).is_empty()

    # The trace's own bounding box must reach both endpoints -- i.e. it
    # actually spans the full gap between the two qubits, not just a
    # stub near one side.
    bbox = trace_region.bbox().to_dtype(layout.dbu)
    assert bbox.left <= min(pin_a.position.x, pin_b.position.x) + 1.0
    assert bbox.right >= max(pin_a.position.x, pin_b.position.x) - 1.0
