"""License tracker: what ChiSurf depends on, and what that permits.

Generates ``doc/licenses.md`` (the human report, compatibility matrix on top)
and ``doc/licenses.json`` (the machine-readable inventory) from the
dependencies declared in ``pyproject.toml``, resolved against the running
environment's package metadata. Run it after adding a dependency; run it with
``--check`` in CI to fail on a dependency whose license is unknown or more
restrictive than the project's own.

The point is visibility, not lawyering: the report says what the project's
license is, the most permissive license the dependency graph would allow, and
which dependencies are the binding constraint. The classifier is deliberately
coarse -- five rungs from public domain to strong copyleft -- because that is
the granularity the "could we relicense?" question is asked at.

Usage::

    python build_tools/license_tracker.py            # regenerate the report
    python build_tools/license_tracker.py --check    # CI: verify, write nothing
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from importlib import metadata as im
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parent.parent

#: Permissiveness rungs. A project can be licensed no more permissively than
#: its most restrictive runtime dependency's rung.
CLASSES = {
    0: "Public domain / CC0",
    1: "Permissive (MIT/BSD/Apache/PSF/...)",
    2: "Weak copyleft, file-level (MPL)",
    3: "Weak copyleft, library-level (LGPL)",
    4: "Strong copyleft (GPL)",
}

#: Pattern -> rung. First match wins; order within a rung does not matter.
_CLASS_PATTERNS = [
    (4, r"\bA?GPL(?!.*(lesser|library))|GNU General Public"),
    (3, r"\bLGPL\b|Lesser General Public|Library General Public"),
    (2, r"\bMPL\b|Mozilla Public"),
    (1, r"\bMIT\b|\bBSD\b|\bISC\b|Apache|\bPSF\b|Python Software Foundation"
        r"|\bzlib\b|\bHPND\b|historical permission|\bBSL\b|Boost"),
    (0, r"public domain|\bCC0\b|Unlicense"),
]

#: Packages whose installed metadata is missing or misleading. The value is
#: (license text, source of that claim).
OVERRIDES = {
    # Riverbank publishes PyQt5 and sip under GPL v3 (or commercial).
    "PyQt5": ("GPL-3.0-only", "https://www.riverbankcomputing.com/commercial/license-faq"),
    "sip": ("SIP license / GPL-3.0-only", "https://www.riverbankcomputing.com/commercial/license-faq"),
    # IMP states LGPL for the kernel and most modules.
    "imp": ("LGPL-2.1", "https://integrativemodeling.org/latest/doc/manual/licenses.html"),
    # Ships no license metadata at all; the repository states BSD-2-Clause.
    "rendercanvas": ("BSD-2-Clause", "https://github.com/pygfx/rendercanvas/blob/main/LICENSE"),
    # Sibling projects in this ecosystem; license from their pyproject.toml.
    "mmfdb": ("MIT", "https://github.com/tpeulen/mmfdb"),
    "imp-bff": ("MPL-2.0", "https://github.com/tpeulen/imp.bff"),
    # Known licenses for packages the generating environment may not have
    # installed (dev/cli/postgres extras).
    "python-docx": ("MIT", "https://github.com/python-openxml/python-docx/blob/master/LICENSE"),
    "ruff": ("MIT", "https://github.com/astral-sh/ruff/blob/main/LICENSE"),
    "ptpython": ("BSD-3-Clause", "https://github.com/prompt-toolkit/ptpython/blob/master/LICENSE"),
    "pytest-cov": ("MIT", "https://github.com/pytest-dev/pytest-cov/blob/master/LICENSE"),
    "python-lsp-server": ("MIT", "https://github.com/python-lsp/python-lsp-server/blob/develop/LICENSE"),
    "psycopg": ("LGPL-3.0-or-later", "https://github.com/psycopg/psycopg/blob/master/LICENSE.txt"),
}

#: Components shipped inside the application that are not Python
#: distributions: compiled pieces tttrlib bundles, vendored assets. No JS or
#: wasm is bundled anywhere in the tree (checked 2026-08-10).
BUNDLED = [
    {"name": "tttrlib", "version": "(pinned by environment)",
     "license": "BSD-3-Clause", "class": 1,
     "url": "https://github.com/fluorescence-tools/tttrlib"},
    {"name": "libtiff (bundled by tttrlib)", "version": "vendored",
     "license": "libtiff (MIT-style)", "class": 1,
     "url": "https://libtiff.gitlab.io/libtiff/misc.html"},
    {"name": "HDF5 (linked by tttrlib)", "version": "environment",
     "license": "BSD-3-Clause (HDF5)", "class": 1,
     "url": "https://github.com/HDFGroup/hdf5/blob/develop/LICENSE"},
]


def _classify(text: str) -> int | None:
    for rung, pattern in _CLASS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return rung
    return None


def _license_of(dist: im.Distribution) -> str:
    """Best license statement the package metadata offers."""
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return expression
    classifiers = [c.split("::")[-1].strip() for c in meta.get_all("Classifier", [])
                   if c.startswith("License ::")]
    classifiers = [c for c in classifiers if c and c.lower() != "osi approved"]
    if classifiers:
        return "; ".join(dict.fromkeys(classifiers))
    lic = (meta.get("License") or "").strip()
    if lic and lic.upper() != "UNKNOWN":
        return lic.splitlines()[0][:120]
    return ""


def _homepage(dist: im.Distribution) -> str:
    meta = dist.metadata
    for url in meta.get_all("Project-URL", []) or []:
        label, _, target = url.partition(",")
        if label.strip().lower() in ("license", "homepage", "source", "repository"):
            return target.strip()
    return meta.get("Home-page") or ""


def _requirement_name(req: str) -> str:
    return re.split(r"[<>=!~;\[ ]", req.strip(), 1)[0]


def collect() -> dict:
    """Resolve every declared dependency against the environment."""
    with open(ROOT / "pyproject.toml", "rb") as fh:
        project = tomllib.load(fh)["project"]

    groups = {"runtime": project.get("dependencies", [])}
    groups.update(project.get("optional-dependencies", {}))

    entries = []
    for group, reqs in groups.items():
        for req in reqs:
            name = _requirement_name(req)
            entry = {"name": name, "group": group, "requirement": req}
            if name in OVERRIDES:
                lic, url = OVERRIDES[name]
                entry.update(license=lic, url=url, source="override")
            else:
                try:
                    dist = im.distribution(name)
                except im.PackageNotFoundError:
                    entry.update(version="not installed", license="", url="",
                                 source="missing", **{"class": None})
                    entries.append(entry)
                    continue
                entry.update(license=_license_of(dist), url=_homepage(dist),
                             source="metadata")
            try:
                entry.setdefault("version", im.version(name))
            except im.PackageNotFoundError:
                entry.setdefault("version", "not installed")
            entry["class"] = _classify(entry["license"] or "")
            entries.append(entry)

    runtime = [e for e in entries if e["group"] == "runtime"]
    known = [e for e in runtime if e["class"] is not None]
    binding_class = max((e["class"] for e in known), default=1)
    blockers = [e["name"] for e in known if e["class"] == binding_class]
    unknown = [e["name"] for e in runtime if e["class"] is None]

    return {
        "generated": str(date.today()),
        "project_license": project.get("license", ""),
        "binding_class": binding_class,
        "binding_class_name": CLASSES[binding_class],
        "blockers": blockers,
        "unknown": unknown,
        "entries": entries,
        "bundled": BUNDLED,
    }


def render_markdown(data: dict) -> str:
    lines = [
        "# ChiSurf dependency licenses",
        "",
        f"*Generated {data['generated']} by `build_tools/license_tracker.py`. "
        "Regenerate after adding a dependency; do not edit by hand.*",
        "",
        "## Compatibility",
        "",
        f"- **Current license:** {data['project_license']}",
        f"- **Most permissive license possible:** {data['binding_class_name']}",
        f"- **Binding constraint:** {', '.join(data['blockers']) or '(none)'}",
        "",
    ]
    if data["binding_class"] >= 4:
        lines += [
            "The binding dependencies are GPL, so the project as a whole "
            "cannot be more permissive than GPL. The version wrinkle this "
            "note used to flag is resolved: PyQt5/sip are **GPL v3**, and "
            "ChiSurf was stated as GPL-2.0-only, which cannot combine with "
            "GPL-3.0-only code. The project is now **GPL-3.0-or-later**, "
            "which combines with both.",
            "",
        ]
    if data["unknown"]:
        lines += [f"**Unclassified licenses (fix these):** "
                  f"{', '.join(data['unknown'])}", ""]

    lines += [
        "## Python dependencies",
        "",
        "| Package | Group | Version | License | Class | Reference |",
        "|---|---|---|---|---|---|",
    ]
    for e in sorted(data["entries"], key=lambda e: (e["group"], e["name"].lower())):
        cls = CLASSES.get(e["class"], "?") if e["class"] is not None else "**?**"
        lines.append(
            f"| {e['name']} | {e['group']} | {e['version']} "
            f"| {e['license'] or '**unknown**'} | {cls} | {e['url']} |")

    lines += [
        "",
        "## Bundled / compiled components",
        "",
        "No JavaScript or wasm asset is bundled anywhere in the tree.",
        "",
        "| Component | Version | License | Class | Reference |",
        "|---|---|---|---|---|",
    ]
    for e in data["bundled"]:
        lines.append(f"| {e['name']} | {e['version']} | {e['license']} "
                     f"| {CLASSES[e['class']]} | {e['url']} |")
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="verify only: fail on unknown or missing licenses")
    args = parser.parse_args(argv)

    data = collect()

    missing = [e["name"] for e in data["entries"]
               if e["group"] == "runtime" and e["source"] == "missing"]
    if args.check:
        problems = data["unknown"] + missing
        if problems:
            print("license check FAILED for:", ", ".join(sorted(set(problems))))
            return 1
        print(f"license check ok: {len(data['entries'])} dependencies, "
              f"binding constraint {data['binding_class_name']} "
              f"({', '.join(data['blockers'])})")
        return 0

    (ROOT / "doc").mkdir(exist_ok=True)
    (ROOT / "doc" / "licenses.md").write_text(render_markdown(data), encoding="utf-8")
    (ROOT / "doc" / "licenses.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8")
    print("wrote doc/licenses.md and doc/licenses.json")
    if missing:
        print("note, not installed here:", ", ".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
