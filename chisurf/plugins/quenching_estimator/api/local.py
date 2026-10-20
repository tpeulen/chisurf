"""QuEst's facade: the verbs, resolved to a local or a remote backend.

>>> from quest import api
>>> project = api.template(with_fret=False)
>>> result = api.simulate(project, pdb_path="tests/148l.pdb")
>>> result.donor_counts.shape == result.time.shape
True

# One registry behind every surface

This was a **re-export shim** until 2026-07-28 (`LAY-04`): it forwarded names
from `quest.core` and had no notion of where a call runs, so the web backend
reached past it into `quest.core` directly and a host had no single thing to
drive. The verbs below go through a *client* -- `InProcessClient` by default,
a remote one when :func:`use_client` is given another -- so every surface
exercises the same registry, the same validation and the same error codes.

# The results are native, not JSON

`simulate` hands back a `DecaySimulationResult` with its numpy arrays intact.
Serialization happens at a **transport** (`quest.rpc.contract.to_payload`),
not in a handler, because `OBJ-02` made a fitting loop QuEst's primary consumer
and converting every decay channel to a Python list per iteration is a tax it
would pay forever.

The trade: payload shape depends on the transport. `tests/test_contract.py`
round-trips each method's native result through `to_payload` and validates it
against the manifest schema, so the two cannot drift quietly.

# The domain is still importable

The classes and functions re-exported below stay: a notebook that wants
`build_donor_from_project` should have it, and pretending otherwise would just
send people to `quest.core` again. The difference is that the *verbs* are now
the supported way in.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional, Tuple

import numpy as np

# Re-export the headless backend so downstream imports stay stable.
from chisurf.plugins.quenching_estimator.core import (
    DecaySimulationResult,
    build_donor_from_project,
    load_project,
    simulate_project,
    top_quenchers,
)
from chisurf.plugins.quenching_estimator.core.fps_json import (
    load_fps_json,
    normalize_to_fps_positions,
    run_fps_scan,
)
from chisurf.plugins.quenching_estimator.core.project import (
    ProjectValidationError,
    template_project,
    validate_project,
)
from chisurf.plugins.quenching_estimator.core.structure import (
    download_pdb_id,
    is_pdb_id,
    resolve_structure_path,
)

#: The client every verb goes through. Swapped by :func:`use_client`.
_CLIENT = None


def client():
    """The active client, creating the default in-process one on first use.

    Lazy because building it registers twelve handlers, and `import quest.api`
    happens in places that never make a call.
    """

    global _CLIENT
    if _CLIENT is None:
        from chisurf.plugins.quenching_estimator.rpc import local_client

        _CLIENT = local_client()
    return _CLIENT


def use_client(new_client) -> None:
    """Point the verbs at *new_client* -- a remote transport, or a test double.

    This is the local/remote resolution `LAY-04` asked for. The call sites do
    not change; only what is behind them does.
    """

    global _CLIENT
    _CLIENT = new_client


def describe() -> dict:
    """The contract: methods, schemas, error codes, serialization boundary."""

    return client().result("quest.contract.describe")


def template(*, with_fret: bool = True) -> MutableMapping[str, Any]:
    """A minimal valid project, ready to edit."""

    return client().result("quest.template", {"with_fret": bool(with_fret)})["project"]


def validate(project: Mapping[str, Any], *, pdb_path: Optional[str] = None) -> None:
    """Raise `RemoteError` if *project* is malformed.

    The failure carries `error_code == "invalid_project"`, so a caller can tell
    a bad document from a failed simulation without reading the message.
    """

    client().result(
        "quest.validate",
        {"project": dict(project), "pdb_path": None if pdb_path is None else str(pdb_path)},
    )


def simulate(
    project: Mapping[str, Any],
    *,
    pdb_path: Optional[Path | str] = None,
    nbins: Optional[int] = None,
    tac_range: tuple[float, float] = (0.0, 50.0),
    project_dir: Optional[Path | str] = None,
    save_outputs: bool = False,
):
    """Run one simulation. Returns the **native** result object."""

    return client().result(
        "quest.simulate",
        {
            "project": dict(project),
            "pdb_path": None if pdb_path is None else str(pdb_path),
            "nbins": nbins,
            "tac_range": tuple(tac_range),
            "project_dir": None if project_dir is None else str(project_dir),
            "save_outputs": bool(save_outputs),
        },
    )


def scan(
    project: Mapping[str, Any],
    positions: Mapping[str, Mapping[str, Any]],
    *,
    pdb_path: Optional[Path | str] = None,
    nbins: Optional[int] = None,
    tac_range: tuple[float, float] = (0.0, 50.0),
    project_dir: Optional[Path | str] = None,
) -> dict:
    """Simulate a set of labelling sites, one record each."""

    return client().result(
        "quest.scan",
        {
            "project": dict(project),
            "positions": dict(positions),
            "pdb_path": None if pdb_path is None else str(pdb_path),
            "nbins": nbins,
            "tac_range": tuple(tac_range),
            "project_dir": None if project_dir is None else str(project_dir),
        },
    )["results"]


def parameter_catalog(locale: Optional[str] = None) -> dict:
    """Parameter labels, units and help, optionally translated."""

    return client().result("quest.parameter_catalog", {"locale": locale})


def dyes() -> dict:
    """The dye presets."""

    return client().result("quest.dyes.list")


def structure_metadata(pdb_path: Path | str) -> dict:
    """Chains, residues and atoms of a structure file."""

    return client().result("quest.structure.metadata", {"pdb_path": str(pdb_path)})


def analysis_template() -> dict:
    """The declared analysis stages, fit presets and fit settings (``quest.analysis.template``)."""

    return client().result("quest.analysis.template")


def analyse(
    stages: Any = "all",
    *,
    data: Optional[Path | str] = None,
    structures: Optional[Mapping[str, Path | str]] = None,
    tables: Optional[Mapping[str, Path | str]] = None,
    cache_dir: Optional[Path | str] = None,
    preset: Optional[str] = None,
    fit_overrides: Optional[Mapping[str, Any]] = None,
    workers: Optional[int] = None,
    profile: bool = True,
    output: Optional[Path | str] = None,
    project_dir: Optional[Path | str] = None,
    save_outputs: bool = True,
    background: bool = False,
    continue_from: Optional[str] = None,
) -> dict:
    """Run stages of the quenching analysis (``quest.analysis.run``).

    Parameters
    ----------
    stages : str or list of str, optional
        ``"all"``, one stage (``"A"``, ``"B"``, ``"naive_h2o"``, ``"C"``, ``"summary"``) or a
        list; a stage also runs what it needs.
    data : str or pathlib.Path, optional
        Measurement folder; the shipped MalE data by default.
    structures : dict, optional
        ``{state: structure path}`` for the site tables.
    tables : dict, optional
        Stored site tables ``{"STATE:site:linker_length": npz path}``.
    cache_dir : str or pathlib.Path, optional
        Site-table cache folder.
    preset : str, optional
        ``"full"`` or ``"quick"``.
    fit_overrides : dict, optional
        Declared fit settings to replace (``{"n_starts": 4}``).
    workers : int, optional
        Worker processes (1 = in process).
    profile : bool, optional
        Compute the profile likelihoods.
    output : str or pathlib.Path, optional
        Results folder; the run directory ``<runs>/<job_id>`` by default.
    project_dir : str or pathlib.Path, optional
        Base of the run directories.
    save_outputs : bool, optional
        False writes nothing.
    background : bool, optional
        Return ``{"job_id", "status"}`` at once; follow it with :func:`job`,
        :func:`cancel_job` and :func:`analysis_result`.
    continue_from : str, optional
        A finished job whose solved graphs are reused.

    Returns
    -------
    dict
        ``job_id``, ``status``, ``run_id``, ``directory``, ``files`` and ``result``: the
        **native** :class:`~..core.inference.stages.AnalysisResult` in process (tables as
        record arrays), its JSON payload over a transport.
    """

    def _path(value):
        return None if value is None else str(value)

    params = {
        "stages": stages if isinstance(stages, str) else list(stages),
        "data": _path(data),
        "structures": None if not structures else {str(k): str(v) for k, v in structures.items()},
        "tables": None if not tables else {str(k): str(v) for k, v in tables.items()},
        "cache_dir": _path(cache_dir),
        "preset": preset,
        "fit_overrides": None if fit_overrides is None else dict(fit_overrides),
        "workers": workers,
        "profile": bool(profile),
        "output": _path(output),
        "project_dir": _path(project_dir),
        "save_outputs": bool(save_outputs),
        "background": bool(background),
        "continue_from": continue_from,
    }
    return client().result("quest.analysis.run", params)


def analysis_result(job_id: str, *, project_dir: Optional[Path | str] = None) -> dict:
    """The result of an analysis job, or of a stored analysis run (``quest.analysis.result``)."""

    return client().result(
        "quest.analysis.result",
        {"job_id": str(job_id), "project_dir": None if project_dir is None else str(project_dir)},
    )


def site_table(
    state: str,
    site: int,
    *,
    dye: Optional[str] = None,
    linker_length: Optional[float] = None,
    structure: Optional[Path | str] = None,
    chain: Optional[str] = None,
    cache_dir: Optional[Path | str] = None,
) -> dict:
    """Build or read one site table and return its summary (``quest.analysis.site_table``)."""

    return client().result(
        "quest.analysis.site_table",
        {
            "state": state,
            "site": int(site),
            "dye": dye,
            "linker_length": None if linker_length is None else float(linker_length),
            "structure": None if structure is None else str(structure),
            "chain": chain,
            "cache_dir": None if cache_dir is None else str(cache_dir),
        },
    )


def job(job_id: str) -> dict:
    """One operation's status and progress (``quest.jobs.get``)."""

    return client().result("quest.jobs.get", {"job_id": str(job_id)})


def cancel_job(job_id: str) -> bool:
    """Ask an operation to stop at its next checkpoint; whether the request was accepted."""

    return bool(client().result("quest.jobs.cancel", {"job_id": str(job_id)})["cancel_requested"])


__all__ = [
    # -- the verbs ------------------------------------------------------
    "client",
    "use_client",
    "describe",
    "template",
    "validate",
    "simulate",
    "scan",
    "parameter_catalog",
    "dyes",
    "structure_metadata",
    "analysis_template",
    "analyse",
    "analysis_result",
    "site_table",
    "job",
    "cancel_job",
    # -- the domain, still importable -----------------------------------
    "DecaySimulationResult",
    "load_project",
    "simulate_project",
    "build_donor_from_project",
    "top_quenchers",
    "ProjectValidationError",
    "template_project",
    "validate_project",
    "download_pdb_id",
    "is_pdb_id",
    "resolve_structure_path",
    "load_fps_json",
    "normalize_to_fps_positions",
    "run_fps_scan",
]
