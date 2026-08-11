"""Forwarder — fps.json / FPS I/O moved to :mod:`IMP.bff.fret.io` (PRD-97).

Unlike the pure module-alias forwarders next to this file, two functions are
overridden here with application behaviour that does not belong in IMP.bff:

* :func:`read_evaluators_json` instantiates this plugin's evaluator classes
  (IMP.bff's reader returns raw dicts, or takes a factory — we pass ours).
* :func:`write_rmf` keeps ChiSurf's PMI-compatible ``StructureRmfWriter``
  output (IMP.bff ships a plain self-contained RMF writer instead).
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import numpy as np

# Everything the moved implementation exports, including the schema-validating
# reader/writer and the legacy C# FPS readers.
from IMP.bff.fret.io import *  # noqa: F401,F403
from IMP.bff.fret.io import (  # noqa: F401  (names used by plugin/tests)
    read_fps_json,
    write_fps_json,
    write_evaluators_json,
    read_old_lps_txt,
    read_old_distances_txt,
    load_structure,
    load_structure_with_particles,
    write_pdb,
    compute_rmsd,
)
from IMP.bff.fret.io import read_evaluators_json as _read_evaluators_json


def read_evaluators_json(path: str | os.PathLike) -> List:
    """Read 'Evaluators' from an fps.json and instantiate this plugin's classes."""
    from .. import evaluators as ev_pkg
    return _read_evaluators_json(path, factory=ev_pkg.from_dict)


def write_rmf(
    atoms: np.ndarray,
    path: str | os.PathLike,
    model_name: str = "structure",
    transform: Optional[np.ndarray] = None,
    metadata: Optional[Dict] = None,
) -> None:
    """Write ``(N, 3)`` coordinates to a PMI-compatible RMF file.

    Requires ``IMP`` + ``IMP.rmf``.
    """
    from chisurf.core.models.structure.rmf import StructureRmfWriter

    coords = np.asarray(atoms[:, :3], dtype=np.float64).copy()
    if transform is not None:
        t = np.asarray(transform, dtype=np.float64)
        if t.shape == (4, 4):
            coords = coords @ t[:3, :3].T + t[:3, 3]
        elif t.shape == (3, 3):
            coords = coords @ t.T
        elif t.shape == (3,):
            coords = coords + t
        else:
            raise ValueError(f"Unexpected transform shape {t.shape}")

    with StructureRmfWriter.from_coordinates(
        str(path),
        atoms,
        model_name=model_name,
        transform=transform,
        metadata=metadata,
    ) as writer:
        writer.append(coords)
