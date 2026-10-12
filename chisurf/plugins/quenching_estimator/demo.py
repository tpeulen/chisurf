"""The QuEst demo: T4 lysozyme (PDB 148L) with a site whose answer is known to be quenched.

A guided tour needs something to demonstrate on that every user has, so the plugin ships one
structure and one project and can start from them without the user's own files. The site is
E36 (Ser), Cβ: labelable at IMP.bff's default accessible-volume parameters and quenched by
nearby Pro/Tyr/His, so the run ends in a quantum yield clearly below 1 rather than a flat 1.0
(a third of 148L's Cβ sites have no accessible volume at the default linker width; see the
plugin's guide in the documentation). The run is short (a few seconds) on purpose.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

#: The shipped structure: T4 lysozyme, crystal waters already absent.
DEMO_STRUCTURE = Path(__file__).resolve().parent / "examples" / "148l.pdb"

#: Donor attachment of the demo, (chain, residue, atom).
DEMO_SITE = ("E", 36, "CB")


def demo_structure(directory: str | Path | None = None) -> Path:
    """The demo structure, copied into *directory* when one is given (so a user can keep it)."""
    if directory is None:
        return DEMO_STRUCTURE
    target = Path(directory) / DEMO_STRUCTURE.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(DEMO_STRUCTURE, target)
    return target


def apply_demo(model: Any, directory: str | Path | None = None) -> Path:
    """Point a ``ProjectFormModel`` at the demo: structure, site and a short run.

    Returns the structure path. FRET is switched off: the demo shows quenching alone.
    """
    path = demo_structure(directory)
    model.pdb = str(path)
    model.auto_attach_to_structure()
    model.attachment_chain, model.attachment_residue, model.attachment_atom = DEMO_SITE
    model.fret_enabled = False
    project = model.project
    dyes = project.get("fret", {}).get("dyes", [])
    if dyes:
        dyes[0]["attachment"] = {"chain": DEMO_SITE[0], "residue": DEMO_SITE[1], "atom": DEMO_SITE[2]}
    model.n_photons, model.t_max = 200_000, 2000.0
    project["random_seed"] = 7
    model._notify()
    return path
