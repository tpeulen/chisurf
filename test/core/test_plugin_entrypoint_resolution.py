"""Every ``entrypoints`` target declared in a manifest must actually resolve.

``chisurf/core/cli.py`` registers plugin commands from ``manifest.json`` *without*
importing the plugin, so a manifest that points at a module attribute which does
not exist only fails when the user runs the command — ``csc --help`` happily
lists it. The classic way to break this is a sibling ``cli.py`` next to a ``cli/``
package: the package always wins, the module file becomes unreachable, and the
attribute the manifest names is nowhere to be found (RF-138).

These tests resolve every ``entrypoints.gui`` / ``.cli`` / ``.services`` target
statically — module path to file, honouring the package-shadows-module rule, then
AST-scan that file for the named attribute — so the whole class of defect is
caught without importing Qt or any plugin.
"""

from __future__ import annotations

import ast
import importlib
import json
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "chisurf" / "plugins"
ENTRYPOINT_KINDS = ("gui", "cli", "services")


def _manifest_entrypoints() -> list[tuple[str, str, str]]:
    """Return ``(plugin directory, kind, entrypoint)`` for every built-in manifest."""
    out: list[tuple[str, str, str]] = []
    for manifest_path in sorted(PLUGIN_ROOT.rglob("manifest.json")):
        if any("{{" in part for part in manifest_path.parts):
            continue  # cookiecutter scaffold, not a real plugin
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        entrypoints = manifest.get("entrypoints") or {}
        plugin_dir = str(manifest_path.parent.relative_to(PLUGIN_ROOT))
        for kind in ENTRYPOINT_KINDS:
            entry = entrypoints.get(kind)
            if isinstance(entry, str) and entry.strip():
                out.append((plugin_dir, kind, entry.strip()))
    return out


def _module_file(module_path: str) -> pathlib.Path | None:
    """Return the source file a dotted ``chisurf.*`` module resolves to.

    Mirrors the import system's precedence: a directory with an ``__init__.py``
    shadows a same-named ``.py`` file in the same parent. Returns ``None`` for
    modules outside the source tree (e.g. ``mmfdb``, ``ndxplorer``), which live
    in ``modules/`` and are not checked here.
    """
    parts = module_path.split(".")
    if parts[0] != "chisurf":
        return None
    parent = REPO_ROOT
    for part in parts[:-1]:
        parent = parent / part
        if not parent.is_dir():
            return None
    package_init = parent / parts[-1] / "__init__.py"
    if package_init.exists():
        return package_init
    module_py = parent / f"{parts[-1]}.py"
    return module_py if module_py.exists() else None


def _binds_name(path: pathlib.Path, name: str) -> bool:
    """Return whether a module file binds *name* at module level.

    Counts definitions (``def``/``class``), assignments and imports, including
    those nested in a top-level ``if``/``try`` block, plus star imports (which
    may bind anything).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))

    def binds(node: ast.AST) -> bool:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return node.name == name
        if isinstance(node, ast.Assign):
            return any(isinstance(t, ast.Name) and t.id == name for t in node.targets)
        if isinstance(node, ast.AnnAssign):
            return isinstance(node.target, ast.Name) and node.target.id == name
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return any(
                alias.name == "*" or (alias.asname or alias.name.split(".")[0]) == name
                for alias in node.names
            )
        return False

    for node in tree.body:
        if binds(node):
            return True
        if isinstance(node, (ast.If, ast.Try)) and any(binds(sub) for sub in ast.walk(node)):
            return True
    return False


def _split(kind: str, entry: str, plugin_dir: str) -> tuple[str, str]:
    """Return ``(module path, attribute)`` for a manifest entrypoint."""
    if kind == "cli":
        from chisurf.core.cli import _parse_cli_entrypoint

        default_alias = pathlib.Path(plugin_dir).name.replace("_", "-")
        _, module_path, attr = _parse_cli_entrypoint(entry, default_alias)
        return module_path, attr
    module_path, _, attr = entry.partition(":")
    return module_path.strip(), attr.strip()


def test_entrypoint_scan_is_not_empty():
    """The scan finds the plugin entrypoints (guards against a false pass)."""
    assert len(_manifest_entrypoints()) > 100


@pytest.mark.parametrize(
    "plugin_dir,kind,entry",
    [pytest.param(*item, id=f"{item[0]}:{item[1]}") for item in _manifest_entrypoints()],
)
def test_manifest_entrypoint_resolves(plugin_dir, kind, entry):
    """The module a manifest names exists and binds the attribute it names."""
    module_path, attr = _split(kind, entry, plugin_dir)
    assert attr, f"{plugin_dir} entrypoints.{kind} = {entry!r} names no attribute"
    path = _module_file(module_path)
    if path is None:
        if module_path.startswith("chisurf."):
            pytest.fail(f"{plugin_dir} entrypoints.{kind} = {entry!r}: no such module file")
        pytest.skip(f"{module_path} lives outside the chisurf source tree")
    assert _binds_name(path, attr), (
        f"{plugin_dir} entrypoints.{kind} = {entry!r}: "
        f"{path.relative_to(REPO_ROOT)} does not define or import {attr!r}"
    )


@pytest.mark.parametrize(
    "module_path",
    [
        "chisurf.plugins.tttr.trace_browser.cli",
        "chisurf.plugins.tttr.tttr_image_browser.cli",
    ],
)
def test_shadowed_cli_shims_are_gone(module_path):
    """The ``cli`` package — not an unreachable sibling shim — exports ``cli``.

    Both plugins used to ship a ``cli.py`` next to their ``cli/`` package; the
    package shadowed it, so the manifest's ``…cli:cli`` target did not exist.
    """
    parts = module_path.split(".")
    package_dir = REPO_ROOT.joinpath(*parts)
    assert (package_dir / "__init__.py").exists()
    assert not package_dir.with_suffix(".py").exists(), "the shadowed shim is back"

    import click

    module = importlib.import_module(module_path)
    assert isinstance(module.cli, click.Group)
