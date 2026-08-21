"""PCell + fixed-cell registration for a kcq technology, from
tech/<name>/pcells/, this package's own python/kcq/pcells/, and
tech/<name>/fixed_cells/ -- registered into two separate pya.Library
instances per technology (PCells vs. fixed cells), for organization in
KLayout's library tree.

Not qfoundry's approach (kqcircuits.util.library_helper.load_libraries) --
this is headless-callable, so both the pytest suite and any future batch
(klayout -b) generation can resolve layout.create_cell(pcell_name,
lib_name, params) before a GUI ever starts. Confirmed directly (not
assumed): create_cell requires an explicit lib_name in this project's
klayout package -- it does not fall back to a layout's technology_name.
Also confirmed directly: a *static* library cell (a fixed cell, not a
PCell) is looked up via the two-argument create_cell(name, lib_name) --
the three-argument PCell form (with a params dict) returns None for it.
"""

import importlib.util
import json
import os
import sys

import pya

from kcq.geometry import pins
from kcq.utils import xml_parser
from kcq.utils.log import get_logger

_LOG = get_logger(__name__)

# Keeps registered pya.Library instances alive for the process lifetime;
# also lets repeated calls (e.g. one per pytest test) be genuinely cheap.
_registered_pcell_libraries = {}
_registered_fixed_cell_libraries = {}

FIXED_CELL_LIBRARY_SUFFIX = "_fixed_cells"


def fixed_cell_library_name(tech_name: str) -> str:
    """The pya.Library name a technology's fixed cells register under --
    always distinct from tech_name itself (the PCell library's name), so
    the two kinds of cell are never in the same library."""
    return f"{tech_name}{FIXED_CELL_LIBRARY_SUFFIX}"


def _import_module_from_path(module_name: str, file_path: str):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import module '{module_name}' from '{file_path}'")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _discover_pcell_classes(pcells_dir: str):
    """Yields (class_name, class_obj) for every *.py file under pcells_dir
    (recursive) whose top-level attribute matching the filename is a
    pya.PCellDeclarationHelper subclass. Files starting with '_' (helper
    modules like junctions/_utils.py, and __init__.py) are skipped as
    PCell candidates, but their directory is still added to sys.path so a
    sibling PCell file can `import _utils` as a plain absolute import --
    each file is loaded ad-hoc via spec_from_file_location, not as part
    of a real package, so a relative import wouldn't resolve."""
    for dirpath, _dirnames, filenames in os.walk(pcells_dir):
        if dirpath not in sys.path:
            sys.path.append(dirpath)
        for filename in filenames:
            if not filename.endswith(".py") or filename.startswith("_"):
                continue
            class_name = filename[:-3]
            file_path = os.path.join(dirpath, filename)
            try:
                module = _import_module_from_path(f"kcq_pcell_{class_name}", file_path)
            except Exception as exc:
                _LOG.warning("pcell_loader: failed to import %s: %s", file_path, exc)
                continue
            obj = getattr(module, class_name, None)
            if obj is None:
                _LOG.warning("pcell_loader: %s has no top-level class '%s'", file_path, class_name)
                continue
            if isinstance(obj, type) and issubclass(obj, pya.PCellDeclarationHelper):
                yield class_name, obj


def _core_pcells_dir() -> str:
    """python/kcq/pcells/ -- home to core, technology-agnostic PCells
    (e.g. Waveguide) shipped by the kcq package itself rather than any
    one PDK's tech/<name>/pcells/. A sibling of this file's own utils/
    directory, not the root pymacros/ (that stays reserved for GUI
    integration -- menus, toolbar buttons -- per the original repo
    layout; a bare PCell class there would be an orphan, not a macro)."""
    this_dir = os.path.dirname(os.path.abspath(__file__))
    package_dir = os.path.dirname(this_dir)
    return os.path.join(package_dir, "pcells")


_FIXED_CELL_EXTENSIONS = (".gds", ".gds2", ".oas")


