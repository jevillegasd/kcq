"""Connected-chain walking for kcq.pcells.Waveguide PCell instances,
shared by the Measure (kcq.gui.waveguide_length) and Extend
(kcq.gui.waveguide_extend) tools.

A waveguide's "extended length" is its own core length plus every other
Waveguide instance reachable by following coincident, opposite-oriented
pins (kcq.geometry.pins.check_alignment) outward from its P1/P2 ends --
the chain stops at a free (unconnected) pin or at a neighbor that isn't
itself a Waveguide instance (e.g. a Transmon).
"""

from dataclasses import dataclass

import pya

from kcq.geometry import cpw, pins
from kcq.gui.instance_pins import global_pins
from kcq.utils import xml_parser
from kcq.utils.errors import KcqConfigError

_PIN_COINCIDENCE_TOLERANCE_UM = 1e-2


def is_waveguide_instance(inst: pya.Instance) -> bool:
    """True if inst is a kcq.pcells.Waveguide PCell instance (any
    technology -- Waveguide is merged into every technology's PCell
    library, so its declaration name alone identifies it)."""
    if not inst.is_pcell():
        return False
    declaration = inst.pcell_declaration()
    return declaration is not None and declaration.name() == "Waveguide"


def core_length(inst: pya.Instance, layout: pya.Layout) -> float:
    """The waveguide's own length, as core (trace) metal area / trace
    width -- read from the built shapes rather than the PCell's path
    parameter, so it reflects the actual geometry even if it was
    hand-edited after placement."""
    if not is_waveguide_instance(inst):
        raise KcqConfigError(
            f"core_length: instance of '{inst.cell.name}' is not a Waveguide PCell instance"
        )
    params = inst.pcell_parameters_by_name()
    cpw_params = xml_parser.get_cpw_params(params["tech_name"], params["cpw_name"])
    trace_layer, trace_datatype = cpw.parse_layer_spec(cpw_params["layer"])
    trace_li = layout.layer(trace_layer, trace_datatype)
    trace_region = pya.Region(inst.cell.shapes(trace_li))
    area_um2 = trace_region.area() * (layout.dbu ** 2)
    return area_um2 / cpw_params["trace_width"]


def find_matching_neighbor(parent_cell: pya.Cell, layout: pya.Layout, pin_global: pins.PinInfo,
                            own_inst: pya.Instance, tolerance: float = _PIN_COINCIDENCE_TOLERANCE_UM):
    """Scans parent_cell's direct child instances (siblings of own_inst,
    which must itself be a direct child of parent_cell) for one with a
    pin coincident with pin_global (within tolerance) and oriented
    opposite to it. Returns (matching pya.Instance, its pin's name), or
    None if pin_global is a free/unconnected end."""
    for candidate in parent_cell.each_inst():
        if candidate == own_inst:
            continue
        for candidate_pin in global_pins(layout, candidate):
            if not pins.check_alignment(pin_global, candidate_pin):
                continue
            if pin_global.position.distance(candidate_pin.position) <= tolerance:
                return candidate, candidate_pin.name
    return None


def _pin_by_name(pin_list, name, inst):
    for pin in pin_list:
        if pin.name == name:
            return pin
    raise KcqConfigError(f"walk_chain: instance of '{inst.cell.name}' has no pin named '{name}'")


def _walk_direction(parent_cell, layout, start_inst, start_pin_name, visited):
    own_pins = global_pins(layout, start_inst)
    pin = _pin_by_name(own_pins, start_pin_name, start_inst)
    match = find_matching_neighbor(parent_cell, layout, pin, start_inst)
    if match is None:
        return 0.0, True, None

    neighbor, entry_pin_name = match
    if not is_waveguide_instance(neighbor) or any(neighbor == v for v in visited):
        return 0.0, False, neighbor

    visited.append(neighbor)
    neighbor_length = core_length(neighbor, layout)
    exit_pin_name = "P2" if entry_pin_name == "P1" else "P1"
    further_length, _far_free, _far_neighbor = _walk_direction(
        parent_cell, layout, neighbor, exit_pin_name, visited)
    return neighbor_length + further_length, False, neighbor


@dataclass
class ChainResult:
    own_length: float
    p1_neighbor: object  # pya.Instance | None
    p2_neighbor: object  # pya.Instance | None
    p1_free: bool
    p2_free: bool
    p1_chain_length: float
    p2_chain_length: float

    @property
    def extended_length(self) -> float:
        return self.own_length + self.p1_chain_length + self.p2_chain_length

    @property
    def is_chained(self) -> bool:
        """True if this waveguide continues into at least one other
        Waveguide instance in either direction."""
        return self.p1_chain_length > 0.0 or self.p2_chain_length > 0.0


def walk_chain(parent_cell: pya.Cell, layout: pya.Layout, start_inst: pya.Instance) -> ChainResult:
    """Measures start_inst's own length and walks outward from both its
    P1 and P2 pins, following only connected Waveguide neighbors, to
    total the length of the whole connected chain it belongs to."""
    if not is_waveguide_instance(start_inst):
        raise KcqConfigError(
            f"walk_chain: instance of '{start_inst.cell.name}' is not a Waveguide PCell instance"
        )
    own_length = core_length(start_inst, layout)

    visited = [start_inst]
    p1_chain_length, p1_free, p1_neighbor = _walk_direction(parent_cell, layout, start_inst, "P1", visited)
    p2_chain_length, p2_free, p2_neighbor = _walk_direction(parent_cell, layout, start_inst, "P2", visited)

    return ChainResult(
        own_length=own_length,
        p1_neighbor=p1_neighbor, p2_neighbor=p2_neighbor,
        p1_free=p1_free, p2_free=p2_free,
        p1_chain_length=p1_chain_length, p2_chain_length=p2_chain_length,
    )
