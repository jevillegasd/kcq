"""Parses a technology's <connectivity> stack (kcq.lyt) into a plain
dict structure, the same way kcq.utils.xml_parser parses
waveguides.xml -- the technology's own XML stays the single source of
truth, never duplicated as a second, hand-maintained Python spec.

Two independent, confirmed-by-inspection consumers of <connectivity>:
- KLayout's own Net Tracer (pya.NetTracer / GUI Tools > Trace Net) reads
  it automatically once a technology is registered and active in a
  running KLayout session -- no kcq code needed there at all.
- pya.LayoutToNetlist (the netlist-extraction engine Phase 4's LVS
  module will use) does NOT: its connectivity has to be built via
  make_layer()/connect() Python calls. This module is the bridge Phase
  4 drives LayoutToNetlist from, instead of hand-declaring a second,
  parallel connectivity spec that could silently drift from kcq.lyt.

Confirmed directly (not assumed): pya.Technology's connectivity data
(surfaced in a running session as a NetTracerTechnologyComponent) isn't
introspectable from the standalone klayout PyPI package outside a real
GUI session -- so this re-parses the .lyt's <connectivity> XML itself,
keeping it headlessly testable like the rest of kcq.
"""

import os
import xml.etree.ElementTree as ET

from kcq.utils import xml_parser
from kcq.utils.errors import KcqConfigError
from kcq.utils.log import get_logger

_LOG = get_logger(__name__)

_UNSUPPORTED_OPERATORS = ("*", "-", "^")


def _resolve_symbol_expr(expr: str, symbols: dict, file_path: str):
    """Resolves a symbol expression like "1/0+110/1" or "L1" into a flat
    list of (layer, datatype) tuples. '+' (union) is the only operator
    any kcq symbol uses today; '*'/'-'/'^' (AND/NOT/XOR) are valid
    KLayout connectivity operators but raise here rather than being
    silently mishandled, since nothing exercises them yet."""
    expr = expr.strip()
    if any(op in expr for op in _UNSUPPORTED_OPERATORS):
        raise KcqConfigError(
            f"{file_path}: connectivity symbol '{expr}' uses an operator other than '+' "
            f"(only union is supported so far -- extend _resolve_symbol_expr if a real "
            f"technology needs '*'/'-'/'^')"
        )
    layers = []
    for token in expr.split("+"):
        token = token.strip()
        if "/" in token:
            layer_str, _, datatype_str = token.partition("/")
            try:
                layers.append((int(layer_str), int(datatype_str)))
            except ValueError as exc:
                raise KcqConfigError(
                    f"{file_path}: connectivity symbol token '{token}' is not a valid "
                    f"'layer/datatype' literal"
                ) from exc
        elif token in symbols:
            layers.extend(_resolve_symbol_expr(symbols[token], symbols, file_path))
        else:
            raise KcqConfigError(
                f"{file_path}: connectivity symbol token '{token}' is neither a "
                f"'layer/datatype' literal nor a previously-defined symbol"
            )
    return layers


def load_connectivity(tech_name: str) -> list:
    """Parses <connectivity> from tech_name's <tech_name>.lyt into a list
    of stack dicts, one per <stack>, in document order:
    {'name': str, 'description': str, 'layers': [(layer, datatype), ...],
     'connections': [{'a': str, 'via': str | None, 'b': str}]}.

    <symbols> entries are collected across the *whole* <connectivity>
    block before resolving any stack's 'layers' -- kcq.lyt itself
    declares both L1's and L2's symbols inside the L2 <stack> node, not
    one symbols block per stack, so per-stack scoping would miss L1's.
    A stack with no matching <symbols> entry gets an empty 'layers' list
    (not an error -- kcq.lyt's own L1 stack node has none, they live
    under L2's node instead, and 'layers' is populated after the fact).
    Returns [] if the technology's .lyt has no <connectivity> element at
    all (not every technology needs one).
    """
    base_path = xml_parser.find_technology_base_path(tech_name)
    file_path = os.path.join(base_path, f"{tech_name}.lyt")
    if not os.path.isfile(file_path):
        raise KcqConfigError(f"{file_path} does not exist for technology '{tech_name}'")

    try:
        tree = ET.parse(file_path)
    except ET.ParseError as exc:
        raise KcqConfigError(f"{file_path}: malformed XML ({exc})") from exc

    conn_node = tree.getroot().find("connectivity")
    if conn_node is None:
        return []
    stack_nodes = conn_node.findall("stack")

    symbols = {}
    for stack_node in stack_nodes:
        for symbols_node in stack_node.findall("symbols"):
            text = (symbols_node.text or "").strip()
            name, sep, expr = text.partition("=")
            name = name.strip()
            expr = expr.strip().strip("'\"")
            if not sep or not name or not expr:
                raise KcqConfigError(
                    f"{file_path}: malformed <symbols>{text}</symbols> "
                    f"(expected NAME='expression')"
                )
            symbols[name] = expr

    stacks = []
    for stack_node in stack_nodes:
        name = stack_node.findtext("name")
        if not name:
            raise KcqConfigError(f"{file_path}: <stack> missing required <name>")

        connections = []
        for conn_node_ in stack_node.findall("connection"):
            text = conn_node_.text or ""
            parts = text.split(",")
            if len(parts) != 3:
                raise KcqConfigError(
                    f"{file_path}: <connection>{text}</connection> under stack '{name}' "
                    f"must have 3 comma-separated fields (layer_a,via,layer_b)"
                )
            a, via, b = (p.strip() for p in parts)
            connections.append({"a": a, "via": via or None, "b": b})

        layers = _resolve_symbol_expr(symbols[name], symbols, file_path) if name in symbols else []
        stacks.append({
            "name": name,
            "description": stack_node.findtext("description") or "",
            "layers": layers,
            "connections": connections,
        })

    _LOG.info("connectivity_loader: parsed %d stack(s) for '%s': %s",
              len(stacks), tech_name, ", ".join(s["name"] for s in stacks))
    return stacks
