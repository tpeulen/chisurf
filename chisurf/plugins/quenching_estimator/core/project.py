"""The QuEst project document: creation and validation.

A QuEst *project* is a plain JSON-serialisable mapping describing one
simulation — structure, labeling site, dye, linker geometry, quenching
chemistry and photon settings. It is the contract every surface shares (CLI,
Python API, web UI, Qt GUI), so the code that creates and checks one belongs in
the domain rather than in any single surface.

This module owns that logic. Surfaces translate :class:`ProjectValidationError`
into whatever their caller expects (a ``ClickException`` in the CLI, an HTTP 400
in the web backend, an ``{"ok": False}`` envelope over RPC).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional, Sequence

from chisurf.plugins.quenching_estimator.core.structure import resolve_structure_path

__all__ = [
    "DEFAULT_FORSTER_RADIUS",
    "ProjectValidationError",
    "REQUIRED_TOP_LEVEL_KEYS",
    "template_project",
    "validate_project",
]

#: Förster radius (Angstrom) written into a template project. **Every length in
#: a QuEst project is in Angstrom**, ``R0_matrix`` included — a value entered in
#: nanometres (~5.5) is ten times too small and makes FRET vanish silently,
#: because the transfer rate goes as ``(R0/r)**6``.
DEFAULT_FORSTER_RADIUS = 52.0

#: Isotropic dynamic average of the orientation factor. See
#: `quest.core.av.ISOTROPIC_KAPPA2` -- this is the assumption a published
#: Forster radius already carries, so it changes no number.
DEFAULT_KAPPA2 = 2.0 / 3.0


class ProjectValidationError(ValueError):
    """Raised when a project mapping is missing or contradicts a requirement."""


#: Keys a project must carry before it can be simulated.
REQUIRED_TOP_LEVEL_KEYS: tuple[str, ...] = (
    "tau0",
    "n_photons",
    "t_max",
    "t_step",
    "dg",
    "critical_distance",
    "av_parameter",
    "amino_acid_interactions",
)


def validate_project(
    project: Mapping[str, Any],
    project_path: Optional[Path | str] = None,
    pdb_path: Optional[Path | str] = None,
) -> None:
    """Check *project* and raise :class:`ProjectValidationError` if malformed.

    Parameters
    ----------
    project : mapping
        The project document to check.
    project_path : path, optional
        Where the project came from. Only used to decide whether a missing
        structure is fatal: a project loaded from a file may legitimately defer
        the structure to a caller-supplied override.
    pdb_path : path or str, optional
        Structure override taking precedence over ``project['pdb']``. May be a
        bare RCSB PDB ID.

    Raises
    ------
    ProjectValidationError
        If a required key is absent, the structure cannot be resolved, no donor
        dye with a diffusion coefficient is defined, or the time range is empty.
    """

    missing = [key for key in REQUIRED_TOP_LEVEL_KEYS if key not in project]
    if missing:
        raise ProjectValidationError(
            f"Project missing required keys: {', '.join(missing)}"
        )

    pdb = pdb_path or project.get("pdb")
    if pdb is None and project_path is None:
        raise ProjectValidationError(
            "Project must define 'pdb' path when no override is provided."
        )
    if pdb is not None:
        try:
            resolve_structure_path(pdb)
        except Exception as exc:
            raise ProjectValidationError(str(exc)) from exc

    fret_block = project.get("fret") or {}
    dyes: Sequence[Mapping[str, Any]] = fret_block.get("dyes") or []
    if not dyes:
        raise ProjectValidationError(
            "Project must define at least one dye in fret.dyes with a diffusion coefficient 'D'."
        )
    if dyes[0].get("D") is None:
        raise ProjectValidationError(
            "Donor dye entry must define diffusion coefficient 'D'."
        )

    # The orientation factor is an assumption the project *states*, so a value
    # outside [0, 4] is a malformed project rather than a runtime surprise --
    # kappa2 = 9 would silently multiply the transfer rate by 13.5.
    kappa2 = fret_block.get("kappa2")
    if kappa2 is not None:
        from chisurf.plugins.quenching_estimator.core.av import _kappa2_scale

        try:
            _kappa2_scale(kappa2)
        except ValueError as exc:
            raise ProjectValidationError(str(exc)) from exc

    t_start = project.get("t_start", 0.0)
    t_stop = project.get("t_max", None)
    if t_stop is None:
        raise ProjectValidationError("Project must define 't_max' (simulation duration).")
    if t_stop <= t_start:
        raise ProjectValidationError("Project 't_max' must be greater than 't_start'.")


def template_project(*, with_fret: bool = True) -> MutableMapping[str, Any]:
    """Return a minimal valid project, ready to be edited.

    Parameters
    ----------
    with_fret : bool
        Add an acceptor dye and an ``R0_matrix`` so the project simulates FRET
        alongside the donor decay.
    """

    from chisurf.plugins.quenching_estimator.core.av import av1_parameter, av_defaults
    from chisurf.plugins.quenching_estimator.core.dye_diffusion import default_amino_acid_interactions

    project: MutableMapping[str, Any] = {
        "tau0": 4.2,
        "n_photons": 500000,
        "t_max": 16000.0,
        "t_step": 0.032,
        # The placeholder AV is IMP.bff's declaration (grid and AV1 geometry),
        # not a dye: the template was 0.5 A and 21.5/0.5/3.5 before the owner's
        # 2026-10-11 "all use same defaults".
        "dg": av_defaults()["simulation_grid_resolution"],
        # Residue-type specific stickiness and PET quenching for a xanthene dye.
        "amino_acid_interactions": default_amino_acid_interactions(slow_factor=0.1),
        # Fallback dye-centre-to-quencher radius for residues that do not
        # define their own quench_radius.
        "critical_distance": 8.5,
        "av_parameter": av1_parameter(),
        "pdb": "structure.pdb",
        "n_bins": 4096,
        "parallel_trajectories": -1,
        "attachment": {"chain": "A", "residue": 1, "atom": "CB"},
        "save_avs": False,
        "slow_radius": 8.5,
        "output_file": "out",
    }

    dyes: list[MutableMapping[str, Any]] = [
        {
            "name": "donor",
            "D": 7.5,
            "slow_radius": project["slow_radius"],
            "amino_acid_interactions": project["amino_acid_interactions"],
            "attachment": {"chain": "A", "residue": 1, "atom": "CB"},
            "av_parameter": dict(project["av_parameter"]),
        }
    ]

    fret_block: MutableMapping[str, Any] = {"enabled": with_fret, "dyes": dyes}
    if with_fret:
        dyes.append(
            {
                "name": "acceptor",
                "D": 7.5,
                "attachment": {"chain": "A", "residue": 2, "atom": "CB"},
                "av_parameter": dict(project["av_parameter"]),
            }
        )
        # Förster radii in Angstrom, like every other length in a project.
        # 52 A is a typical donor-acceptor pair; calibrate it for the real one.
        fret_block["R0_matrix"] = [[None, DEFAULT_FORSTER_RADIUS], [DEFAULT_FORSTER_RADIUS, None]]
        # The orientation factor, stated rather than modelled. 2/3 is the
        # isotropic dynamic average, which is what a published R0 already
        # assumes -- so the default changes no number, and the point of having
        # it in the template is that the assumption is visible.
        fret_block["kappa2"] = DEFAULT_KAPPA2

    project["fret"] = fret_block
    return project
