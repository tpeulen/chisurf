"""Readers: structures, trajectories, density maps and RMF hierarchies.

Nothing is imported eagerly, for the reason given in :mod:`chimol` and
:mod:`chimol.renderer`. This package used to import all of its readers at once,
so asking for the PDB parser -- which is self-contained -- also pulled in the
density-map reader, and through it marching cubes, ambient occlusion and
``scipy``. That is what a browser found: chimol can parse a PDB with numpy
alone, and could not, because reading one meant loading everything that reads
anything.

The names below resolve on first use, through :pep:`562`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - for type checkers and IDEs only
    from .atoms import ATOM_DTYPE, BEAD_RES_NAME, bead_mask, bead_row, make_bead_rows
    from .mrc import load_mrc_as_points
    from .rmf import RmfHierarchyNode, RmfNotAvailableError, load_rmf_full
    from .structure import (
        TrajectoryFormatError,
        load_structure_payload,
        load_trajectory_frames,
        open_structure_files,
    )

__all__ = [
    "ATOM_DTYPE",
    "BEAD_RES_NAME",
    "bead_mask",
    "bead_row",
    "make_bead_rows",
    "open_structure_files",
    "load_structure_payload",
    "load_trajectory_frames",
    "TrajectoryFormatError",
    "load_mrc_as_points",
    "load_rmf_full",
    "RmfHierarchyNode",
    "RmfNotAvailableError",
]

#: Which module each public name lives in.
_LAZY: dict[str, str] = {
    "ATOM_DTYPE": ".atoms",
    "BEAD_RES_NAME": ".atoms",
    "bead_mask": ".atoms",
    "bead_row": ".atoms",
    "make_bead_rows": ".atoms",
    "open_structure_files": ".structure",
    "load_structure_payload": ".structure",
    "load_trajectory_frames": ".structure",
    "TrajectoryFormatError": ".structure",
    "load_mrc_as_points": ".mrc",
    "load_rmf_full": ".rmf",
    "RmfHierarchyNode": ".rmf",
    "RmfNotAvailableError": ".rmf",
}


def __getattr__(name: str):
    """Resolve a reader on first access.

    Parameters
    ----------
    name : str

    Returns
    -------
    object

    Raises
    ------
    AttributeError
        If ``name`` is not in :data:`__all__`.
    """
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(module, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """List the module's attributes, including the ones not yet imported."""
    return sorted({*globals(), *__all__})
