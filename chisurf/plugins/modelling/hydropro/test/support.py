"""Shared fixtures-as-functions for the HydroPro native tests: a temporary world with a fake HYDRO and structure files."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from . import hermetic

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
REAL_PDB = REPO / "test/data/atomic_coordinates/pdb_files/148l.pdb"
BIG = (1200, 800)
SMALL = (800, 600)
#: Structure stems the fake program knows (see data/fake_hydro.sh) and what it reports for each.
EXPECTED = {"148l": 1.047e-06, "small": 2.5e-07, "plain": 4.0, "garbled": None, "silent": None, "fails": None, "slow": None}


def make_world(home: Path) -> dict:
    """Fake executables (``hydropro10.exe`` -> HYDROPRO, ``hydro++10.exe`` -> HYDRO++) and structure files in *home*."""
    bin_dir = home / "bin"
    exe = hermetic.install_fake_exe(bin_dir, "hydropro10.exe")
    hpp = hermetic.install_fake_exe(bin_dir, "hydro++10.exe")
    noexec = bin_dir / "hydropro_noexec.exe"
    noexec.write_text("#!/bin/sh\n")
    noexec.chmod(0o644)
    structures = {}
    for stem in EXPECTED:
        path = home / f"{stem}.pdb"
        if stem == "148l" and REAL_PDB.exists():
            shutil.copyfile(REAL_PDB, path)
        else:
            path.write_text("ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00  0.00           C\nEND\n")
        structures[stem] = path
    return {"exe": exe, "hpp": hpp, "noexec": noexec, "files": structures, "home": home}


def drain(app_or_model, timeout=60.0):
    """Wait for the worker of a model (or an app's model) and apply its events."""
    model = getattr(app_or_model, "model", app_or_model)
    end = time.monotonic() + timeout
    while model.running and time.monotonic() < end:
        model.wait(0.1)
    assert not model.running, "the HYDRO worker did not finish"
    return model
