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


def _search(recipe: Recipe, path: Path, uid: str) -> tuple[Path, Any]:
    """Burst Selection's search, through its model (the run goes into the container of the
    measurement's photon dataset); the run written and the model."""
    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel

    from .workflow_context import searched_runs

    from chisurf.core.fio.staging import open_tttr

    try:  # said plainly here: the search's own worker reports an unreadable file as "Unknown"
        open_tttr(str(path))
    except Exception as exc:  # noqa: BLE001 - the sample fails with the reason
        reason = str(exc).replace(str(path), path.name).split(". ")[0]
        raise ValueError(f"{path.name} cannot be read as a photon stream: {reason}") from exc
    model = BurstSelectionModel()
    model.set_setup({**recipe.setup, "setup_name": recipe.setup_name})
    model.import_settings(recipe.selection)
    # the pipeline writes .pto only; zipped folders are Legacy Export's
    model.zip_output = model.remove_folder = False
    if not model.add_paths([path]):
        raise ValueError(f"{path.name} is not a photon file Burst Selection reads")
    model.sources = {str(Path(p).resolve()): uid for p in model.files} if uid else {}
    why = model.prepare_run(force=True)
    if why is not None:
        raise RuntimeError(why)
    result = model.run()
    runs = searched_runs(result, model.files)
    if not runs:
        raise RuntimeError(f"the burst search wrote no run ({model.status_text})")
    return runs[0], model


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


def _bva(recipe: Recipe, run: Path) -> None:
    from .gui.background_tasks import bva_task

    settings = dict(recipe.optional["bva"])
    fingerprint, inputs, params = _stamp_args("bva", run, settings)
    _columns, note = bva_task(str(run), settings, True, fingerprint, inputs, params)
    if note:
        raise RuntimeError(note.strip(" ()"))


def _two_cde(recipe: Recipe, run: Path) -> None:
    from .gui.background_tasks import two_cde_task

    settings = dict(recipe.optional["two_cde"])
    fingerprint, inputs, params = _stamp_args("two_cde", run, settings)
    _columns, _variant, note = two_cde_task(str(run), settings, fingerprint, inputs, params)
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


def _fit(recipe: Recipe, run: Path, path: Path, should_stop, progress) -> Any:
    """Burst MLE: the bursts handed over as the hub hands them (the background of this
    measurement, the buffer's when there is one), then the recipe's IRF, shifts, model and fit
    window; fitted and written into the container. Returns the session."""
    from chisurf.plugins.burst.burst_mle_analysis.engine import MleSettings
    from chisurf.plugins.burst.burst_mle_analysis.gui.model import MleViewModel

    model = MleViewModel()
    model.split_by_state = bool(recipe.mle.get("split_by_state", False))
    model.take_bursts([str(run)], recipe.setup, [str(path)], recipe.references())
    session = model.session
    if session.df_bursts is None:
        raise RuntimeError("Burst MLE read no bursts from the run")
    known = set(MleSettings.__dataclass_fields__)
    settings = (recipe.mle.get("settings") or {}).get("detector_settings") or {}
    for det, values in settings.items():
        if det in session.detectors:
            session.det_settings[det] = MleSettings(
                **copy.deepcopy({k: v for k, v in values.items() if k in known})
            )
    for det, irf in (recipe.mle.get("irf") or {}).items():
        if det in session.detectors and np.asarray(irf).size:
            session.irf_np[det] = np.asarray(irf, dtype=float)
            source = (recipe.mle.get("irf_source") or {}).get(det, "")
            session.irf_source[det] = f"the recipe ({source})" if source else "the recipe"
    for det, entry in (recipe.mle.get("shift_calibration") or {}).items():
        if det in session.detectors:
            session.shift_calibration[det] = dict(entry)
    session.outcome = None
    _check(should_stop)
    session.run_batch(progress=progress, should_stop=should_stop)
    _check(should_stop)
    session.export_results()
    return session


