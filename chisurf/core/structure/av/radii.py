"""The one atom-radius set an accessible volume's obstacles use.

IMP's radii -- the all-atom CHARMM radius ``IMP::atom::read_pdb`` gives an atom
by its residue and name -- times the single factor ``IMP.bff`` declares,
``AV_DEFAULT_RADIUS_SCALE`` (fitted to FPS's smaller Bondi radii). Owner,
2026-10-12: one radius set for accessible volumes everywhere, no second table.
``IMP.bff.imp_atom_radius`` carries IMP's mapping in the IMP-free build too,
so every AV door in ChiSurf reads it from here rather than from a table of its
own; ``test/core/test_av_single_radius_set.py`` fails if one reappears.
"""

from __future__ import annotations

import numpy as np


def radius_scale(value: float | None = None) -> float:
    """The factor on IMP's radii: ``value`` when given, else IMP.bff's default.

    Parameters
    ----------
    value : float, optional
        An explicit factor; ``None`` takes ``IMP.bff.AV_DEFAULT_RADIUS_SCALE``.

    Returns
    -------
    float
        The factor, positive.

    Raises
    ------
    ValueError
        For a factor that is not positive.
    """
    if value is None:
        import IMP.bff

        value = IMP.bff.AV_DEFAULT_RADIUS_SCALE
    value = float(value)
    if not value > 0.0:
        raise ValueError(f"radius_scale must be positive, got {value!r}")
    return value


def imp_radii(res_names, atom_names) -> np.ndarray:
    """IMP's radius for each atom, by residue and atom name (Angstrom, unscaled).

    Parameters
    ----------
    res_names, atom_names : sequence of str
        One residue name and one PDB atom name per atom.

    Returns
    -------
    numpy.ndarray
        ``IMP.bff.imp_atom_radius`` per atom; IMP's 1.7 A default for an atom
        whose type IMP does not know (ligands, waters).
    """
    import IMP.bff

    cache: dict = {}
    out = np.empty(len(res_names), dtype=np.float64)
    for index, (res, name) in enumerate(zip(res_names, atom_names)):
        key = (str(res).strip().upper(), str(name).strip().upper())
        radius = cache.get(key)
        if radius is None:
            radius = cache[key] = float(IMP.bff.imp_atom_radius(*key))
        out[index] = radius
    return out


def obstacle_radii(res_names, atom_names, scale: float | None = None) -> np.ndarray:
    """The obstacle radius of each atom: IMP's radius times the scale.

    Parameters
    ----------
    res_names, atom_names : sequence of str
        One residue name and one PDB atom name per atom.
    scale : float, optional
        The factor on IMP's radii; ``None`` takes ``AV_DEFAULT_RADIUS_SCALE``.

    Returns
    -------
    numpy.ndarray
        Radii in Angstrom.
    """
    return imp_radii(res_names, atom_names) * radius_scale(scale)


def obstacle_xyzr(pdb_path: str, scale: float | None = None) -> np.ndarray:
    """A PDB's atoms as the ``(N, 4)`` x, y, z, radius array the AV solver takes.

    Every ATOM/HETATM record, in file order, its radius IMP's times the scale:
    ``IMP.bff.load_structure_with_vdw``, cached inside the library on the file's
    path, modification time and size.

    Parameters
    ----------
    pdb_path : str
        The structure.
    scale : float, optional
        The factor on IMP's radii; ``None`` takes ``AV_DEFAULT_RADIUS_SCALE``.

    Returns
    -------
    numpy.ndarray
        ``(N, 4)`` float64.
    """
    import IMP.bff

    xyzr = IMP.bff.load_structure_with_vdw(str(pdb_path), radius_scale(scale))
    return np.ascontiguousarray(np.asarray(xyzr, dtype=np.float64).reshape(-1, 4))