def _import_fixed_cells(library_layout: pya.Layout, fixed_cells_dir: str):
    """Imports every GDS/OAS file directly under fixed_cells_dir into
    library_layout, one static cell per file, named after the file's stem
    (so it's creatable via layout.create_cell(name, lib_name) the same
    way a PCell is created via layout.create_cell(name, lib_name,
    params)). A same-named .json sidecar (e.g. launcher_15p5_7.json next
    to launcher_15p5_7.oas) documents its pins -- imported GDS/OAS has no
    PinRec layer by convention, so pins.add_pin is called once per sidecar
    entry after import. Yields the imported cell names."""
    if not os.path.isdir(fixed_cells_dir):
        return
    for filename in sorted(os.listdir(fixed_cells_dir)):
        stem, ext = os.path.splitext(filename)
        if ext.lower() not in _FIXED_CELL_EXTENSIONS:
            continue
        file_path = os.path.join(fixed_cells_dir, filename)
        try:
            source_layout = pya.Layout()
            source_layout.read(file_path)
            cell = library_layout.create_cell(stem)
            cell.copy_tree(source_layout.top_cell())
        except Exception as exc:
            _LOG.warning("pcell_loader: failed to import fixed cell %s: %s", file_path, exc)
            continue

        sidecar_path = os.path.join(fixed_cells_dir, f"{stem}.json")
        if os.path.isfile(sidecar_path):
            with open(sidecar_path, "r", encoding="utf-8") as f:
                sidecar = json.load(f)
            for pin in sidecar.get("pins", []):
                pins.add_pin(cell, library_layout, pin["name"],
                              pya.DPoint(pin["x"], pin["y"]), pin["angle_deg"], pin["width"])
        else:
            _LOG.warning("pcell_loader: fixed cell %s has no pin sidecar (%s)", stem, sidecar_path)

        yield stem


def register_pcell_library(tech_name: str = "kcq") -> pya.Library:
    """Registers every PCell under tech/<tech_name>/pcells/ (recursive)
    PLUS every core PCell under this package's own python/kcq/pcells/
    into one pya.Library named tech_name. Core PCells (e.g. Waveguide)
    are technology-agnostic -- their own tech_name param just picks which
    waveguides.xml sizes them -- but still need to be creatable as
    layout.create_cell(name, tech_name, params) like any PDK-specific
    PCell, so every technology's library merges them in rather than
    keeping them in a library of their own. Idempotent: safe to call once
    per test, or repeatedly across a session -- re-registration replaces
    the previous library under that name."""
    base_path = xml_parser.find_technology_base_path(tech_name)
    pcells_dir = os.path.join(base_path, "pcells")
    discovered = list(_discover_pcell_classes(pcells_dir))
    discovered += list(_discover_pcell_classes(_core_pcells_dir()))

    class _KcqPCellLibrary(pya.Library):
        def __init__(self):
            self.description = f"{tech_name} PCell library"
            for class_name, cls in discovered:
                self.layout().register_pcell(class_name, cls())
            self.register(tech_name)

    library = _KcqPCellLibrary()
    _registered_pcell_libraries[tech_name] = library
    _LOG.info("pcell_loader: registered %d PCell(s) for '%s': %s",
              len(discovered), tech_name, ", ".join(name for name, _ in discovered))
    return library


def register_fixed_cell_library(tech_name: str = "kcq") -> pya.Library:
    """Registers every fixed cell under tech/<tech_name>/fixed_cells/ into
    its own pya.Library, named fixed_cell_library_name(tech_name) --
    kept separate from the PCell library (register_pcell_library) so the
    two kinds of cell are organized independently in KLayout's library
    tree. Idempotent, same as register_pcell_library."""
    base_path = xml_parser.find_technology_base_path(tech_name)
    fixed_cells_dir = os.path.join(base_path, "fixed_cells")
    lib_name = fixed_cell_library_name(tech_name)

    class _KcqFixedCellLibrary(pya.Library):
        def __init__(self):
            self.description = f"{tech_name} fixed-cell library"
            self.imported_fixed_cells = list(_import_fixed_cells(self.layout(), fixed_cells_dir))
            self.register(lib_name)

    library = _KcqFixedCellLibrary()
    _registered_fixed_cell_libraries[tech_name] = library
    _LOG.info("pcell_loader: imported %d fixed cell(s) for '%s' into '%s': %s",
              len(library.imported_fixed_cells), tech_name, lib_name,
              ", ".join(library.imported_fixed_cells))
    return library


def register_library(tech_name: str = "kcq"):
    """Convenience: registers both the PCell library and the fixed-cell
    library for tech_name. Returns (pcell_library, fixed_cell_library)."""
    return register_pcell_library(tech_name), register_fixed_cell_library(tech_name)
