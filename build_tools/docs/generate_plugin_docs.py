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

import functools
import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from build_tools.docs import okf  # noqa: E402

PLUGIN_ROOT = REPO_ROOT / "chisurf" / "plugins"
REGISTRY = REPO_ROOT / "chisurf" / "core" / "settings" / "constants" / "parameter_registry.json"
OUT_DIR = REPO_ROOT / "docs" / "reference"

# view.json section types that describe a user-editable parameter.
PARAM_TYPES = {"value", "choice", "toggle", "toggle_row", "table"}
#: Custom-section keys that *are* a user-editable control, so they get a
#: documented row like any ``value``. Display-only custom sections (a plot, an
#: image, an info box) are deliberately absent: they show a result, they are not
#: something the user sets.
#:
#: A custom section binds through ``target``; only the two picker kinds put an
#: ``attr`` in ``options``. Requiring the latter is why every ``path_list`` —
#: the file list of eleven migrated plugins — documented nothing at all despite
#: carrying a written ``description``.
CUSTOM_PARAM_KEYS = {
    "data_source", "setup_selector", "path_list", "region_list",
    "rate_matrix", "scalar_table", "equation_editor", "level_histogram",
    "code_editor",
}

# Curated fallback descriptions for common fit/model parameters that the
# auto-generated parameter registry leaves blank. Kept here (not in the model
# source) so the glossary reads completely without editing chisurf/core.
FALLBACK_DESCRIPTIONS = {
    "N": "Mean number of molecules in the confocal detection volume; sets the correlation amplitude G(0)=1/N.",
    "N1": "Mean number of molecules of species 1 in the detection volume.",
    "N2": "Mean number of molecules of species 2 in the detection volume.",
    "N3": "Mean number of molecules of species 3 in the detection volume.",
    "n": "Refractive index of the immersion/sample medium.",
    "s": "Structure (aspect) parameter of the confocal volume, s = w_z / w_xy.",
    "b": "Correlation baseline offset G(τ→∞): ~1 for normalized ACFs, 0 for background-subtracted curves.",
    "offset": "Constant additive offset of the model curve.",
    "tauD": "Diffusion time — mean residence time in the confocal volume, τ_D = w_xy²/(4D).",
    "tauT": "Triplet/blinking relaxation time.",
    "aT": "Triplet/blinking amplitude — fraction of molecules transiently in a dark state.",
    "alpha": "Anomalous-diffusion exponent (α<1 sub-diffusion, α=1 normal, α>1 super-diffusion).",
    "ba": "Bunching (blinking/triplet) amplitude of a relaxation term.",
    "bt": "Bunching (blinking/triplet) relaxation time.",
    "fcs.tb1": "Relaxation (bunching) time constant of the 1st term.",
    "fcs.tb2": "Relaxation (bunching) time constant of the 2nd term.",
    "fcs.tb3": "Relaxation (bunching) time constant of the 3rd term.",
    "fcs.tb4": "Relaxation (bunching) time constant of the 4th term.",
    "diam": "Known inter-focus distance (two-focus FCS) or scan diameter (scanning FCS), in µm.",
    "w0": "Lateral 1/e² radius of the confocal detection volume (µm).",
    "w_r": "Lateral 1/e² radius of the confocal detection volume (µm).",
    "w_z": "Axial 1/e² radius of the confocal detection volume (µm).",
    "wem": "Emission-side Gauss–Lorentz detection waist.",
    "Veff": "Effective confocal detection volume, V_eff = π^{3/2}·γ·w_xy³.",
    "conc": "Molecular concentration derived from N and the effective volume.",
    "cpm": "Counts per molecule (molecular brightness), (I−B)/N.",
    "cpm_all": "Counts per molecule summed over all detection channels.",
    "brightness": "Molecular brightness — background-corrected count rate per molecule, (CR−bg)/N (kHz).",
    "BG": "Background count rate used in the correlation-amplitude correction (kHz).",
    "bg": "Constant background count rate (kHz).",
    "bg0": "Background count rate in detection channel 0 (kHz).",
    "bg1": "Background count rate in detection channel 1 (kHz).",
    "BR": "Brightness ratio between species.",
    "eps1": "Molecular brightness of species 1 (counts/molecule/s).",
    "eps2": "Molecular brightness of species 2 (counts/molecule/s).",
    "eps3": "Molecular brightness of species 3 (counts/molecule/s).",
    "QYD": "Fluorescence quantum yield of the donor.",
    "QYA": "Fluorescence quantum yield of the acceptor.",
    "gG": "Detection efficiency / g-factor of the green (donor) channel.",
    "gR": "Detection efficiency / g-factor of the red (acceptor) channel.",
    "kQ": "Dynamic-quenching rate constant.",
    "lam_ex": "Excitation wavelength (nm).",
    "lam_em": "Emission wavelength (nm).",
    "pinhole": "Confocal pinhole diameter (µm).",
    "mag": "Magnification of the imaging optics.",
    "temp": "Sample temperature.",
    "pxl_dur": "Pixel dwell time in an image scan (s).",
    "pxl_size": "Pixel size in an image scan (µm).",
    "line_dur": "Line duration in a confocal scan (s).",
    "dtMT[ns]": "Macro-time resolution (ns).",
    "dtTAC[ns]": "Micro-time (TAC) channel width (ns).",
    "nTAC": "Number of micro-time (TAC) channels.",
    "nPh_max": "Maximum number of photons per burst considered.",
    "nPh_min": "Minimum number of photons per burst considered.",
    "n photons": "Number of photons.",
    "n curves": "Number of correlation curves.",
    "n_rh": "Number of hydrodynamic-radius grid points (distribution fit).",
    "n_td": "Number of diffusion-time grid points (distribution fit).",
    "rh_min": "Lower bound of the hydrodynamic-radius axis.",
    "rh_max": "Upper bound of the hydrodynamic-radius axis.",
    "td_min": "Lower bound of the diffusion-time axis.",
    "td_max": "Upper bound of the diffusion-time axis.",
    "reg": "Regularization weight for distribution (MEM/Tikhonov) fits.",
}


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
        elif stype == "custom" and section.get("key") in CUSTOM_PARAM_KEYS:
            # A bound custom section. The pickers carry attr/label/description in
            # ``options``; every other kind binds through ``target`` and titles
            # itself with ``title``. Flatten either shape so it documents like a
            # field.
            options = dict(section.get("options") or {})
            attr = options.get("attr") or section.get("target")
            if attr:
                row = {
                    "type": "custom",
                    "kind": section.get("key", "custom"),
                    **options,
                    "attr": attr,
                    "label": options.get("label") or section.get("title") or attr,
                }
                if section.get("description") and not options.get("description"):
                    row["description"] = section["description"]
                yield panel, row
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


