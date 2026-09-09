"""PMI-compatible RMF output for ChiSurf structures.

The hierarchy and the per-frame ``stat`` values are written by
``IMP.bff.RmfStructureWriter``, which builds the tree through **RMF's own
decorators** rather than through ``IMP.rmf``. That matters twice over: the
connection layer's IMP does not carry ``IMP.rmf`` at all, and this module
therefore imports no IMP -- only ``IMP.bff``, whose structure record it fills
from ChiSurf's atom array.

What is left here is the part that is ChiSurf's: turning an atom array into
that record, and the coordinate-only convenience constructor.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional

import numpy as np


class RmfWriterError(RuntimeError):
    """Raised when ChiSurf cannot write an RMF trajectory."""


def _bff():
    """Return ``IMP.bff``, imported on first use.

    Returns
    -------
    module
        The ``IMP.bff`` module.

    Raises
    ------
    RmfWriterError
        When ``IMP.bff`` is absent, or was built without RMF. The pip wheel is
        the second case: RMF pulls Boost.Iostreams and through it all of ICU,
        40 MB for four I/O functions, so the wheel leaves it out and both
        conda packages keep it.
    """
    try:
        import IMP.bff as bff
    except ImportError as exc:
        raise RmfWriterError("RMF output requires IMP.bff.") from exc

    if not hasattr(bff, "RmfStructureWriter"):
        raise RmfWriterError(
            "this IMP.bff was built without RMF, so it cannot write a "
            f"trajectory (build {getattr(bff, 'get_build', lambda: '?')()}). "
            "The pip wheel leaves RMF out; the conda packages carry it."
        )
    return bff


def _as_text(value: Any) -> str:
    """Convert fixed-width NumPy string values to plain text.

    Parameters
    ----------
    value : object
        A NumPy string scalar, bytes, or anything with a ``str``.

    Returns
    -------
    str
        The value as stripped text.
    """
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore").strip()
    return str(value).strip()


def _jsonable(values: Mapping[str, Any]) -> str:
    """Render per-frame metadata as the JSON object the writer takes.

    Parameters
    ----------
    values : mapping
        Per-frame scalars. NumPy scalars are unwrapped; anything that is not a
        number, a bool or a string becomes its ``str``.

    Returns
    -------
    str
        A JSON object, or ``""`` for empty metadata.
    """
    if not values:
        return ""
    out = {}
    for name, value in values.items():
        if isinstance(value, np.generic):
            value = value.item()
        if not isinstance(value, (bool, int, float, str)):
            value = str(value)
        out[str(name)] = value
    return json.dumps(out)


def _table_from_atoms(atoms: np.ndarray):
    """Build an ``IMP.bff.StructureTable`` from a ChiSurf atom array.

    Parameters
    ----------
    atoms : numpy.ndarray
        A structured array with at least ``xyz``; ``chain``, ``res_id``,
        ``res_name``, ``atom_name``, ``radius`` and ``mass`` are used when
        present and given the defaults the writer this replaced used.

    Returns
    -------
    IMP.bff.StructureTable
        The record the writer takes.
    """
    bff = _bff()
    names = atoms.dtype.names or ()
    n = len(atoms)

    table = bff.StructureTable()
    table.xyz = np.ascontiguousarray(atoms["xyz"], dtype=np.float64).reshape(-1)

    if "radius" in names:
        table.radius = np.ascontiguousarray(atoms["radius"], dtype=np.float64)
    else:
        table.radius = np.full(n, 1.5)
    if "mass" in names:
        table.mass = np.ascontiguousarray(atoms["mass"], dtype=np.float64)
    else:
        table.mass = np.ones(n)
    if "res_id" in names:
        table.res_id = np.ascontiguousarray(atoms["res_id"], dtype=np.int32)
    else:
        table.res_id = np.arange(1, n + 1, dtype=np.int32)

    # A blank chain is "A": a PDB with no chain column is one chain, and an
    # empty node name is not something a viewer can show.
    if "chain" in names:
        table.chain = [(_as_text(v) or "A") for v in atoms["chain"]]
    else:
        table.chain = ["A"] * n
    if "res_name" in names:
        table.res_name = [(_as_text(v) or "UNK") for v in atoms["res_name"]]
    else:
        table.res_name = ["UNK"] * n
    if "atom_name" in names:
        table.atom_name = [
            (_as_text(v) or f"A{i}") for i, v in enumerate(atoms["atom_name"])
        ]
    else:
        table.atom_name = [f"A{i}" for i in range(n)]
    return table


class StructureRmfWriter:
    """Write ChiSurf structure frames as a PMI-compatible RMF trajectory."""

    def __init__(
        self,
        filename: str | Path,
        structure: Any,
        *,
        stat_output: Optional[Mapping[str, Any]] = None,
        root_name: str = "ProteinMC",
    ) -> None:
        """Open an RMF file and build the hierarchy ``structure`` describes.

        Parameters
        ----------
        filename : str or pathlib.Path
            Output RMF/RMF3 filename.
        structure : object
            A ChiSurf structure, or anything with an ``atoms`` record array.
        stat_output : mapping, optional
            Written as the file's description. Per-frame values go to
            :meth:`append`.
        root_name : str, optional
            Name for the top-level RMF hierarchy node.

        Raises
        ------
        RmfWriterError
            When ``IMP.bff`` is absent or was built without RMF, or the file
            cannot be written.
        """
        bff = _bff()
        self.filename = str(Path(filename))
        self.structure = structure
        try:
            self._writer = bff.RmfStructureWriter(
                self.filename,
                _table_from_atoms(structure.atoms),
                root_name=root_name,
                metadata_json=_jsonable(stat_output or {}),
            )
        except RmfWriterError:
            raise
        except Exception as exc:
            raise RmfWriterError(
                f"could not open {self.filename} for RMF output: {exc}"
            ) from exc

    def __enter__(self) -> "StructureRmfWriter":
        """Return this writer for ``with``-statement use."""
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        """Close the RMF file when leaving a ``with`` block."""
        self.close()

    @classmethod
    def from_coordinates(
        cls,
        filename: str | Path,
        coords: np.ndarray,
        model_name: str = "structure",
        transform: np.ndarray | None = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> "StructureRmfWriter":
        """Create a writer for raw ``(N, 3)`` or ``(N, 4)`` coordinates.

        Parameters
        ----------
        filename : str or pathlib.Path
            Output RMF/RMF3 filename.
        coords : array_like, shape ``(N, 3)`` or ``(N, 4)``
            Cartesian coordinates. A fourth column is ignored.
        model_name : str, optional
            Name used for the generated hierarchy root.
        transform : array_like, optional
            A translation ``(3,)``, a rotation ``(3, 3)`` or a homogeneous
            ``(4, 4)``, applied to ``coords`` before writing.
        metadata : mapping, optional
            Written as the file's description.

        Returns
        -------
        StructureRmfWriter
            A writer whose hierarchy is one chain of single-atom residues,
            ready for :meth:`append`.

        Raises
        ------
        ValueError
            For coordinates that are not ``(N, 3)`` or ``(N, 4)``, or a
            transform of an unexpected shape.
        """
        coords = np.asarray(coords, dtype=np.float64)
        if coords.ndim != 2 or coords.shape[1] < 3:
            raise ValueError(
                f"Expected (N, 3) or (N, 4) coordinates, got {coords.shape}"
            )

        xyz = coords[:, :3].copy()
        if transform is not None:
            t = np.asarray(transform, dtype=np.float64)
            if t.shape == (4, 4):
                xyz = xyz @ t[:3, :3].T + t[:3, 3]
            elif t.shape == (3, 3):
                xyz = xyz @ t.T
            elif t.shape == (3,):
                xyz = xyz + t
            else:
                raise ValueError(f"Unexpected transform shape {t.shape}")

        from chisurf.core.fio.structure.coordinates import atom_dtype
        from chisurf.core.structure.structure import Structure

        atoms = np.zeros(len(xyz), dtype=atom_dtype)
        atoms["i"] = np.arange(1, len(xyz) + 1)
        atoms["atom_id"] = atoms["i"]
        atoms["atom_name"] = "CA"
        atoms["res_name"] = "UNK"
        atoms["res_id"] = atoms["i"]
        atoms["chain"] = "A"
        atoms["element"] = "C"
        atoms["xyz"] = xyz
        atoms["radius"] = 1.0
        atoms["mass"] = 1.0

        structure = Structure()
        structure.atoms = atoms
        return cls(
            filename, structure, stat_output=metadata, root_name=model_name
        )

    def append(
        self,
        xyz: np.ndarray,
        name: str | None = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Append one coordinate frame to the trajectory.

        Parameters
        ----------
        xyz : array_like, shape ``(n_atoms, 3)``
            Cartesian coordinates for the frame, in the hierarchy's atom order.
        name : str, optional
            RMF frame name. The frame index is used when omitted.
        metadata : mapping, optional
            Per-frame scalars written to the RMF ``stat`` category, which is
            where PMI puts them.

        Raises
        ------
        ValueError
            When ``xyz`` does not have three coordinates per atom.
        """
        coords = np.asarray(xyz, dtype=np.float64)
        n = self._writer.n_atoms
        if coords.shape != (n, 3):
            raise ValueError(
                f"xyz must have shape ({n}, 3), got {coords.shape!r}"
            )
        self._writer.append(
            np.ascontiguousarray(coords).reshape(-1),
            frame_name="" if name is None else str(name),
            metadata_json=_jsonable(metadata or {}),
        )

    @property
    def n_frames(self) -> int:
        """Number of frames written so far."""
        return int(self._writer.n_frames)

    def close(self) -> None:
        """Flush and release the RMF file handle."""
        self._writer.close()


#: Backwards-compatible alias for existing ProteinMC imports.
ProteinMCRmfWriter = StructureRmfWriter


__all__ = [
    "RmfWriterError",
    "StructureRmfWriter",
    "ProteinMCRmfWriter",
]
