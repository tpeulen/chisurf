#!/usr/bin/env python
"""Generate the ChiSurf plugin & parameter reference for Sphinx.

This walks every ``manifest.json`` under ``chisurf/plugins/`` and, for each
plugin, extracts:

* identity (id, menu path, categories, surfaces) from the manifest,
* every declarative UI parameter from the plugin's AutoForm ``*.view.json``
  files (``value`` / ``choice`` / ``toggle`` / ``toggle_row`` / ``table``
  sections — attribute, label, kind, range, default, description),
* the JSON-RPC method surface from the manifest.

It writes one page per plugin under ``docs/reference/plugins/<id>.md``, a
catalogue ``docs/reference/plugins/index.md`` grouped by category, and a master
**parameter glossary** ``docs/reference/parameters.md`` built from the parameter
registry (``chisurf/core/settings/constants/parameter_registry.json``) so that
every named fit/model parameter has an explanation in one place.

Usage::

    python build_tools/docs/generate_plugin_docs.py
"""

from __future__ import annotations

import json
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
PLUGIN_ROOT = REPO_ROOT / "chisurf" / "plugins"
REGISTRY = REPO_ROOT / "chisurf" / "core" / "settings" / "constants" / "parameter_registry.json"
OUT_DIR = REPO_ROOT / "docs" / "reference"

# view.json section types that describe a user-editable parameter.
PARAM_TYPES = {"value", "choice", "toggle", "toggle_row", "table"}


def _md(text) -> str:
    """Escape a value so it is safe inside a Markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def _load_json(path: pathlib.Path):
    """Load JSON, returning ``None`` on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _iter_view_params(section, panel: str = ""):
    """Yield ``(panel, section)`` for every parameter-bearing view.json section.

    ``panel`` accumulates the nearest enclosing panel/dock title so parameters
    can be grouped the way the UI groups them.
    """
    if isinstance(section, dict):
        stype = section.get("type")
        title = section.get("title")
        next_panel = title if (stype in {"panel", "dock_area"} and title) else panel
        if stype in PARAM_TYPES and section.get("attr"):
            yield panel, section
        for value in section.values():
            yield from _iter_view_params(value, next_panel)
    elif isinstance(section, list):
        for item in section:
            yield from _iter_view_params(item, panel)


def _param_row(sec: dict) -> tuple:
    """Build a (label, attr, kind, default, range, desc) row for a view section."""
    attr = sec.get("attr", "")
    label = sec.get("label") or attr
    stype = sec.get("type")
    kind = sec.get("kind") or {"choice": "choice", "toggle": "bool",
                               "toggle_row": "bool", "table": "table"}.get(stype, "float")
    rng = ""
    if "minimum" in sec or "maximum" in sec:
        rng = f"{sec.get('minimum', '')} … {sec.get('maximum', '')}"
        if sec.get("step") not in (None, ""):
            rng += f" (step {sec['step']})"
    elif sec.get("options_source"):
        rng = f"choices: `{sec['options_source']}`"
    elif isinstance(sec.get("options"), list):
        rng = "choices: " + ", ".join(str(o) for o in sec["options"])
    return (_md(label), f"`{attr}`", _md(kind), _md(sec.get("default", "")),
            _md(rng), _md(sec.get("description", "")))


def _display_parts(display_name: str, fallback: str) -> tuple:
    """Split an ``A:B:Leaf`` menu path into (category-path, leaf label)."""
    dn = (display_name or fallback).strip()
    if ":" in dn:
        *cats, leaf = [p.strip() for p in dn.split(":")]
        return " → ".join(cats), leaf
    return "Uncategorized", dn


