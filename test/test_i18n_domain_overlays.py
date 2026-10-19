"""A translation table layered over the shared "chisurf" domain fills gaps; it never re-translates.

``emtk.i18n.add_translations(..., domain="chisurf")`` puts rows *into* the domain every ChiSurf tool
reads, ahead of the catalogue. A row whose source the catalogue (or emtk) already translates
therefore changes that text for every tool in the process, from the moment the plugin that owns
the table is opened, and only then. That is how the release gate saw the LUT tools show
"Verarbeitung…" for "Working…" (the ALEX Creator's row) instead of the catalogue's "Läuft…":
one test order red, every other green.

The invariant: for every overlay table, each translation of a source that resolves *before* any
overlay is installed is the one the table carries. The baseline is taken in a fresh interpreter,
so an overlay a previous test installed cannot hide a conflict.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOCALES = ("de", "fr", "es", "pt", "ru")
#: overlay tables: module -> the name of its rows table ("source|de|fr|es|pt|ru", or with an "en" column first)
OVERLAYS = {
    "chisurf.emtk.shared_i18n": "_ROWS",
    "chisurf.plugins.tttr.ptu_alex_creator.gui.translations": "ROWS",
}

_BASELINE = r"""
import importlib, json, sys
from emtk import i18n
from chisurf.core.support import i18n as core_i18n

core_i18n.register_catalogues()
out = {}
for spec in sys.argv[1:]:
    module, name = spec.split(":")
    table = getattr(importlib.import_module(module), name)
    lines = table.strip().splitlines() if isinstance(table, str) else ["|".join(r) for r in table]
    rows = [line.split("|") for line in lines]
    found = {}
    for code in %r:
        i18n.set_locale(code)
        for row in rows:
            found.setdefault(row[0], {})[code] = i18n.tr(row[0])
    out[spec] = {"rows": rows, "baseline": found}
print(json.dumps(out, ensure_ascii=False))
""" % (LOCALES,)


def _overlay_modules() -> set[str]:
    """Modules under ``chisurf/`` that layer translations over the "chisurf" domain in its own context.

    A table in a context of its own ("Trajectory Tools") cannot re-translate: the catalogue's
    contexts are merged first and win the any-context lookup, so such a table only fills gaps.
    The domain-named context ("chisurf") and the default one win it, so those are guarded.
    """
    call = re.compile(r"add_translations\(([^)]*)\)", re.S)
    context = re.compile(r"context=\"([^\"]*)\"")
    found = set()
    for path in (REPO / "chisurf").rglob("*.py"):
        if "test" in path.parts or "tests" in path.parts:
            continue
        for args in call.findall(path.read_text(encoding="utf-8", errors="ignore")):
            if 'domain="chisurf"' not in args:
                continue
            named = context.search(args)
            if named is None or named.group(1) == "chisurf":
                found.add(".".join(path.relative_to(REPO).with_suffix("").parts))
    return found


def test_every_domain_overlay_is_listed_here():
    assert _overlay_modules() == set(OVERLAYS), (
        "a module layers translations over the shared 'chisurf' domain without this guard; "
        "add it to OVERLAYS"
    )


def test_no_overlay_row_changes_a_translation_the_catalogue_already_gives():
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(REPO), os.environ.get("PYTHONPATH", "")]))
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    specs = [f"{m}:{n}" for m, n in OVERLAYS.items()]
    run = subprocess.run(
        [sys.executable, "-c", _BASELINE, *specs],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert run.returncode == 0, run.stderr[-2000:]
    result = json.loads(run.stdout.strip().splitlines()[-1])
    conflicts = []
    for spec, data in result.items():
        for row in data["rows"]:
            offset = len(row) - len(LOCALES)  # an "en" column first is allowed
            for index, code in enumerate(LOCALES):
                before = data["baseline"][row[0]][code]
                if before != row[0] and row[offset + index] != before:
                    conflicts.append(f"{spec} [{code}] {row[0]!r}: {row[offset + index]!r} != {before!r}")
    assert not conflicts, f"{len(conflicts)} overlay rows re-translate catalogue text:\n" + "\n".join(
        conflicts[:40]
    )
