"""Buffer and scatter measurements beside a measurement: the background and IRF a fit can use.

A lab measures the buffer (background) and a scatterer (water, Ludox: the IRF) in the session of
the sample; a lifetime fit should use them without the user hunting for them. They are found by
name in the folders of the analysed files (and one level up), never the analysed files themselves.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

__all__ = ["BACKGROUND_PATTERN", "IRF_PATTERN", "find_reference_measurements"]

#: Names of a scatter / IRF measurement.
IRF_PATTERN = re.compile(r"(?<![a-z])(irf|scatter|ludox|water|h2o|prompt)(?![a-z])", re.I)
#: Names of a buffer / background measurement.
BACKGROUND_PATTERN = re.compile(
    r"(?<![a-z])(buffer|background|bg|blank|pbs|tris|hepes|bckg|bkg)(?![a-z])", re.I
)


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
    """``{"irf": [...], "bg": [...]}`` -- the scatter and buffer measurements near *analysed*.

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
    found: dict[str, list[Path]] = {"irf": [], "bg": []}
    for folder in folders:
        for candidate in _measurements(folder):
            if candidate.resolve() in analysed:
                continue
            stem = candidate.stem
            if IRF_PATTERN.search(stem) and candidate not in found["irf"]:
                found["irf"].append(candidate)
            elif BACKGROUND_PATTERN.search(stem) and candidate not in found["bg"]:
                found["bg"].append(candidate)
        if found["irf"] or found["bg"]:
            break  # the nearest folder with references is the session's
    return found
