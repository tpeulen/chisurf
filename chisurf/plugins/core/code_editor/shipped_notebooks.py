"""The example notebooks ChiSurf ships, for the editor's *File ▸ Open Notebook* menu.

Toolkit-free; the emtk editor builds its submenu from :func:`notebook_groups`.
"""

from __future__ import annotations

import pathlib

import chisurf as cs

__all__ = ["notebook_groups", "shipped_notebooks", "shipped_notebooks_dir"]


def shipped_notebooks_dir() -> pathlib.Path | None:
    """Return the checkout's curated ``examples/notebooks`` directory, or ``None``.

    Resolved from the installed package file (as ``docs_root`` resolves the documentation), so
    the same lookup works from a source checkout; a packaged install without the examples
    directory yields ``None`` and the menu says there are none.
    """
    here = pathlib.Path(cs.__file__).resolve().parent
    candidate = here.parent / "examples" / "notebooks"
    return candidate if candidate.is_dir() else None


def shipped_notebooks() -> list[pathlib.Path]:
    """Return the shipped ``*.ipynb`` files (top level of ``examples/notebooks``), sorted by name."""
    base = shipped_notebooks_dir()
    if base is None:
        return []
    return [path for path in sorted(base.glob("*.ipynb")) if path.is_file()]


def notebook_groups() -> dict[str, list[pathlib.Path]]:
    """The shipped notebooks grouped by the prefix before the first ``_`` (``Other`` without one).

    Returns
    -------
    dict
        ``{group: [paths sorted by name]}`` with the groups in sorted order.
    """
    groups: dict[str, list[pathlib.Path]] = {}
    for path in shipped_notebooks():
        group = path.name.split("_", 1)[0] if "_" in path.name else "Other"
        groups.setdefault(group, []).append(path)
    return {group: sorted(groups[group], key=lambda p: p.name) for group in sorted(groups)}
