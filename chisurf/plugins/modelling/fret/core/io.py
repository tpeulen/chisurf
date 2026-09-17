"""fps.json and FPS I/O: the plugin's face on ``IMP.bff``'s readers.

The formats are ``IMP.bff``'s and the readers are C++. Two functions carry
application behaviour that does not belong in a format library:

* :func:`read_evaluators_json` instantiates this plugin's evaluator classes
  (IMP.bff's reader returns raw dicts, or takes a factory — we pass ours).
* :func:`write_rmf` keeps ChiSurf's PMI-compatible ``StructureRmfWriter``
  output (IMP.bff ships a plain self-contained RMF writer instead).
"""

from __future__ import annotations

import os

import numpy as np

#: `compute_rmsd` upstream; the interface pass renamed the free functions to
#: `get_`/`create_` and this is the survivor. Aliased rather than renamed at
#: the call sites, because "rmsd between two coordinate sets" is what the
#: plugin means and `get_rmsd` reads like an accessor.
from IMP.bff import get_rmsd as compute_rmsd  # noqa: F401

# The readers and writers are IMP.bff's, in C++: an fps.json is a format, and
# reading a format is not this application's business. Named imports rather
# than a star, so a name that disappears upstream is an error here and not a
# mystery at the call site.
from IMP.bff import (  # noqa: F401  (names used by plugin/tests)
    load_structure,
    read_old_distances_txt,
    read_old_lps_txt,
    write_fps_json,
    write_pdb,
)
from IMP.bff import read_evaluators_json as _read_evaluators_json


def read_fps_json(path, pdb_paths=(), validate=False):
    """Read an fps.json as the three sections the plugin works in.

    Parameters
    ----------
    path : str
        The labelling file.
    pdb_paths : sequence of str
        Structures the file names, for resolving relative references.
    validate : bool
        Check the document against the shipped schema.

    Returns
    -------
    tuple
        ``(positions, distances, score_sets, extra)`` -- the four sections
        this plugin's callers unpack.

    Notes
    -----
    Upstream returns an ``FPSDocument``, one value with named sections, which
    is the better shape and not the one the callers use. Unpacked here, once,
    rather than at each of them. ``molecules`` is reachable as
    ``IMP.bff.read_fps_json(path).molecules`` for anything that wants it.
    """
    import json as _json

    import IMP.bff as bff

    doc = bff.read_fps_json(str(path), [str(p) for p in pdb_paths], bool(validate))
    # The sections come back as JSON text. Parsed here so that a caller walks
    # a dict, which is what every one of them does with it.
    return tuple(
        _json.loads(section)
        if isinstance(section, str) and section
        else (section if section else {})
        for section in (doc.positions, doc.distances, doc.score_sets, doc.extra)
    )


def write_evaluators_json(path, evaluators) -> None:
    """Write an ``Evaluators`` section.

    Parameters
    ----------
    path : str
        Where to write.
    evaluators : str or object
        The section, as JSON text or as anything ``json.dumps`` accepts.
        Upstream takes text; taking either here keeps the plugin's callers,
        which hold lists of evaluator objects, from each doing the dump.
    """
    import json as _json

    import IMP.bff as bff

    if not isinstance(evaluators, str):
        evaluators = _json.dumps([e.to_dict() if hasattr(e, "to_dict") else e for e in evaluators])
    bff.write_evaluators_json(str(path), evaluators)


def load_structure_with_particles(path):
    """Read a PDB into a model and return its hierarchy, leaves and coordinates.

    Parameters
    ----------
    path : str
        The structure.

    Returns
    -------
    IMP.bff.LoadedStructure
        The hierarchy, its leaves and their ``(N, 3)`` coordinates.

    Raises
    ------
    ImportError
        On a build without the connection layer. Unlike everything else this
        module re-exports, this one hands back **IMP particles**, so it is
        wrapped only where IMP's own Python is there -- which is why it is
        resolved here and not imported at module scope: importing it eagerly
        made the whole plugin unimportable on the wheel.
    """
    import IMP.bff as bff

    if not hasattr(bff, "load_structure_with_particles"):
        raise ImportError(
            "load_structure_with_particles hands back IMP particles, and this "
            f"IMP.bff (build {getattr(bff, 'get_build', lambda: '?')()}) does "
            "not wrap them. Use load_structure for the coordinates."
        )
    return bff.load_structure_with_particles(str(path))


def read_evaluators_json(path: str | os.PathLike) -> list:
    """Read an ``Evaluators`` section and instantiate this plugin's classes.

    Parameters
    ----------
    path : str or os.PathLike
        An fps.json, or an evaluators file beside one.

    Returns
    -------
    list
        One evaluator object per entry.

    Notes
    -----
    Upstream reads the section and hands back **JSON text**: which classes an
    entry becomes is the application's question, and a C++ reader has no
    business knowing this plugin's class names. It used to take a factory;
    the text is the better seam, and the instantiation is here.
    """
    import json as _json

    from .. import evaluators as ev_pkg

    text = _read_evaluators_json(str(path))
    if not text:
        return []
    entries = _json.loads(text)
    if isinstance(entries, dict):
        # An object keyed by name, which is how an fps.json writes it; the
        # name belongs in the entry so the factory sees a complete record.
        entries = [dict(v, name=v.get("name", k)) for k, v in entries.items()]
    return [ev_pkg.from_dict(e) for e in entries]


def write_rmf(
    atoms: np.ndarray,
    path: str | os.PathLike,
    model_name: str = "structure",
    transform: np.ndarray | None = None,
    metadata: dict | None = None,
) -> None:
    """Write ``(N, 3)`` coordinates to a PMI-compatible RMF file.

    Needs an ``IMP.bff`` built with RMF; the pip wheel is not one.
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
