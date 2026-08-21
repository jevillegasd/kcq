# $autorun

"""Registers the "kcq" technology's two pya.Library instances:
- "kcq": PCells (TransmonStar, Transmon, Manhattan, ManhattanSQUID,
  ... from tech/kcq/pcells/, plus core PCells like Waveguide shipped
  by the kcq package's own python/kcq/pcells/).
- "kcq_fixed_cells": fixed cells (launchers, ... from
  tech/kcq/fixed_cells/), kept in a separate library so the two kinds
  of cell are organized independently in KLayout's library tree.
Both via kcq.utils.pcell_loader.register_library.

This lives under the *technology's* own pymacros/, not the kcq
package's pymacros/ -- library registration is part of the PDK, not the
package: kcq (the framework) could host more than one technology, each
with its own libraries, and each technology is responsible for
registering its own.

kcq.utils.pcell_loader.register_library is a plain, headless-callable
Python function -- the pytest suite calls it directly via a fixture;
this script is only the GUI-side trigger, so `layout.create_cell(name,
"kcq", params)` (PCells) and `layout.create_cell(name,
"kcq_fixed_cells")` (fixed cells) resolve without the user having to
call it by hand from the macro console.
"""

from kcq.utils import pcell_loader
from kcq.utils.log import get_logger

_LOG = get_logger(__name__)

try:
    pcell_loader.register_library("kcq")
except Exception as exc:
    _LOG.error("Failed to register the kcq library: %s", exc)
