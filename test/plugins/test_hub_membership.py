"""Every tool has one home: a ribbon button, or a panel in exactly one hub.

A hub (TTTR Tools, Image Tools, Calculators, ...) is one ribbon button standing
for the tools it hosts. The ribbon knows nothing about hubs: a hosted tool
disappears from it only because its own manifest says ``menu_hidden``. So three
things drift apart silently, and each is checked here:

* a hosted tool that is **not** hidden shows twice — as its own button and
  inside its hub;
* a tool hosted by **two** hubs has two homes, and the next edit lands in one;
* a hidden tool hosted by **no** hub cannot be reached from the GUI at all.

Children are read from each hub's own declaration (``panels.json``, a registry,
a panel table), never from a list kept here.
"""

from __future__ import annotations

import json
import pathlib
import re
from functools import cache

import pytest

import chisurf.plugins

ROOT = pathlib.Path(chisurf.plugins.__file__).parent

#: Plugins hosted by two hubs on purpose, with the reason.
SHARED = {
    "setup_channel_definition": "Settings edits detector setups; Image Tools' Setup step is the "
    "pipeline context every imaging step reads.",
    "fcs_channel_preset": "Settings edits FCS definitions; the FCS correlator workflow picks one.",
    "burst_fcs_correlator": "Burst-wise FCS is both a burst-analysis step and an FCS method.",
}

#: Hosted plugins that keep their own ribbon button, with the reason.
VISIBLE_CHILDREN = {
    "ndxplorer": "a standalone application; the ALEX suite embeds it as its E-S histogram.",
}

#: Hidden plugins with a GUI that no hub hosts, with the reason.
UNHOSTED = {
    "project_browser": "File › Project › Project Browser opens it.",
}


@cache
def manifests() -> dict[str, tuple[pathlib.Path, dict]]:
    """``{plugin id: (plugin dir, manifest)}`` for every built-in manifest."""
    found = {}
    for path in sorted(ROOT.rglob("manifest.json")):
        if "cookiecutter" in str(path) or "/renders/" in str(path):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        found[data["id"]] = (path.parent, data)
    return found


def plugin_of(ref: str) -> str | None:
    """The id of the plugin a module path, ``family/name`` path or id names."""
    module = ref.split(":", 1)[0]
    if module.startswith("chisurf.plugins."):
        parts = module.split(".")[2:]
    elif "/" in module:
        parts = [p for p in module.split("/") if p]
    else:
        return module if module in manifests() else None
    by_dir = {d: pid for pid, (d, _m) in manifests().items()}
    for end in range(len(parts), 0, -1):
        pid = by_dir.get(ROOT.joinpath(*parts[:end]))
        if pid:
            return pid
    return None


def _module_refs(*paths: pathlib.Path) -> list[str]:
    """Plugins a hub's panel code names: imported modules and ``"plugin": "family/name"`` keys."""
    refs = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        refs += re.findall(r"from (chisurf\.plugins\.[\w.]+) import", text)
        refs += re.findall(r'"plugin":\s*"([\w/-]+)"', text)
    return refs


def _panels_json(rel: str) -> list[str]:
    spec = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    return [p["entrypoint"] for p in spec["panels"] if not p.get("separator")]


