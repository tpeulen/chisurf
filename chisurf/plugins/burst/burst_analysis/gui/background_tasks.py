"""BVA and 2CDE of the pipeline, computed in worker processes while the user works on.

In Simple mode the pipeline computes BVA and 2CDE with their defaults as soon as the bursts are
there. On their own worker threads they took the interpreter from Burst MLE (which prepares in
the same moment) and from the window; here each is a task of its own process: it reads the run,
computes, writes the result into the analysis container and stamps it current -- exactly what
the step's own computation does -- and the step's controller then receives the result as if its
thread had made it (its panel, check mark and "unchanged" logic work as before).
"""

from __future__ import annotations

import concurrent.futures
import logging
import threading
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_POOL: Any = None
_POOL_LOCK = threading.Lock()


def pool():
    """The kept pool of two task processes (BVA and 2CDE side by side), started on first use."""
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            import atexit
            import multiprocessing as mp

            _POOL = concurrent.futures.ProcessPoolExecutor(
                max_workers=2, mp_context=mp.get_context("spawn")
            )
            atexit.register(_POOL.shutdown, wait=False, cancel_futures=True)
        return _POOL


def warm() -> None:
    """Start the task processes and load their modules, so the first task does not wait."""
    try:
        p = pool()
        for _ in range(2):
            p.submit(_warm_worker)
    except Exception:  # noqa: BLE001 - the tasks start them themselves
        pass


def _warm_worker() -> None:
    from chisurf.plugins.burst.burst_2cde.core import computation  # noqa: F401
    from chisurf.plugins.burst.burst_bva.core import computation as _bva  # noqa: F401


def _columns(store) -> dict[str, np.ndarray]:
    from chisurf.core.datastore import column_names

    return {name: np.asarray(store[name]) for name in column_names(store)}


def _store(columns: dict[str, np.ndarray]):
    from chisurf.core.datastore import store_from_arrays

    return store_from_arrays(columns)


# -- the tasks (worker side) -------------------------------------------------------------------- #
def bva_task(folder, settings, write_output, fingerprint, inputs, params):
    """BVA of the run *folder*: computed, written, stamped; the result's columns and a note."""
    from chisurf.core.runtime import analysis_cache
    from chisurf.plugins.burst.burst_bva.core import computation as core

    saved_settings = dict(settings)
    settings = dict(settings)
    file_type = settings.pop("file_type")
    burst_df, tttrs = core.read_burst_analysis(Path(folder), file_type, pattern="bi4_bur")
    result = core.compute_bva(burst_df, tttrs, **settings)
    note = ""
    if write_output:
        written = []
        try:
            written = core.write_bva_container(
                result, parameters=saved_settings, analysis_folder=Path(folder)
            )
        except Exception as exc:  # noqa: BLE001 - the result stands, as in the step itself
            note = f" (could not write the BVA result: {exc})"
        analysis_cache.write_stamp(
            analysis_cache.stamp_path(Path(folder), "bva"),
            fingerprint,
            params=params,
            inputs=inputs,
            outputs=[Path(p) for p in written],
            tool="bva",
        )
    return _columns(result), note


