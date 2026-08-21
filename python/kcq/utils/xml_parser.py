"""XML parsing for kcq technology parameters.

Loads waveguides.xml for a named technology and exposes its CPW/routing
parameters as plain dicts, so geometry code never hardcodes a trace width,
gap width, clearance, bend radius, or taper length -- those always come
from here.

Resolution order for a technology's base directory:
  1. A KLayout-registered technology (pya.Technology.technology_by_name),
     which is how this resolves once kcq is installed as a Salt grain
     and its tech/<name> folder is auto-registered by KLayout.
  2. The KCQ_TECH_PATH environment variable (os.pathsep-separated list
     of directories, each containing one or more <name>/ subfolders).
  3. The repo-relative tech/ folder next to this package, so the module
     works headlessly (unit tests, `klayout -b`) without any KLayout
     technology registration step.
"""

import os
import xml.etree.ElementTree as ET

from kcq.utils.errors import TechnologyNotFoundError, KcqConfigError
from kcq.utils.log import get_logger

try:
    import pya
except ImportError:  # pragma: no cover - exercised only outside KLayout
    pya = None

_LOG = get_logger(__name__)

WAVEGUIDES_FILENAME = "waveguides.xml"

# Cache: tech_name -> (waveguides.xml mtime, parsed dict)
_TECH_CACHE = {}


def _repo_tech_root() -> str:
    # python/kcq/utils/xml_parser.py -> repo_root/tech
    this_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(this_dir, os.pardir, os.pardir, os.pardir))
    return os.path.join(repo_root, "tech")


def find_technology_base_path(tech_name: str) -> str:
    """Resolves tech_name's directory: a registered pya.Technology, else
    KCQ_TECH_PATH, else the repo-relative tech/ folder. Shared by any
    module that needs a technology's files (waveguides.xml here;
    tech/<name>/pcells/ for kcq.utils.pcell_loader)."""
    if pya is not None:
        tech = pya.Technology.technology_by_name(tech_name)
        if tech is not None and tech.base_path():
            return tech.base_path()

    search_roots = []
    env_path = os.environ.get("KCQ_TECH_PATH")
    if env_path:
        search_roots.extend(env_path.split(os.pathsep))
    search_roots.append(_repo_tech_root())

    for root in search_roots:
        candidate = os.path.join(root, tech_name)
        if os.path.isdir(candidate):
            return candidate

    raise TechnologyNotFoundError(
        f"Technology '{tech_name}' not found via pya.Technology, "
        f"KCQ_TECH_PATH, or the repo tech/ folder (searched: {search_roots})"
    )


def _parse_float_attr(node: ET.Element, tag: str, attr: str, file_path: str) -> float:
    child = node.find(tag)
    if child is None or attr not in child.attrib:
        raise KcqConfigError(
            f"{file_path}: <{node.tag} name='{node.attrib.get('name')}'> "
            f"missing required <{tag} {attr}=.../>"
        )
    try:
        return float(child.attrib[attr])
    except ValueError as exc:
        raise KcqConfigError(
            f"{file_path}: <{tag} {attr}='{child.attrib[attr]}'/> under "
            f"<{node.tag} name='{node.attrib.get('name')}'> is not numeric"
        ) from exc


