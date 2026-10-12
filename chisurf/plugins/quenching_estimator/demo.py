"""The QuEst demo: T4 lysozyme (PDB 148L) with a site whose answer is known to be quenched.

A guided tour needs something to demonstrate on that every user has, so the plugin ships one
structure and one project and can start from them without the user's own files. The site is
E36 (Ser), Cβ: labelable at IMP.bff's default accessible-volume parameters and quenched by
nearby Pro/Tyr/His, so the run ends in a quantum yield clearly below 1 rather than a flat 1.0
(a third of 148L's Cβ sites have no accessible volume at the default linker width; see the
plugin's guide in the documentation). The run is short (a few seconds) on purpose.

:func:`make_demo` writes the structure and the demo project into the plugin's settings cache
(``<settings>/demos/quenching_estimator``, stamped by :mod:`chisurf.plugins.demo_cache`), and the
window's *Load example* reads that project, so the window, the CLI and a test all start from the
same file.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

#: The shipped structure: T4 lysozyme, crystal waters already absent.
DEMO_STRUCTURE = Path(__file__).resolve().parent / "examples" / "148l.pdb"

#: Donor attachment of the demo, (chain, residue, atom).
DEMO_SITE = ("E", 36, "CB")

#: The demo, in one place so the guide, the cache stamp and the tests agree.
DEMO: dict[str, Any] = dict(
    version=1,
    structure=DEMO_STRUCTURE.name,
    site=list(DEMO_SITE),
    fret_enabled=False,
    n_photons=200_000,
    t_max=2000.0,
    random_seed=7,
)

#: The demo project's file name inside the cache folder.
PROJECT_FILENAME = "quest_demo.json"


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder of this plugin."""
    from chisurf.plugins.demo_cache import cache_folder

    return cache_folder("quenching_estimator")


def make_demo(folder: str | Path | None = None, *, overwrite: bool = False) -> Path:
    """Write or reuse the demo: the structure and a project pointing at it.

    Parameters
    ----------
    folder : str or Path, optional
        Cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Write again even when the stamped parameters and checksums match.

    Returns
    -------
    Path
        The demo project JSON (its ``pdb`` is the structure copied beside it).
    """
    from chisurf.plugins.demo_cache import is_current, record

    folder = demo_folder() if folder is None else Path(folder)
    names = [DEMO_STRUCTURE.name, PROJECT_FILENAME]
    project_path = folder / PROJECT_FILENAME
    if not overwrite and is_current(folder, names, DEMO):
        return project_path
    from chisurf.plugins.quenching_estimator.gui.form_model import ProjectFormModel

    model = ProjectFormModel(locale="en")
    apply_demo(model, folder)
    model.save_project(project_path)
    record(folder, names, DEMO)
    return project_path


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
    model.fret_enabled = DEMO["fret_enabled"]
    project = model.project
    dyes = project.get("fret", {}).get("dyes", [])
    if dyes:
        dyes[0]["attachment"] = {
            "chain": DEMO_SITE[0],
            "residue": DEMO_SITE[1],
            "atom": DEMO_SITE[2],
        }
    model.n_photons, model.t_max = DEMO["n_photons"], DEMO["t_max"]
    project["random_seed"] = DEMO["random_seed"]
    model._notify()
    return path
