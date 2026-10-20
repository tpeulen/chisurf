"""QuEst's RPC surface: the operations every front end shares.

Each handler takes plain data, calls the domain, and returns the envelope
described in :mod:`quest.rpc.dispatcher`. Nothing here computes anything —
if a handler grows logic, that logic belongs in the domain where the CLI and
notebooks can reach it too.

Registering with a host application's dispatcher is the whole point of the
split: :func:`register_services` only needs an object with
``register(name, handler)``, so ChiSurf (or any other host) can expose QuEst
without QuEst importing the host.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from chisurf.plugins.quenching_estimator import settings
from chisurf.plugins.quenching_estimator.core import runs
from chisurf.plugins.quenching_estimator.rpc.contract import (
    register_payload_converter,
    service_error,
    to_payload,
)
from chisurf.plugins.quenching_estimator.rpc.dispatcher import (
    InProcessClient,
    ServiceDispatcher,
    fail,
    ok,
)

__all__ = [
    "register_services",
    "local_client",
    "METHODS",
    "result_payload",
    "simulation_payload",
    "analysis_payload",
]

#: Method names in registration order, with a one-line summary each. This is
#: the table a manifest declares and a host advertises.
METHODS: dict[str, str] = {
    "quest.template": "Return a minimal valid project, optionally with FRET.",
    "quest.validate": "Check a project and report why it is malformed.",
    "quest.simulate": "Run one simulation and return the decay and derived metrics.",
    "quest.scan": "Simulate a set of labeling sites and return one record each.",
    "quest.parameter_catalog": "Return the parameter catalog (labels, units, help), optionally translated.",
    "quest.locales": "List the languages QuEst's labels and help text are available in.",
    "quest.dyes.list": "Return the dye presets.",
    "quest.dyes.save": "Add or replace a dye preset.",
    "quest.quenching_defaults": "Return the residue-type PET chemistry defaults.",
    "quest.structure.metadata": "Return the chains, residues and atoms of a structure file.",
    "quest.runs.list": "Return run-artefact summaries, newest first.",
    "quest.runs.get": "Return a finished run's result.",
    "quest.jobs.list": "Return the running and recent operations.",
    "quest.jobs.get": "Return one operation's status and progress.",
    "quest.jobs.cancel": "Ask a running operation to stop at its next checkpoint.",
    "quest.analysis.template": "Return the declared analysis stages, fit presets and fit settings.",
    "quest.analysis.run": "Run stages of the quenching analysis (inverse fit), blocking or as a background job.",
    "quest.analysis.result": "Return the result of an analysis job or of a stored analysis run.",
    "quest.analysis.site_table": "Build or read one site table and return its summary.",
    "quest.contract.describe": "Return the contract: methods, schemas, error codes and where serialization happens.",
}


def simulation_payload(result: Any) -> dict[str, Any]:
    """Convert a :class:`~quest.core.DecaySimulationResult` to plain data.

    Arrays become lists and absent channels stay ``None``. This is the boundary
    shape: whatever crosses to a browser, a host application or a file goes
    through here, so there is one definition of what a simulation result *is*.

    **Called by a transport, not by a handler.** It ran inside
    `simulate_handler` until 2026-07-28, so an in-process caller paid a
    numpy->list conversion of every decay channel whether it wanted one or not
    -- including the fitting loop `OBJ-02` chose as QuEst's primary consumer,
    which calls `simulate` thousands of times. See
    `quest.rpc.contract`.
    """

    def _list(value: Any) -> Any:
        return None if value is None else value.tolist()

    return {
        "job_id": result.job_id,
        "time_ns": result.time.tolist(),
        "donor_counts": result.donor_counts.tolist(),
        "fret_counts": _list(result.fret_counts),
        "quantum_yield_donor": result.quantum_yield_donor,
        "lifetime_donor": getattr(result, "lifetime_donor", 0.0),
        "quantum_yield_fret": result.quantum_yield_fret,
        "collisions_fraction": result.collisions_fraction,
        "fret_efficiency": result.fret_efficiency,
        "project": result.project,
        "trajectory_distance_to_mean": _list(result.trajectory_distance_to_mean),
        "trajectory_time_ns": _list(result.trajectory_time_ns),
        "trajectory_autocorr": _list(result.trajectory_autocorr),
        "trajectory_autocorr_lag_ns": _list(result.trajectory_autocorr_lag_ns),
        "trajectory_points": _list(result.trajectory_points),
        "av_points": _list(result.av_points),
        "acv_points": _list(result.acv_points),
        "av_volume": result.av_volume,
        "contact_volume": result.contact_volume,
        "contact_to_free_ratio": result.contact_to_free_ratio,
        "aa_residence": getattr(result, "aa_residence", []),
    }


register_payload_converter("DecaySimulationResult", simulation_payload)

#: Retained under its old name for callers that import it directly.
result_payload = simulation_payload


def _finite(value: Any) -> Any:
    """*value* with non-finite floats as None (JSON has no NaN)."""
    import math

    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_finite(item) for item in value]
    return value


def analysis_payload(result: Any) -> dict[str, Any]:
    """Convert an :class:`~..core.inference.stages.AnalysisResult` to plain data.

    ``AnalysisResult.to_dict()`` (per stage ``title``, ``numbers``, ``text`` and the declared
    ``tables`` as row lists; per graph its size) plus each stage's ``plots`` (the plot data a
    GUI draws). Called by a transport, like :func:`simulation_payload`.
    """

    out = result.to_dict()
    for name, stage in result.stages.items():
        out["stages"][name]["plots"] = to_payload(stage.plots)
    return _finite(to_payload(out))


register_payload_converter("AnalysisResult", analysis_payload)


def template_handler(with_fret: bool = True) -> dict[str, Any]:
    from chisurf.plugins.quenching_estimator.core.project import template_project

    return ok({"project": template_project(with_fret=bool(with_fret))})


def validate_handler(
    project: Mapping[str, Any],
    pdb_path: Optional[str] = None,
) -> dict[str, Any]:
    from chisurf.plugins.quenching_estimator.core.project import (
        ProjectValidationError,
        validate_project,
    )

    try:
        validate_project(project, pdb_path=pdb_path)
    except ProjectValidationError as exc:
        return service_error(str(exc), "invalid_project", type(exc).__name__)
    return ok({"valid": True, "project": dict(project)})


def simulate_handler(
    project: Mapping[str, Any],
    pdb_path: Optional[str] = None,
    nbins: Optional[int] = None,
    tac_range: Any = (0.0, 50.0),
    project_dir: Optional[str] = None,
    # Opt-in since 2026-07-28, matching `simulate_project`. An RPC caller is a
    # host or a notebook; it has to ask for a run directory.
    save_outputs: bool = False,
) -> dict[str, Any]:
    from chisurf.plugins.quenching_estimator.api import local as api
    from chisurf.plugins.quenching_estimator.core.project import (
        ProjectValidationError,
        validate_project,
    )

    try:
        validate_project(project, pdb_path=pdb_path)
    except ProjectValidationError as exc:
        return service_error(str(exc), "invalid_project", type(exc).__name__)

    start, stop = tac_range
    try:
        result = api.simulate_project(
            project,
            pdb_path=pdb_path,
            nbins=nbins,
            tac_range=(float(start), float(stop)),
            project_dir=Path(project_dir) if project_dir else None,
            save_outputs=bool(save_outputs),
        )
    except Exception as exc:
        from chisurf.plugins.quenching_estimator.rpc.contract import error_code_for

        return service_error(f"Simulation failed: {exc}", error_code_for(exc), type(exc).__name__)
    # The **native** result. A transport calls `contract.to_payload`.
    return ok(result)


def scan_handler(
    project: Mapping[str, Any],
    positions: Mapping[str, Mapping[str, Any]],
    pdb_path: Optional[str] = None,
    nbins: Optional[int] = None,
    tac_range: Any = (0.0, 50.0),
    project_dir: Optional[str] = None,
) -> dict[str, Any]:
    """Simulate every position and return the records.

    Blocking, but **observable and cancelable**: it registers a job with
    :mod:`quest.tasks`, reports progress per site, and stops at the next site
    boundary when `quest.jobs.cancel` is called on the returned ``job_id``. That
    is one mechanism rather than the three ``LAY-07`` recorded.

    A cancelled scan returns the sites it *did* complete rather than failing:
    the caller asked to stop, and partial results are the point of stopping.
    """

    from chisurf.plugins.quenching_estimator.core.scan import scan_positions
    from chisurf.plugins.quenching_estimator.core.tasks import default_manager

    manager = default_manager()
    job = manager.create("quest.scan", {"n_positions": len(positions)})
    manager.start(job.job_id)

    start, stop = tac_range
    try:
        records = list(
            scan_positions(
                project,
                positions,
                pdb_path=pdb_path,
                nbins=nbins,
                tac_range=(float(start), float(stop)),
                project_dir=Path(project_dir) if project_dir else None,
                should_cancel=manager.canceller(job.job_id),
                report_progress=manager.reporter(job.job_id),
            )
        )
    except Exception as exc:
        from chisurf.plugins.quenching_estimator.rpc.contract import error_code_for

        manager.fail(job.job_id, str(exc), error_code_for(exc))
        return service_error(str(exc), error_code_for(exc), type(exc).__name__)

    manager.finish(job.job_id)
    final = manager.get(job.job_id)
    return ok(
        {
            "job_id": job.job_id,
            "cancelled": final is not None and final.status.value == "cancelled",
            "results": {record["name"]: record for record in records},
        }
    )


def locales_handler(locale: str | None = None) -> dict[str, Any]:
    """Which languages exist, which one was resolved, and its UI strings.

    One call, because a client that has the list still needs the strings, and a
    second round trip to get them is a round trip for nothing.
    """
    from chisurf.plugins.quenching_estimator.core import i18n

    resolved = i18n.resolve_locale(locale) if locale else i18n.DEFAULT_LOCALE
    return ok(
        {
            "available": i18n.available_locales(),
            "locale": resolved,
            "default": i18n.DEFAULT_LOCALE,
            "strings": i18n.ui_strings(resolved),
        }
    )


def parameter_catalog_handler(locale: str | None = None) -> dict[str, Any]:
    """The catalog, translated when a known locale is asked for.

    Callers that pass nothing get English rather than the server's system
    language: a shared backend must not answer differently depending on how the
    machine it runs on is configured.
    """
    from chisurf.plugins.quenching_estimator.core import i18n

    try:
        return ok(i18n.translate_catalog(locale or i18n.DEFAULT_LOCALE))
    except FileNotFoundError as exc:
        return fail(str(exc))


def dyes_list_handler() -> dict[str, Any]:
    try:
        return ok(settings.dye_repository())
    except FileNotFoundError as exc:
        return fail(str(exc))


def dyes_save_handler(dye: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return ok(settings.save_dye(dye))
    except (ValueError, OSError) as exc:
        return fail(str(exc))


def quenching_defaults_handler() -> dict[str, Any]:
    return ok(settings.quenching_defaults())


def structure_metadata_handler(pdb_path: str) -> dict[str, Any]:
    from chisurf.plugins.quenching_estimator.core.structure import (
        resolve_structure_path,
        structure_metadata,
    )

    try:
        resolved = resolve_structure_path(pdb_path)
    except Exception as exc:
        return fail(str(exc))
    try:
        metadata = structure_metadata(resolved)
    except Exception as exc:
        return fail(f"Failed to parse structure: {exc}")
    if metadata["atom_count"] == 0:
        return fail("No ATOM/HETATM records found in the structure.")
    return ok(metadata)


def runs_list_handler(
    project_dir: Optional[str] = None,
    limit: int = runs.DEFAULT_RUN_LIST_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    return ok(runs.list_runs(project_dir, limit=limit, offset=offset))


def runs_get_handler(job_id: str, project_dir: Optional[str] = None) -> dict[str, Any]:
    try:
        return ok(runs.read_run(job_id, project_dir))
    except (ValueError, FileNotFoundError) as exc:
        return fail(str(exc))


def jobs_list_handler() -> dict[str, Any]:
    """Running and recent operations -- **not** run artefacts.

    `quest.runs.list` is the directories on disk. Those were both called "jobs"
    until 2026-07-28, so a host asking for its running tasks got directories.
    """
    from chisurf.plugins.quenching_estimator.core.tasks import default_manager

    return ok({"jobs": default_manager().list()})


def jobs_get_handler(job_id: str) -> dict[str, Any]:
    from chisurf.plugins.quenching_estimator.core.tasks import default_manager

    job = default_manager().get(job_id)
    if job is None:
        return service_error(f"No such job: {job_id}", "operation_failed")
    return ok(job.to_dict())


def jobs_cancel_handler(job_id: str) -> dict[str, Any]:
    """Ask a job to stop.

    Cooperative: this sets a flag and returns. A running job moves to
    `cancelling` and stays there until its worker reaches a checkpoint -- for a
    scan, the boundary between two sites; for a single simulation, effectively
    the end, since `simulate_traj` computes a whole trajectory inside one
    compiled IMP.bff call, and compiled code cannot poll a Python flag.
    """
    from chisurf.plugins.quenching_estimator.core.tasks import default_manager

    accepted = default_manager().cancel(job_id)
    return ok({"job_id": job_id, "cancel_requested": accepted})


def contract_describe_handler() -> dict[str, Any]:
    """What QuEst offers, in a form a host can read without importing QuEst.

    Built from `quest/manifest.json`, so it cannot drift from the declaration a
    host already reads.
    """
    from chisurf.plugins.quenching_estimator.rpc.contract import contract_descriptor

    return ok(contract_descriptor())


# -- the quenching analysis ---------------------------------------------------------------


def _analysis_problem(stages: Any, preset: Optional[str], fit_overrides: Any,
                      data: Optional[str]) -> Optional[str]:
    """Why these analysis inputs cannot run, or None. Checked before any work starts."""
    from chisurf.plugins.quenching_estimator.core.inference import graph_fit
    from chisurf.plugins.quenching_estimator.core.inference import stages as st

    names = st.stage_names()
    asked = names if stages in (None, "all") else ([stages] if isinstance(stages, str) else list(stages))
    unknown = [name for name in asked if name not in names]
    if unknown:
        return f"Unknown stage(s) {unknown}; declared: {names}."
    if preset is not None and preset not in graph_fit.preset_names():
        return f"Unknown fit preset {preset!r}; declared: {graph_fit.preset_names()}."
    if fit_overrides is not None and not isinstance(fit_overrides, Mapping):
        return "fit_overrides must be an object of declared fit settings."
    declared = graph_fit.settings()
    undeclared = sorted(set(fit_overrides or {}) - set(declared))
    if undeclared:
        return f"Undeclared fit setting(s) {undeclared}."
    if data is not None and not Path(data).is_dir():
        return f"Measurement folder not found: {data}"
    return None


def analysis_template_handler() -> dict[str, Any]:
    """What a caller can ask ``quest.analysis.run`` for, all from the declarations."""
    from chisurf.plugins.quenching_estimator.core.inference import (
        columns,
        graph_fit,
        measurements,
    )
    from chisurf.plugins.quenching_estimator.core.inference import (
        stages as st,
    )

    declaration = st.stage_settings()
    full = graph_fit.settings()
    presets = {name: {k: v for k, v in graph_fit.settings(name).items() if full.get(k) != v}
               for name in graph_fit.preset_names()}
    return ok(
        {
            "stages": [
                {"name": name, "title": declaration["stages"][name]["title"],
                 "kind": declaration["stages"][name]["kind"],
                 "graph": declaration["stages"][name].get("graph")}
                for name in declaration["order"]
            ],
            "order": list(declaration["order"]),
            "graphs": {name: {"description": g.get("description", ""),
                              "blocks": [b["label"] for b in g["blocks"]]}
                       for name, g in declaration["graphs"].items()},
            "presets": presets,
            "fit_settings": full,
            "data": str(measurements.EXAMPLE_FOLDER),
            "result_tables": sorted(
                name for name, spec in columns.declaration(graph_fit.RESULT_COLUMNS).items()
                if isinstance(spec, dict) and "columns" in spec),
            "defaults": {"stages": "all", "preset": None, "profile": True, "workers": None,
                         "save_outputs": True, "background": False},
        }
    )


def _job_entry(manager, job_id: Optional[str]):
    """The finished-job record (``runs.analyse``'s return) of *job_id*, or None."""
    job = manager.get(job_id) if job_id else None
    if job is None or job.status.value != "completed" or not isinstance(job.result, dict):
        return None
    return job.result


def analysis_run_handler(
    stages: Any = "all",
    data: Optional[str] = None,
    structures: Optional[Mapping[str, str]] = None,
    tables: Optional[Mapping[str, str]] = None,
    cache_dir: Optional[str] = None,
    preset: Optional[str] = None,
    fit_overrides: Optional[Mapping[str, Any]] = None,
    workers: Optional[int] = None,
    profile: bool = True,
    output: Optional[str] = None,
    project_dir: Optional[str] = None,
    save_outputs: bool = True,
    background: bool = False,
    continue_from: Optional[str] = None,
) -> dict[str, Any]:
    """Run analysis stages as a job (``runs.analyse``).

    Blocking by default: the job is listed (``quest.jobs.list``), reports progress and can be
    cancelled from another caller while this call waits, and the reply carries the result.
    With ``background`` the call returns the ``job_id`` at once; poll ``quest.jobs.get``,
    stop with ``quest.jobs.cancel``, fetch with ``quest.analysis.result``.
    ``continue_from`` reuses the solved graphs of a finished job of this server.
    """
    from chisurf.plugins.quenching_estimator.core import runs as _runs
    from chisurf.plugins.quenching_estimator.core.tasks import CancelledError, default_manager
    from chisurf.plugins.quenching_estimator.rpc.contract import error_code_for

    problem = _analysis_problem(stages, preset, fit_overrides, data)
    if problem:
        return service_error(problem, "invalid_analysis")
    manager = default_manager()
    previous = None
    if continue_from:
        entry = _job_entry(manager, continue_from)
        if entry is None:
            return service_error(f"No finished analysis job {continue_from} on this server.",
                                 "invalid_analysis")
        previous = entry["analysis"]

    job = manager.create("quest.analysis.run", {"stages": stages, "preset": preset})

    def work(progress, cancel):
        return _runs.analyse(
            stages, data=data, structures=dict(structures) if structures else None,
            tables=dict(tables) if tables else None, cache_dir=cache_dir, preset=preset,
            fit_overrides=dict(fit_overrides) if fit_overrides else None, workers=workers,
            profile=bool(profile), output=output, project_dir=project_dir,
            save_outputs=bool(save_outputs), run_id=job.job_id, progress=progress,
            cancel=cancel, analysis=previous,
        )

    if background:
        manager.submit("quest.analysis.run", work, error_code=error_code_for, job=job)
        return ok({"job_id": job.job_id, "status": job.status.value, "background": True})

    manager.start(job.job_id)
    try:
        entry = work(manager.reporter(job.job_id), manager.canceller(job.job_id))
    except CancelledError:
        manager.finish(job.job_id)
        return service_error("The analysis was cancelled.", "operation_cancelled",
                             "CancelledError", {"job_id": job.job_id})
    except Exception as exc:
        manager.fail(job.job_id, str(exc), error_code_for(exc))
        return service_error(f"Analysis failed: {exc}", error_code_for(exc), type(exc).__name__,
                             {"job_id": job.job_id})
    manager.finish(job.job_id, entry)
    return ok(_analysis_reply(job.job_id, "completed", entry))


def _analysis_reply(job_id: str, status: str, entry: Mapping[str, Any]) -> dict[str, Any]:
    """The reply of a finished analysis: native result, plain metadata."""
    return {
        "job_id": job_id,
        "status": status,
        "run_id": entry["run_id"],
        "directory": entry["directory"],
        "files": list(entry["files"]),
        "result": entry["result"],
    }


def analysis_result_handler(job_id: str, project_dir: Optional[str] = None) -> dict[str, Any]:
    """The result of an analysis job (from memory) or of a stored analysis run (from disk).

    A job this server ran returns the native result (with plot data); a stored run returns
    its ``summary.json`` (tables, numbers, text; no plot data) and its run record.
    """
    from chisurf.plugins.quenching_estimator.core import runs as _runs
    from chisurf.plugins.quenching_estimator.core.tasks import default_manager

    job = default_manager().get(job_id)
    if job is not None and job.action == "quest.analysis.run":
        status = job.status.value
        if status == "completed":
            return ok(_analysis_reply(job_id, status, job.result))
        if status == "cancelled":
            return service_error(f"Analysis job {job_id} was cancelled.", "operation_cancelled",
                                 details={"job_id": job_id})
        if status == "failed":
            return service_error(job.error or "failed", job.error_code or "operation_failed",
                                 details={"job_id": job_id})
        return service_error(f"Analysis job {job_id} is {status} ({job.progress} %).",
                             "job_not_finished", details=job.to_dict())
    try:
        stored = _runs.read_analysis_run(job_id, project_dir)
    except (ValueError, FileNotFoundError) as exc:
        return service_error(str(exc), "operation_failed", type(exc).__name__)
    return ok({"job_id": job_id, "status": "completed", "run_id": job_id,
               "directory": stored.pop("directory"), "files": stored["run"].get("files", []),
               "result": stored})


def analysis_site_table_handler(
    state: str,
    site: int,
    dye: Optional[str] = None,
    linker_length: Optional[float] = None,
    structure: Optional[str] = None,
    chain: Optional[str] = None,
    cache_dir: Optional[str] = None,
) -> dict[str, Any]:
    """Build (or read from the cache) one site table and summarise it."""
    import numpy as np

    from chisurf.plugins.quenching_estimator.core.inference import site_table as _st
    from chisurf.plugins.quenching_estimator.rpc.contract import error_code_for

    settings_ = _st.settings()
    if linker_length is None:
        lengths = settings_["linker_lengths"]
        if dye not in lengths:
            return service_error(f"Give linker_length or a dye of {sorted(lengths)}.",
                                 "invalid_analysis")
        linker_length = lengths[dye]
    if structure is None:
        if state not in settings_["structures"]:
            return service_error(f"Give structure or a state of {sorted(settings_['structures'])}.",
                                 "invalid_analysis")
        structure = str(_st.male_structure(state, settings_))
    try:
        table = _st.site_table(structure, int(site), float(linker_length), chain=chain,
                               settings_=settings_, cache_dir=cache_dir)
    except Exception as exc:
        return service_error(f"Site table failed: {exc}", error_code_for(exc), type(exc).__name__)
    exposure = np.asarray(table.exposure, dtype=float)
    return ok(
        {
            "state": state,
            "site": int(site),
            "linker_length": float(linker_length),
            "structure": str(structure),
            "path": None if table.path is None else str(table.path),
            "n_voxels": table.n_voxels,
            "residue_types": list(_st.residue_types(settings_)),
            "neighbour_totals": table.neighbours.sum(axis=0).astype(int).tolist(),
            "exposure": {"mean": float(exposure.mean()) if exposure.size else None,
                         "min": float(exposure.min()) if exposure.size else None,
                         "max": float(exposure.max()) if exposure.size else None},
            "meta": to_payload(table.meta),
        }
    )


def register_services(dispatcher: Any) -> None:
    """Register QuEst's methods with *dispatcher*.

    Parameters
    ----------
    dispatcher : object
        Anything exposing ``register(name, handler)`` — QuEst's own
        :class:`~quest.rpc.dispatcher.ServiceDispatcher`, or a host
        application's.
    """

    dispatcher.register("quest.template", lambda p: template_handler(**(p or {})))
    dispatcher.register("quest.validate", lambda p: validate_handler(**(p or {})))
    dispatcher.register("quest.simulate", lambda p: simulate_handler(**(p or {})))
    dispatcher.register("quest.scan", lambda p: scan_handler(**(p or {})))
    dispatcher.register(
        "quest.parameter_catalog",
        lambda p: parameter_catalog_handler((p or {}).get("locale")),
    )
    dispatcher.register("quest.locales", lambda p: locales_handler((p or {}).get("locale")))
    dispatcher.register("quest.dyes.list", lambda p: dyes_list_handler())
    dispatcher.register("quest.dyes.save", lambda p: dyes_save_handler(**(p or {})))
    dispatcher.register("quest.quenching_defaults", lambda p: quenching_defaults_handler())
    dispatcher.register(
        "quest.structure.metadata", lambda p: structure_metadata_handler(**(p or {}))
    )
    dispatcher.register("quest.runs.list", lambda p: runs_list_handler(**(p or {})))
    dispatcher.register("quest.runs.get", lambda p: runs_get_handler(**(p or {})))
    dispatcher.register("quest.jobs.list", lambda p: jobs_list_handler())
    dispatcher.register("quest.jobs.get", lambda p: jobs_get_handler(**(p or {})))
    dispatcher.register("quest.jobs.cancel", lambda p: jobs_cancel_handler(**(p or {})))
    dispatcher.register("quest.contract.describe", lambda p: contract_describe_handler())
    dispatcher.register("quest.analysis.template", lambda p: analysis_template_handler())
    dispatcher.register("quest.analysis.run", lambda p: analysis_run_handler(**(p or {})))
    dispatcher.register("quest.analysis.result", lambda p: analysis_result_handler(**(p or {})))
    dispatcher.register(
        "quest.analysis.site_table", lambda p: analysis_site_table_handler(**(p or {}))
    )


def local_client() -> InProcessClient:
    """Return a client wired to a fresh dispatcher with QuEst's methods on it."""

    dispatcher = ServiceDispatcher()
    register_services(dispatcher)
    return InProcessClient(dispatcher)


def registered_method_names() -> tuple[str, ...]:
    """The names :func:`register_services` adds, without registering them."""
    return tuple(METHODS)
