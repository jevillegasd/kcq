import pya
import pytest

from kcq.utils import pcell_loader, xml_parser

SIMPLE_PCELL_SOURCE = """
import pya

class {class_name}(pya.PCellDeclarationHelper):
    def __init__(self):
        super().__init__()
        self.param("w", self.TypeDouble, "width", default=10.0)

    def produce_impl(self):
        pass
"""

NOT_A_PCELL_SOURCE = """
class NotAPCell:
    pass
"""

MISMATCHED_CLASS_SOURCE = """
import pya

class SomeOtherName(pya.PCellDeclarationHelper):
    def produce_impl(self):
        pass
"""


@pytest.fixture(autouse=True)
def _clear_tech_cache():
    xml_parser._TECH_CACHE.clear()
    yield
    xml_parser._TECH_CACHE.clear()


def _make_tech_with_pcells(tmp_path, monkeypatch, tech_name, files: dict):
    """files: {relative_path_under_pcells: source_code}"""
    tech_dir = tmp_path / tech_name
    pcells_dir = tech_dir / "pcells"
    pcells_dir.mkdir(parents=True, exist_ok=True)
    for rel_path, source in files.items():
        full_path = pcells_dir / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(source, encoding="utf-8")
    monkeypatch.setenv("KCQ_TECH_PATH", str(tmp_path))
    return pcells_dir


def _new_layout(tech_name):
    layout = pya.Layout()
    layout.dbu = 0.001
    layout.technology_name = tech_name
    layout.create_cell("TOP")
    return layout


class TestRegisterLibrary:
    def test_registers_a_single_pcell(self, tmp_path, monkeypatch):
        _make_tech_with_pcells(tmp_path, monkeypatch, "loader_tech1", {
            "Foo.py": SIMPLE_PCELL_SOURCE.format(class_name="Foo"),
        })
        pcell_loader.register_library("loader_tech1")

        layout = _new_layout("loader_tech1")
        cell = layout.create_cell("Foo", "loader_tech1", {"w": 5.0})
        assert cell is not None

    def test_registers_pcells_in_nested_subdirectories(self, tmp_path, monkeypatch):
        _make_tech_with_pcells(tmp_path, monkeypatch, "loader_tech2", {
            "Foo.py": SIMPLE_PCELL_SOURCE.format(class_name="Foo"),
            "junctions/Bar.py": SIMPLE_PCELL_SOURCE.format(class_name="Bar"),
        })
        pcell_loader.register_library("loader_tech2")

        layout = _new_layout("loader_tech2")
        assert layout.create_cell("Foo", "loader_tech2", {"w": 5.0}) is not None
        assert layout.create_cell("Bar", "loader_tech2", {"w": 5.0}) is not None

    def test_skips_underscore_prefixed_helper_files(self, tmp_path, monkeypatch):
        _make_tech_with_pcells(tmp_path, monkeypatch, "loader_tech3", {
            "Foo.py": SIMPLE_PCELL_SOURCE.format(class_name="Foo"),
            "_utils.py": "def helper(): return 1\n",
        })
        # Must not raise even though _utils.py has no PCellDeclarationHelper class.
        library = pcell_loader.register_library("loader_tech3")
        assert library is not None

    def test_skips_non_pcell_class(self, tmp_path, monkeypatch):
        _make_tech_with_pcells(tmp_path, monkeypatch, "loader_tech4", {
            "NotAPCell.py": NOT_A_PCELL_SOURCE,
        })
        library = pcell_loader.register_library("loader_tech4")
        assert library is not None
        layout = _new_layout("loader_tech4")
        assert layout.create_cell("NotAPCell", "loader_tech4", {}) is None

    def test_skips_file_with_mismatched_class_name(self, tmp_path, monkeypatch):
        _make_tech_with_pcells(tmp_path, monkeypatch, "loader_tech5", {
            "MismatchedClass.py": MISMATCHED_CLASS_SOURCE,
        })
        # Must not raise -- logs a warning and continues.
        library = pcell_loader.register_library("loader_tech5")
        assert library is not None

    def test_idempotent_reregistration(self, tmp_path, monkeypatch):
        _make_tech_with_pcells(tmp_path, monkeypatch, "loader_tech6", {
            "Foo.py": SIMPLE_PCELL_SOURCE.format(class_name="Foo"),
        })
        pcell_loader.register_library("loader_tech6")
        pcell_loader.register_library("loader_tech6")  # must not raise or duplicate-error

        layout = _new_layout("loader_tech6")
        assert layout.create_cell("Foo", "loader_tech6", {"w": 5.0}) is not None

    def test_pcell_and_fixed_cell_libraries_are_separate(self, tmp_path, monkeypatch):
        _make_tech_with_pcells(tmp_path, monkeypatch, "loader_tech8", {
            "Foo.py": SIMPLE_PCELL_SOURCE.format(class_name="Foo"),
        })
        pcell_library, fixed_cell_library = pcell_loader.register_library("loader_tech8")
        assert pcell_library.name() != fixed_cell_library.name()
        assert fixed_cell_library.name() == pcell_loader.fixed_cell_library_name("loader_tech8")

    def test_sub_instance_pattern_like_manhattan_squid(self, tmp_path, monkeypatch):
        # Mirrors how ManhattanSQUID builds itself from two Manhattan
        # sub-instances: a PCell's own produce_impl calling
        # self.layout.create_cell(pcell_name, lib_name, params).
        composite_source = """
import pya

class Composite(pya.PCellDeclarationHelper):
    def __init__(self):
        super().__init__()

    def produce_impl(self):
        sub = self.layout.create_cell("Foo", "loader_tech7", {"w": 5.0})
        if sub is None:
            raise RuntimeError("Foo PCell not found")
        self.cell.insert(pya.CellInstArray(sub.cell_index(), pya.Trans(0, 0)))
"""
        _make_tech_with_pcells(tmp_path, monkeypatch, "loader_tech7", {
            "Foo.py": SIMPLE_PCELL_SOURCE.format(class_name="Foo"),
            "Composite.py": composite_source,
        })
        pcell_loader.register_library("loader_tech7")

        layout = _new_layout("loader_tech7")
        cell = layout.create_cell("Composite", "loader_tech7", {})
        assert cell is not None
        assert cell.called_cells() or list(cell.each_inst())


class TestPackageLevelCorePCells:
    """Core PCells (e.g. Waveguide) live under this package's own
    python/kcq/pcells/, not any one technology's tech/<name>/pcells/,
    but still need to resolve via layout.create_cell(name, tech_name,
    params) for *every* technology -- register_pcell_library merges
    _core_pcells_dir() in alongside a technology's own pcells/."""

    def test_package_level_pcell_merges_into_an_arbitrary_technology_library(
        self, tmp_path, monkeypatch
    ):
        _make_tech_with_pcells(tmp_path, monkeypatch, "loader_tech9", {
            "Foo.py": SIMPLE_PCELL_SOURCE.format(class_name="Foo"),
        })
        core_pcells_dir = tmp_path / "core_pcells"
        core_pcells_dir.mkdir()
        (core_pcells_dir / "CoreWidget.py").write_text(
            SIMPLE_PCELL_SOURCE.format(class_name="CoreWidget"), encoding="utf-8"
        )
        monkeypatch.setattr(pcell_loader, "_core_pcells_dir", lambda: str(core_pcells_dir))

        pcell_loader.register_library("loader_tech9")

        layout = _new_layout("loader_tech9")
        assert layout.create_cell("Foo", "loader_tech9", {"w": 5.0}) is not None
        assert layout.create_cell("CoreWidget", "loader_tech9", {"w": 5.0}) is not None
