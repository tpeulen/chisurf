"""Example data for the Burstwise importer: a legacy burstwise folder, written on demand.

``make_demo`` writes the deterministic legacy sample
(:mod:`chisurf.plugins.burst.burstwise_import.sample`: ``.bur`` splits, a ``.mti``
metadata file, ``bg4``/``br4`` companions, burst IDs) into the settings tree, beside
a JSON sidecar holding :data:`DEMO` and a digest of the folder, and reuses it while
both still match. *Load example* points the importer at it and inventories it,
ready to convert.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from chisurf.plugins.burst.burstwise_import.sample import (
    FOLDER,
    N_BURSTS,
    SEED,
    STEMS,
    write_sample,
)

STEM = "burstwise_sample"
#: Everything that decides the folder's bytes; the sidecar compares against it.
DEMO = {"folder": FOLDER, "seed": SEED, "stems": list(STEMS), "bursts": list(N_BURSTS)}
SIDECAR_NAME = "demo.json"


def demo_folder() -> Path:
    """The settings-owned demonstration folder of the importer."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "burstwise_import"


def _digest(sample: Path) -> str:
    """One sha256 over every file of the sample (relative path and bytes, in order)."""
    h = hashlib.sha256()
    for path in sorted(p for p in sample.rglob("*") if p.is_file()):
        h.update(path.relative_to(sample).as_posix().encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def _current(folder: Path) -> bool:
    """Reuse only a sample whose sidecar matches :data:`DEMO` and its bytes."""
    try:
        record = json.loads((folder / SIDECAR_NAME).read_text(encoding="utf-8"))
        return record == {"demo": DEMO, "sha256": _digest(folder / FOLDER)}
    except (OSError, ValueError):
        return False


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write (or reuse) the example legacy folder; return the analysis folder."""
    folder = demo_folder() if folder is None else Path(folder)
    sample = folder / FOLDER
    if overwrite or not _current(folder):
        if sample.exists():
            shutil.rmtree(sample)
        write_sample(folder)
        record = {"demo": DEMO, "sha256": _digest(sample)}
        (folder / SIDECAR_NAME).write_text(
            json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
    return sample


def load_into(model) -> Path:
    """Point the importer at the example folder and inventory it."""
    folder = make_demo()
    model.set_folder(str(folder))
    model.scan()
    return folder
