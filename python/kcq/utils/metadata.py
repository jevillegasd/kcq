"""Simulation/experimental metadata pointers for kcq components.

Phase 6 (EPR extraction, S-parameters for scikit-rf) and future
experimental data need to be recoverable from a placed cell later. The
data itself never lives in the GDS: it's written to a sidecar JSON file
(plus referenced Touchstone files for S-parameters), and the GDS only
carries a pointer to it.

The pointer is a pya.Text label on the MetaRef layer, not a KLayout cell
property: verified directly (see tests/test_metadata.py) that
Cell.set_property values round-trip through OASIS but are lost on a
plain GDS2 write/read, while Text shapes survive GDS2 unchanged. GDS2 is
the actual fab-submission format, so the text label is the load-bearing
mechanism; a cell property is set too, best-effort, for in-session/OASIS
convenience.
"""

import hashlib
import json
import os

import pya

from kcq.utils.log import get_logger

_LOG = get_logger(__name__)

META_REF_LAYER = (110, 3)  # kcq bookkeeping group, alongside PinRec (110/1) / PinRecText (110/2)

PROPERTY_KEY = "kcq_metadata_id"
_POINTER_PREFIX = "kcq:"


def _stable_id(component_type: str, params: dict) -> str:
    canonical = json.dumps({"component_type": component_type, "params": params},
                            sort_keys=True, default=str)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]


def attach_pointer(cell, layout, component_type: str, params: dict) -> str:
    """Generates a metadata_id (stable hash of component_type + params, so
    identical instances share one id), writes it as a 'kcq:<id>' text
    label on the MetaRef layer at the cell origin, and best-effort sets
    it as a cell property too. Returns metadata_id."""
    metadata_id = _stable_id(component_type, params)

    li = layout.layer(*META_REF_LAYER)
    cell.shapes(li).insert(pya.DText(_POINTER_PREFIX + metadata_id, 0.0, 0.0))

    try:
        cell.set_property(PROPERTY_KEY, metadata_id)
    except Exception:
        _LOG.warning("attach_pointer: cell.set_property unavailable/failed; text label still set")

    return metadata_id


def read_pointer(cell, layout) -> str:
    """Reads the MetaRef text label back out; falls back to the cell
    property if the label is missing. None if neither is present."""
    li = layout.layer(*META_REF_LAYER)
    for shape in cell.shapes(li).each():
        if shape.is_text():
            text = shape.dtext.string
            if text.startswith(_POINTER_PREFIX):
                return text[len(_POINTER_PREFIX):]

    try:
        prop = cell.property(PROPERTY_KEY)
        if prop:
            return prop
    except Exception:
        pass
    return None


def write_metadata(metadata_id: str, data: dict, metadata_dir: str) -> str:
    """Writes data (EPR participation ratios, extracted Ej/Ec/f01/
    anharmonicity, a 'touchstone_path' reference, source: 'fem'|
    'experimental', timestamp, ...) as <metadata_dir>/<metadata_id>.json.
    S-parameter arrays are never embedded here -- they live in the
    referenced Touchstone (.sNp) file (scikit-rf reads that natively;
    Phase 4's to_touchstone produces it). Returns the written path."""
    os.makedirs(metadata_dir, exist_ok=True)
    path = os.path.join(metadata_dir, f"{metadata_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    return path


def read_metadata(metadata_id: str, metadata_dir: str) -> dict:
    """Reads <metadata_dir>/<metadata_id>.json; None if not yet populated
    (expected for most cells until Phase 6 simulation runs)."""
    path = os.path.join(metadata_dir, f"{metadata_id}.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
