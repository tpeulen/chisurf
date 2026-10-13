"""Guard: pyqtgraph is gone, and chiplot is *the* plotting API.

**The rule: plot through chiplot.** ``chisurf.gui.chiplot`` is the plotting API
and its only renderer is emtk. pyqtgraph is not a dependency any more (W8
removed the last two importers, the AutoForm ``image`` section and the Qt
intensity-trace tool, then the backend itself), so concretely:

* no file under ``chisurf/`` may import pyqtgraph, and there is no allow-list
  to add yourself to;
* ``pixi.toml``, ``pyproject.toml`` and the conda recipe do not declare it;
* asking chiplot for the pyqtgraph backend fails with a message that says it was
  removed, instead of an unexplained ``KeyError``;
* use the chiplot spelling -- ``Plot.line`` not ``plot``, ``to_pen`` not
  ``mkPen`` -- chiplot has no passthrough to a backing library, so another
  spelling is an ``AttributeError`` where it is written;
* **if chiplot cannot do it, add the API to chiplot**, then use it. Reaching
  into the backend's internals through ``.native`` is the other way past the
  seam, and ``test/chiplot_native_allowlist.txt`` (empty, and it stays so) is
  its guard.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PKG = _ROOT / "chisurf"
_IMPORT_RE = re.compile(r"^\s*(?:import\s+pyqtgraph|from\s+pyqtgraph)", re.MULTILINE)
_DOCKAREA_RE = re.compile(
    r"^\s*(?:import\s+pyqtgraph\.dockarea|from\s+pyqtgraph\.dockarea\s+import|"
    r"from\s+pyqtgraph\s+import\s+dockarea)",
    re.MULTILINE,
)


def _current_importers() -> set[str]:
    found = set()
    for path in _PKG.rglob("*.py"):
        if _IMPORT_RE.search(path.read_text(encoding="utf-8", errors="ignore")):
            found.add(path.relative_to(_ROOT).as_posix())
    return found


def test_nothing_imports_pyqtgraph():
    """No file under ``chisurf/`` imports pyqtgraph; there is no allow-list."""
    offenders = sorted(_current_importers())
    assert not offenders, (
        "pyqtgraph was removed -- plot through chisurf.gui.chiplot instead:\n  "
        + "\n  ".join(offenders)
    )
    assert not (_ROOT / "test" / "pyqtgraph_import_allowlist.txt").exists(), (
        "the import allow-list is retired with the dependency"
    )
    assert not (_PKG / "gui" / "chiplot" / "backends" / "pyqtgraph_backend.py").exists()
    assert not (_PKG / "gui" / "chiplot" / "_passthrough.py").exists()


@pytest.mark.parametrize("manifest", ["pixi.toml", "pyproject.toml", "rattler-recipe/recipe.yaml"])
def test_the_dependency_is_not_declared(manifest):
    """pyqtgraph is in no dependency list: the build files do not pull it in."""
    text = (_ROOT / manifest).read_text(encoding="utf-8")
    declared = [
        line.strip()
        for line in text.splitlines()
        if "pyqtgraph" in line.lower() and not line.strip().startswith("#")
    ]
    assert not declared, f"{manifest} still declares pyqtgraph: {declared}"


def test_asking_for_the_pyqtgraph_backend_says_it_was_removed(monkeypatch):
    """A stale ``CHISURF_PLOT_BACKEND=pyqtgraph`` fails with the reason."""
    from chisurf.chiplot import backends

    monkeypatch.setenv("CHISURF_PLOT_BACKEND", "pyqtgraph")
    monkeypatch.setattr(backends, "_active", None)
    with pytest.raises(KeyError, match="pyqtgraph backend was removed"):
        backends.get_backend()
    with pytest.raises(KeyError, match="pyqtgraph backend was removed"):
        backends.set_backend("pyqtgraph")
    assert backends.available_backends() == ["emtk"]
    # an unknown name still lists what is registered
    monkeypatch.setenv("CHISURF_PLOT_BACKEND", "nonesuch")
    monkeypatch.setattr(backends, "_active", None)
    with pytest.raises(KeyError, match="registered"):
        backends.get_backend()


def test_no_pyqtgraph_dockarea():
    """``pyqtgraph.dockarea`` is deprecated repo-wide — use the chisurf DockArea.

    Replaced by ``chisurf.gui.widgets.dock_area.dock_area`` (DockArea /
    DockSplitter). This guard forbids reintroducing the pyqtgraph dock system.
    """
    offenders = sorted(
        path.relative_to(_ROOT).as_posix()
        for path in _PKG.rglob("*.py")
        if _DOCKAREA_RE.search(path.read_text(encoding="utf-8", errors="ignore"))
    )
    assert not offenders, (
        "pyqtgraph.dockarea is deprecated — use chisurf.gui.widgets.dock_area "
        "(DockArea / DockSplitter) instead:\n  " + "\n  ".join(offenders)
    )


# ── the other way past the seam: ``.native`` ──────────────────────────────────
#
# ``Plot.native`` is the *documented* escape hatch to the backend's own object
# (emtk's display list), which makes it the invisible one: it reaches the
# renderer without importing it, so every check above passes while the call site
# is as coupled to the renderer as a direct import. Most of these were never
# gaps -- they predate the chiplot API that covers them (``set_si_prefix``,
# ``set_axis_visible``, ``set_tick_spacing``, ``legend``).
#
# The list is empty, and adding to it is never the fix.

_NATIVE_ALLOWLIST = _ROOT / "test" / "chiplot_native_allowlist.txt"
#: ``.native`` on a chiplot handle or canvas. Deliberately loose — it also
#: catches ``handle.native``, which is the same reach one level down.
_NATIVE_RE = re.compile(r"\.native\b(?!_)")
#: Attribute names that merely *start* with ``native`` and have nothing to do
#: with plotting (``self.native_tools``, ``native_cutoff_on``).
_NATIVE_FALSE_POSITIVES = re.compile(r"\.native_[a-z]")
#: A ``#`` comment. Naming the escape hatch in prose — which the comment
#: *explaining a port away from it* necessarily does — is not reaching through
#: it, and a guard that cannot tell the difference punishes documenting the fix.
_COMMENT_RE = re.compile(r"#.*$", re.MULTILINE)


def _load_native_allowlist() -> set[str]:
    if not _NATIVE_ALLOWLIST.is_file():
        return set()
    lines = _NATIVE_ALLOWLIST.read_text().splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}


def _current_native_users() -> set[str]:
    """Return the files that read a ``.native`` attribute in real code.

    Parsed, not matched: ``native`` is also a *module* name here
    (``chisurf.core.fitting.mcts.native``, ``emtk.gpu.native``), and a
    text search reported every import of one and every docstring that named one
    as a reach past the seam. An attribute read is an ``ast.Attribute``; an
    import is not, and neither is prose.
    """
    found = set()
    for path in _PKG.rglob("*.py"):
        rel = path.relative_to(_ROOT).as_posix()
        if rel.startswith(("chisurf/chiplot/", "chisurf/gui/chiplot/")):
            continue  # chiplot *is* the seam; ``.native`` is its own property
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:  # pragma: no cover - not this test's business
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "native":
                found.add(rel)
                break
    return found


def test_no_new_reaches_past_the_chiplot_seam():
    """A file outside chiplot must not reach the renderer through ``.native``."""
    offenders = sorted(_current_native_users() - _load_native_allowlist())
    assert not offenders, (
        "these files reach the renderer through the chiplot escape hatch:\n  "
        + "\n  ".join(offenders)
        + "\n\nCheck whether chiplot already has the API — most of these predate "
        "one that exists (set_si_prefix, set_axis_visible, set_tick_spacing, "
        "legend). If it genuinely does not, add it to chiplot and use that. Do "
        "NOT add the file to test/chiplot_native_allowlist.txt; that list only "
        "shrinks."
    )


def test_native_allowlist_has_no_stale_entries():
    """A file that no longer reaches past the seam must be struck from the list."""
    stale = sorted(_load_native_allowlist() - _current_native_users())
    assert not stale, (
        "these files no longer use .native — remove them from "
        "test/chiplot_native_allowlist.txt:\n  " + "\n  ".join(stale)
    )


def test_no_setting_or_ui_string_names_pyqtgraph():
    """No settings key and no user-facing string names the removed renderer.

    A setting that names pyqtgraph is a control that changes nothing -- Settings ▸ Plots
    showed a "pyqtgraph Configuration" section and a renderer choice with one option for
    as long as the keys were in ``settings_chisurf.yaml``. Shipped settings, view specs,
    guided tours and help pages are checked; the retired keys live on only in the
    migration that removes them from old settings files (``settings_utils.RETIRED_KEYS``).
    """
    import yaml

    offenders = []

    def keys(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                if "pyqtgraph" in str(key).lower():
                    offenders.append(f"{path}/{key}")
                keys(value, f"{path}/{key}")
        elif isinstance(node, list):
            for value in node:
                keys(value, path)

    for settings in sorted((_PKG / "core" / "settings").glob("*.yaml")):
        keys(yaml.safe_load(settings.read_text(encoding="utf-8")), settings.name)
    ui_files = [
        *_PKG.rglob("*.view.json"),
        *_PKG.rglob("guide.json"),
        *_PKG.rglob("*guide*.json"),
        *_PKG.rglob("help.md"),
        *_PKG.rglob("*_help.md"),
        *_PKG.rglob("manifest.json"),
    ]
    for path in sorted(set(ui_files)):
        if "pyqtgraph" in path.read_text(encoding="utf-8", errors="ignore").lower():
            offenders.append(path.relative_to(_ROOT).as_posix())
    assert not offenders, "the removed renderer is still named in settings / UI text:\n  " + (
        "\n  ".join(offenders)
    )