def _parse_waveguides_xml(file_path: str) -> dict:
    try:
        tree = ET.parse(file_path)
    except ET.ParseError as exc:
        raise KcqConfigError(f"{file_path}: malformed XML ({exc})") from exc

    root = tree.getroot()
    if root.tag != "waveguides":
        raise KcqConfigError(f"{file_path}: expected root <waveguides>, found <{root.tag}>")

    tech_node = root.find("technology")
    if tech_node is None:
        raise KcqConfigError(f"{file_path}: missing <technology> element")

    units = tech_node.attrib.get("units")
    if not units:
        raise KcqConfigError(f"{file_path}: <technology> missing required 'units' attribute")

    cpws = {}
    for cpw_node in tech_node.findall("cpw"):
        name = cpw_node.attrib.get("name")
        if not name:
            raise KcqConfigError(f"{file_path}: <cpw> element missing 'name' attribute")
        layer = cpw_node.attrib.get("layer")
        if not layer:
            raise KcqConfigError(f"{file_path}: <cpw name='{name}'> missing 'layer' attribute")

        bend_node = cpw_node.find("bend_radius")
        if bend_node is None or "min" not in bend_node.attrib or "default" not in bend_node.attrib:
            raise KcqConfigError(
                f"{file_path}: <cpw name='{name}'> missing <bend_radius min=... default=.../>"
            )

        routing_node = cpw_node.find("routing")
        routing_style = routing_node.attrib.get("style", "octilinear") if routing_node is not None else "octilinear"
        if routing_style not in ("octilinear", "manhattan"):
            raise KcqConfigError(
                f"{file_path}: <cpw name='{name}'> <routing style='{routing_style}'/> "
                f"must be 'octilinear' or 'manhattan'"
            )

        bend_style = bend_node.attrib.get("style", "arc")
        if bend_style not in ("euler", "arc"):
            raise KcqConfigError(
                f"{file_path}: <cpw name='{name}'> <bend_radius style='{bend_style}'/> "
                f"must be 'euler' or 'arc'"
            )

        taper_node = cpw_node.find("taper")

        cpws[name] = {
            "layer": layer,
            "gap_layer": cpw_node.attrib.get("gap_layer", layer),
            "trace_width": _parse_float_attr(cpw_node, "trace_width", "value", file_path),
            "gap_width": _parse_float_attr(cpw_node, "gap_width", "value", file_path),
            "ground_clearance": _parse_float_attr(cpw_node, "ground_clearance", "value", file_path),
            "bend_radius_min": float(bend_node.attrib["min"]),
            "bend_radius_default": float(bend_node.attrib["default"]),
            "bend_style": bend_style,
            "taper_length": float(taper_node.attrib["length"]) if taper_node is not None else 0.0,
            "routing_style": routing_style,
            "units": units,
        }

    if not cpws:
        raise KcqConfigError(f"{file_path}: <technology> defines no <cpw> entries")

    launcher_pitches = []
    pitch_parent = tech_node.find("launcher_pitch")
    if pitch_parent is not None:
        for pitch_node in pitch_parent.findall("pitch"):
            launcher_pitches.append(float(pitch_node.attrib["value"]))

    return {"units": units, "cpws": cpws, "launcher_pitches_um": launcher_pitches}


def load_technology(tech_name: str) -> dict:
    """Returns {'units', 'cpws': {cpw_name: {...}}, 'launcher_pitches_um': [...]}
    for the given technology, parsed from its waveguides.xml.

    Cached per (tech_name, file mtime) so repeated PCell instantiation
    doesn't re-parse XML on every call; editing waveguides.xml and
    re-running invalidates the cache automatically.
    """
    base_path = find_technology_base_path(tech_name)
    file_path = os.path.join(base_path, WAVEGUIDES_FILENAME)
    if not os.path.isfile(file_path):
        raise TechnologyNotFoundError(f"{file_path} does not exist for technology '{tech_name}'")

    mtime = os.path.getmtime(file_path)
    cached = _TECH_CACHE.get(tech_name)
    if cached is not None and cached[0] == mtime:
        return cached[1]

    _LOG.info("Loading waveguide parameters for technology '%s' from %s", tech_name, file_path)
    parsed = _parse_waveguides_xml(file_path)
    _TECH_CACHE[tech_name] = (mtime, parsed)
    return parsed


def get_cpw_params(tech_name: str, cpw_name: str) -> dict:
    """Returns the parameter dict for a single <cpw name=cpw_name> entry."""
    tech = load_technology(tech_name)
    try:
        return tech["cpws"][cpw_name]
    except KeyError as exc:
        available = ", ".join(sorted(tech["cpws"]))
        raise KcqConfigError(
            f"Technology '{tech_name}' has no cpw '{cpw_name}' (available: {available})"
        ) from exc
