# kcq

A KLayout Salt package for circuit quantum electrodynamics (cQED) design. kcq replaces
hardcoded, legacy layout approaches with a layout-driven design philosophy inspired by
SiEPIC-Tools: routing, verification, LVS and simulation logic lives in the `kcq` Python
package, while every trace width, gap width, clearance, and bend radius is pulled from the
active technology's XML at runtime.

This README documents the package for **developers** working on kcq itself. For a
task-oriented guide to *using* kcq to design a chip — installation, first layout, the
component library, fixed cells, and how simulation/FEM interfacing will plug in — see the
[user manual](doc/readme.html).

## Status

Phases 1–3 are complete:

- **Phase 1 (foundation & scaffolding):** the Salt package manifest, the `kcq` technology's
  `waveguides.xml`, the XML parser, logging/error handling.
- **Phase 2 (core geometry & routing engine):** an octilinear (Manhattan + diagonal) waypoint
  router with L/Z/U-route solving, Euler-spiral and circular-arc bend generation, adiabatic sine
  S-bends, technology-driven CPW (trace + gap) synthesis, boolean ground-plane generation, and an
  AST-based lint enforcing the "shapes, not cell" convention across the package.
- **Phase 3 (default PDK & component library):** the `kcq` technology's `.lyt`/`.lyp`, a
  pin/port standard (`kcq.geometry.pins`) shared by PCells and the router, headless PCell +
  fixed-cell registration (`kcq.utils.pcell_loader`) into two separate `pya.Library` instances
  per technology (`"kcq"` for PCells, `"kcq_fixed_cells"` for fixed cells), metadata pointers
  for attaching FEM/experimental results to a placed cell (`kcq.utils.metadata`), and the
  component library itself: `Transmon` (a new DiCarlo-style two-island design), `TransmonStar`,
  and the `junctions.Manhattan` / `junctions.ManhattanSQUID` junction PCells, migrated from an
  internal fab-specific PDK and adapted to be dependency-free of `kqcircuits`. A real fixed-cell
  asset (`launcher_15p5_7`, an RF wirebond launcher) is imported, pinned, and routes end-to-end to
  a `Transmon` in the test suite. A package-level, technology-agnostic `Waveguide` PCell (a
  placeable CPW segment) lives in `python/kcq/pcells/` and is merged into every technology's
  PCell library alongside that technology's own PCells. `kcq.lyt` also carries a
  native KLayout `<connectivity>` stack (`kcq.utils.connectivity_loader`), so GUI net tracing
  works with zero kcq code and Phase 4's LVS extraction will build its `LayoutToNetlist`
  connectivity from this same source instead of a hand-duplicated spec.

Later phases (LVS extraction, verification/DFT, Elmer FEM simulation, GUI) are not yet
implemented — see [`doc/readme.html`](doc/readme.html) for what each of those will look like
once built.

## Repository layout

```text
kcq/
├── grain.xml                   # KLayout Salt package manifest
├── doc/readme.html              # User manual (installation, tutorial, component reference)
├── pymacros/                   # GUI integration (menus, toolbar buttons)
├── python/kcq/                # Core Python API
│   ├── geometry/                # Routing, curves, CPW synthesis, ground planes, pins
│   ├── pcells/                  # Core, technology-agnostic PCells (e.g. Waveguide), merged
│   │                             # into every technology's own PCell library
│   ├── verification/            # FRC (impedance, connectivity) and DFT (launcher alignment)
│   ├── lvs/                     # Netlist extraction for lumped-element equivalents
│   ├── simulation/              # Meshing and Elmer FEM pipes for EPR analysis
│   ├── gui/                     # Dialogs bound to the pymacros/ menu
│   └── utils/                   # XML parser, logging, error hierarchy, PCell/fixed-cell
│                                 # registration, metadata pointers
├── tech/kcq/                  # Default PDK
│   ├── kcq.lyt
│   ├── waveguides.xml
│   ├── lyp/kcq.lyp
│   ├── pcells/                  # Transmon, TransmonStar, junctions/{Manhattan,ManhattanSQUID}
│   └── fixed_cells/              # Imported GDS/OAS cells + .json pin sidecars
└── tests/
```

## Coding standards

- **Shapes, not cells.** Layout mutation/inspection always goes through `cell.shapes(layer)`
  (`.insert()`, `.is_empty()`, `.each()`), never through cell-level convenience methods.
- **Layout-driven, not hardcoded.** No trace width, gap width, clearance, bend radius, or
  material constant appears as a Python literal — everything is read from the active
  technology's `waveguides.xml` (and `materials.xml`, added in the simulation phase) via
  `kcq.utils.xml_parser`.
- **Merged geometry.** Boolean results are merged before being written to `cell.shapes(...)` to
  avoid meshing artifacts when a layout is later piped to Elmer FEM.

## Development setup

Dependencies for headless development/testing (separate from the KLayout application itself)
are declared in `pyproject.toml`. Set up a fresh environment with
[uv](https://docs.astral.sh/uv/):

```sh
uv sync
```

This installs `pytest` and the standalone [`klayout`](https://pypi.org/project/klayout/) PyPI
package, which provides `pya` outside the KLayout GUI so geometry/XML/graph logic can be unit
tested headlessly. The resulting environment is local to your checkout and is not part of the
shipped package.

Run the test suite:

```sh
uv run pytest
```

## External (non-Python) dependencies

Later phases (multi-physics simulation) shell out to tools that are **not** installable via pip
or the Salt package manager and must be present on the system separately:

- [Gmsh](https://gmsh.info/) — GDS-to-mesh conversion
- [Elmer FEM](https://www.elmerfem.org/) — electrostatic/eigenmode solving for EPR extraction

## Installing as a KLayout Salt package

Once cloned (or unpacked from a release `.zip`), install via KLayout's Package Manager using
"Install from File" and pointing at this repository's root (containing `grain.xml`).
