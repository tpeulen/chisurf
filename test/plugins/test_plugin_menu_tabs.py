"""Tree-wide guard on the ribbon tab a plugin manifest opens.

The ribbon builds its top-level tabs from the manifests themselves: the first
segment of ``display_name`` becomes a category, created on demand
(:meth:`PluginMethodsMixin._create_hierarchical_menu_structure`). A first
segment nobody else uses therefore opens a **whole tab holding one entry**,
beside the tab its siblings live in, and nothing says so — the same
misdescribes-its-own-location failure family as INC-07's ``Uncategorized``
plugin and its case-split sibling menus.

``img_tracking`` declared ``Microscopy:Imaging:Particle Tracking`` while the
fourteen other tools in ``plugins/microscopy/`` declared ``Imaging:…``, so the
ribbon grew a ``Microscopy`` tab whose single ``Imaging`` panel held that one
tool. The set below is the closed vocabulary that replaces the accident.
"""

from __future__ import annotations

import json
import pathlib

import chisurf.plugins

#: The top-level menu segments a menu-visible manifest may declare.
#:
#: ``Main``/``Edit``/``Analysis``/``Tools`` are built statically by
#: ``ribbon_categories.py`` and reused when a plugin names them; ``Setup`` and
#: ``Help`` are pulled out of the plugin loop and rendered by their own hosts;
#: ``Spectroscopy``/``Structure``/``Imaging`` are the domain tabs the plugins
#: themselves create. Adding a tab is a deliberate act — extend this set.
ALLOWED_TOP_LEVEL = frozenset(
    {
        "Main",
        "Edit",
        "Analysis",
        "Tools",
        "Setup",
        "Help",
        "Spectroscopy",
        "Structure",
        "Imaging",
    }
)


def _plugins_root() -> pathlib.Path:
    """Return the built-in plugin package directory.

    Returns
    -------
    pathlib.Path
        Directory the manifest paths below are reported relative to.
    """
    return pathlib.Path(chisurf.plugins.__file__).parent


def _builtin_manifests() -> list[tuple[pathlib.Path, dict]]:
    """Return every built-in manifest path together with its contents.

    Returns
    -------
    list of (pathlib.Path, dict)
        Sorted ``(path, manifest)`` pairs, excluding the cookiecutter template
        whose fields are placeholders rather than real labels.
    """
    return [
        (mf, json.loads(mf.read_text()))
        for mf in sorted(_plugins_root().rglob("manifest.json"))
        if "cookiecutter" not in str(mf)
    ]


def _reaches_the_ribbon(manifest: dict) -> bool:
    """Return whether the ribbon builds a tab for this manifest.

    Parameters
    ----------
    manifest : dict
        Parsed ``manifest.json`` contents.

    Returns
    -------
    bool
        ``True`` when the plugin is neither ``menu_hidden`` nor CLI-only.
        ``cli_only`` is derived as "declares no GUI entrypoint"
        (:func:`chisurf.plugins._read_manifest_metadata`), and the ribbon hides
        those outside experimental mode — so neither kind opens a tab.
    """
    if manifest.get("menu_hidden"):
        return False
    return bool((manifest.get("entrypoints") or {}).get("gui"))


def test_manifests_exist():
    """The tree-wide guard below is only meaningful over a populated tree."""
    assert len(_builtin_manifests()) > 50


def test_menu_visible_plugins_use_the_known_top_level_tabs():
    """INC-07 guard: no plugin opens a ribbon tab of its own invention."""
    root = _plugins_root()
    bad = []
    for mf, data in _builtin_manifests():
        if not _reaches_the_ribbon(data):
            continue
        parents = [p.strip() for p in (data.get("display_name") or "").split(":")[:-1]]
        if parents and parents[0] not in ALLOWED_TOP_LEVEL:
            bad.append(f"{mf.relative_to(root)}: top-level segment {parents[0]!r}")
    assert not bad, (
        f"manifests declaring a ribbon tab outside the known set {sorted(ALLOWED_TOP_LEVEL)}: {bad}"
    )


def test_every_allowed_tab_is_one_the_ribbon_really_builds():
    """The vocabulary is not free-form: each entry is a tab that exists.

    Either the ribbon creates it statically, or at least one menu-visible
    plugin declares it — otherwise the set would drift into a wish list and
    stop catching the next accidental tab.
    """
    static = {"Main", "Edit", "Analysis", "Tools"}  # ribbon_categories.py
    hosted = {"Setup", "Help"}  # rendered outside the plugin loop
    declared = {
        (data.get("display_name") or "").split(":")[0].strip()
        for _mf, data in _builtin_manifests()
        if _reaches_the_ribbon(data)
    }
    unused = ALLOWED_TOP_LEVEL - static - hosted - declared
    assert not unused, f"allowed tabs no plugin and no host builds: {sorted(unused)}"


def test_particle_tracking_sits_with_the_other_imaging_tools():
    """Pin the manifest this guard was written for."""
    manifest = _plugins_root() / "microscopy" / "img_tracking" / "manifest.json"
    data = json.loads(manifest.read_text())
    assert data["display_name"] == "Imaging:Particle Tracking"
    assert data["categories"][0] == "Imaging"
