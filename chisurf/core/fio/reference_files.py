"""Buffer, scatter and reference-dye measurements beside a measurement: what a fit's IRF and
background come from.

A lab measures the buffer (background), a scatterer (water, Ludox: the IRF) and reference dyes of
known lifetime (Rh110, Alexa647) in the session of the sample; a lifetime fit should use them
without the user hunting for them. They are found by name in the folders of the analysed files
(and one level up), never the analysed files themselves. The reference dyes and their lifetimes
are declared in ``reference_dyes.yaml``.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable

__all__ = [
    "BACKGROUND_PATTERN",
    "IRF_PATTERN",
    "find_reference_measurements",
    "reference_dye",
    "reference_dyes",
]

#: Names of a scatter / IRF measurement.
IRF_PATTERN = re.compile(r"(?<![a-z])(irf|scatter|ludox|water|h2o|prompt)(?![a-z])", re.I)
#: Names of a buffer / background measurement.
BACKGROUND_PATTERN = re.compile(
    r"(?<![a-z])(buffer|background|bg|blank|pbs|tris|hepes|bckg|bkg)(?![a-z])", re.I
)


@lru_cache(maxsize=1)
def reference_dyes() -> tuple[dict, ...]:
    """The reference dyes of ``reference_dyes.yaml``: ``name``, ``pattern`` (compiled), ``tau_ns``."""
    import yaml

    with open(Path(__file__).with_name("reference_dyes.yaml"), encoding="utf-8") as fh:
        rows = yaml.safe_load(fh) or []
    return tuple(
        {
            "name": str(r["name"]),
            "pattern": re.compile(rf"(?<![a-z0-9])(?:{r['pattern']})(?![a-z])", re.I),
            "tau_ns": float(r["tau_ns"]),
        }
        for r in rows
    )


def reference_dye(path: str | Path) -> dict | None:
    """The reference dye *path* is a measurement of (by its name), or ``None``."""
    stem = Path(path).stem
    return next((d for d in reference_dyes() if d["pattern"].search(stem)), None)


def _measurements(folder: Path) -> list[Path]:
    from chisurf.core.fio.staging import TTTR_EXTENSIONS

    try:
        return sorted(
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in TTTR_EXTENSIONS and not p.name.startswith("._")
        )
    except OSError:
        return []


def find_reference_measurements(
    analysed: Iterable[str | Path], *, parents: int = 1
) -> dict[str, list[Path]]:
    """``{"irf": [...], "dye": [...], "bg": [...]}`` -- the scatter, reference-dye and buffer
    measurements near *analysed*.

    Parameters
    ----------
    analysed : iterable of path
        The measurements being analysed (their folders are searched; they are never returned).
    parents : int
        How many folder levels above each measurement are searched too.
    """
    analysed = [Path(p).resolve() for p in analysed]
    folders: list[Path] = []
    for path in analysed:
        folder = path.parent
        for _ in range(int(parents) + 1):
            if folder not in folders:
                folders.append(folder)
            folder = folder.parent
    found: dict[str, list[Path]] = {"irf": [], "dye": [], "bg": []}
    for folder in folders:
        for candidate in _measurements(folder):
            if candidate.resolve() in analysed:
                continue
            stem = candidate.stem
            if IRF_PATTERN.search(stem) and candidate not in found["irf"]:
                found["irf"].append(candidate)
            elif reference_dye(candidate) is not None and candidate not in found["dye"]:
                found["dye"].append(candidate)
            elif BACKGROUND_PATTERN.search(stem) and candidate not in found["bg"]:
                found["bg"].append(candidate)
        if any(found.values()):
            break  # the nearest folder with references is the session's
    return found