def _plugin_page(manifest: dict, plugin_dir: pathlib.Path, registry_params: dict) -> str:
    pid = manifest.get("id", plugin_dir.name)
    category, leaf = _display_parts(manifest.get("display_name", ""), pid)
    rel_dir = plugin_dir.relative_to(PLUGIN_ROOT)
    out = [f"(plugin-{pid})=", f"# {leaf}", ""]
    if manifest.get("description"):
        out += [_md(manifest["description"]), ""]

    out += ["## Identity", "", "| Field | Value |", "| --- | --- |",
            f"| Plugin id | `{pid}` |", f"| Menu path | {category} → **{leaf}** |"]
    if manifest.get("categories"):
        out.append(f"| Categories | {', '.join(manifest['categories'])} |")
    if manifest.get("version"):
        out.append(f"| Version | {manifest['version']} |")
    if manifest.get("entrypoints"):
        out.append(f"| Surfaces | {', '.join(sorted(manifest['entrypoints']))} |")
    if manifest.get("state_namespace"):
        out.append(f"| State namespace | `{manifest['state_namespace']}` |")
    out.append("")

    # UI parameters from view.json
    views = sorted(plugin_dir.rglob("*.view.json"))
    rows: list[tuple] = []
    seen: set = set()
    for view in views:
        data = _load_json(view)
        if not data:
            continue
        for panel, sec in _iter_view_params(data):
            attr = sec.get("attr")
            if attr in seen:
                continue
            seen.add(attr)
            label, a, kind, default, rng, desc = _param_row(sec)
            if not desc and attr in registry_params:
                desc = _md(registry_params[attr].get("description", ""))
            rows.append((panel or "General", label, a, kind, default, rng, desc))

    out += ["## Parameters", ""]
    if rows:
        out += ["Editable parameters exposed by the plugin's declarative "
                "(AutoForm) interface, grouped by panel.", ""]
        by_panel: dict = {}
        for panel, *cells in rows:
            by_panel.setdefault(panel, []).append(cells)
        multi = len(by_panel) > 1
        for panel, cells_list in by_panel.items():
            if multi:
                out += [f"### {panel}", ""]
            out += ["| Parameter | Attribute | Type | Default | Range / options | Meaning |",
                    "| --- | --- | --- | --- | --- | --- |"]
            out += ["| " + " | ".join(c) + " |" for c in cells_list]
            out.append("")
    else:
        out += ["This plugin builds its interface from custom Qt widgets (no "
                "declarative `*.view.json` parameter sections were found). Its "
                "controls are shown in the plugin's guide; the fit/model "
                "parameters it edits are defined in the "
                "[parameter glossary](../parameters.md).", ""]

    rpc = manifest.get("rpc_methods", [])
    if rpc:
        out += ["## JSON-RPC methods", "", "| Method | Long-running | Summary |",
                "| --- | --- | --- |"]
        for m in rpc:
            out.append(f"| `{m.get('name','')}` | "
                       f"{'yes' if m.get('long_running') else 'no'} | "
                       f"{_md(m.get('description') or m.get('summary',''))} |")
        out.append("")

    out += ["## Source", "",
            f"- Plugin package: `chisurf/plugins/{rel_dir}/`",
            f"- Manifest: `chisurf/plugins/{rel_dir}/manifest.json`"]
    for v in views:
        out.append(f"- UI spec: `{v.relative_to(REPO_ROOT)}`")
    out.append("")
    return "\n".join(out)


def _parameter_glossary(registry: dict) -> str:
    params = registry.get("parameters", {})
    out = ["(reference-parameters)=", "# Parameter glossary", "",
           "Every named fit/model parameter known to ChiSurf, with its meaning "
           "and the analysis contexts it appears in. Generated from the parameter "
           "registry (`chisurf/core/settings/constants/parameter_registry.json`), "
           "which is built from the model and plugin source. Plugin-specific UI "
           "controls are listed on each [plugin page](plugins/index.md).", "",
           f"Total registered parameters: **{len(params)}**.", "",
           "| Parameter | Meaning | Keywords |", "| --- | --- | --- |"]
    for name in sorted(params, key=str.lower):
        p = params[name]
        out.append(f"| `{name}` | {_md(p.get('description', ''))} | "
                   f"{_md(', '.join(p.get('keywords', []) or []))} |")
    out.append("")
    return "\n".join(out)


def generate() -> None:
    registry = _load_json(REGISTRY) or {}
    registry_params = registry.get("parameters", {})
    plugins_dir = OUT_DIR / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)

    catalogue: dict = {}
    written = 0
    for man_path in sorted(PLUGIN_ROOT.rglob("manifest.json")):
        manifest = _load_json(man_path)
        if not manifest or not manifest.get("id"):
            continue
        pid = manifest["id"]
        (plugins_dir / f"{pid}.md").write_text(
            _plugin_page(manifest, man_path.parent, registry_params), encoding="utf-8")
        category, leaf = _display_parts(manifest.get("display_name", ""), pid)
        catalogue.setdefault(category, []).append(
            (leaf, pid, manifest.get("description", ""), bool(manifest.get("menu_hidden"))))
        written += 1

    idx = ["# Plugin catalogue", "",
           "Every discoverable ChiSurf plugin, grouped by its menu category. Each "
           "page lists the plugin's editable parameters and its JSON-RPC surface. "
           "Model/fit parameter meanings are collected in the "
           "[parameter glossary](../parameters.md).", "",
           "```{toctree}", ":hidden:", ":glob:", "", "*", "```", "",
           f"**{written} plugins** across {len(catalogue)} categories.", ""]
    for category in sorted(catalogue):
        idx += [f"## {category}", "", "| Plugin | Summary |", "| --- | --- |"]
        for leaf, pid, desc, hidden in sorted(catalogue[category]):
            tag = " *(hidden)*" if hidden else ""
            idx.append(f"| [{_md(leaf)}]({pid}.md){tag} | {_md(desc)} |")
        idx.append("")
    (plugins_dir / "index.md").write_text("\n".join(idx), encoding="utf-8")

    (OUT_DIR / "parameters.md").write_text(_parameter_glossary(registry), encoding="utf-8")

    old = OUT_DIR / "plugins.md"
    if old.exists():
        old.unlink()

    print(f"Wrote {written} plugin pages + catalogue to {plugins_dir}")
    print(f"Wrote parameter glossary ({len(registry_params)} params)")


# Backwards-compatible entry point used by the docs pipeline.
def generate_plugin_md(output_path=None) -> None:  # noqa: D401
    """Compatibility shim: regenerate the full plugin & parameter reference."""
    generate()


if __name__ == "__main__":
    generate()