def _declared_children() -> dict[str, list[str]]:
    """``{hub id: [child refs]}``, read from each hub's declaration."""
    from chisurf.plugins.burst.burst_analysis.gui.native import STEPS as BURST
    from chisurf.plugins.calculator.hub.core.registry import default_calculators
    from chisurf.plugins.core.setup.gui.model import PANELS as SETUP
    from chisurf.plugins.core.wizards.core.registry import default_wizards
    from chisurf.plugins.fluorescence_decay.lifetime_analysis.gui.app import PANELS as DECAY
    from chisurf.plugins.microscopy.imaging_tools.gui.app import PANELS as IMAGING
    from chisurf.plugins.misc.games.gui.registry import GAME_PANELS
    from chisurf.plugins.modelling.structure_tools.registry import STRUCTURE_TOOL_PANELS
    from chisurf.plugins.traj.traj_tools.registry import TOOL_PANELS

    return {
        "tttr_toolbox": _panels_json("tttr/tttr_toolbox/gui/panels.json"),
        "filetools": _panels_json("tttr/filetools/gui/panels.json"),
        "imaging_tools": [row[1] for row in IMAGING],
        "calculators": [e.widget for e in default_calculators()],
        "wizards": [e.widget for e in default_wizards()],
        "games": [p["class_path"] for p in GAME_PANELS],
        "setup": [ref for p in SETUP for ref in (p.plugin, p.entry) if ref],
        # Its native cards live in the hub; the Qt panel table names the plugins behind them.
        "structure_tools": [p["emtk"] for p in STRUCTURE_TOOL_PANELS]
        + _module_refs(ROOT / "modelling/structure_tools/gui/tool.py"),
        "traj_tools": [p["emtk"] for p in TOOL_PANELS],
        "lifetime_analysis": [row[0] for row in DECAY],
        "burst_analysis": [p["plugin"] for p in BURST if p.get("plugin")],
        # Qt-only hubs: their panel factories import the hosted tools.
        "alex_suite": _module_refs(ROOT / "burst/alex_suite/gui/tool.py"),
        "fcs_toolbox": _module_refs(ROOT / "fcs/fcs_toolbox/tool.py", ROOT / "fcs/fcs_toolbox/gui/app.py"),
        "fcs_correlator": _module_refs(ROOT / "fcs/fcs_correlator/tool.py", ROOT / "fcs/fcs_correlator/gui/app.py"),
    }


@cache
def hub_children() -> dict[str, frozenset[str]]:
    """``{hub id: {child plugin id}}``; a hub never counts as its own child."""
    resolved = {}
    for hub, refs in _declared_children().items():
        ids = {plugin_of(ref) for ref in refs}
        resolved[hub] = frozenset(i for i in ids if i and i != hub)
    return resolved


def test_every_hub_is_a_known_plugin_and_declares_children():
    for hub, children in hub_children().items():
        assert hub in manifests(), hub
        assert children, f"{hub}: no hosted tool was found in its declaration"


def test_hosted_tools_have_no_ribbon_button_of_their_own():
    shown = sorted(
        f"{child} (in {hub})"
        for hub, children in hub_children().items()
        for child in children
        if child not in VISIBLE_CHILDREN and not manifests()[child][1].get("menu_hidden")
        and child not in hub_children()  # a hub inside a hub keeps its own visibility rule
    )
    assert not shown, f"hosted by a hub but still a ribbon button: {shown}"


def test_no_tool_lives_in_two_hubs():
    homes: dict[str, list[str]] = {}
    for hub, children in hub_children().items():
        for child in children:
            homes.setdefault(child, []).append(hub)
    doubled = {c: sorted(h) for c, h in homes.items() if len(h) > 1 and c not in SHARED}
    assert not doubled, f"hosted by more than one hub: {doubled}"


@pytest.mark.parametrize("table", [SHARED, VISIBLE_CHILDREN, UNHOSTED], ids=["shared", "visible", "unhosted"])
def test_every_exception_is_still_needed(table):
    """An allow-list line whose reason no longer holds is deleted, not kept."""
    homes = [c for children in hub_children().values() for c in children]
    for pid in table:
        assert pid in manifests(), f"{pid}: no such plugin any more"
        if table is SHARED:
            assert homes.count(pid) > 1, f"{pid}: no longer in two hubs"
        elif table is VISIBLE_CHILDREN:
            assert pid in homes and not manifests()[pid][1].get("menu_hidden"), pid
        else:
            assert pid not in homes, f"{pid}: now hosted by a hub"
            assert manifests()[pid][1].get("menu_hidden"), f"{pid}: has its own button now"


def test_every_hidden_tool_is_reachable_from_a_hub():
    hosted = {c for children in hub_children().values() for c in children}
    lost = []
    for pid, (_d, manifest) in manifests().items():
        entry = manifest.get("entrypoints", {})
        has_gui = bool(entry.get("gui") or entry.get("emtk"))
        demo = "Games" in manifest.get("display_name", "").split(":")[:-1]
        if manifest.get("menu_hidden") and has_gui and pid not in hosted and not demo:
            if pid not in UNHOSTED:
                lost.append(f"{pid} ({manifest.get('display_name')})")
    assert not lost, f"hidden, and no hub hosts them — unreachable from the GUI: {sorted(lost)}"