def _discovered_plugins() -> list:
    """Every plugin the application itself discovers, manifest or not."""
    try:
        import chisurf.plugins as plugins_module

        return list(plugins_module.iter_plugins())
    except Exception as exc:  # pragma: no cover - docs build outside the env
        print(f"  (plugin discovery unavailable: {exc})")
        return []


#: Where the theory and the workflows live, and how each reads in a link.
_DOC_SECTIONS = (
    ("concepts", "Theory"),
    ("guides", "Workflow"),
)


def _page_title(path: pathlib.Path) -> str:
    """First heading of a documentation page, or its file name."""
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        heading = re.match(r"^#\s+(?P<title>.+?)\s*$", line)
        if heading:
            return heading.group("title").strip()
    return path.stem.replace("_", " ")


@functools.lru_cache(maxsize=1)
def _plugin_mentions() -> dict:
    """Map ``chisurf/plugins/<dir>`` to the documentation pages that name it.

    Built by reading the documentation rather than by declaring the link in a
    manifest: a page that talks about a plugin already says so, by naming its
    package or one of its files, and a link derived from that cannot go stale
    while the sentence around it is still true. Declaring it twice is what
    drifts.
    """
    docs = REPO_ROOT / "docs"
    mentions: dict = {}
    reference = re.compile(r"chisurf/plugins/(?P<rest>[\w.-]+(?:/[\w.-]+)*)")
    for section, _label in _DOC_SECTIONS:
        directory = docs / section
        if not directory.is_dir():
            continue
        for page in sorted(directory.rglob("*.md")) + sorted(directory.rglob("*.rst")):
            if page.name.startswith("index."):
                continue
            text = page.read_text(encoding="utf-8", errors="ignore")
            seen = set()
            for match in reference.finditer(text):
                parts = match.group("rest").split("/")
                # The reference may be a file deep inside the package; a
                # trailing name with a suffix is not a directory.
                if "." in parts[-1]:
                    parts = parts[:-1]
                # Every prefix is a candidate plugin directory; the caller knows
                # which of them actually exist.
                for depth in range(1, len(parts) + 1):
                    seen.add("/".join(parts[:depth]))
            for key in seen:
                mentions.setdefault(key, []).append((section, page))
    return mentions


