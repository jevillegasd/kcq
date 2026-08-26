import os

import pytest

from kcq.utils import xml_parser
from kcq.utils.errors import TechnologyNotFoundError, KcqConfigError

VALID_WAVEGUIDES_XML = """<?xml version="1.0" encoding="utf-8"?>
<waveguides version="1">
  <technology name="fixture_tech" units="um">
    <cpw name="feedline" layer="M1/0" clearance_layer="M2/0">
      <trace_width value="10.0"/>
      <gap_width value="6.0"/>
      <ground_clearance value="20.0"/>
      <bend_radius min="50.0" default="100.0" style="euler"/>
      <taper length="150.0"/>
      <routing style="octilinear"/>
    </cpw>
    <launcher_pitch>
      <pitch value="1000.0"/>
      <pitch value="2540.0"/>
    </launcher_pitch>
  </technology>
</waveguides>
"""


def _make_tech_dir(root, tech_name, xml_content):
    tech_dir = root / tech_name
    tech_dir.mkdir(parents=True, exist_ok=True)
    (tech_dir / xml_parser.WAVEGUIDES_FILENAME).write_text(xml_content, encoding="utf-8")
    return tech_dir


@pytest.fixture(autouse=True)
def _clear_tech_cache():
    xml_parser._TECH_CACHE.clear()
    yield
    xml_parser._TECH_CACHE.clear()


def test_load_technology_parses_valid_fixture(tmp_path, monkeypatch):
    _make_tech_dir(tmp_path, "fixture_tech", VALID_WAVEGUIDES_XML)
    monkeypatch.setenv("KCQ_TECH_PATH", str(tmp_path))

    tech = xml_parser.load_technology("fixture_tech")

    assert tech["units"] == "um"
    assert tech["launcher_pitches_um"] == [1000.0, 2540.0]
    feedline = tech["cpws"]["feedline"]
    assert feedline["trace_width"] == 10.0
    assert feedline["gap_width"] == 6.0
    assert feedline["ground_clearance"] == 20.0
    assert feedline["clearance_layer"] == "M2/0"
    assert feedline["bend_radius_min"] == 50.0
    assert feedline["bend_radius_default"] == 100.0
    assert feedline["bend_style"] == "euler"
    assert feedline["taper_length"] == 150.0
    assert feedline["routing_style"] == "octilinear"


def test_get_cpw_params_returns_single_entry(tmp_path, monkeypatch):
    _make_tech_dir(tmp_path, "fixture_tech2", VALID_WAVEGUIDES_XML.replace("fixture_tech", "fixture_tech2"))
    monkeypatch.setenv("KCQ_TECH_PATH", str(tmp_path))

    params = xml_parser.get_cpw_params("fixture_tech2", "feedline")
    assert params["trace_width"] == 10.0


def test_get_cpw_params_unknown_cpw_raises_config_error(tmp_path, monkeypatch):
    _make_tech_dir(tmp_path, "fixture_tech3", VALID_WAVEGUIDES_XML.replace("fixture_tech", "fixture_tech3"))
    monkeypatch.setenv("KCQ_TECH_PATH", str(tmp_path))

    with pytest.raises(KcqConfigError, match="no cpw 'nonexistent'"):
        xml_parser.get_cpw_params("fixture_tech3", "nonexistent")


def test_unknown_technology_raises_technology_not_found_error(tmp_path, monkeypatch):
    monkeypatch.setenv("KCQ_TECH_PATH", str(tmp_path))
    with pytest.raises(TechnologyNotFoundError):
        xml_parser.load_technology("does_not_exist")


def test_malformed_xml_raises_config_error(tmp_path, monkeypatch):
    _make_tech_dir(tmp_path, "broken_tech", "<not valid xml")
    monkeypatch.setenv("KCQ_TECH_PATH", str(tmp_path))

    with pytest.raises(KcqConfigError, match="malformed XML"):
        xml_parser.load_technology("broken_tech")


def test_missing_bend_radius_raises_config_error(tmp_path, monkeypatch):
    xml_missing_bend = """<?xml version="1.0" encoding="utf-8"?>
<waveguides version="1">
  <technology name="missing_bend_tech" units="um">
    <cpw name="feedline" layer="M1/0" clearance_layer="M2/0">
      <trace_width value="10.0"/>
      <gap_width value="6.0"/>
      <ground_clearance value="20.0"/>
    </cpw>
  </technology>
</waveguides>
"""
    _make_tech_dir(tmp_path, "missing_bend_tech", xml_missing_bend)
    monkeypatch.setenv("KCQ_TECH_PATH", str(tmp_path))

    with pytest.raises(KcqConfigError, match="bend_radius"):
        xml_parser.load_technology("missing_bend_tech")


def test_missing_clearance_layer_raises_config_error(tmp_path, monkeypatch):
    xml_missing_clearance = VALID_WAVEGUIDES_XML.replace(' clearance_layer="M2/0"', '')
    _make_tech_dir(tmp_path, "missing_clearance_tech",
                   xml_missing_clearance.replace("fixture_tech", "missing_clearance_tech"))
    monkeypatch.setenv("KCQ_TECH_PATH", str(tmp_path))

    with pytest.raises(KcqConfigError, match="clearance_layer"):
        xml_parser.load_technology("missing_clearance_tech")


def test_invalid_routing_style_raises_config_error(tmp_path, monkeypatch):
    xml_bad_routing = VALID_WAVEGUIDES_XML.replace(
        'fixture_tech', 'bad_routing_tech'
    ).replace('style="octilinear"', 'style="diagonal"')
    _make_tech_dir(tmp_path, "bad_routing_tech", xml_bad_routing)
    monkeypatch.setenv("KCQ_TECH_PATH", str(tmp_path))

    with pytest.raises(KcqConfigError, match="octilinear' or 'manhattan'"):
        xml_parser.load_technology("bad_routing_tech")


def test_cache_invalidates_on_file_change(tmp_path, monkeypatch):
    tech_dir = _make_tech_dir(tmp_path, "cache_tech", VALID_WAVEGUIDES_XML.replace("fixture_tech", "cache_tech"))
    monkeypatch.setenv("KCQ_TECH_PATH", str(tmp_path))

    first = xml_parser.get_cpw_params("cache_tech", "feedline")
    assert first["trace_width"] == 10.0

    updated_xml = VALID_WAVEGUIDES_XML.replace("fixture_tech", "cache_tech").replace(
        '<trace_width value="10.0"/>', '<trace_width value="12.5"/>'
    )
    xml_path = tech_dir / xml_parser.WAVEGUIDES_FILENAME
    xml_path.write_text(updated_xml, encoding="utf-8")
    # Ensure the new mtime is observably different on filesystems with
    # coarse mtime resolution.
    new_time = os.path.getmtime(xml_path) + 1
    os.utime(xml_path, (new_time, new_time))

    second = xml_parser.get_cpw_params("cache_tech", "feedline")
    assert second["trace_width"] == 12.5


def test_kcq_technology_loads_from_repo_tech_folder(monkeypatch):
    # No KCQ_TECH_PATH set -> falls back to the repo-relative tech/ folder,
    # proving the real kcq/waveguides.xml shipped with the repo is itself
    # valid against this parser.
    monkeypatch.delenv("KCQ_TECH_PATH", raising=False)
    tech = xml_parser.load_technology("kcq")
    assert "feedline" in tech["cpws"]
    assert "resonator" in tech["cpws"]
    assert "flux_line" in tech["cpws"]
    assert tech["cpws"]["flux_line"]["routing_style"] == "manhattan"
    assert tech["cpws"]["feedline"]["routing_style"] == "octilinear"
