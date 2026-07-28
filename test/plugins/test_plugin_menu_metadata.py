"""Tree-wide guards on the menu path a plugin manifest declares.

``display_name`` is the one live identity field: the manifest wins over the
legacy module-level ``name`` (:func:`chisurf.plugins._read_manifest_metadata`),
and its ``:``-separated segments are what the ribbon and the generated plugin
catalogue group by. A manifest that omits the path does not fail — it lands in
a fallback bucket (``Main`` in the ribbon, ``Uncategorized`` in the catalogue),
which is the silent-misdescription failure mode of INC-07.
"""

from __future__ import annotations

import json
import pathlib

import pytest

import chisurf.plugins


def _builtin_manifests() -> list[pathlib.Path]:
    """Return every built-in ``manifest.json``, minus the cookiecutter template.

    Returns
    -------
    list of pathlib.Path
        Manifest paths, sorted, excluding the template whose fields are
        ``{{ cookiecutter.* }}`` placeholders rather than real labels (plugin
        discovery skips it on the same grounds).
    """
    root = pathlib.Path(chisurf.plugins.__file__).parent
    return [mf for mf in sorted(root.rglob("manifest.json")) if "cookiecutter" not in str(mf)]


def test_manifests_exist():
    """The tree-wide guards below are only meaningful over a populated tree."""
    assert len(_builtin_manifests()) > 50


def test_builtin_manifests_declare_a_menu_path():
    """INC-07 guard: every ``display_name`` carries at least one parent segment.

    Without a ``:`` the ribbon's name parser returns the ``Main`` fallback
    category and the catalogue generator prints ``Uncategorized`` — so a plugin
    silently advertises a location its author never chose, and the ``Categories``
    row on its own docs page contradicts its ``Menu path`` row.
    """
    root = pathlib.Path(chisurf.plugins.__file__).parent
    pathless = [
        str(mf.relative_to(root))
        for mf in _builtin_manifests()
        if ":" not in (json.loads(mf.read_text()).get("display_name") or "")
    ]
    assert not pathless, (
        "manifests whose display_name declares no menu path (they fall back to "
        f"Main/Uncategorized): {pathless}"
    )


@pytest.mark.parametrize("display_name", ["Spectra Downloader", "", "Tools"])
def test_pathless_names_fall_back(display_name):
    """Pin the fallback these guards exist to prevent, on the live parser."""
    from chisurf.gui.widgets.ribbon.ribbon_plugins import PluginMethodsMixin

    hierarchy, leaf = PluginMethodsMixin._parse_hierarchical_plugin_name(None, display_name)
    assert hierarchy == ["Main"]
    assert leaf == display_name.strip()


def test_spectra_downloader_is_reachable_under_spectroscopy():
    """The one manifest that had dropped its path keeps it.

    Its module-level ``name`` declared ``Spectroscopy:Spectra Downloader`` all
    along; the manifest added later omitted the path, and the manifest wins.
    """
    root = pathlib.Path(chisurf.plugins.__file__).parent
    data = json.loads((root / "spectra_downloader" / "manifest.json").read_text())
    assert data["display_name"] == "Spectroscopy:Spectra Downloader"
    assert data["categories"][0] == "Spectroscopy"