def _theory_and_workflow(rel_dir: pathlib.Path) -> list:
    """Lines linking a plugin to the pages that explain and apply it."""
    found = _plugin_mentions().get(rel_dir.as_posix(), [])
    if not found:
        return []
    docs = REPO_ROOT / "docs"
    out = ["## Theory and workflow", ""]
    for section, label in _DOC_SECTIONS:
        pages = sorted(
            {page for kind, page in found if kind == section},
            key=lambda page: page.name,
        )
        if not pages:
            continue
        links = ", ".join(
            f"[{_page_title(page)}](/{page.relative_to(docs).with_suffix('.md').as_posix()})"
            for page in pages
        )
        out.append(f"- **{label}** — {links}")
    out.append("")
    return out if len(out) > 2 else []


def _docstring_summary(text: str, *names: str) -> str:
    """Return the first paragraph of a module docstring that says something.

    A plugin without a manifest is described from its docstring, and these
    docstrings conventionally open with the plugin's own name on a line of its
    own. Taking the first paragraph therefore produced descriptions like
    "FCS Correlator" — the title restated, which tells a reader (and the
    assistant ranking pages) nothing at all.

    Parameters
    ----------
    text : str
        The module docstring.
    *names : str
        Spellings of the plugin's name that a lead paragraph may only repeat.

    Returns
    -------
    str
        The first informative paragraph as one line, or ``""``.
    """
    banned = {re.sub(r"[^a-z0-9]+", "", str(name).lower()) for name in names if name}
    for paragraph in (text or "").strip().split("\n\n"):
        collapsed = " ".join(paragraph.split())
        if not collapsed:
            continue
        if re.sub(r"[^a-z0-9]+", "", collapsed.lower()) in banned:
            continue
        return collapsed
    return ""


def _plugin_front_matter(manifest: dict, plugin_dir: pathlib.Path, title: str) -> str:
    """Return the OKF header for a generated plugin page.

    A generated page needs the header as much as a written one — it is the
    largest part of the corpus the assistant searches. It is emitted here
    rather than injected afterwards, because the next regeneration would
    overwrite an injected one.
    """
    pid = manifest.get("id", plugin_dir.name)
    tags = ["reference", "plugins", pid.replace("_", "-")]
    for category in manifest.get("categories", []) or []:
        tag = str(category).strip().lower().replace(" ", "-")
        if tag and tag not in tags:
            tags.append(tag)
    return okf.render_front_matter(
        {
            "type": "Plugin Reference",
            "title": title,
            "description": okf.plain_text(manifest.get("description", "") or "")
            or f"Reference page for the {title} plugin.",
            "resource": plugin_dir.relative_to(REPO_ROOT).as_posix() + "/",
            "tags": tags[:8],
            "anchor": f"plugin-{pid}",
            # No timestamp: a regeneration date would change on every run and
            # bury the real diff. What a reader needs is "do not hand-edit".
            "generator": "build_tools/docs/generate_plugin_docs.py",
        }
    )


