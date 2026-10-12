"""One atom-radius set for accessible volumes: IMP's radii times one scale.

Owner, 2026-10-12: an accessible volume's obstacles are IMP's radii times
``IMP.bff.AV_DEFAULT_RADIUS_SCALE``, everywhere, with no second radii table.
ChiSurf reads them through ``chisurf.core.structure.av.radii``. The FRET plugin
carried FPS's Bondi element table (``VDW_RADII``) until then; this guard fails
if a private radius table reappears in the shipped tree, or if an AV module
reaches for the viewer's element radii.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2] / "chisurf"

#: Radius tables that are deliberately not an AV's obstacle set.
ALLOWED = {
    # PyMOL's element radii: what the structure viewer draws a sphere with.
    "core/fio/structure/elements.py",
}

#: A module-level radius table: ``VDW_RADII = {``, ``BONDI_RADII: dict = {`` ...
_TABLE = re.compile(r"^[A-Z_]*(RADII|VDW|BONDI)[A-Z_]*\s*(:[^=\n]*)?=\s*\{", re.M)
#: Bondi's carbon and nitrogen side by side, keyed by atomic number or symbol.
_BONDI = (
    re.compile(
        r"\b6\s*:\s*1\.70?\b[^\n]*?\b7\s*:\s*1\.55\b|\b6\s*:\s*1\.70?\s*,\s*\n\s*7\s*:\s*1\.55\b"
    ),
    re.compile(r"[\"']C[\"']\s*:\s*1\.70?\b[^}]*?[\"']N[\"']\s*:\s*1\.55\b", re.S),
)

#: The modules that compute accessible volumes.
AV_MODULES = (
    "core/structure/av",
    "plugins/modelling/fret/core",
    "plugins/quenching_estimator/core",
)


def _sources():
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if "/test" in rel or rel.startswith("plugins/chimol/"):
            continue
        yield rel, path.read_text(encoding="utf-8", errors="replace")


def test_no_private_radius_table():
    offenders = []
    for rel, text in _sources():
        if rel in ALLOWED:
            continue
        if _TABLE.search(text) or any(p.search(text) for p in _BONDI):
            offenders.append(rel)
    assert offenders == [], (
        "a private atom-radius table is back; accessible volumes take IMP's radii "
        "times AV_DEFAULT_RADIUS_SCALE from chisurf.core.structure.av.radii: "
        f"{offenders}"
    )


def test_av_modules_do_not_use_viewer_radii():
    offenders = []
    for rel, text in _sources():
        if not rel.startswith(AV_MODULES):
            continue
        if re.search(r"\b(radii_for|radius_of|VDW_RADIUS|DEFAULT_VDW_RADIUS)\b", text):
            offenders.append(rel)
    assert offenders == []


def test_the_helper_reads_imp_bff():
    import IMP.bff

    from chisurf.core.structure.av import radii

    assert radii.radius_scale() == IMP.bff.AV_DEFAULT_RADIUS_SCALE
    got = radii.obstacle_radii(["ALA", "ALA", "HOH"], ["CA", "O", "O"])
    scale = IMP.bff.AV_DEFAULT_RADIUS_SCALE
    assert got.tolist() == [
        IMP.bff.imp_atom_radius("ALA", "CA") * scale,
        IMP.bff.imp_atom_radius("ALA", "O") * scale,
        IMP.bff.get_imp_atom_default_radius() * scale,
    ]
