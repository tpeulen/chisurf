"""A sphere of known size and a stand-in solver, so the tool can teach itself.

HYDROPRO is a separate download, so the tour cannot assume it is installed. ``make_demo(folder)``
writes two files side by side:

* ``sphere_r17.pdb`` -- a cubic lattice of atoms cut to a sphere of radius :data:`DEMO` ``radius_A``;
* ``hydropro_demo`` -- a small stand-in program that follows the HYDROPRO protocol (reads the
  main input file named on stdin, writes ``<name>-res.txt``) but computes **nothing but the
  Stokes-Einstein law** for the sphere that has the volume of the structure's atoms.

The answer is therefore known: ``D = kT / (6 pi eta R)`` for the radius that was built, and it
scales with the temperature and viscosity you set. The stand-in is **not** HYDROPRO and says so
in every report it writes; real structures need the real program.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from pathlib import Path
from typing import Any

import numpy as np

STEM = "sphere_r17"
EXE_NAME = "hydropro_demo"
DEMO: dict[str, Any] = {"version": 1, "radius_A": 17.0, "spacing_A": 2.0}
KB_ERG_PER_K = 1.380649e-16

#: Source of the stand-in program (standard library only, so any Python 3 runs it).
STANDIN = '''#!/usr/bin/env python3
"""Stand-in for HYDROPRO in the ChiSurf tour: Stokes-Einstein for the sphere of the atoms' volume."""
import math, sys
name = sys.stdin.readline().strip()
lines = open(name).read().splitlines()
generic, pdb = lines[1].split()[0], lines[2].split()[0]
def field(tag):
    return float(next(l for l in lines if tag in l).split("!")[0].replace(",", "").split()[0])
t_c, eta = field("!T ("), field("!ETA")
atoms = sum(1 for l in open(pdb) if l.startswith(("ATOM", "HETATM")))
spacing = %(spacing)r
radius_cm = (3.0 * atoms * spacing ** 3 / (4.0 * math.pi)) ** (1.0 / 3.0) * 1e-8
d = %(kb)r * (t_c + 273.15) / (6.0 * math.pi * eta * radius_cm)
print("HYDROPRO demo stand-in: %%d atoms, equivalent sphere radius %%.2f A" %% (atoms, radius_cm * 1e8))
with open(generic + "-res.txt", "w") as out:
    out.write(" HYDROPRO demo stand-in (Stokes-Einstein sphere; NOT a HYDROPRO calculation)\\n")
    out.write(" Temperature (C): %%.1f   Viscosity (poise): %%.4f\\n" %% (t_c, eta))
    out.write(" Translational diffusion coefficient: %%.4E cm**2/s\\n" %% d)
'''


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "hydropro"


def expected_diffusion(t_celsius: float = 20.0, eta_poise: float = 0.01) -> float:
    """Return the true D (cm^2/s) of the built sphere: ``kT / (6 pi eta R)``."""
    radius_cm = DEMO["radius_A"] * 1e-8
    return KB_ERG_PER_K * (t_celsius + 273.15) / (6.0 * math.pi * eta_poise * radius_cm)


def sphere_atoms() -> np.ndarray:
    """Return lattice points (Angstrom) inside the sphere, one per cell."""
    s, r = DEMO["spacing_A"], DEMO["radius_A"]
    n = int(r // s) + 1
    axis = np.arange(-n, n + 1) * s
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), axis=-1).reshape(-1, 3)
    return grid[np.einsum("ij,ij->i", grid, grid) <= r * r]


def _pdb_text() -> str:
    """Render the sphere as ATOM records (carbon atoms of one residue chain)."""
    rows = [
        f"ATOM  {i % 99999 + 1:5d}  C   GLY A{i // 10 % 9999 + 1:4d}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00           C"
        for i, (x, y, z) in enumerate(sphere_atoms())
    ]
    return "\n".join(rows + ["END", ""])


def _digest(folder: Path) -> str:
    """Return a checksum over both generated files."""
    h = hashlib.sha256()
    for name in (f"{STEM}.pdb", EXE_NAME):
        h.update((folder / name).read_bytes())
    return h.hexdigest()


def _cache_is_good(folder: Path) -> bool:
    """Require matching parameters, intact files and an executable stand-in."""
    try:
        side = json.loads((folder / f"{STEM}.json").read_text(encoding="utf-8"))
        return side == {"demo": DEMO, "sha256": _digest(folder)} and os.access(
            folder / EXE_NAME, os.X_OK
        )
    except (OSError, ValueError):
        return False


def standin_path(folder: Path | None = None) -> Path:
    """Return the stand-in executable inside *folder* (default: the demo cache)."""
    return (demo_folder() if folder is None else Path(folder)) / EXE_NAME


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write or reuse the sphere structure and its stand-in solver.

    Parameters
    ----------
    folder : pathlib.Path, optional
        Dedicated cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Regenerate even when the stored parameters and checksum match.

    Returns
    -------
    pathlib.Path
        The PDB file; the stand-in program (:func:`standin_path`) sits beside it.
    """
    folder = demo_folder() if folder is None else Path(folder)
    pdb = folder / f"{STEM}.pdb"
    if not overwrite and _cache_is_good(folder):
        return pdb
    folder.mkdir(parents=True, exist_ok=True)
    pdb.write_text(_pdb_text(), encoding="ascii")
    exe = folder / EXE_NAME
    exe.write_text(STANDIN % {"spacing": DEMO["spacing_A"], "kb": KB_ERG_PER_K}, encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    (folder / f"{STEM}.json").write_text(
        json.dumps({"demo": DEMO, "sha256": _digest(folder)}, sort_keys=True), encoding="utf-8"
    )
    return pdb