def _plugin_page(manifest: dict, plugin_dir: pathlib.Path, registry_params: dict) -> str:
    pid = manifest.get("id", plugin_dir.name)
    category, leaf = _display_parts(manifest.get("display_name", ""), pid)
    rel_dir = plugin_dir.relative_to(PLUGIN_ROOT)
    out = [_plugin_front_matter(manifest, plugin_dir, leaf).rstrip("\n"), ""]
    out += [f"(plugin-{pid})=", f"# {leaf}", ""]
    if manifest.get("description"):
        out += [_md(manifest["description"]), ""]

    if manifest.get("_no_manifest"):
        out += [
            ":::{note}",
            "This plugin declares itself in code rather than in a `manifest.json`, "
            "so the identity below is what the plugin loader reads from the module "
            "and there is no declared RPC surface to list.",
            ":::",
            "",
        ]

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
            if not desc:
                desc = _md(FALLBACK_DESCRIPTIONS.get(attr, ""))
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

    # Where the reader goes for *why* and for *how*, derived from the pages
    # that already name this plugin.
    out += _theory_and_workflow(rel_dir)

    # A file is written as a ``{src}`` role so the reader can open it: in the
    # application it goes to the code editor, on the website to the repository
    # browser. The package is a directory and stays a plain code span.
    out += ["## Source", "",
            f"- Plugin package: `chisurf/plugins/{rel_dir}/`"]
    # A plugin that declares itself in code has no manifest, and linking to the
    # file it does not have was thirteen "no source file" warnings in the build
    # and thirteen dead links for the reader.
    if (plugin_dir / "manifest.json").is_file():
        out.append(f"- Manifest: {{src}}`chisurf/plugins/{rel_dir}/manifest.json`")
    for v in views:
        out.append(f"- UI spec: {{src}}`{v.relative_to(REPO_ROOT)}`")
    out.append("")
    return "\n".join(out)


