import pytest

from kcq.geometry import pins
from kcq.utils import connectivity_loader, xml_parser
from kcq.utils.errors import KcqConfigError

GAP_LAYER = (1, 0)


@pytest.fixture(autouse=True)
def _clear_tech_cache():
    xml_parser._TECH_CACHE.clear()
    yield
    xml_parser._TECH_CACHE.clear()


def _make_lyt(tmp_path, monkeypatch, tech_name, connectivity_xml=""):
    tech_dir = tmp_path / tech_name
    tech_dir.mkdir(parents=True, exist_ok=True)
    (tech_dir / f"{tech_name}.lyt").write_text(
        f"""<?xml version="1.0" encoding="utf-8"?>
<technology>
 <name>{tech_name}</name>
 <dbu>0.001</dbu>
 {connectivity_xml}
</technology>
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("KCQ_TECH_PATH", str(tmp_path))
    return tech_dir


class TestLoadConnectivityAgainstRealKcqLyt:
    """Exercises the real, shipped tech/kcq/kcq.lyt -- the whole point
    of this loader is to stay in sync with whatever that file says, not a
    synthetic fixture."""

    def test_parses_both_stacks_in_document_order(self):
        stacks = connectivity_loader.load_connectivity("kcq")
        assert [s["name"] for s in stacks] == ["L1", "L2"]

    def test_l1_symbol_resolves_to_the_layers_pins_and_cpw_actually_use(self):
        # L1 unions every L1 physical layer's drawing and pin (datatype
        # PIN_DATATYPE) sublayer in kcq.lyt -- catches future drift
        # between kcq.lyt's connectivity block, pins.PIN_DATATYPE, and
        # waveguides.xml's gap_layer if any of them changes without the
        # others.
        stacks = {s["name"]: s for s in connectivity_loader.load_connectivity("kcq")}
        assert GAP_LAYER in stacks["L1"]["layers"]
        assert (1, pins.PIN_DATATYPE) in stacks["L1"]["layers"]
        assert (2, pins.PIN_DATATYPE) in stacks["L1"]["layers"]

    def test_l2_connections_reference_l1_via_a_named_via_placeholder(self):
        stacks = {s["name"]: s for s in connectivity_loader.load_connectivity("kcq")}
        connections = stacks["L2"]["connections"]
        assert {"a": "L1", "via": None, "b": "L1"} in connections
        assert {"a": "L2", "via": None, "b": "L2"} in connections
        assert {"a": "L1", "via": "via12", "b": "L2"} in connections


class TestLoadConnectivitySynthetic:
    def test_technology_with_no_connectivity_block_returns_empty_list(self, tmp_path, monkeypatch):
        _make_lyt(tmp_path, monkeypatch, "no_conn_tech")
        assert connectivity_loader.load_connectivity("no_conn_tech") == []

    def test_unknown_symbol_reference_raises(self, tmp_path, monkeypatch):
        _make_lyt(tmp_path, monkeypatch, "bad_symbol_tech", """
 <connectivity>
  <stack>
   <name>M1</name>
   <symbols>M1='NOT_A_LAYER'</symbols>
  </stack>
 </connectivity>
""")
        with pytest.raises(KcqConfigError):
            connectivity_loader.load_connectivity("bad_symbol_tech")

    def test_malformed_connection_field_count_raises(self, tmp_path, monkeypatch):
        _make_lyt(tmp_path, monkeypatch, "bad_conn_tech", """
 <connectivity>
  <stack>
   <name>M1</name>
   <connection>M1,M1</connection>
  </stack>
 </connectivity>
""")
        with pytest.raises(KcqConfigError):
            connectivity_loader.load_connectivity("bad_conn_tech")

    def test_unsupported_operator_raises(self, tmp_path, monkeypatch):
        _make_lyt(tmp_path, monkeypatch, "bad_op_tech", """
 <connectivity>
  <stack>
   <name>M1</name>
   <symbols>M1='1/0*2/0'</symbols>
  </stack>
 </connectivity>
""")
        with pytest.raises(KcqConfigError):
            connectivity_loader.load_connectivity("bad_op_tech")
