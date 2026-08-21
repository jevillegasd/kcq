import os

import pya
import pytest

from kcq.utils import metadata


def _new_layout():
    layout = pya.Layout()
    layout.dbu = 0.001
    cell = layout.create_cell("TOP")
    return layout, cell


class TestAttachReadPointer:
    def test_attach_then_read_in_memory(self):
        layout, cell = _new_layout()
        metadata_id = metadata.attach_pointer(cell, layout, "transmon", {"island_width": 420.0})
        assert metadata.read_pointer(cell, layout) == metadata_id

    def test_same_params_produce_same_id(self):
        layout, cell = _new_layout()
        id1 = metadata.attach_pointer(cell, layout, "transmon", {"a": 1, "b": 2})
        id2 = metadata._stable_id("transmon", {"b": 2, "a": 1})  # different key order
        assert id1 == id2

    def test_different_params_produce_different_ids(self):
        id1 = metadata._stable_id("transmon", {"island_width": 420.0})
        id2 = metadata._stable_id("transmon", {"island_width": 400.0})
        assert id1 != id2

    def test_different_component_type_produces_different_id(self):
        id1 = metadata._stable_id("transmon", {"a": 1})
        id2 = metadata._stable_id("resonator", {"a": 1})
        assert id1 != id2

    def test_no_pointer_returns_none(self):
        layout, cell = _new_layout()
        assert metadata.read_pointer(cell, layout) is None

    def test_pointer_survives_gds_roundtrip(self, tmp_path):
        # The actual finding that shaped this design: cell properties are
        # lost on a plain GDS2 write/read in this project's klayout
        # package, but Text labels are not -- verify the real mechanism
        # (the text label), not just in-memory behavior.
        layout, cell = _new_layout()
        metadata_id = metadata.attach_pointer(cell, layout, "transmon", {"x": 1})

        gds_path = str(tmp_path / "roundtrip.gds")
        layout.write(gds_path)

        layout2 = pya.Layout()
        layout2.read(gds_path)
        cell2 = layout2.cell("TOP")

        assert metadata.read_pointer(cell2, layout2) == metadata_id

    def test_pointer_survives_oasis_roundtrip(self, tmp_path):
        layout, cell = _new_layout()
        metadata_id = metadata.attach_pointer(cell, layout, "transmon", {"x": 1})

        oas_path = str(tmp_path / "roundtrip.oas")
        layout.write(oas_path)

        layout2 = pya.Layout()
        layout2.read(oas_path)
        cell2 = layout2.cell("TOP")

        assert metadata.read_pointer(cell2, layout2) == metadata_id


class TestWriteReadMetadata:
    def test_round_trip(self, tmp_path):
        metadata_dir = str(tmp_path)
        data = {"f01_GHz": 5.123, "anharmonicity_MHz": -180.0, "source": "fem"}
        path = metadata.write_metadata("abc123", data, metadata_dir)
        assert os.path.isfile(path)

        result = metadata.read_metadata("abc123", metadata_dir)
        assert result == data

    def test_unpopulated_metadata_returns_none(self, tmp_path):
        assert metadata.read_metadata("does_not_exist", str(tmp_path)) is None

    def test_creates_metadata_dir_if_missing(self, tmp_path):
        metadata_dir = str(tmp_path / "nested" / "metadata")
        metadata.write_metadata("id1", {"a": 1}, metadata_dir)
        assert os.path.isfile(os.path.join(metadata_dir, "id1.json"))
