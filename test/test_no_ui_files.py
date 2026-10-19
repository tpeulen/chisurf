"""No Qt Designer ``.ui`` files, no ``.ui`` loaders and no ``.ui`` packaging globs.

The Qt shell is retired and every form is an AutoForm ``view.json`` drawn by emtk,
so there is nothing for a ``.ui`` file to be loaded by. There is no allow-list: a
new Designer file, a ``loadUi``-style call or a ``*.ui`` package-data glob fails.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOADER_NAMES = {
    "loadUi",
    "loadUiType",
    "qtpy_loadUi",
    "init_with_ui",
    "resolve_ui_path",
    "_compiled_ui_class",
    "compileUi",
}
PACKAGING_FILES = ("pyproject.toml", "setup.py", "MANIFEST.in", "pixi.toml")
_UI_GLOB = re.compile(r"""\*\.ui\b|["']\.ui["']""")


def _tracked_files() -> list[str]:
    """Return every path git tracks or would add (untracked, not ignored)."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [row for row in out.splitlines() if row]


def test_no_ui_files():
    """No Designer file exists anywhere in the tree git sees."""
    found = [p for p in _tracked_files() if p.endswith(".ui") and (ROOT / p).is_file()]
    assert not found, sorted(found)


def test_no_ui_loader_tokens():
    """No Python file names a ``.ui`` loader, imports ``uic`` or lists the ``.ui`` suffix."""
    violations = []
    for top in ("chisurf", "test", "build_tools"):
        for path in sorted((ROOT / top).rglob("*.py")):
            relative = str(path.relative_to(ROOT))
            if relative == "test/test_no_ui_files.py":
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    name = node.id
                elif isinstance(node, ast.Attribute):
                    name = node.attr
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    name = node.name
                elif isinstance(node, ast.alias):
                    name = node.name.rsplit(".", 1)[-1]
                elif isinstance(node, ast.Constant) and node.value in {".ui", "*.ui"}:
                    name = repr(node.value)
                else:
                    continue
                if (
                    name in LOADER_NAMES
                    or (isinstance(node, ast.alias) and name == "uic")
                    or isinstance(node, ast.Constant)
                ):
                    violations.append(f"{relative}:{getattr(node, 'lineno', '?')}: {name}")
    assert not violations, "\n".join(violations)


def test_no_ui_packaging_globs():
    """No package-data glob or suffix list still ships ``.ui`` files."""
    candidates = [ROOT / name for name in PACKAGING_FILES]
    recipe = ROOT / "rattler-recipe"
    if recipe.is_dir():
        candidates += sorted(recipe.rglob("*"))
    hits = []
    for path in candidates:
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if _UI_GLOB.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not hits, "\n".join(hits)
