"""Step 4 of the burst workflow, *More samples*: further measurements processed as the first one was.

The user tunes the pipeline on one measurement -- the setup (step 0), the calibration files and
what they gave (step 1), the burst search (step 2), Burst MLE's IRF, background, model and fit
window (step 3) and the optional steps (Fusion, BVA, 2CDE, H2MM) -- and then drops more
measurements of the same kind on step 4. Each goes through exactly that pipeline:

* :class:`Recipe` is the pipeline as tuned, one object, captured from what the steps already
  export: :meth:`.workflow_context.BurstWorkflowContext.to_payload` (setup, calibration files,
  calibration and its report), Burst Selection's ``export_settings``, Burst MLE's
  ``settings_payload`` (every detector's model, start values, fixed flags, fit window and IRF
  shifts) with the IRF it fitted with, and the settings of each optional step that ran.
* :func:`process_sample` replays it on one measurement through the steps' own code: Burst
  Selection's model searches (the run goes into the measurement's ``.pto`` container, under its
  photon dataset), the optional steps run on the run, Burst MLE's model takes the bursts as the hub
  hands them over (the background is the strict selection of *this* measurement, the buffer's when
  there is one) and then fits with the recipe's IRF, shifts and window. The calibration report and
  the recipe go into the container beside the runs, so the results name what made them.
* :class:`SampleQueue` processes a list of samples off the UI thread, one at a time or as many at
  once as the burst search would use processes for them; a failed sample does not stop the
  others. :func:`process_more` is the same queue, run to the end (the headless API,
  :meth:`..api.workflow.BurstWorkflow.process_more`).

Nothing here imports a GUI toolkit.
"""

from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Mapping

import numpy as np

logger = logging.getLogger(__name__)

#: The recipe's format, for a reader to check.
SCHEMA = "chisurf.burst_recipe/1"
#: The name of the recipe object in a measurement's container.
RECIPE_NAME = "burst_recipe"
#: What a sample can be: waiting, being processed, processed, or failed (its tooltip says why).
STATUSES = ("queued", "running", "done", "failed")
#: The optional steps a recipe can carry, in the order a sample goes through them.
OPTIONAL_STEPS = ("fusion", "bva", "two_cde", "h2mm")
#: Their names, as the rail shows them.
STEP_LABELS = {"fusion": "Fusion", "bva": "BVA", "two_cde": "2CDE", "h2mm": "H2MM"}

#: What the workflow payload keeps of the first data: not its files, bursts or MMFDB records.
_WORKFLOW_KEYS = ("channel_settings", "setup_name", "samples", "calibration", "estimated",
                  "calibration_report")
#: The shift calibration's curves are the report's, not the recipe's.
_SHIFT_CURVES = ("fit_data", "fit_model", "fit_residuals")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=_jsonable)


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (set, tuple)):
        return list(value)
    return str(value)


def _plain(value: Any) -> Any:
    """*value* as JSON gives it back (lists for arrays and tuples, strings for paths)."""
    return json.loads(json.dumps(value, default=_jsonable))


