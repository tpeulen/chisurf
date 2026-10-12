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


def local_client() -> InProcessClient:
    """Return a client wired to a fresh dispatcher with QuEst's methods on it."""

    dispatcher = ServiceDispatcher()
    register_services(dispatcher)
    return InProcessClient(dispatcher)


def registered_method_names() -> tuple[str, ...]:
    """The names :func:`register_services` adds, without registering them."""
    return tuple(METHODS)
