"""Measure Waveguide Length (hotkey 'L'): reports a selected Waveguide
instance's own core length and, if it connects to other Waveguide
instances, the connected chain's total length too.
"""

import pya

from kcq.gui import waveguide_chain


def measure(parent_cell: pya.Cell, layout: pya.Layout, inst: pya.Instance) -> waveguide_chain.ChainResult:
    """Thin wrapper over kcq.gui.waveguide_chain.walk_chain -- kept as
    its own module/function so the GUI trigger has one obvious entry
    point per tool, matching kcq.gui.snap/kcq.gui.path_to_waveguide."""
    return waveguide_chain.walk_chain(parent_cell, layout, inst)
