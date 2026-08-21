import os

from kcq.verification import lint

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PACKAGE_ROOT = os.path.join(_REPO_ROOT, "python", "kcq")


def _write(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return str(path)


class TestCheckShapesConvention:
    def test_flags_cell_level_insert_shortcut(self, tmp_path):
        path = _write(tmp_path, "bad.py", "def f(cell, region):\n    cell.insert(region)\n")
        violations = lint.check_shapes_convention(path)
        assert len(violations) == 1
        assert "bad.py:2" in violations[0]
        assert "cell.insert" in violations[0]

    def test_flags_cell_level_is_empty_shortcut(self, tmp_path):
        path = _write(tmp_path, "bad2.py", "def f(top):\n    return top.is_empty()\n")
        violations = lint.check_shapes_convention(path)
        assert len(violations) == 1
        assert "top.is_empty" in violations[0]

    def test_allows_shapes_based_insert(self, tmp_path):
        path = _write(
            tmp_path, "good.py",
            "def f(cell, layer_index, region):\n    cell.shapes(layer_index).insert(region)\n",
        )
        assert lint.check_shapes_convention(path) == []

    def test_allows_forbidden_method_names_on_non_cell_variables(self, tmp_path):
        # Same method name, but the receiver isn't a cell-like variable
        # (e.g. a Region/Shapes object already) -- not a violation.
        path = _write(
            tmp_path, "region_ops.py",
            "def f(region, other):\n    region.insert(other)\n    return region.is_empty()\n",
        )
        assert lint.check_shapes_convention(path) == []

    def test_ignores_unrelated_method_calls_on_cell(self, tmp_path):
        path = _write(tmp_path, "unrelated.py", "def f(cell):\n    return cell.name\n")
        assert lint.check_shapes_convention(path) == []


class TestCheckDirectory:
    def test_finds_violations_across_multiple_files(self, tmp_path):
        _write(tmp_path, "a.py", "def f(cell, r):\n    cell.insert(r)\n")
        (tmp_path / "sub").mkdir()
        _write(tmp_path / "sub", "b.py", "def g(top):\n    top.erase(0)\n")
        violations = lint.check_directory(str(tmp_path))
        assert len(violations) == 2

    def test_kcq_package_source_is_clean(self):
        # The actual enforcement: no cell.<method> shortcut anywhere in
        # the shipped kcq package (this is what Phase 5's full-codebase
        # standards check builds on).
        violations = lint.check_directory(_PACKAGE_ROOT)
        assert violations == [], "\n".join(violations)
