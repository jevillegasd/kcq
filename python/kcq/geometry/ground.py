"""Ground-plane boolean generation.

Builds a cell's ground metal as (outline - keepouts), merged before being
written back to avoid coincident-edge meshing artifacts when piped to
Elmer FEM later. Layout is always read/written via cell.shapes(layer),
never a cell.<method> shortcut.
"""

import pya

from kcq.utils.log import get_logger

_LOG = get_logger(__name__)


def region_from_layer(cell: pya.Cell, layer_index: int) -> pya.Region:
    """Reads all shapes on `layer_index` into a Region, via cell.shapes(...)."""
    return pya.Region(cell.shapes(layer_index))


def build_ground_plane(cell: pya.Cell, layout: pya.Layout,
                        outline_layer: int, keepout_regions, ground_layer: int) -> None:
    """Ground metal = outline_layer's shapes minus every Region in
    keepout_regions, merged, then inserted on ground_layer. Logs a
    warning (does not raise) if the result ends up empty."""
    outline = region_from_layer(cell, outline_layer)
    if outline.is_empty():
        _LOG.warning(
            "build_ground_plane: outline_layer %s has no shapes on cell '%s'",
            outline_layer, cell.name,
        )

    ground = outline
    for keepout in keepout_regions:
        ground -= keepout
    ground.merge()

    cell.shapes(ground_layer).insert(ground)

    if cell.shapes(ground_layer).is_empty():
        _LOG.warning(
            "build_ground_plane: resulting ground plane on cell '%s' is empty "
            "(outline fully covered by %d keepout region(s)?)",
            cell.name, len(keepout_regions),
        )
    else:
        _LOG.info(
            "build_ground_plane: cell '%s' ground plane built from %d keepout region(s)",
            cell.name, len(keepout_regions),
        )