def write_recipe(source: str | Path, recipe: Recipe, out_dir: str | Path | None = None,
                 runs: Iterable[str] = ()) -> str:
    """Write *recipe* into the container of the measurement *source* (replacing the one written
    before), derived from its photon streams, with the runs it made; returns the container."""
    from chisurf.core.fio.fluorescence.burst_container import open_measurement

    payload = {**recipe.to_payload(), "recipe_id": recipe.recipe_id,
               "calibration_report_id": recipe.calibration_report_id, "runs": list(runs)}
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
            parameters={"schema": SCHEMA, "recipe_id": recipe.recipe_id,
                        "calibration_report_id": recipe.calibration_report_id},
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
) -> dict:
    """Run the recipe's pipeline on one *sample* (a :func:`new_sample` row, updated in place):
    search, optional steps, Burst MLE, then the calibration report and the recipe into its
    container. Raises what the failing step raised (the caller marks the sample failed)."""
    from chisurf.core.project.analysis import container_dir

    from .calibration_report import write_report

    def stage(text: str) -> None:
        sample["stage"] = text
        if on_stage is not None:
            on_stage(text)

    if not recipe.ready:
        raise ValueError("the recipe is not complete: run 3. Burst MLE on the first data first")
    path = Path(sample["path"])
    uid = str(sample.get("uid") or "")
    folder = container_dir(uid)
    stage("searching bursts")
    run, search = _search(recipe, path, uid)
    sample["search_model"] = search  # the caller registers the run in the workspace
    _check(should_stop)
    if "fusion" in recipe.optional:
        stage("fusing bursts")
        run = _fuse(recipe, run)
        _check(should_stop)
    for step, work in (("bva", _bva), ("two_cde", _two_cde)):
        if step in recipe.optional:
            stage(f"computing {STEP_LABELS[step]}")
            work(recipe, run)
            _check(should_stop)
    stage("fitting lifetimes")

    def progress(done: int, total: int) -> None:
        stage(f"fitting lifetimes {done}/{total}")

    session = _fit(recipe, run, path, should_stop, progress)
    if "h2mm" in recipe.optional:
        stage("computing H2MM")
        _h2mm(recipe, run)
    stage("writing provenance")
    report = recipe.workflow.get("calibration_report") or {}
    if report:
        write_report(path, report, folder)
    sample["container"] = write_recipe(path, recipe, folder, runs=[str(run)])
    sample["run"] = str(run)
    sample["recipe_id"] = recipe.recipe_id
    sample["report_id"] = recipe.calibration_report_id
    _summarise(sample, session)
    stage("")
    return sample


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
def sample_workers(paths: Iterable[str | Path], uids: Iterable[str] = ()) -> int:
    """How many samples are processed at once: as many processes as the burst search would use for
    these files (one per file, never more than its cap and the cores; one for small files)."""
    from chisurf.core.project.analysis import container_dir
    from chisurf.plugins.burst.burst_selection.api.selection import _search_workers

    paths = [str(p) for p in paths]
    uids = list(uids) + [""] * len(paths)
    request = SimpleNamespace(
        files=paths, output_dir=None,
        container_dirs={p: str(container_dir(u)) for p, u in zip(paths, uids)},
    )
    try:
        return max(1, int(_search_workers(request, None)))
    except Exception:  # noqa: BLE001 - one at a time
        return 1


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

    def _one(self, recipe: Recipe, sample: dict) -> None:
        if self._stop.is_set():
            return
        sample.update(status="running", stage="starting", error="")
        self._changed()
        try:
            process_sample(recipe, sample, should_stop=self._stop.is_set,
                           on_stage=lambda _text: self._changed())
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
        if not targets:
            return
        n = workers or sample_workers([s["path"] for s in targets], [s["uid"] for s in targets])
        n = max(1, min(int(n), len(targets)))
        if n == 1:
            for sample in targets:
                self._one(recipe, sample)
            return
        # the fit processes are shared: started once, before the samples ask for them together
        from chisurf.plugins.burst.burst_mle_analysis.engine import fit_pool

        fit_pool()
        with concurrent.futures.ThreadPoolExecutor(max_workers=n, thread_name_prefix="burst-sample") as pool:
            list(pool.map(lambda s: self._one(recipe, s), targets))

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
    "sample_workers",
    "write_recipe",
]
