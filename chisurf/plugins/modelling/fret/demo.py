"""The HIV reverse-transcriptase docking project, copied where the docking tour can work on it.

``make_demo(folder)`` copies the shipped example (``examples/fps_hiv_rt``: the protein ``1R0A``, its DNA, the
``hiv_rt.fps.json`` with 20 measured distances and the ``docking_project.json`` naming them) into a settings-owned
folder, so a run writes its output there and never into the installed package. The answer is known: the docked DNA
sits where the crystal structure has it, and the reference pose scores the 20 distances within their errors.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

EXAMPLE = Path(__file__).resolve().parent / "examples" / "fps_hiv_rt"
FILES = ("protein_1R0A.pdb", "dna.pdb", "hiv_rt.fps.json", "docking_project.json")
DEMO: dict[str, Any] = {"version": 1, "example": "fps_hiv_rt", "files": list(FILES)}


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "fret_docking"


def _digest(folder: Path) -> str:
    """Return a checksum over the copied files."""
    h = hashlib.sha256()
    for name in FILES:
        h.update((folder / name).read_bytes())
    return h.hexdigest()


def _cache_is_good(folder: Path) -> bool:
    """Require matching parameters and the files the stamp was written for."""
    try:
        side = json.loads((folder / "demo.json").read_text(encoding="utf-8"))
        return side == {"demo": DEMO, "sha256": _digest(folder)}
    except (OSError, ValueError):
        return False


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Copy (or reuse) the HIV-RT docking example.

    Parameters
    ----------
    folder : pathlib.Path, optional
        Dedicated cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Copy again even when the stored parameters and checksum match.

    Returns
    -------
    pathlib.Path
        The ``docking_project.json``; the structures and the fps.json it names sit beside it.
    """
    folder = demo_folder() if folder is None else Path(folder)
    project = folder / "docking_project.json"
    if not overwrite and _cache_is_good(folder):
        return project
    folder.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copyfile(EXAMPLE / name, folder / name)
    (folder / "demo.json").write_text(
        json.dumps({"demo": DEMO, "sha256": _digest(folder)}, sort_keys=True), encoding="utf-8"
    )
    return project
