"""AST-based lint enforcing kcq's "evaluate/manipulate cell.shapes, not
cell directly" coding standard.

Name-based heuristic (plain `ast` can't resolve real types): flags calls
like `cell.insert(...)` where the receiver is a cell-like variable name
and the method also exists on pya.Shapes/pya.Region.
"""

import ast
import os

# Methods that exist on both pya.Cell (as a shortcut) and pya.Shapes /
# pya.Region -- calling them on a cell-like variable is almost always the
# shortcut kcq's standard forbids.
FORBIDDEN_METHODS = frozenset({"insert", "is_empty", "each", "flatten", "erase", "clear"})

# Variable/parameter names treated as "this is a cell" for the heuristic.
CELL_LIKE_NAMES = frozenset({"cell", "top", "top_cell", "target_cell"})


def check_shapes_convention(module_path: str) -> list:
    """Returns a list of 'file:line: message' violation strings for the
    Python source file at `module_path`. Empty list means clean."""
    with open(module_path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=module_path)

    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        func = node.func
        if func.attr not in FORBIDDEN_METHODS:
            continue
        target = func.value
        if isinstance(target, ast.Name) and target.id in CELL_LIKE_NAMES:
            violations.append(
                f"{module_path}:{node.lineno}: '{target.id}.{func.attr}(...)' looks like a "
                f"cell-level shortcut; use '{target.id}.shapes(layer).{func.attr}(...)' instead"
            )
    return violations


def check_directory(root_dir: str) -> list:
    """Runs check_shapes_convention over every .py file under root_dir,
    recursively. Returns the combined violation list."""
    violations = []
    for dirpath, _dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith(".py"):
                violations.extend(check_shapes_convention(os.path.join(dirpath, filename)))
    return violations