def _short_id(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()[:12]


@dataclass
class Recipe:
    """The burst pipeline as tuned on the first data, to process further measurements with.

    Attributes
    ----------
    workflow : dict
        The workflow context's payload without its files: ``channel_settings`` (the setup, its G
        factors included), ``setup_name``, ``samples`` (the calibration files and their rows:
        buffer, IRF and reference dye per colour), ``calibration``, ``estimated`` and
        ``calibration_report``.
    selection : dict
        Burst Selection's ``export_settings`` (the search and the filter).
    mle : dict
        Burst MLE: ``settings`` (the session's ``settings_payload``: per detector the model, start
        values, fixed flags, the fit window and the IRF shifts), ``irf`` (per detector the IRF the
        fit used, VV | VH), ``irf_source`` and ``irf_choice`` (where it came from), and
        ``shift_calibration`` (what the shifts were calibrated on).
    optional : dict
        The settings of each optional step that ran on the first data (``fusion``, ``bva``,
        ``two_cde``, ``h2mm``); a step that did not run is not in it.
    """

    workflow: dict = field(default_factory=dict)
    selection: dict = field(default_factory=dict)
    mle: dict = field(default_factory=dict)
    optional: dict = field(default_factory=dict)

    # -- capture ------------------------------------------------------------------------------- #
    @classmethod
    def capture(
        cls,
        context: Any,
        selection: Any,
        mle_session: Any,
        optional: Mapping[str, dict] | None = None,
    ) -> Recipe:
        """The recipe of a workflow: its *context* (a :class:`.workflow_context.BurstWorkflowContext`),
        Burst Selection's model *selection*, Burst MLE's session *mle_session* and the settings of
        the *optional* steps that ran (``{"bva": {...}, ...}``).

        Only the calibration files of the context are kept (not its measurements).
        """
        payload = context.to_payload()
        workflow = {key: copy.deepcopy(payload.get(key)) for key in _WORKFLOW_KEYS}
        workflow["samples"] = {
            p: row for p, row in (payload.get("samples") or {}).items() if row != "measurement"
        }
        mle: dict[str, Any] = {}
        if mle_session is not None:
            mle = {
                "settings": mle_session.settings_payload(),
                "irf": {d: np.asarray(v, dtype=float) for d, v in (mle_session.irf_np or {}).items()},
                "irf_source": dict(mle_session.irf_source or {}),
                "irf_choice": dict(mle_session.irf_choice or {}),
                "shift_calibration": {
                    d: {k: v for k, v in (entry or {}).items() if k not in _SHIFT_CURVES}
                    for d, entry in (mle_session.shift_calibration or {}).items()
                },
                "split_by_state": bool(getattr(mle_session, "split_by_state", False)),
            }
        return cls.from_payload({
            "workflow": workflow,
            "selection": selection.export_settings() if selection is not None else {},
            "mle": mle,
            "optional": {k: v for k, v in (optional or {}).items() if k in OPTIONAL_STEPS and v is not None},
        })

    # -- round trip -------------------------------------------------------------------------- #
    def to_payload(self) -> dict[str, Any]:
        """The recipe as JSON-ready data (what the hub's settings and the containers keep)."""
        return _plain({
            "schema": SCHEMA,
            "workflow": self.workflow,
            "selection": self.selection,
            "mle": self.mle,
            "optional": self.optional,
        })

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> Recipe:
        """The recipe of :meth:`to_payload` (an empty recipe for ``None``)."""
        payload = _plain(dict(payload or {}))
        schema = payload.get("schema")
        if schema not in (None, SCHEMA):
            raise ValueError(f"not a burst recipe (schema {schema!r})")
        return cls(
            workflow=dict(payload.get("workflow") or {}),
            selection=dict(payload.get("selection") or {}),
            mle=dict(payload.get("mle") or {}),
            optional=dict(payload.get("optional") or {}),
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Recipe) and self.to_payload() == other.to_payload()

    # -- what it is ------------------------------------------------------------------------- #
    @property
    def ready(self) -> bool:
        """Whether the recipe can process a sample: a setup, a search and a fit."""
        return bool(self.setup.get("detectors") and self.selection and self.mle.get("settings"))

    @property
    def recipe_id(self) -> str:
        """A short hash of the recipe: what the results it made are stamped with."""
        payload = self.to_payload()
        return _short_id({k: payload[k] for k in ("workflow", "selection", "mle", "optional")})

    @property
    def calibration_report_id(self) -> str:
        """A short hash of the calibration report the recipe carries (empty: none)."""
        report = self.workflow.get("calibration_report") or {}
        return _short_id(report) if report else ""

    @property
    def setup(self) -> dict:
        return dict(self.workflow.get("channel_settings") or {})

    @property
    def setup_name(self) -> str:
        return str(self.workflow.get("setup_name") or "")

    def context(self) -> Any:
        """The workflow context the recipe was taken from, without its measurements."""
        from .workflow_context import BurstWorkflowContext

        return BurstWorkflowContext(
            channel_settings=copy.deepcopy(self.setup),
            setup_name=self.setup_name,
            samples=dict(self.workflow.get("samples") or {}),
            calibration=copy.deepcopy(self.workflow.get("calibration") or {}),
            calibration_report=copy.deepcopy(self.workflow.get("calibration_report") or {}),
        )

    def references(self) -> dict[str, Any]:
        """The calibration files as Burst MLE takes them (``{"buffer", "irf", "reference"}``)."""
        return self.context().references()

    def steps(self) -> list[str]:
        """The optional steps a sample goes through, in order."""
        return [s for s in OPTIONAL_STEPS if s in self.optional]

    def fit_window(self) -> dict[str, tuple[int, int]]:
        """``{detector: (first bin, last bin)}`` of the fit (``-1``: the detector's gate)."""
        settings = (self.mle.get("settings") or {}).get("detector_settings") or {}
        return {
            det: (int(v.get("micro_time_start", -1)), int(v.get("micro_time_stop", -1)))
            for det, v in settings.items()
        }

    def fit_models(self) -> dict[str, str]:
        settings = (self.mle.get("settings") or {}).get("detector_settings") or {}
        return {det: str(v.get("model", "")) for det, v in settings.items()}

    def summary(self) -> str:
        """One short line: setup · calibration · search · fit · optional steps."""
        if not self.ready:
            return "No recipe yet: run 3. Burst MLE first."
        rows = set((self.workflow.get("samples") or {}).values())
        n_ref = sum(1 for r in rows if r != "measurement")
        models = sorted(set(self.fit_models().values()))
        parts = [
            self.setup_name or "unsaved setup",
            f"{n_ref} calibration file(s)" if n_ref else "no calibration files",
            str(self.selection.get("algorithm") or "search"),
            "/".join(models) or "fit",
        ]
        parts += [STEP_LABELS[s] for s in self.steps()]
        return " · ".join(parts)

    def detail_rows(self) -> list[dict[str, str]]:
        """The recipe for the Advanced table: one short row per part, the details in its tip."""
        if not self.ready:
            return []
        setup = self.setup
        detectors = setup.get("detectors") or {}
        rows = [{
            "part": "Setup",
            "value": self.setup_name or "unsaved",
            "tip": "Detectors: " + "; ".join(
                f"{d} ch {v.get('chs')} G {float(v.get('g_factor', 1.0)):.3f}" for d, v in detectors.items()
            ),
        }]
        samples = self.workflow.get("samples") or {}
        rows.append({
            "part": "Calibration",
            "value": f"{len(samples)} file(s)",
            "tip": "\n".join(f"{row}: {Path(p).name}" for p, row in sorted(samples.items(), key=lambda kv: kv[1]))
            or "No calibration files: background, IRF and G estimated from each measurement.",
        })
        report = self.calibration_report_id
        rows.append({
            "part": "Report",
            "value": report or "none",
            "tip": "The calibration report written into every sample's container with its runs "
                   f"(burst_calibration); id {report or '—'}.",
        })
        params = self.selection.get("parameters") or {}
        rows.append({
            "part": "Search",
            "value": str(self.selection.get("algorithm") or ""),
            "tip": "; ".join(f"{k} {v}" for k, v in params.items())
            + f"; min photons {self.selection.get('min_photons', '')}",
        })
        windows = self.fit_window()
        models = self.fit_models()
        sources = self.mle.get("irf_source") or {}
        shifts = self.mle.get("shift_calibration") or {}
        det_settings = (self.mle.get("settings") or {}).get("detector_settings") or {}
        for det in windows:
            lo, hi = windows[det]
            st = det_settings.get(det, {})
            rows.append({
                "part": f"Fit {det}",
                "value": f"{models.get(det, '')} {lo}–{hi}" if lo >= 0 else models.get(det, ""),
                "tip": f"Model {models.get(det, '')}, fit window bins {lo}–{hi} "
                       f"(binning {st.get('micro_time_binning', 1)}); IRF from {sources.get(det, '—')}; "
                       f"shifts VV {float(st.get('shift_sp', 0.0)):.2f}, VH {float(st.get('shift_ss', 0.0)):.2f} bins"
                       + (f" ({shifts[det].get('source', '')} {shifts[det].get('dye', '')})" if det in shifts else ""),
            })
        for step in self.steps():
            rows.append({
                "part": STEP_LABELS[step],
                "value": "on",
                "tip": "; ".join(f"{k} {v}" for k, v in (self.optional.get(step) or {}).items()
                                 if not isinstance(v, (dict, list)))[:400],
            })
        rows.append({"part": "Recipe", "value": self.recipe_id,
                     "tip": "Written into each sample's container (burst_recipe) with its runs."})
        return rows

    def details(self) -> str:
        """The recipe in words, a line per part (the summary's tooltip)."""
        rows = self.detail_rows()
        if not rows:
            return self.summary()
        return "\n".join(f"{r['part']}: {r['value']} — {r['tip']}" for r in rows)


# -- what every sample shares ------------------------------------------------------------------- #
@dataclass
class Calibration:
    """What every sample of a batch shares, computed once per batch and handed to every sample
    read-only: the recipe (and its payload and ids), the detectors, every detector's fit settings
    (window, shifts, model, start values), the IRF and where it came from, the shift calibration,
    and -- when step 1 has a Buffer -- the buffer's background histogram per detector (its files
    read once). Nothing in it depends on a sample; what does (its photons, bursts, own strict
    background, BVA, 2CDE, H2MM, the lifetime fits) is computed per sample.

    The pool's workers get it through shared memory (:func:`publish_calibration`): one copy per
    batch, read once per worker process, never pickled into a task."""

    recipe: Recipe
    payload: dict
    recipe_id: str
    report_id: str
    setup: dict
    det_settings: dict
    irf: dict
    irf_source: dict
    shift_calibration: dict
    buffer_files: list
    buffer: dict
    split_by_state: bool = False

    @property
    def key(self) -> str:
        """What identifies it in the workers' cache: the recipe and the buffer it holds."""
        digest = hashlib.sha256(self.recipe_id.encode())
        for det in sorted(self.buffer):
            digest.update(det.encode() + np.ascontiguousarray(self.buffer[det]).tobytes())
        return digest.hexdigest()[:16]


def _read_only(array) -> np.ndarray:
    out = np.array(array, dtype=float)
    out.setflags(write=False)
    return out


def prepare_calibration(recipe: Recipe) -> Calibration:
    """The :class:`Calibration` of *recipe*: everything calibration-related, once per batch."""
    from chisurf.plugins.burst.burst_mle_analysis.engine import MleSession

    if not recipe.ready:
        raise ValueError("the recipe is not complete: run 3. Burst MLE on the first data first")
    payload = recipe.to_payload()
    mle = recipe.mle
    buffers = [str(b) for b in recipe.references().get("buffer") or ()]
    buffer: dict = {}
    if buffers:
        # the buffer's histograms at the setup's binning and channels, as Burst MLE's
        # prepare_patterns reads them (one buffer serves every detector)
        session = MleSession()
        session.set_definition(recipe.setup)
        if session.detectors:
            session.bg_one_for_all = True
            session.set_pattern_files("bg", next(iter(session.detectors)), buffers)
            buffer = {d: _read_only(a) for d, a in session.buffer_np.items()}
    return Calibration(
        recipe=recipe,
        payload=payload,
        recipe_id=recipe.recipe_id,
        report_id=recipe.calibration_report_id,
        setup=copy.deepcopy(recipe.setup),
        det_settings=copy.deepcopy((mle.get("settings") or {}).get("detector_settings") or {}),
        irf={d: _read_only(v) for d, v in (mle.get("irf") or {}).items() if np.asarray(v).size},
        irf_source=dict(mle.get("irf_source") or {}),
        shift_calibration=copy.deepcopy(mle.get("shift_calibration") or {}),
        buffer_files=buffers,
        buffer=buffer,
        split_by_state=bool(mle.get("split_by_state", False)),
    )


#: The calibrations this process has read from shared memory, by :attr:`Calibration.key`.
_SHARED: dict = {}


def publish_calibration(calibration: Calibration):
    """Put *calibration* into one shared-memory block for the pool's workers; returns the handle
    the tasks carry (``(key, block name, size)``) and the block (the caller closes and unlinks it
    when the batch is done)."""
    import pickle
    from multiprocessing import shared_memory

    blob = pickle.dumps(calibration, protocol=pickle.HIGHEST_PROTOCOL)
    block = shared_memory.SharedMemory(create=True, size=max(1, len(blob)))
    block.buf[: len(blob)] = blob
    _SHARED[calibration.key] = calibration
    return (calibration.key, block.name, len(blob)), block


def calibration_of(handle) -> Calibration:
    """The calibration a task names: itself, or read once per process from its shared block."""
    if isinstance(handle, Calibration):
        return handle
    key, name, size = handle
    found = _SHARED.get(key)
    if found is not None:
        return found
    import pickle
    from multiprocessing import resource_tracker, shared_memory

    block = shared_memory.SharedMemory(name=name)
    try:
        calibration = pickle.loads(bytes(block.buf[:size]))
    finally:
        block.close()
        try:  # the batch owns the block; a worker that read it must not unlink it on exit
            resource_tracker.unregister(block._name, "shared_memory")  # noqa: SLF001
        except Exception:  # noqa: BLE001 - nothing registered
            pass
    _SHARED.clear()  # one batch at a time per worker
    _SHARED[key] = calibration
    return calibration


# -- one sample -------------------------------------------------------------------------------- #
def new_sample(path: str | Path, uid: str = "") -> dict[str, Any]:
    """A sample row: queued, nothing computed yet."""
    path = Path(path)
    return {"path": str(path), "name": path.stem, "uid": str(uid or ""), "status": "queued",
            "stage": "", "error": "", "bursts": None, "tau": {}, "E": None, "run": "",
            "container": "", "recipe_id": "", "report_id": ""}


class SampleStopped(InterruptedError):
    """The user stopped the queue while a sample was processed."""


def _check(should_stop: Callable[[], bool] | None) -> None:
    if should_stop is not None and should_stop():
        raise SampleStopped("stopped")


def search_task(handle, path: str, uid: str, container_dir: str) -> str:
    """Burst Selection's search of one measurement through its model, in whichever process runs
    it (a worker of the shared pool): the run goes into *container_dir*, the folder of the
    measurement's analysis container (given, not derived: a worker has a session of its own).
    Returns the run written."""
    from chisurf.core.fio.staging import open_tttr
    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel

    from .workflow_context import searched_runs

    calibration = calibration_of(handle)
    setup, setup_name = calibration.setup, calibration.recipe.setup_name
    selection = calibration.recipe.selection
    path = Path(path)

    try:  # said plainly here: the search's own worker reports an unreadable file as "Unknown"
        open_tttr(str(path))
    except Exception as exc:  # noqa: BLE001 - the sample fails with the reason
        reason = str(exc).replace(str(path), path.name).split(". ")[0]
        raise ValueError(f"{path.name} cannot be read as a photon stream: {reason}") from exc
    model = BurstSelectionModel()
    model.set_setup({**setup, "setup_name": setup_name})
    model.import_settings(selection)
    # the pipeline writes .pto only; zipped folders are Legacy Export's
    model.zip_output = model.remove_folder = False
    if not model.add_paths([path]):
        raise ValueError(f"{path.name} is not a photon file Burst Selection reads")
    model.sources = {str(Path(p).resolve()): uid for p in model.files} if uid else {}
    dirs = {str(p): str(container_dir) for p in model.files}
    model.container_dirs = lambda: dict(dirs)
    why = model.prepare_run(force=True)
    if why is not None:
        raise RuntimeError(why)
    result = model.run()
    runs = searched_runs(result, model.files)
    if not runs:
        raise RuntimeError(f"the burst search wrote no run ({model.status_text})")
    return str(runs[0])


def _search(handle, path: Path, uid: str, folder: Path, pool, should_stop) -> tuple[Path, Any]:
    """The search of one sample (in *pool* when given); the run and what registers it in the
    workspace (Burst Selection's files, sources and container folders)."""
    run = _call(pool, should_stop, search_task, handle, str(path), uid, str(folder))
    files = [Path(path).resolve()]
    dirs = {str(files[0]): str(folder)}
    model = SimpleNamespace(files=files, sources={str(files[0]): uid} if uid else {},
                            container_dirs=lambda: dict(dirs))
    return Path(run), model


def _call(pool, should_stop, fn, *args):
    """*fn(*args)* in *pool* (a process pool shared by every sample and stage) or here; a Stop
    cancels a task not started yet and abandons a running one."""
    if pool is None:
        return fn(*args)
    future = pool.submit(fn, *args)
    while True:
        try:
            return future.result(timeout=0.2)
        except concurrent.futures.TimeoutError:
            if should_stop is not None and should_stop():
                future.cancel()
                raise SampleStopped("stopped") from None


def _fuse(recipe: Recipe, run: Path) -> Path:
    from chisurf.plugins.burst.burst_fusion.api.contract import settings_from_payload
    from chisurf.plugins.burst.burst_fusion.core.fusion import fuse_folder

    setup = recipe.setup
    result = fuse_folder(run, settings_from_payload(recipe.optional["fusion"]),
                         detectors=setup.get("detectors"), windows=setup.get("windows"))
    runs = [Path(r) for r in result.get("runs") or ()]
    if not runs:
        raise RuntimeError("the fusion wrote no run")
    return runs[0]


def _stamp_args(tool: str, run: Path, settings: dict) -> tuple[str, list, dict]:
    """The fingerprint, inputs and parameters the step's own run stamps its result with."""
    from chisurf.core.fio.fluorescence.burst_manifest import source_inputs
    from chisurf.core.runtime import analysis_cache

    if tool == "bva":
        from chisurf.plugins.burst.burst_bva.gui.view_model import ALGORITHM_VERSION
        tag = "bva"
    else:
        from chisurf.plugins.burst.burst_2cde.gui.view_model import ALGORITHM_VERSION
        tag = "2cde"
    inputs = [f for d in sorted(run.glob("bi4_bur")) for f in sorted(d.glob("*")) if f.is_file()]
    inputs += list(source_inputs(run))
    params = {**settings, "_read_context": analysis_cache.photon_read_context()}
    fingerprint = analysis_cache.fingerprint(
        inputs, params, extra=analysis_cache.algorithm_tag(tag, ALGORITHM_VERSION, "tttrlib")
    )
    return fingerprint, inputs, params


def _bva(recipe: Recipe, run: Path, pool=None, should_stop=None) -> None:
    from .gui.background_tasks import bva_task

    settings = dict(recipe.optional["bva"])
    fingerprint, inputs, params = _stamp_args("bva", run, settings)
    _columns, note = _call(pool, should_stop, bva_task, str(run), settings, True, fingerprint,
                           inputs, params)
    if note:
        raise RuntimeError(note.strip(" ()"))


def _two_cde(recipe: Recipe, run: Path, pool=None, should_stop=None) -> None:
    from .gui.background_tasks import two_cde_task

    settings = dict(recipe.optional["two_cde"])
    fingerprint, inputs, params = _stamp_args("two_cde", run, settings)
    _columns, _variant, note = _call(pool, should_stop, two_cde_task, str(run), settings,
                                     fingerprint, inputs, params)
    if note:
        raise RuntimeError(note.strip(" ()"))


def _h2mm(recipe: Recipe, run: Path) -> None:
    from chisurf.plugins.burst.burst_h2mm.gui.model import SETTING_FIELDS, H2mmViewModel

    model = H2mmViewModel()
    for name, value in (recipe.optional.get("h2mm") or {}).items():
        if name in SETTING_FIELDS:
            setattr(model, name, type(getattr(model, name))(value))
    model.apply_workflow_context({"burst_folder": str(run), "channel_settings": recipe.setup})
    model.compute(force=True)


def _fit(calibration: Calibration, run: Path, should_stop, progress, workers=None) -> Any:
    """Burst MLE of one sample: its bursts and photons read, the batch's calibration taken as it
    is -- setup, every detector's settings (fit window, shifts, model), the recipe's IRF, the
    buffer's histogram -- and only what depends on the sample computed: the photons outside its
    bursts and their strict background selection (judged with the recipe's IRF), then the fit,
    written into the container. The same state Burst MLE reaches by hand, without deriving any
    calibration again. Returns the session."""
    from chisurf.core.fluorescence.burst import extract_mle_irf_background
    from chisurf.plugins.burst.burst_mle_analysis.engine import MleSession, MleSettings

    session = MleSession()
    session.split_by_state = calibration.split_by_state
    session.add_burst_files([Path(run)])
    if session.df_bursts is None:
        raise RuntimeError("Burst MLE read no bursts from the run")
    session.set_definition(calibration.setup)  # the workflow's setup on top of the container's
    if calibration.buffer:
        session.bg_files = {d: [Path(p) for p in calibration.buffer_files] for d in calibration.buffer}
        session.buffer_np = dict(calibration.buffer)
    known = set(MleSettings.__dataclass_fields__)
    for det, values in calibration.det_settings.items():
        if det in session.detectors:
            session.det_settings[det] = MleSettings(
                **copy.deepcopy({k: v for k, v in values.items() if k in known})
            )
    for det, irf in calibration.irf.items():
        if det in session.detectors:
            session.irf_np[det] = irf
            source = calibration.irf_source.get(det, "")
            session.irf_source[det] = f"the recipe ({source})" if source else "the recipe"
    for det, entry in calibration.shift_calibration.items():
        if det in session.detectors:
            session.shift_calibration[det] = dict(entry)
    session.outcome = None
    # this sample's own: the histograms of the photons outside its bursts (what ensure_background
    # reads -- without the IRF estimate it would make of them and throw away) and their strict
    # selection, judged with the recipe's IRF
    tttr = session.current_tttr()
    index = session.burst_index_array()
    if tttr is not None and index.size:
        in_burst = np.zeros(len(tttr), dtype=bool)
        in_burst[index] = True
        patterns = extract_mle_irf_background(
            tttr, session.detectors, micro_time_binning=session.settings.micro_time_binning,
            mask=~in_burst, min_photons=max(2, int(session.settings.min_photons)),
            irf_model="experimental",
        )
        for det, pattern in patterns.items():
            if det in session.detectors:
                session.bg_np[det] = np.asarray(pattern["bg"], dtype=float)
        session.select_background()
    _check(should_stop)
    # the shared fit pool (engine.fit_pool) at the batch's size: every sample's chunks go into the
    # same processes, so a sample alone gets all of them and several share them
    session.run_batch(progress=progress, should_stop=should_stop, max_workers=workers)
    _check(should_stop)
    session.export_results()
    return session


def write_recipe(source: str | Path, recipe: Recipe | Calibration, out_dir: str | Path | None = None,
                 runs: Iterable[str] = ()) -> str:
    """Write *recipe* (or a batch's :class:`Calibration` of it: its payload and ids as computed
    once) into the container of the measurement *source* (replacing the one written before),
    derived from its photon streams, with the runs it made; returns the container."""
    from chisurf.core.fio.fluorescence.burst_container import open_measurement

    if isinstance(recipe, Calibration):
        base, recipe_id, report_id = recipe.payload, recipe.recipe_id, recipe.report_id
    else:
        base, recipe_id, report_id = (recipe.to_payload(), recipe.recipe_id,
                                      recipe.calibration_report_id)
    payload = {**base, "recipe_id": recipe_id, "calibration_report_id": report_id,
               "runs": list(runs)}
    data = json.dumps(payload, indent=1, sort_keys=True).encode("utf-8")
    with open_measurement(source, out_dir, raw_data="sidecar") as m:
        for obj in list(m._f.objects()):
            if getattr(obj, "name", "") == RECIPE_NAME:
                m._f.remove(obj.uid)
        m.put_blob(
            RECIPE_NAME,
            data,
            artifact_kind="parameter_table",
            data_format="json",
            operation_type="analysis_run",
            parameters={"schema": SCHEMA, "recipe_id": recipe_id,
                        "calibration_report_id": report_id},
            derived_from=m.instrument_uids or m.instrument_uid,
            mime_type="application/json",
        )
        return str(m.path)


def read_recipe(container: str | Path) -> dict[str, Any]:
    """The recipe a container's runs were made with (``{}``: none written), with its ids."""
    from chisurf.core.fio.pto import Measurement

    with Measurement.open(container) as m:
        for obj in m._f.objects():
            if getattr(obj, "name", "") == RECIPE_NAME:
                return json.loads(m.get_blob(obj.uid).decode("utf-8"))
    return {}


def _summarise(sample: dict, session: Any) -> None:
    """The short numbers of a processed sample into *sample*: bursts, mean τ per detector, mean E."""
    from chisurf.core.datastore import row_count
    from chisurf.plugins.burst.burst_mle_analysis.gui.fit_view import burst_lifetimes
    from chisurf.plugins.burst.burst_selection.api.features import proximity_ratio

    sample["bursts"] = int(row_count(session.df_bursts))
    sample["tau"] = {k: float(np.mean(v)) for k, v in burst_lifetimes(session.burst_results).items()}
    e = proximity_ratio(session.df_bursts)
    e = np.asarray(e, dtype=float) if e is not None else np.array([])
    sample["E"] = float(np.nanmean(e)) if np.isfinite(e).any() else None


def process_sample(
    recipe: Recipe,
    sample: dict,
    *,
    should_stop: Callable[[], bool] | None = None,
    on_stage: Callable[[str], Any] | None = None,
    pool: Any = None,
    workers: int | None = None,
    share: Callable[[], int] | None = None,
    calibration: Any = None,
) -> dict:
    """Run the recipe's pipeline on one *sample* (a :func:`new_sample` row, updated in place):
    search, optional steps, Burst MLE, then the calibration report and the recipe into its
    container. Raises what the failing step raised (the caller marks the sample failed).

    With *pool* (the process pool a batch shares, :func:`batch_pool`) the search, BVA and 2CDE
    run in it. Then *share()* (default *workers*) says how many of its processes this sample may
    count on now: one -- many samples in flight -- and everything after the search is a single
    task of the pool; more -- few samples left -- and the stages run here, Burst MLE's chunks
    fanned out over the pool. Without a pool, everything here and in the fit's own pool.

    *calibration* is the batch's :class:`Calibration` (or its shared-memory handle,
    :func:`publish_calibration`): computed once and given to every sample; without, it is
    prepared here (one sample alone)."""
    from chisurf.core.project.analysis import container_dir

    def stage(text: str) -> None:
        sample["stage"] = text
        if on_stage is not None:
            on_stage(text)

    handle = calibration if calibration is not None else prepare_calibration(recipe)
    path = Path(sample["path"])
    uid = str(sample.get("uid") or "")
    folder = container_dir(uid)
    stage("searching bursts")
    run, search = _search(handle, path, uid, folder, pool, should_stop)
    sample["search_model"] = search  # the caller registers the run in the workspace
    _check(should_stop)
    now = int(share() if callable(share) else (workers or 0))
    if pool is not None and now <= 1:
        # many samples in flight: everything after the search is one task of the pool (its fit
        # chunks in that worker), so the samples' stages run side by side on every core
        stage("analysing (one worker)")
        sample.update(_call(pool, should_stop, analyse_task, handle, str(run), str(path),
                            str(folder)))
    else:
        # few samples left: the stages here, the fit's chunks fanned out over the pool
        sample.update(_analyse(calibration_of(handle), run, path, folder, pool=pool,
                               workers=workers or None, should_stop=should_stop, stage=stage))
    stage("")
    return sample


#: What :func:`_analyse` gives a sample row.
RESULT_KEYS = ("run", "container", "recipe_id", "report_id", "bursts", "tau", "E")


def _analyse(calibration: Calibration, run: Path, path: Path, folder: Path, *, pool=None,
             workers=None, should_stop=None, stage=None) -> dict:
    """The stages after the search: fusion, BVA, 2CDE, Burst MLE, H2MM, then the calibration
    report and the recipe into the container. Returns :data:`RESULT_KEYS`."""
    from .calibration_report import write_report

    recipe = calibration.recipe
    stage = stage or (lambda _text: None)
    if "fusion" in recipe.optional:
        stage("fusing bursts")
        run = _fuse(recipe, run)
        _check(should_stop)
    for step, work in (("bva", _bva), ("two_cde", _two_cde)):
        if step in recipe.optional:
            stage(f"computing {STEP_LABELS[step]}")
            work(recipe, run, pool, should_stop)
            _check(should_stop)
    stage("fitting lifetimes")

    def progress(done: int, total: int) -> None:
        stage(f"fitting lifetimes {done}/{total}")

    session = _fit(calibration, run, should_stop, progress, workers)
    if "h2mm" in recipe.optional:
        stage("computing H2MM")
        _h2mm(recipe, run)
    stage("writing provenance")
    report = recipe.workflow.get("calibration_report") or {}
    if report:
        write_report(path, report, folder)
    out: dict = {
        "container": write_recipe(path, calibration, folder, runs=[str(run)]),
        "run": str(run),
        "recipe_id": calibration.recipe_id,
        "report_id": calibration.report_id,
    }
    _summarise(out, session)
    return out


class _InlineExecutor:
    """An executor that runs what it is given at once, here: Burst MLE's fit chunks inside the
    pool worker that analyses a sample (no pool started from a worker)."""

    def submit(self, fn, *args, **kwargs):
        future: concurrent.futures.Future = concurrent.futures.Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001 - delivered through the future
            future.set_exception(exc)
        return future

    def shutdown(self, *args, **kwargs) -> None:
        pass


def analyse_task(handle, run: str, path: str, folder: str) -> dict:
    """:func:`_analyse` of one sample in a worker of the batch pool, every stage in this process
    (the fit's chunks too); returns :data:`RESULT_KEYS`."""
    from chisurf.plugins.burst.burst_mle_analysis import engine

    pool_of = engine.fit_pool
    engine.fit_pool = lambda workers=None: _InlineExecutor()
    try:
        return _analyse(calibration_of(handle), Path(run), Path(path), Path(folder), workers=1)
    finally:
        engine.fit_pool = pool_of


def sample_tip(sample: dict) -> str:
    """Everything about a sample row that its short cells leave out."""
    lines = [str(sample.get("path", ""))]
    status = sample.get("status", "")
    if status == "running" and sample.get("stage"):
        lines.append(f"running: {sample['stage']}")
    elif status == "failed":
        lines.append(f"failed: {sample.get('error') or 'unknown error'}")
    elif status == "queued" and sample.get("error"):
        lines.append(str(sample["error"]))
    if sample.get("run"):
        lines.append(f"run: {Path(sample['run']).parent.name}/{Path(sample['run']).name}")
    for det, tau in (sample.get("tau") or {}).items():
        lines.append(f"mean τ {det}: {tau:.3f} ns")
    if sample.get("E") is not None:
        lines.append(f"mean E (proximity ratio): {sample['E']:.3f}")
    if sample.get("recipe_id"):
        lines.append(f"recipe {sample['recipe_id']}, calibration report {sample.get('report_id') or '—'}")
    return "\n".join(lines)


def sample_cells(sample: dict) -> dict[str, Any]:
    """The short cells of a sample row: name, bursts, mean τ, mean E, status."""
    tau = sample.get("tau") or {}
    first = next(iter(tau.values()), None)
    return {
        "name": sample.get("name", ""),
        "bursts": "" if sample.get("bursts") is None else str(int(sample["bursts"])),
        "tau": "" if first is None else f"{first:.2f}",
        "E": "" if sample.get("E") is None else f"{sample['E']:.2f}",
        "status": sample.get("status", ""),
    }


# -- many samples ------------------------------------------------------------------------------ #
#: Peak memory of one sample in flight, per byte of its photon file: the TTTR read in the
#: window's process and in a search worker, the burst table, the MLE session's per-photon arrays
#: and the fit's shared-memory copies. Measured as the summed physical footprint (compressed
#: pages included) of the process and its pool: 20 M photons (103 MB PTU) +3.73 GB, 2 M photons
#: (10 MB) +0.31 GB -- about 37 bytes per file byte, 190 bytes per photon (okf/plugins/burst.md).
MEMORY_PER_FILE_BYTE = 37.0
#: What a sample needs besides its photons (models, tables, the IRF and background patterns).
MEMORY_PER_SAMPLE = 100 * 1024**2
#: The share of the available memory a batch may plan for (the rest stays free: no swap).
MEMORY_SHARE = 0.6


def physical_cores() -> int:
    """The physical cores this process may run on (not hyper-threads)."""
    import os

    try:
        allowed = len(os.sched_getaffinity(0))  # type: ignore[attr-defined]
    except AttributeError:
        allowed = getattr(os, "process_cpu_count", os.cpu_count)() or 1
    try:
        import psutil

        physical = psutil.cpu_count(logical=False) or allowed
    except Exception:  # noqa: BLE001 - no psutil: the logical count
        physical = allowed
    return max(1, min(int(physical), int(allowed)))


def core_budget() -> int:
    """Worker processes a batch uses in all: the physical cores but one (the window's and the
    sample threads'), never more than the burst fit's own limit -- its pool is the one shared."""
    from chisurf.plugins.burst.burst_mle_analysis.engine import fit_workers

    cores = physical_cores()
    return max(1, min(int(fit_workers()), cores - 1 if cores > 1 else 1))


def batch_pool(budget: int | None = None):
    """The one process pool of a batch: Burst MLE's fit pool at *budget* processes. The searches,
    BVA and 2CDE of every sample are tasks in it, and every sample's fit chunks go into it, so
    the batch never runs more than *budget* worker processes."""
    from chisurf.plugins.burst.burst_mle_analysis.engine import fit_pool

    return fit_pool(int(budget or core_budget()))


def sample_memory(path: str | Path) -> int:
    """What one sample needs in memory while it is processed, bytes (from its file's size)."""
    try:
        size = Path(path).stat().st_size
    except OSError:
        size = 0
    return int(size * MEMORY_PER_FILE_BYTE + MEMORY_PER_SAMPLE)


def available_memory() -> int:
    """The memory a batch may plan for, bytes (:data:`MEMORY_SHARE` of what is available)."""
    try:
        import psutil

        free = psutil.virtual_memory().available
    except Exception:  # noqa: BLE001 - unknown: assume 4 GB free
        free = 4 * 1024**3
    return int(free * MEMORY_SHARE)


def concurrent_samples(paths: Iterable[str | Path], budget: int | None = None,
                       memory: int | None = None) -> int:
    """How many samples are in flight at once: every one while there are cores (one process
    each at least) and memory for them -- the largest first, so the bound holds whichever run
    together; at least one."""
    sizes = sorted((sample_memory(p) for p in paths), reverse=True)
    if not sizes:
        return 1
    budget = int(budget or core_budget())
    memory = available_memory() if memory is None else int(memory)
    n, used = 0, 0
    for size in sizes[:budget]:
        if n and used + size > memory:
            break
        used += size
        n += 1
    return max(1, n)


class SampleQueue:
    """The samples of step 4 and the work on them, off the caller's thread.

    :meth:`start` processes every sample that is not done (or the ones named) with a recipe, in a
    thread; :attr:`running`, :attr:`progress` and :meth:`stop` are what the busy overlay reads;
    :meth:`poll` hands the samples finished since the last poll to the caller's thread (where the
    hub registers their runs in the workspace). :meth:`run` is the same work on the caller's thread.
    """

    def __init__(self) -> None:
        self.samples: list[dict] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._finished: list[dict] = []
        self._total = 0
        self.recipe: Recipe | None = None
        #: Worker processes of the batch running (:func:`core_budget`; 0 before one).
        self.budget = 0
        #: Called (from the worker) whenever a sample changes; a window wakes its frame loop.
        self.on_change: Callable[[], Any] | None = None

    # -- the list -------------------------------------------------------------------------- #
    def paths(self) -> list[str]:
        return [s["path"] for s in self.samples]

    def add(self, paths: Iterable[str | Path], uids: Iterable[str] = ()) -> int:
        """Queue measurements not listed yet; returns how many were added."""
        paths = [Path(str(p)) for p in paths]
        uids = list(uids) + [""] * len(paths)
        known = {str(Path(p).resolve()) for p in self.paths()}
        added = 0
        with self._lock:
            for path, uid in zip(paths, uids):
                key = str(path.resolve())
                if key in known:
                    if key in known and uid:  # handed again with its dataset: keep the uid
                        for s in self.samples:
                            if str(Path(s["path"]).resolve()) == key and not s["uid"]:
                                s["uid"] = str(uid)
                    continue
                known.add(key)
                self.samples.append(new_sample(path.resolve(), uid))
                added += 1
        return added

    def remove(self, path: str) -> bool:
        with self._lock:
            for index, sample in enumerate(self.samples):
                if sample["path"] == path and sample["status"] != "running":
                    self.samples.pop(index)
                    return True
        return False

    def clear(self) -> None:
        with self._lock:
            self.samples = [s for s in self.samples if s["status"] == "running"]

    def find(self, path: str) -> dict | None:
        return next((s for s in self.samples if s["path"] == path), None)

    def counts(self) -> dict[str, int]:
        out = dict.fromkeys(STATUSES, 0)
        for sample in self.samples:
            out[sample["status"]] = out.get(sample["status"], 0) + 1
        return out

    # -- the work --------------------------------------------------------------------------- #
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def progress(self) -> tuple[int, int]:
        """``(samples finished, samples of this run)``."""
        done = sum(1 for s in self.samples if s.get("_batch") and s["status"] in ("done", "failed"))
        return done, self._total

    def message(self) -> str:
        """What the queue is doing, in one line (the busy card's)."""
        running = [s for s in self.samples if s["status"] == "running"]
        done, total = self.progress
        if not running:
            return f"{done}/{total} samples processed" if total else ""
        first = running[0]
        return f"Sample {done + 1}/{total}: {first['name']} — {first.get('stage') or 'starting'}"

    def stop(self) -> None:
        """Stop after the step each running sample is in; the samples not started stay queued."""
        self._stop.set()

    def _targets(self, only: Iterable[str] | None) -> list[dict]:
        if only is not None:
            wanted = set(only)
            return [s for s in self.samples if s["path"] in wanted and s["status"] != "running"]
        return [s for s in self.samples if s["status"] in ("queued", "failed")]

    def start(self, recipe: Recipe, only: Iterable[str] | None = None,
              workers: int | None = None) -> bool:
        """Process the samples not done yet (or *only* these paths, again) in a thread; ``False``
        when nothing was started (running already, nothing to do, or no recipe)."""
        if self.running or recipe is None or not recipe.ready:
            return False
        targets = self._prepare(recipe, only)
        if not targets:
            return False
        self._thread = threading.Thread(
            target=self._work, args=(recipe, targets, workers), name="burst-more-samples", daemon=True
        )
        self._thread.start()
        return True

    def run(self, recipe: Recipe, only: Iterable[str] | None = None,
            workers: int | None = None) -> list[dict]:
        """The work of :meth:`start` on this thread; returns the samples processed."""
        if not recipe.ready:
            raise ValueError("the recipe is not complete: run 3. Burst MLE on the first data first")
        targets = self._prepare(recipe, only)
        self._work(recipe, targets, workers)
        return targets

    def _prepare(self, recipe: Recipe, only) -> list[dict]:
        self._stop.clear()
        self.recipe = recipe
        with self._lock:
            for sample in self.samples:
                sample.pop("_batch", None)
            targets = self._targets(only)
            for sample in targets:
                sample.update(status="queued", stage="", error="", _batch=True)
            self._total = len(targets)
        return targets

    def _changed(self) -> None:
        if callable(self.on_change):
            try:
                self.on_change()
            except Exception:  # noqa: BLE001 - a window that cannot be woken redraws later
                pass

    def _one(self, recipe: Recipe, sample: dict, pool=None, budget: int | None = None,
             calibration=None) -> None:
        if self._stop.is_set():
            return
        sample.update(status="running", stage="starting", error="")
        self._changed()
        try:
            process_sample(recipe, sample, should_stop=self._stop.is_set,
                           on_stage=lambda _text: self._changed(), pool=pool, workers=budget,
                           share=None if pool is None else self.share, calibration=calibration)
            sample["status"] = "done"
        except (SampleStopped, InterruptedError):
            sample.update(status="queued", stage="", error="Stopped before it finished; Run goes on.")
        except Exception as exc:  # noqa: BLE001 - one failed sample never stops the others
            logger.warning("More samples: %s failed: %s", sample["name"], exc, exc_info=True)
            sample.update(status="failed", stage="", error=str(exc) or type(exc).__name__)
        with self._lock:
            self._finished.append(sample)
        self._changed()

    def _work(self, recipe: Recipe, targets: list[dict], workers: int | None) -> None:
        """Every target through the pipeline: up to *workers* samples in flight (default: as many
        as cores and memory allow, :func:`concurrent_samples`), each admitted while the memory of
        those in flight leaves room for it, their stages overlapping in the one process pool of
        :func:`core_budget` processes (sample 2 searches while sample 1 fits)."""
        if not targets:
            return
        budget = core_budget()
        limit = max(1, min(int(workers or budget), budget, len(targets)))
        memory = available_memory()
        pool = batch_pool(budget)
        self.budget = budget
        # the calibration once for the batch, in one shared block every worker reads once
        try:
            calibration = prepare_calibration(recipe)
        except Exception as exc:  # noqa: BLE001 - nothing can run: every sample says why
            logger.warning("More samples: the calibration could not be prepared: %s", exc, exc_info=True)
            for sample in targets:
                sample.update(status="failed", stage="", error=f"calibration: {exc}")
                with self._lock:
                    self._finished.append(sample)
            self._changed()
            return
        handle, block = publish_calibration(calibration)
        try:
            self._schedule(recipe, targets, limit, memory, pool, budget, handle)
        finally:
            block.close()
            block.unlink()

    def _schedule(self, recipe, targets, limit, memory, pool, budget, handle) -> None:
        """Admit the samples into flight (cores, memory) until every one is done or Stop."""
        pending = list(targets)
        running: dict = {}
        self._in_flight = lambda: len(running)
        with concurrent.futures.ThreadPoolExecutor(max_workers=limit,
                                                   thread_name_prefix="burst-sample") as threads:
            while pending or running:
                while pending and len(running) < limit and not self._stop.is_set():
                    need = sample_memory(pending[0]["path"])
                    if running and sum(running.values()) + need > memory:
                        break  # waits until a sample in flight has given its memory back
                    sample = pending.pop(0)
                    running[threads.submit(self._one, recipe, sample, pool, budget, handle)] = need
                if self._stop.is_set():
                    pending = []
                if not running:
                    break
                done, _ = concurrent.futures.wait(
                    list(running), timeout=0.2, return_when=concurrent.futures.FIRST_COMPLETED
                )
                for future in done:
                    running.pop(future)

    def share(self) -> int:
        """The worker processes one sample may count on now: the batch's, divided among the
        samples in flight -- more each as fewer are left."""
        in_flight = getattr(self, "_in_flight", None)
        n = in_flight() if callable(in_flight) else 1
        return max(1, int(self.budget or 1) - max(1, n) + 1)

    def poll(self) -> list[dict]:
        """The samples finished since the last poll (on the caller's thread)."""
        with self._lock:
            out, self._finished = self._finished, []
        return out

    # -- persistence ------------------------------------------------------------------------- #
    def export(self) -> list[dict]:
        """The rows, JSON-ready (a running sample is kept as queued)."""
        keep = ("path", "name", "uid", "status", "error", "bursts", "tau", "E", "run", "container",
                "recipe_id", "report_id")
        rows = []
        for s in self.samples:
            row = {k: s.get(k) for k in keep}
            if row["status"] == "running":
                row["status"] = "queued"
            rows.append(_plain(row))
        return rows

    def restore(self, rows: Iterable[dict] | None) -> None:
        self.samples = []
        for row in rows or ():
            if not isinstance(row, dict) or not row.get("path"):
                continue
            sample = new_sample(row["path"], row.get("uid", ""))
            sample.update({k: v for k, v in row.items() if k in sample})
            if sample["status"] not in STATUSES or sample["status"] == "running":
                sample["status"] = "queued"
            self.samples.append(sample)


def register_sample(sample: dict) -> None:
    """Show a processed sample in the workspace: its run under its photon dataset (Burst
    Selection's :func:`register_runs`)."""
    model = sample.pop("search_model", None)
    if model is None or sample.get("status") != "done":
        return
    try:
        from chisurf.plugins.burst.burst_selection.gui.native import register_runs

        register_runs(model, getattr(model, "sources", None) or {})
    except Exception:  # noqa: BLE001 - the run is in the container either way
        logger.debug("registering the run of %s", sample.get("name"), exc_info=True)


def process_more(
    recipe: Recipe,
    paths: Iterable[str | Path],
    uids: Iterable[str] = (),
    *,
    workers: int | None = None,
    register: bool = True,
) -> list[dict]:
    """Process further measurements *paths* with *recipe*, to the end, on this thread.

    Each is searched, analysed and fitted as the first data was; its runs, its calibration report
    and the recipe go into its analysis container. A sample that fails is marked ``failed`` (with
    the error) and the others go on.

    Returns
    -------
    list of dict
        One row per sample: ``path``, ``name``, ``status`` (``done`` / ``failed``), ``error``,
        ``bursts``, ``tau`` (``{detector: mean τ in ns}``), ``E`` (mean proximity ratio, ``None``
        for one colour), ``run``, ``container``, ``recipe_id``, ``report_id``.
    """
    queue = SampleQueue()
    queue.add(paths, uids)
    queue.run(recipe, workers=workers)
    for sample in queue.poll():
        if register:
            register_sample(sample)
        sample.pop("search_model", None)
    return queue.export()


__all__ = [
    "OPTIONAL_STEPS",
    "RECIPE_NAME",
    "SCHEMA",
    "STATUSES",
    "Recipe",
    "SampleQueue",
    "new_sample",
    "process_more",
    "process_sample",
    "read_recipe",
    "register_sample",
    "sample_cells",
    "sample_tip",
    "batch_pool",
    "concurrent_samples",
    "core_budget",
    "physical_cores",
    "sample_memory",
    "write_recipe",
]