def _parameter_glossary(registry: dict) -> str:
    params = registry.get("parameters", {})
    out = [okf.render_front_matter({
               "type": "Reference",
               "title": "Parameter glossary",
               "description": "Every named fit/model parameter known to ChiSurf, with its "
                              "meaning and the analysis contexts it appears in.",
               "resource": "chisurf/core/settings/constants/parameter_registry.json",
               "tags": ["reference", "parameters", "fitting", "glossary"],
               "anchor": "reference-parameters",
               "generator": "build_tools/docs/generate_plugin_docs.py",
           }).rstrip("\n"), "",
           "(reference-parameters)=", "# Parameter glossary", "",
           "Every named fit/model parameter known to ChiSurf, with its meaning "
           "and the analysis contexts it appears in. Generated from the parameter "
           "registry (`chisurf/core/settings/constants/parameter_registry.json`), "
           "which is built from the model and plugin source. Plugin-specific UI "
           "controls are listed on each [plugin page](plugins/index.md).", "",
           f"Total registered parameters: **{len(params)}**.", "",
           "| Parameter | Meaning | Keywords |", "| --- | --- | --- |"]
    for name in sorted(params, key=str.lower):
        p = params[name]
        desc = p.get("description", "").strip() or FALLBACK_DESCRIPTIONS.get(name, "")
        out.append(f"| `{name}` | {_md(desc)} | "
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
    n_declarative = 0
    for man_path in sorted(PLUGIN_ROOT.rglob("manifest.json")):
        manifest = _load_json(man_path)
        if not manifest or not manifest.get("id"):
            continue
        pid = manifest["id"]
        (plugins_dir / f"{pid}.md").write_text(
            _plugin_page(manifest, man_path.parent, registry_params), encoding="utf-8")
        # coverage: does the plugin expose declarative (AutoForm) parameters?
        if any(True for v in man_path.parent.rglob("*.view.json")
               for _ in _iter_view_params(_load_json(v) or {})):
            n_declarative += 1
        category, leaf = _display_parts(manifest.get("display_name", ""), pid)
        catalogue.setdefault(category, []).append(
            (leaf, pid, manifest.get("description", ""), bool(manifest.get("menu_hidden"))))
        written += 1

    # Plugins that predate manifests are still discoverable, still appear in
    # the menus, and were therefore in the application but not in its
    # documentation. They are described from the metadata the loader reads
    # (the module docstring), and their page says the manifest is missing.
    for info in _discovered_plugins():
        directory = pathlib.Path(info["package_dir"])
        if (directory / "manifest.json").exists():
            continue
        pid = info.get("module_name") or directory.name
        manifest = {
            "id": pid,
            "display_name": info.get("plugin_name", pid),
            "description": _docstring_summary(
                info.get("description") or "", info.get("plugin_name"), pid
            ),
            "menu_hidden": bool(info.get("menu_hidden")),
            "_no_manifest": True,
        }
        (plugins_dir / f"{pid}.md").write_text(
            _plugin_page(manifest, directory, registry_params), encoding="utf-8")
        category, leaf = _display_parts(manifest["display_name"], pid)
        catalogue.setdefault(category, []).append(
            (leaf, pid, manifest["description"], manifest["menu_hidden"]))
        written += 1

    idx = [okf.render_front_matter({
               "type": "Index",
               "title": "Plugin catalogue",
               "description": "Every discoverable ChiSurf plugin, grouped by its menu category, "
                              "with a link to its reference page.",
               "tags": ["reference", "plugins", "catalogue"],
               "generator": "build_tools/docs/generate_plugin_docs.py",
           }).rstrip("\n"), "",
           "# Plugin catalogue", "",
           "Every discoverable ChiSurf plugin, grouped by its menu category. Each "
           "page gives the plugin's identity, its editable parameters, and its "
           "JSON-RPC surface.", "",
           f"Of the **{written} plugins**, **{n_declarative}** build their interface "
           "from declarative AutoForm specs and get a full per-parameter table on "
           "their page; the remainder use custom Qt widgets, so their controls are "
           "described in each plugin's guide while every named fit/model parameter "
           "is defined once in the **[parameter glossary](../parameters.md)**.", "",
           "```{toctree}", ":hidden:", ":glob:", "", "*", "```", "",
           f"**{written} plugins** across {len(catalogue)} categories.", ""]
    for category in sorted(catalogue):
        idx += [f"## {category}", "", "| Plugin | Summary |", "| --- | --- |"]
        for leaf, pid, desc, hidden in sorted(catalogue[category]):
            tag = " *(hidden)*" if hidden else ""
            idx.append(f"| [{_md(leaf)}]({pid}.md){tag} | {_md(desc)} |")
        idx.append("")
    (plugins_dir / "index.md").write_text("\n".join(idx), encoding="utf-8")

    # A plugin that is removed or renamed leaves its page behind, and a page
    # nothing generated is a page nobody maintains: it stays in the tree,
    # appears in the toctree glob, and points at code that is no longer there.
    # (burst_state_mle, proteinmc, fcs_correlator … were all in that state.)
    kept = {f"{pid}.md" for pids in catalogue.values() for _leaf, pid, *_rest in pids}
    kept.add("index.md")
    removed = 0
    for page in sorted(plugins_dir.glob("*.md")):
        if page.name in kept or "cookiecutter" in page.name:
            continue
        page.unlink()
        removed += 1
    if removed:
        print(f"Removed {removed} pages of plugins that no longer exist")

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
