import pya
import pytest

from kcq.geometry import cpw
from kcq.utils import xml_parser
from kcq.utils.errors import KcqConfigError

FIXTURE_WAVEGUIDES_XML = """<?xml version="1.0" encoding="utf-8"?>
<waveguides version="1">
  <technology name="{tech_name}" units="um">
    <cpw name="feedline" layer="{layer}" gap_layer="{gap_layer}">
      <trace_width value="{trace_width}"/>
      <gap_width value="{gap_width}"/>
      <ground_clearance value="20.0"/>
      <bend_radius min="10.0" default="{bend_radius}" style="{bend_style}"/>
      <taper length="50.0"/>
      <routing style="octilinear"/>
    </cpw>
  </technology>
</waveguides>
"""


@pytest.fixture(autouse=True)
def _clear_tech_cache():
    xml_parser._TECH_CACHE.clear()
    yield
    xml_parser._TECH_CACHE.clear()


def _make_fixture_tech(tmp_path, monkeypatch, tech_name, trace_width, gap_width,
                        layer="3/0", gap_layer="3/1", bend_radius=10.0, bend_style="arc"):
    tech_dir = tmp_path / tech_name
    tech_dir.mkdir(parents=True, exist_ok=True)
    (tech_dir / xml_parser.WAVEGUIDES_FILENAME).write_text(
        FIXTURE_WAVEGUIDES_XML.format(
            tech_name=tech_name, layer=layer, gap_layer=gap_layer,
            trace_width=trace_width, gap_width=gap_width,
            bend_radius=bend_radius, bend_style=bend_style,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("KCQ_TECH_PATH", str(tmp_path))


def _new_layout():
    layout = pya.Layout()
    layout.dbu = 0.001
    cell = layout.create_cell("TOP")
    return layout, cell


class TestParseLayerSpec:
    def test_parses_valid_spec(self):
        assert cpw.parse_layer_spec("1/0") == (1, 0)
        assert cpw.parse_layer_spec("12/34") == (12, 34)

    def test_rejects_non_numeric_spec(self):
        with pytest.raises(KcqConfigError):
            cpw.parse_layer_spec("M1/0")

    def test_rejects_malformed_spec(self):
        with pytest.raises(KcqConfigError):
            cpw.parse_layer_spec("1-0")


class TestCPWBuildStraight:
    def test_trace_and_gap_areas_match_xml_params(self, tmp_path, monkeypatch):
        _make_fixture_tech(tmp_path, monkeypatch, "straight_tech", trace_width=10.0, gap_width=6.0)
        layout, cell = _new_layout()
        waypoints = [pya.DPoint(0, 0), pya.DPoint(1000, 0)]

        c = cpw.CPW("straight_tech", "feedline", waypoints)
        c.build(cell, layout)

        trace_li = layout.layer(3, 0)
        gap_li = layout.layer(3, 1)
        assert not cell.shapes(trace_li).is_empty()
        assert not cell.shapes(gap_li).is_empty()

        trace_area = pya.Region(cell.shapes(trace_li)).area() * layout.dbu ** 2
        gap_area = pya.Region(cell.shapes(gap_li)).area() * layout.dbu ** 2
        assert trace_area == pytest.approx(10.0 * 1000, rel=1e-3)
        assert gap_area == pytest.approx((10.0 + 2 * 6.0) * 1000, rel=1e-3)

    def test_requires_at_least_two_waypoints(self, tmp_path, monkeypatch):
        _make_fixture_tech(tmp_path, monkeypatch, "single_pt_tech", trace_width=10.0, gap_width=6.0)
        with pytest.raises(KcqConfigError):
            cpw.CPW("single_pt_tech", "feedline", [pya.DPoint(0, 0)])


class TestCPWNoHardcoding:
    def test_dimensions_come_from_xml_not_python_literals(self, tmp_path, monkeypatch):
        _make_fixture_tech(tmp_path, monkeypatch, "tech_narrow", trace_width=4.0, gap_width=2.0,
                            layer="3/0", gap_layer="3/1")
        _make_fixture_tech(tmp_path, monkeypatch, "tech_wide", trace_width=40.0, gap_width=20.0,
                            layer="4/0", gap_layer="4/1")

        waypoints = [pya.DPoint(0, 0), pya.DPoint(500, 0)]

        layout, cell = _new_layout()
        cpw.CPW("tech_narrow", "feedline", waypoints).build(cell, layout)
        cpw.CPW("tech_wide", "feedline", waypoints).build(cell, layout)

        narrow_trace_area = pya.Region(cell.shapes(layout.layer(3, 0))).area() * layout.dbu ** 2
        wide_trace_area = pya.Region(cell.shapes(layout.layer(4, 0))).area() * layout.dbu ** 2

        assert narrow_trace_area == pytest.approx(4.0 * 500, rel=1e-3)
        assert wide_trace_area == pytest.approx(40.0 * 500, rel=1e-3)
        # A 10x wider technology must produce ~10x trace area for the same
        # waypoints -- if this ratio held regardless of XML content, that
        # would mean the width was hardcoded rather than XML-driven.
        assert wide_trace_area / narrow_trace_area == pytest.approx(10.0, rel=1e-3)


class TestCPWBuildWithBend:
    def test_bend_style_from_xml_is_applied(self, tmp_path, monkeypatch):
        _make_fixture_tech(tmp_path, monkeypatch, "bend_tech", trace_width=2.0, gap_width=1.0,
                            bend_radius=10.0, bend_style="arc")
        layout, cell = _new_layout()
        # Single 90 deg corner, generous room either side for a radius-10 arc.
        waypoints = [pya.DPoint(0, 0), pya.DPoint(100, 0), pya.DPoint(100, 100)]

        c = cpw.CPW("bend_tech", "feedline", waypoints)
        centerline = c.smoothed_centerline()
        assert len(centerline) > len(waypoints)  # bend was actually inscribed

        c.build(cell, layout)
        trace_li = layout.layer(3, 0)
        assert not cell.shapes(trace_li).is_empty()

    def test_bend_too_tight_raises(self, tmp_path, monkeypatch):
        _make_fixture_tech(tmp_path, monkeypatch, "tight_bend_tech", trace_width=2.0, gap_width=1.0,
                            bend_radius=500.0, bend_style="arc")
        layout, cell = _new_layout()
        waypoints = [pya.DPoint(0, 0), pya.DPoint(10, 0), pya.DPoint(10, 10)]
        c = cpw.CPW("tight_bend_tech", "feedline", waypoints)
        with pytest.raises(Exception):
            c.build(cell, layout)