def two_cde_task(folder, settings, fingerprint, inputs, params):
    """2CDE of the run *folder*: computed, written, stamped; the result's columns, variant, note."""
    from chisurf.core.runtime import analysis_cache
    from chisurf.plugins.burst.burst_2cde.core import computation as core

    df, tttrs = core.read_burst_analysis(Path(folder), settings["file_type"], pattern="bi4_bur")
    df = core.compute_2cde(
        df,
        tttrs,
        donor_channels=settings["donor_channels"],
        acceptor_channels=settings["acceptor_channels"],
        donor_micro_time_ranges=settings.get("donor_micro_time_ranges", []),
        acceptor_micro_time_ranges=settings.get("acceptor_micro_time_ranges", []),
        acceptor_excitation_channels=settings.get("acceptor_excitation_channels"),
        acceptor_excitation_micro_time_ranges=settings.get("acceptor_excitation_micro_time_ranges"),
        micro_time_resolution_ps=settings.get("micro_time_resolution_ps"),
        alex_donor_channel_ranges=settings.get("alex_donor_channel_ranges"),
        alex_acceptor_channel_ranges=settings.get("alex_acceptor_channel_ranges"),
        donor_macro_phase_ranges=settings.get("donor_macro_phase_ranges", []),
        acceptor_macro_phase_ranges=settings.get("acceptor_macro_phase_ranges", []),
        acceptor_excitation_macro_phase_ranges=settings.get(
            "acceptor_excitation_macro_phase_ranges", []
        ),
        alternation_period_ticks=settings.get("alternation_period_ticks", 0),
        alternation_offset_ticks=settings.get("alternation_offset_ticks", 0),
        tau=settings["tau_us"] * 1e-6,
        kernel=settings["kernel"],
        variant=settings["variant"],
    )
    note = ""
    try:
        written = core.write_2cde_container(
            df, settings["variant"], parameters=params, analysis_folder=Path(folder)
        )
        analysis_cache.write_stamp(
            analysis_cache.stamp_path(Path(folder), "2cde"),
            fingerprint,
            params=params,
            inputs=inputs,
            outputs=[Path(p) for p in written],
            tool="2cde",
        )
    except Exception as exc:  # noqa: BLE001 - the result stands; say why nothing was written
        note = f" (could not write the 2CDE result: {exc})"
    return _columns(df), settings["variant"], note


# -- starting them (GUI side) ------------------------------------------------------------------- #
def _relay(task_future, deliver) -> concurrent.futures.Future:
    """A future the step's controller polls, resolved by *deliver(task result)* off the UI thread."""
    out: concurrent.futures.Future = concurrent.futures.Future()

    def done(f) -> None:
        try:
            out.set_result(deliver(f.result()))
        except BaseException as exc:  # noqa: BLE001 - the controller's poll reports it
            out.set_exception(exc)

    task_future.add_done_callback(done)
    return out


def start_bva(controller) -> bool:
    """Compute the BVA step's result in a task process; ``False`` when the step cannot run (then
    nothing started). What the controller's own Run does, with the computation elsewhere."""
    from chisurf.core.fio.address import container_of
    from chisurf.plugins.burst.burst_bva.core import computation as core

    model = controller.model
    folder = model.analysis_folder
    if model.is_running or folder is None or not container_of(folder).exists():
        return False
    folder = Path(folder)
    settings = model.bva_settings()
    controller._fingerprint = model.analysis_fingerprint(settings)
    controller._cache.allow()
    controller._cancel.clear()
    controller.model.restart_attention = False
    model.is_running = True
    model.status_text = "Computing BVA (in the background) …"
    task = pool().submit(
        bva_task,
        str(folder),
        dict(settings),
        True,
        controller._fingerprint,
        model.input_files(),
        model.fingerprint_params(settings),
    )
    file_type = settings.get("file_type")

    def deliver(out):
        columns, note = out
        # the bursts and photons the panel shows: the run's table, the photons from the shared read
        burst_df, tttrs = core.read_burst_analysis(folder, file_type, pattern="bi4_bur")
        checked = model.check_windows(tttrs)
        return burst_df, tttrs, _store(columns), note, checked

    controller._future = _relay(task, deliver)
    return True


def start_two_cde(controller) -> bool:
    """Compute the 2CDE step's result in a task process; ``False`` when the step cannot run."""
    from chisurf.plugins.burst.workspace_io import is_burst_source

    model = controller.model
    if model.is_running or not model.folder:
        return False
    folder = Path(model.folder).expanduser()
    if not is_burst_source(folder):
        return False
    fingerprint = model.analysis_fingerprint()
    controller._fingerprint = fingerprint
    controller._cache.allow()
    controller._cancel.clear()
    model.restart_attention = False
    model.is_running = model.is_locked = True
    model.status_text = "Computing 2CDE (in the background) …"
    task = pool().submit(
        two_cde_task,
        str(folder),
        dict(model.settings()),
        fingerprint,
        model.input_files(),
        model.fingerprint_params(),
    )

    def deliver(out):
        columns, variant, note = out
        return _store(columns), variant, note

    controller._future = _relay(task, deliver)
    return True


__all__ = ["bva_task", "pool", "start_bva", "start_two_cde", "two_cde_task", "warm"]
