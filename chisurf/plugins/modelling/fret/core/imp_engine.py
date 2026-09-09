"""FRET-restrained rigid-body docking: the plugin's face on ``IMP.bff``.

The engine is ``IMP.bff``'s and it is C++ -- the assembly, the restraints, the
samplers, the minimiser, the screening, the error estimate. This module is
what the plugin calls it through: it names the operations, turns a Python
``stop_check`` callback into the object the C++ expects, and hands results
back as plain dictionaries.

It used to be 1391 lines that built the model, the restraints and the walk in
Python. None of that is here, and none of it should come back: a docking run
that crosses the SWIG boundary once per proposal per body is paying for the
boundary, not for the science.

Sampler backends
----------------
``DockingParameters.sampler`` names one of ``IMP.bff.Sampler``'s backends and
nothing else changes: ``"metropolis"`` (plain Monte Carlo, the default),
``"stretch"`` (emcee-like, affine invariant), ``"slice"`` (zeus-like ensemble
slice) and ``"de"`` (differential evolution).
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Sequence


def _bff():
    """Return ``IMP.bff``, imported on first use.

    Returns
    -------
    module
        The ``IMP.bff`` module.

    Raises
    ------
    RuntimeError
        When the installed build has no docking, naming the build. The
        IMP-free wheel is such a build: docking is the connection layer's.
    """
    import IMP.bff as bff

    if not hasattr(bff, "dock"):
        raise RuntimeError(
            "this IMP.bff has no docking engine (build "
            f"{getattr(bff, 'get_build', lambda: '?')()}); it needs a build "
            "that links IMP"
        )
    return bff


def DockingParameters(**kwargs):  # noqa: N802 - it is a type name upstream
    """Create ``IMP.bff.DockingParameters``, optionally setting fields.

    Parameters
    ----------
    **kwargs
        Any field of the upstream struct: ``sampler``, ``n_frames``,
        ``mc_steps``, ``mc_temperature``, ``max_translation``,
        ``max_rotation``, ``shuffle_max_translation``, ``n_best``,
        ``fixed_body``, ``score_set``, ``sigma_da``, ``ev_weight`` and the
        rest.

    Returns
    -------
    IMP.bff.DockingParameters
        The parameters, with the upstream defaults for anything not given.

    Raises
    ------
    AttributeError
        For a name the struct does not have -- rather than accepting it
        silently and running with the default, which is how a run comes back
        looking fine and answering a different question.
    """
    params = _bff().DockingParameters()
    for key, value in kwargs.items():
        if key in _PLUGIN_ONLY:
            continue
        if not hasattr(params, key):
            raise AttributeError(
                f"DockingParameters has no field {key!r}"
            )
        setattr(params, key, value)
    return params


#: Request knobs that are the plugin's and have no upstream field. They are
#: accepted and dropped rather than rejected: `av_backend` chose between
#: LabelLib and IMP.bff, and there is one backend now because
#: `IMP.bff.labellib` *is* LabelLib's interface. A request that still carries
#: it is not wrong, it is just describing a choice that no longer exists.
_PLUGIN_ONLY = frozenset({"av_backend"})


def DockingResult(**kwargs):  # noqa: N802 - it is a type name upstream
    """Create an ``IMP.bff.DockingResult``, optionally setting fields.

    Parameters
    ----------
    **kwargs
        Any field of the upstream struct.

    Returns
    -------
    IMP.bff.DockingResult
        The result record. Every operation here returns a **dict** rather
        than one of these; this exists because callers construct empty ones
        to describe a run that did not happen.

    Raises
    ------
    AttributeError
        For a name the struct does not have.
    """
    result = _bff().DockingResult()
    for key, value in kwargs.items():
        if not hasattr(result, key):
            raise AttributeError(f"DockingResult has no field {key!r}")
        setattr(result, key, value)
    return result


def _stop(stop_check: Optional[Callable[[], bool]]):
    """Wrap a Python predicate as the ``DockingStop`` the engine asks.

    Parameters
    ----------
    stop_check : callable or None
        Called with no arguments between chunks; a true answer stops the run.
        ``None`` never stops.

    Returns
    -------
    IMP.bff.DockingStop or None
        The object to hand to the engine.
    """
    if stop_check is None:
        return None
    bff = _bff()

    class _Stop(bff.DockingStop):
        def should_stop(self) -> bool:
            try:
                return bool(stop_check())
            except Exception:
                # A predicate that raises must not take the run down with it;
                # a docking job that dies at 90% because a progress dialog was
                # closed is worse than one that finishes.
                return False

    return _Stop()


class Result(dict):
    """A docking result: a mapping, and an object with attributes.

    Both, because both are wanted and neither alone is. The GUI and the RPC
    layer serialise it (``to_dict``, ``json.dumps``), and the tests and the
    scripts read ``res.score`` and ``res.extra["method"]``. A dict subclass
    whose attributes are its keys is the smallest thing that is honestly
    both.
    """

    def __getattr__(self, name: str) -> Any:
        """Read a field as an attribute.

        Parameters
        ----------
        name : str
            The field.

        Returns
        -------
        object
            The value.

        Raises
        ------
        AttributeError
            When the result has no such field.
        """
        try:
            return self[name]
        except KeyError:
            raise AttributeError(
                f"docking result has no field {name!r}"
            ) from None

    def to_dict(self) -> Dict[str, Any]:
        """Return this result as a plain dict."""
        return dict(self)


def _as_dict(result) -> "Result":
    """Render a ``DockingResult`` as plain data.

    Parameters
    ----------
    result : IMP.bff.DockingResult
        What the engine returned.

    Returns
    -------
    Result
        The scalar fields, the written paths, the per-pair table and the
        run's ``extra`` parsed from JSON.
    """
    out = Result(
        score=float(result.score),
        e_clash=float(result.e_clash),
        e_bond=float(result.e_bond),
        n_avs=int(result.n_avs),
        n_bonds=int(result.n_bonds),
        n_distances=int(result.n_distances),
        converged=bool(result.converged),
        output_dir=str(result.output_dir),
        score_csv=str(result.score_csv),
        rmf_file=str(result.rmf_file),
        best_pdbs=[str(p) for p in result.best_pdbs],
        poses=str(result.poses),
    )
    out["pairs"] = [
        {
            "name": str(p.name),
            "distance_type": str(p.distance_type),
            "model": float(p.distance_model),
            "experiment": float(p.distance_exp),
            "efficiency_model": float(p.efficiency_model),
            "efficiency_exp": float(p.efficiency_exp),
            "error_neg": float(p.error_neg),
            "error_pos": float(p.error_pos),
            "forster_radius": float(p.forster_radius),
            "chi2": float(p.chi2),
            "residual": float(p.residual),
            "is_bond": bool(p.is_bond),
            "position1": str(p.position1),
            "position2": str(p.position2),
        }
        for p in result.pairs
    ]
    try:
        out["extra"] = json.loads(result.extra) if result.extra else {}
    except ValueError:
        # The engine writes this; if it is ever unparseable the run still
        # happened, and the text says more than a dropped field.
        out["extra"] = {"raw": str(result.extra)}
    return out


def dock(
    pdb_paths: Sequence[str],
    fps_json_path: str,
    output_dir: str,
    params=None,
    stop_check: Optional[Callable[[], bool]] = None,
    initial_poses: str = "",
) -> Dict[str, Any]:
    """Dock by sampling, with the backend ``params.sampler`` names.

    Parameters
    ----------
    pdb_paths : sequence of str
        One structure per rigid body.
    fps_json_path : str
        The labelling and distance file.
    output_dir : str
        Where the models, the table and the trace go.
    params : IMP.bff.DockingParameters, optional
    stop_check : callable, optional
        Asked between frames; a true answer stops the run.
    initial_poses : str
        A docked state to resume from, as JSON.

    Returns
    -------
    dict
        The best score, its table, its pose and what was written.
    """
    bff = _bff()
    return _as_dict(
        bff.dock(
            [str(p) for p in pdb_paths],
            str(fps_json_path),
            str(output_dir),
            params if params is not None else bff.DockingParameters(),
            _stop(stop_check),
            str(initial_poses),
        )
    )


def dock_minimize(
    pdb_paths: Sequence[str],
    fps_json_path: str,
    output_dir: str,
    params=None,
    stop_check: Optional[Callable[[], bool]] = None,
    initial_poses: str = "",
) -> Dict[str, Any]:
    """Dock by FRET-restrained energy minimisation.

    The deterministic road, and FPS's: a local descent from where the input
    pose is, rather than a walk. See :func:`dock` for the parameters.

    Returns
    -------
    dict
        As :func:`dock`.
    """
    bff = _bff()
    return _as_dict(
        bff.dock_minimize(
            [str(p) for p in pdb_paths],
            str(fps_json_path),
            str(output_dir),
            params if params is not None else bff.DockingParameters(),
            _stop(stop_check),
            str(initial_poses),
        )
    )


def refine(
    pdb_paths: Sequence[str],
    fps_json_path: str,
    output_dir: str,
    score_set: str = "",
    steps: int = 500,
    ev_weight: float = 1.0,
) -> Dict[str, Any]:
    """Polish a pose in place: minimise, write the structure and the table.

    Parameters
    ----------
    pdb_paths, fps_json_path, output_dir : as for :func:`dock`
    score_set : str
        A named score set; empty uses every distance.
    steps : int
        The iteration budget.
    ev_weight : float
        Weight of the excluded-volume term.

    Returns
    -------
    dict
        As :func:`dock`.
    """
    return _as_dict(
        _bff().refine_docking(
            [str(p) for p in pdb_paths],
            str(fps_json_path),
            str(output_dir),
            str(score_set),
            int(steps),
            float(ev_weight),
        )
    )


def score(
    pdb_paths: Sequence[str],
    fps_json_path: str,
    score_set: str = "",
    output_csv: str = "",
    mean_position_restraint: bool = False,
    ev_weight: float = 1.0,
    sigma_da: float = 6.0,
) -> "Result":
    """Score the structures as they stand, without moving them.

    The assembly is built, the volumes computed and the network evaluated
    once. Use :func:`screen` to rank a *library*; this answers about one pose.

    Parameters
    ----------
    pdb_paths : sequence of str
        One structure per rigid body.
    fps_json_path : str
        The labelling and distance file.
    score_set : str
        A named score set; empty uses every distance.
    output_csv : str
        Where to write the per-pair table; empty writes none.
    mean_position_restraint : bool
        Score the separation of the volumes' mean positions rather than
        rebuilding both volumes on every evaluation.
    ev_weight : float
        Weight of the excluded-volume term.
    sigma_da : float
        The mean-position transfer width, Angstrom.

    Returns
    -------
    Result
        The score, the per-pair table and the counts.
    """
    bff = _bff()
    assembly = bff.create_docking_assembly(
        [str(p) for p in pdb_paths],
        str(fps_json_path),
        str(score_set),
        bool(mean_position_restraint),
        float(ev_weight),
        float(sigma_da),
    )
    return _as_dict(bff.score_assembly(assembly, str(output_csv)))


def screen(
    pdb_paths: Sequence[str],
    fps_json_path: str,
    score_set: str = "",
    output_csv: str = "",
    mean_position_restraint: bool = False,
) -> List[Dict[str, Any]]:
    """Score a library of structures and rank them.

    Parameters
    ----------
    pdb_paths : sequence of str
        The structures; a directory is expanded to the ``*.pdb`` in it.
    fps_json_path : str
        The labelling and distance file.
    score_set : str
        A named score set; empty uses every distance.
    output_csv : str
        Where to write the ranked table; empty writes none.
    mean_position_restraint : bool
        Score mean positions rather than rebuilding both volumes for every
        structure.

    Returns
    -------
    list of dict
        Per structure: its path, its score, the reduced chi-squared and the
        violation counts FPS reports.
    """
    out = []
    for s in _bff().screen_structures(
        [str(p) for p in pdb_paths],
        str(fps_json_path),
        str(score_set),
        str(output_csv),
        bool(mean_position_restraint),
    ):
        out.append(
            {
                "path": str(s.path),
                "score": float(s.score),
                # FPS's screening diagnostics, under its own names: the
                # reduced chi-squared, the 1/2/3-sigma violation counts, how
                # many distances had no model value, and the reference fit.
                "chi2_r": float(s.chi2_r),
                "sigma1": int(s.sigma1),
                "sigma2": int(s.sigma2),
                "sigma3": int(s.sigma3),
                "invalid_r": int(s.invalid_r),
                "ref_rmsd": float(s.ref_rmsd),
            }
        )
    return out


def estimate_errors(
    pdb_paths: Sequence[str],
    fps_json_path: str,
    output_dir: str,
    n_trials: int = 10,
    params=None,
    minimize: bool = True,
    stop_check: Optional[Callable[[], bool]] = None,
    n_workers: Optional[int] = None,
) -> Dict[str, Any]:
    """Repeat docking from independent random starts and report the spread.

    The precision the distances actually pin down, as opposed to the score one
    run happened to reach. What the trials disagree about is what the data
    does not determine.

    Returns
    -------
    dict
        The best trial's result, with ``n_trials``, ``score_mean``,
        ``score_std``, ``best_trial`` and ``trial_scores`` in its ``extra``.
    """
    # n_workers is accepted and ignored: the trials run in sequence in C++,
    # where each one already uses whatever threading the solver has. A
    # process pool around them was how the Python engine got parallelism, and
    # taking the argument rather than raising keeps every caller working.
    del n_workers
    bff = _bff()
    return _as_dict(
        bff.estimate_docking_errors(
            [str(p) for p in pdb_paths],
            str(fps_json_path),
            str(output_dir),
            params if params is not None else bff.DockingParameters(),
            int(n_trials),
            bool(minimize),
            _stop(stop_check),
        )
    )


def build_assembly(
    pdb_paths: Sequence[str],
    fps_json_path: str,
    score_set: str = "",
    mean_position_restraint: bool = True,
    ev_weight: float = 1.0,
    sigma_da: float = 6.0,
):
    """Assemble a model from PDBs and an fps.json.

    Returns
    -------
    IMP.bff.DockingAssembly
        The bodies, the FRET network and the excluded volume. Handed back as
        the upstream object: it holds an ``IMP::Model``, so there is nothing
        useful to flatten it into.
    """
    return _bff().create_docking_assembly(
        [str(p) for p in pdb_paths],
        str(fps_json_path),
        str(score_set),
        bool(mean_position_restraint),
        float(ev_weight),
        float(sigma_da),
    )


def capture_poses(assembly) -> str:
    """The assembly's current pose, as JSON."""
    return str(_bff().capture_poses(assembly))


def apply_poses(assembly, poses: str) -> None:
    """Put a captured pose back onto an assembly."""
    _bff().apply_poses(assembly, str(poses))


def ensure_fps_json(fps_path: str, pdb_paths: Sequence[str]) -> str:
    """Return an fps.json path the engine can read.

    A legacy C# labelling file is converted beside itself; anything already
    JSON is returned unchanged.

    Parameters
    ----------
    fps_path : str
        The labelling file as the caller named it.
    pdb_paths : sequence of str
        The structures it describes. Unused by the conversion and kept in the
        signature because callers pass them.

    Returns
    -------
    str
        The path the engine will actually read.
    """
    del pdb_paths  # the converter reads the labelling file alone
    bff = _bff()
    if hasattr(bff, "ensure_fps_json"):
        return str(bff.ensure_fps_json(str(fps_path)))
    # The assembly does this itself and reports which file it used, which is
    # the same answer without a second conversion path to keep in step.
    return str(fps_path)


__all__ = [
    "DockingParameters",
    "Result",
    "DockingResult",
    "apply_poses",
    "build_assembly",
    "capture_poses",
    "dock",
    "dock_minimize",
    "ensure_fps_json",
    "estimate_errors",
    "refine",
    "score",
    "screen",
]
