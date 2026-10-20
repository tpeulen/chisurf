"""The QuEst window's *Analysis* page: the inverse analysis of measured site lifetimes, drawn by emtk.

The forward simulator (:mod:`.card`) predicts the lifetime of a dye at one site from the structure. This page runs
the other direction: from the measured lifetimes on many labelled sites, the free-dye amino-acid titrations and the
structures, it fits what the dye's quenching chemistry and stickiness must be (the stages of
``settings/analysis/stages.yaml``; theory in ``docs/concepts/quenching_inference.md``).

Two halves, as everywhere in the plugin:

- :class:`AnalysisModel` is Qt-free and draws nothing. It is the AutoForm model of ``analysis.view.json``: the
  attributes the spec's fields edit, the actions its buttons call, and the table sources (``tables.<name>.rows`` /
  ``.columns``; the columns are the declared ones of ``settings/analysis/*.yaml``, so a renamed column is a settings
  change). Loading, building site tables and running stages happen on a worker thread
  (:meth:`AnalysisModel.poll` hands the result over on the UI thread), so the frame never blocks; progress and cancel
  are the callback shapes the headless entry (:mod:`..core.inference.stages`) takes.
- :class:`AnalysisCard` is the window: the spec's two panels as dock windows, its tables, and the implot drawings of
  the ``custom`` ``analysis_plot`` sections (Stern-Volmer, hyper-posterior, water bars, kQ, site exposure, parity,
  forest, leave-one-out, profile, slopes before/after, water access, exposure histograms, scale B vs C, summary).

The page has a ``?`` help of its own (``analysis_help.md``) and a guided tour (``analysis_guide.json``) whose first
step is **Load example**: the shipped MalE data set, staged by :func:`..demo.analysis_demo`.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from emtk import im, implot
from emtk.docking import DockManager, Region, Split
from emtk.i18n import tr
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.card_shell import CardShell, Rows
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

_LOG = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
SPEC_PATH = HERE / "analysis.view.json"
HELP_PATH = HERE / "analysis_help.md"
GUIDE_PATH = HERE / "analysis_guide.json"

#: The measurement tables a data folder must hold (the reader's file names).
DATA_FILES = ("tcspc_fit_results.csv", "amino_acid_quenching_flt.csv", "titration_summary.csv")

#: Line colours of the dyes and solvents (RGBA 0-255).
DYE_COLOURS = {
    "AF488": (44, 160, 44, 255),
    "Cy3B": (255, 127, 14, 255),
    "Atto655": (214, 39, 40, 255),
}
SOLVENT_COLOURS = {"H2O": (31, 119, 180, 255), "D2O": (148, 103, 189, 255)}
PALETTE = (
    (31, 119, 180, 255),
    (255, 127, 14, 255),
    (44, 160, 44, 255),
    (214, 39, 40, 255),
    (148, 103, 189, 255),
    (140, 86, 75, 255),
    (227, 119, 194, 255),
    (127, 127, 127, 255),
)
GREY = (128, 128, 128, 255)

#: Plot heights (pixels) by drawing; the rest are :data:`PLOT_HEIGHT`.
PLOT_HEIGHT = 260.0
PLOT_HEIGHTS = {"loo": 200.0, "k_graph": 230.0, "summary_scale": 220.0}


def _colour(i: int) -> tuple:
    return PALETTE[i % len(PALETTE)]


def _arr(values) -> np.ndarray:
    return np.asarray(values if values is not None else [], dtype=float)


# --------------------------------------------------------------------------------------------
# tables


class TableView:
    """One table of the page: ``rows()`` and ``columns()`` for a ``data_table`` section.

    Parameters
    ----------
    model : AnalysisModel
    getter : callable
        ``getter(model) -> numpy record array, list of dict, or None``.
    declaration : tuple of (pathlib.Path, str), optional
        The YAML file and table name whose declared columns head the table.
    hidden : sequence of str, optional
        Declared columns not shown (they hold one value for the whole table, e.g. the data set).
    """

    def __init__(self, model: AnalysisModel, getter: Callable, declaration=None, hidden=()) -> None:
        self.model = model
        self.getter = getter
        self.declaration = declaration
        self.hidden = set(hidden)
        self._rows: Rows | None = None
        self._revision = -1
        self._columns: list | None = None

    def rows(self) -> Rows:
        """The rows (rebuilt only when the model's revision moved, so a selection survives frames)."""
        if self._rows is None or self._revision != self.model.revision:
            data = None
            try:
                data = self.getter(self.model)
            except (AttributeError, KeyError):  # nothing loaded or run yet: an empty table
                data = None
            except Exception:  # noqa: BLE001 - shown empty, but said: a silent blank hides a defect
                _LOG.exception("QuEst analysis table could not be built")
                data = None
            rows = Rows(_records(data))
            rows.revision = self.model.revision
            self._rows, self._revision = rows, self.model.revision
        return self._rows

    def columns(self) -> list:
        """The declared columns: title, units, description as tooltip, a number format."""
        if self._columns is None:
            columns = declared_columns(*self.declaration) if self.declaration else []
            for c in columns:
                if c["key"] in self.hidden:  # the same in every row of the shown data set
                    c["visible"] = False
            self._columns = columns
        return self._columns


def _records(data) -> list:
    """Plain dicts of a record array or a list of dicts (NaN stays NaN, the table shows N/A)."""
    if data is None:
        return []
    if isinstance(data, np.ndarray):
        names = data.dtype.names or ()
        return [{n: (r[n].item() if hasattr(r[n], "item") else r[n]) for n in names} for r in data]
    return [dict(r) for r in data]


def declared_columns(path: Path, table: str) -> list[dict]:
    """The columns of a declared table as ``data_table`` column specs.

    Parameters
    ----------
    path : pathlib.Path
        Declaration file (``settings/analysis/*.yaml``).
    table : str
        Table name in it.

    Returns
    -------
    list of dict
        ``key``, ``title``, ``units``, ``description`` (the tooltip) and ``format`` for floats.
    """
    from chisurf.plugins.quenching_estimator.core.inference import columns as _columns

    out = []
    for c in _columns.columns(table, path):
        spec = {
            "key": c["column"],
            "title": c["column"],
            "description": str(c.get("description", "")),
        }
        units = str(c.get("units") or "")
        if units:
            spec["units"] = units
        if c.get("dtype") == "float":
            spec["format"] = "%.4g"
        if c.get("dtype") in ("int", "str"):
            spec["shade"] = False
        out.append(spec)
    return out


def _paths() -> dict[str, Path]:
    from chisurf.plugins.quenching_estimator.core.inference import columns as _columns
    from chisurf.plugins.quenching_estimator.core.inference import graph_fit as _gf
    from chisurf.plugins.quenching_estimator.core.inference import site_table as _st

    return {
        "measurement": _columns.MEASUREMENT_COLUMNS,
        "result": _gf.RESULT_COLUMNS,
        "site": _st.SITE_MODEL,
    }


class Tables:
    """The page's tables by name (the spec's ``tables.<name>.rows`` / ``.columns``)."""

    def __init__(self, model: AnalysisModel) -> None:
        p = _paths()
        m, r, s = p["measurement"], p["result"], p["site"]
        self.k_posterior = TableView(model, lambda md: md.data.posterior.table, (m, "k_posterior"))
        self.site_lifetimes = TableView(
            model, lambda md: md.data.errors.data, (m, "site_lifetimes")
        )
        self.free_dye_lifetimes = TableView(
            model, lambda md: md.free_dye_rows(), (m, "free_dye_lifetimes")
        )
        self.kq_contact = TableView(model, lambda md: md.kq.as_table(), (m, "kq_contact"))
        self.site_tables = TableView(model, lambda md: md.site_table_rows())
        self.estimates = TableView(
            model,
            lambda md: md.block_table("estimates"),
            (r, "fit_estimates"),
            ("graph", "block", "dye"),
        )
        self.predictions = TableView(
            model,
            lambda md: md.block_table("predictions"),
            (r, "fit_predictions"),
            ("graph", "block", "dye"),
        )
        self.titration_slopes = TableView(
            model,
            lambda md: md.stage_table("titration_slopes"),
            (r, "graph_titration_slopes"),
            ("graph",),
        )
        self.water_access = TableView(
            model, lambda md: md.stage_table("water_access", "C"), (r, "water_access_model")
        )
        self.exposure = TableView(
            model, lambda md: md.stage_table("exposure", "C"), (s, "site_exposure")
        )
        self.dye_summary = TableView(
            model, lambda md: md.stage_table("dyes", "summary"), (r, "dye_summary")
        )


# --------------------------------------------------------------------------------------------
# the model


class AnalysisModel:
    """The Analysis page's state and actions (Qt-free; the AutoForm model of ``analysis.view.json``).

    Parameters
    ----------
    library : object, optional
        Site models (``.site(state, site, linker_length)``) instead of the default
        :class:`~..core.inference.site_model.SiteLibrary` on the shipped structures (a test's stand-in).
    fit_overrides : dict, optional
        Fit settings replacing the preset's (a test's short searches).
    cache_dir : str or pathlib.Path, optional
        Site-table cache folder (the settings cache by default).
    """

    def __init__(self, library=None, fit_overrides=None, cache_dir=None) -> None:
        self.library_override = library
        self.fit_overrides = fit_overrides
        self.cache_dir = cache_dir
        # the spec's fields
        self.data_folder = ""
        self.preset = "quick"
        self.stage_selection = "all"
        self.workers = 0
        self.profile = True
        self.data_dye = ""
        self.view_stage = ""
        self.view_block = ""
        # state
        self.data = None
        self.kq = None
        self.analysis = None
        self.site_models: dict[tuple, Any] = {}
        self.selected_site: tuple | None = None
        self.busy = ""
        self.progress_fraction: float | None = 0.0
        self.progress_message = ""
        self.status = tr("Press Load example, or pick a data folder.")
        self.status_error = False
        self.revision = 0
        self.dialog_request: dict | None = None
        self.used_hook: Callable[[str], None] | None = None
        self.wake: Callable[[], None] | None = None
        self._cancel = threading.Event()
        self._finished: tuple | None = None
        self._started = 0.0
        self.tables = Tables(self)

    # ---- what the spec reads

    def stage_options(self) -> list[str]:
        """``all`` and the declared stages."""
        from chisurf.plugins.quenching_estimator.core.inference import stages

        return ["all", *stages.stage_names()]

    def dye_options(self) -> list[str]:
        """The titrated dyes of the loaded data."""
        if self.data is None:
            return []
        return sorted({str(d) for d in self.data.posterior.table["dye"]})

    def fit_stage_options(self) -> list[str]:
        """Stages run so far that have data sets (A, B, the naive test, C)."""
        stages = self.result_stages()
        return [n for n, s in stages.items() if any(k.startswith("parity:") for k in s.plots)]

    def block_options(self) -> list[str]:
        """The data sets of the shown stage."""
        stage = self.result_stages().get(self.view_stage)
        if stage is None:
            return []
        return [k[len("parity:") :] for k in stage.plots if k.startswith("parity:")]

    def progress_text(self) -> str:
        if not self.busy:
            return ""
        elapsed = time.monotonic() - self._started
        return f"{self.progress_message}  ({elapsed:.0f} s)"

    def state_text(self) -> str:
        return tr("State: {status}").format(status=self.status)

    def stage_text(self) -> str:
        stage = self.result_stages().get(self.view_stage)
        if stage is None:
            return tr("No result yet: press Run.")
        return f"#### {stage.title}\n\n{stage.text}" if stage.text else f"#### {stage.title}"

    def summary_text(self) -> str:
        stage = self.result_stages().get("summary")
        if stage is None:
            return tr("The summary appears once the summary stage has run (Stages: all).")
        return stage.text

    def enabled(self, name: str) -> bool:
        """Which actions are usable now (``view_form``'s hook)."""
        if name == "cancel_analysis":
            return bool(self.busy)
        if name in ("run_analysis", "build_site_tables"):
            return not self.busy and self.data is not None
        if name == "write_results":
            return not self.busy and bool(self.result_stages())
        if name in ("load_example", "choose_folder"):
            return not self.busy
        return True

    # ---- data behind the tables and plots

    def result_stages(self) -> dict:
        return self.analysis.result.stages if self.analysis is not None else {}

    def free_dye_rows(self) -> list[dict]:
        tau0 = self.data.errors.tau0
        return [dict(dye=d, solvent=s, tau0=float(v)) for (d, s), v in sorted(tau0.items())]

    def stage_table(self, name: str, stage: str | None = None):
        s = self.result_stages().get(stage or self.view_stage)
        return None if s is None else s.tables.get(name)

    def block_table(self, name: str):
        table = self.stage_table(name)
        if table is None or "block" not in (table.dtype.names or ()):
            return table
        return table[table["block"] == self.view_block]

    def stage_plot(self, key: str, stage: str | None = None):
        s = self.result_stages().get(stage or self.view_stage)
        return None if s is None else s.plots.get(key)

    def site_keys(self) -> list[tuple[str, str, int, float]]:
        """``(dye, state, site, linker_length)`` of every measured site the declared graphs read."""
        if self.data is None:
            return []
        from chisurf.plugins.quenching_estimator.core.inference import stages

        lengths = self.data.site_settings["linker_lengths"]
        keys = []
        for graph in stages.stage_settings()["graphs"].values():
            for block in graph["blocks"]:
                dye = block["dye"]
                for solvent in block["solvents"]:
                    for r in self.data.rows(dye, solvent):
                        key = (dye, str(r["state"]), int(r["site"]), float(lengths[dye]))
                        if key not in keys:
                            keys.append(key)
        return keys

    def site_table_rows(self) -> list[dict]:
        rows = []
        for (dye, state, site, length), model in sorted(self.site_models.items()):
            table = getattr(model, "table", None)
            exposure = getattr(table, "exposure", getattr(model, "exposure", None))
            neighbours = getattr(table, "neighbours", None)
            rows.append(
                dict(
                    key=f"{dye}:{state}:{site}",
                    dye=dye,
                    state=state,
                    site=site,
                    linker_length=length,
                    positions=int(getattr(model, "n_positions", 0) or len(_arr(exposure))),
                    distinct=int(np.size(getattr(model, "count", ()))),
                    exposure=float(np.mean(np.clip(_arr(exposure), 0, 1)))
                    if exposure is not None
                    else math.nan,
                    neighbours=float(np.mean(np.asarray(neighbours, float).sum(1)))
                    if neighbours is not None
                    else math.nan,
                )
            )
        return rows

    def select_site_table(self, record) -> None:
        if isinstance(record, dict):
            self.selected_site = (record["dye"], record["state"], int(record["site"]))

    def selected_site_exposure(self) -> np.ndarray | None:
        if self.selected_site is None:
            return None
        for (dye, state, site, _), model in self.site_models.items():
            if (dye, state, site) == self.selected_site:
                table = getattr(model, "table", None)
                return np.clip(
                    _arr(getattr(table, "exposure", getattr(model, "exposure", None))), 0, 1
                )
        return None

    def stern_volmer(self) -> list[dict]:
        """Per amino acid of :attr:`data_dye`: the points (M, tau0/tau - 1) and the posterior line."""
        if self.data is None:
            return []
        pts = self.data.measurements.titration_points
        post = self.data.posterior.table
        out = []
        for aa in sorted({str(a) for a in pts["amino_acid"][pts["dye"] == self.data_dye]}):
            here = pts[(pts["dye"] == self.data_dye) & (pts["amino_acid"] == aa)]
            x = np.asarray(here["concentration_mM"], float) / 1000.0
            y = np.asarray(here["tau0_ns"], float) / np.asarray(here["tau_x"], float) - 1.0
            k = post[(post["dye"] == self.data_dye) & (post["amino_acid"] == aa)]
            ksv = float(k["ksv"][0]) if len(k) else math.nan
            out.append(dict(amino_acid=aa, x=x, y=y, ksv=ksv))
        return out

    def water_rows(self) -> list[dict]:
        if self.data is None:
            return []
        w = self.data.errors.water
        w = w[w["dye"] == self.data_dye]
        return [dict(state=str(r["state"]), site=int(r["site"]), kq_w=float(r["kq_w"])) for r in w]

    # ---- actions

    def load_example(self) -> None:
        """Stage the shipped MalE data set and choose the quick preset."""
        from chisurf.plugins.quenching_estimator.demo import analysis_demo

        try:
            folder, preset = analysis_demo()
        except Exception as exc:  # noqa: BLE001 - shown in the window
            self.say(tr("Failed to stage the example: {error}").format(error=exc), True)
            return
        if preset != self.preset:
            self.preset = preset
        self.open_folder(str(folder))

    def choose_folder(self) -> None:
        """Ask the window for a measurement folder."""
        self.dialog_request = {
            "kind": "data_folder",
            "title": tr("Choose a measurement folder"),
            "mode": "folder",
            "filters": "",
        }

    def write_results(self) -> None:
        """Ask the window where to write the tables."""
        self.dialog_request = {
            "kind": "write_results",
            "title": tr("Write the results into a folder"),
            "mode": "folder",
            "filters": "",
        }

    def finish_dialog(self, kind: str, path: str) -> None:
        """A folder chosen in the window's dialog."""
        if kind == "data_folder":
            self.open_folder(path)
        elif kind == "write_results":
            self.write_to(path)

    def open_folder(self, folder: str) -> bool:
        """Read a measurement folder in the background."""
        missing = [n for n in DATA_FILES if not (Path(folder) / n).is_file()]
        if missing:
            self.say(
                tr("Not a measurement folder ({missing} missing): {folder}").format(
                    missing=", ".join(missing), folder=folder
                ),
                True,
            )
            return False
        self.data_folder = str(folder)
        return self._start("load", tr("Reading the measurements"), self._load)

    def preset_changed(self, value=None) -> None:
        """A different preset solves different graphs: the solved ones are dropped."""
        if self.analysis is not None:
            self.analysis = None
            self.view_stage = self.view_block = ""
            self.touch()
            self.say(tr("Preset changed: the next run solves the graphs again."))

    def stage_changed(self, value=None) -> None:
        blocks = self.block_options()
        if self.view_block not in blocks:
            self.view_block = blocks[0] if blocks else ""
        self.touch()

    def build_site_tables(self) -> bool:
        if self.data is None:
            return False
        return self._start("sites", tr("Building site tables"), lambda: self._build_sites(1.0))

    def run_analysis(self) -> bool:
        """Build the missing site tables, then run the chosen stages (both in the background)."""
        if self.data is None:
            self.say(tr("Cannot run: load a data folder first."), True)
            return False
        return self._start("run", tr("Building site tables"), self._run)

    def cancel_analysis(self) -> bool:
        if not self.busy:
            return False
        self._cancel.set()
        self.progress_message = tr("Stopping at the next checkpoint...")
        return True

    def write_to(self, folder: str) -> list:
        if self.analysis is None or not self.result_stages():
            self.say(tr("Nothing to write: run a stage first."), True)
            return []
        try:
            written = self.analysis.result.write(folder)
        except Exception as exc:  # noqa: BLE001 - shown in the window
            self.say(tr("Failed to write the results: {error}").format(error=exc), True)
            return []
        self.say(tr("Wrote {n} files into {folder}").format(n=len(written), folder=folder))
        return written

    # ---- background work

    def _start(self, kind: str, message: str, work: Callable[[], Any]) -> bool:
        if self.busy:
            return False
        self._cancel = threading.Event()
        self.busy, self.progress_fraction, self.progress_message = kind, None, message
        self._started = time.monotonic()
        self._finished = None

        def run() -> None:
            from chisurf.plugins.quenching_estimator.core.tasks import CancelledError

            try:
                out, error = work(), ""
            except CancelledError:
                out, error = None, "cancelled"
            except Exception as exc:  # noqa: BLE001 - handed to the UI thread
                out, error = None, f"{type(exc).__name__}: {exc}"
                _LOG.exception("QuEst analysis %s failed", kind)
            self._finished = (kind, out, error)
            self._wake()

        threading.Thread(target=run, name=f"quest-analysis-{kind}", daemon=True).start()
        return True

    def _wake(self) -> None:
        if self.wake is not None:
            try:
                self.wake()
            except Exception:  # noqa: BLE001 - a host that went away
                pass

    def _progress(self, fraction: float, message: str) -> None:
        self.progress_fraction = max(0.0, min(1.0, float(fraction)))
        self.progress_message = str(message)
        self._wake()

    def _check(self) -> None:
        if self._cancel.is_set():
            from chisurf.plugins.quenching_estimator.core.tasks import CancelledError

            raise CancelledError("cancelled")

    def _load(self):
        from chisurf.plugins.quenching_estimator.core.inference import kq_scaling, stages

        data = stages.load_analysis_data(
            self.data_folder, library=self.library_override, cache_dir=self.cache_dir
        )
        return data, kq_scaling.kq_table(data.posterior)

    def _build_sites(self, share: float) -> dict:
        keys = self.site_keys()
        built = dict(self.site_models)
        for i, (dye, state, site, length) in enumerate(keys):
            self._check()
            self._progress(
                share * i / max(len(keys), 1),
                tr("Site table {i} of {n}: {state} {site} ({dye})").format(
                    i=i + 1, n=len(keys), state=state, site=site, dye=dye
                ),
            )
            if (dye, state, site, length) not in built:
                built[(dye, state, site, length)] = self.data.library.site(state, site, length)
                self.site_models = dict(built)  # the table grows while it is built
        return built

    def _run(self):
        from chisurf.plugins.quenching_estimator.core.inference import stages

        share = 0.0 if all(k in self.site_models for k in self.site_keys()) else 0.25
        built = self._build_sites(share)
        analysis = self.analysis
        if analysis is None:
            analysis = stages.Analysis(
                self.data,
                preset=self.preset,
                fit_overrides=self.fit_overrides,
                workers=int(self.workers) or None,
                profile=bool(self.profile),
            )
        analysis.profile = bool(self.profile)
        self._progress(share, tr("Preparing the fit (site models, then the first searches)"))
        names = "all" if self.stage_selection == "all" else self.stage_selection
        analysis.run(
            names,
            progress=lambda p, m: self._progress(share + (1 - share) * p / 100.0, m),
            cancel=self._cancel.is_set,
        )
        return built, analysis

    def poll(self) -> bool:
        """Apply finished background work (on the UI thread); True when something changed."""
        done, self._finished = self._finished, None
        if done is None:
            return bool(self.busy)
        kind, out, error = done
        elapsed = time.monotonic() - self._started
        self.busy, self.progress_fraction = "", (1.0 if not error else 0.0)
        self.progress_message = ""
        if error == "cancelled":
            self.say(tr("Cancelled after {s:.0f} s; what was finished is kept.").format(s=elapsed))
        elif error:
            self.say(tr("Failed: {error}").format(error=error), True)
        elif kind == "load":
            self.data, self.kq = out
            self.analysis = None
            self.site_models = {}
            self.view_stage = self.view_block = ""
            dyes = self.dye_options()
            if self.data_dye not in dyes:
                self.data_dye = dyes[0] if dyes else ""
            n = len(self.data.errors.data)
            self.say(
                tr("Loaded {n} site lifetimes and {k} titrations from {folder}").format(
                    n=n, k=len(self.data.posterior.table), folder=Path(self.data_folder).name
                )
            )
            self._used(
                "load_example" if "demos" in Path(self.data_folder).parts else "choose_folder"
            )
        elif kind == "sites":
            self.site_models = out
            self.say(tr("{n} site tables ready ({s:.0f} s).").format(n=len(out), s=elapsed))
        elif kind == "run":
            self.site_models, self.analysis = out
            options = self.fit_stage_options()
            if self.view_stage not in options:
                self.view_stage = options[0] if options else ""
            self.stage_changed()
            ran = ", ".join(self.result_stages())
            self.say(tr("Done in {s:.0f} s: stages {stages}.").format(s=elapsed, stages=ran))
            self._used("run_analysis")
        self.touch()
        return True

    def wait(self, timeout: float = 600.0) -> bool:
        """Block until the background work is done (tests and scripts); True when it finished."""
        end = time.monotonic() + timeout
        while self.busy and time.monotonic() < end:
            time.sleep(0.02)
            self.poll()
        return not self.busy

    # ---- bookkeeping

    def touch(self) -> None:
        """Something the tables read changed."""
        self.revision += 1

    def say(self, text: str, error: bool = False) -> None:
        self.status, self.status_error = text, error

    def _used(self, name: str) -> None:
        if self.used_hook is not None:
            self.used_hook(name)

    def export_settings(self) -> dict:
        return dict(
            data_folder=self.data_folder,
            preset=self.preset,
            stage_selection=self.stage_selection,
            workers=int(self.workers),
            profile=bool(self.profile),
        )

    def restore_settings(self, settings: dict) -> None:
        if not isinstance(settings, dict):
            return
        if settings.get("preset") in ("quick", "full"):
            self.preset = settings["preset"]
        if settings.get("stage_selection") in self.stage_options():
            self.stage_selection = settings["stage_selection"]
        if isinstance(settings.get("workers"), int):
            self.workers = settings["workers"]
        if isinstance(settings.get("profile"), bool):
            self.profile = settings["profile"]
        folder = settings.get("data_folder")
        if folder and all((Path(folder) / n).is_file() for n in DATA_FILES):
            self.data_folder = str(folder)


# --------------------------------------------------------------------------------------------
# the window


class AnalysisCard(CardShell):
    """The Analysis page (a card of its own; the QuEst window hosts it beside the forward model).

    Parameters
    ----------
    model : AnalysisModel, optional
    page_bar : callable, optional
        ``page_bar(card)`` draws the host window's page switch in the strip above the docks.
    """

    def __init__(
        self, model: AnalysisModel | None = None, page_bar: Callable | None = None
    ) -> None:
        self.model = model or AnalysisModel()
        self.page_bar = page_bar
        self.spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
        self.panels = {str(p.get("dock")): p for p in self.spec["sections"]}
        super().__init__("QuEst Analysis", HERE, "quest-analysis")
        # The page has its own help and tour (the folder's help.md / guide.json are the forward model's).
        self.help_window = EmTkHelpWindow(
            title=tr("QuEst Analysis — Help"),
            resource=HELP_PATH,
            owner=self,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=GUIDE_PATH,
            get_target_rect=lambda k: self.item_rects.get(k) or self.form.rects.get(k),
            owner=self,
            wait_for_controls=True,
        )
        self.form = FormState(on_used=self.used)
        self.form.custom["analysis_plot"] = lambda s, m, st, w: self.draw_plot(
            str(s.get("target", "")), s
        )
        self.model.used_hook = self.used
        self.model.wake = self.request_frame

    def build_docks(self) -> DockManager:
        docks = DockManager(Split("h", 0.30, Region("inputs"), Region("results")))
        for dock, panel in self.panels.items():
            docks.add_window(
                dock,
                str(panel.get("title", dock)),
                lambda box, p=panel: self._draw_panel(p),
                dock=dock,
                closable=False,
                tooltip=str(panel.get("description", "")),
            )
        return docks

    # ---- frame

    def toolbar_height(self) -> float:
        return 34.0 if self.page_bar is not None else 0.0

    def draw_toolbar(self, box) -> None:
        if self.page_bar is not None:
            self.page_bar(self)

    def before_frame(self) -> None:
        self.serve_dialog_request()
        if self.model.poll():
            self.status, self.status_error = self.model.status, self.model.status_error
        if self.model.busy:
            self.request_frame()

    def animating(self) -> bool:
        return super().animating() or bool(self.model.busy)

    def next_frame_in(self):
        return 0.1 if self.model.busy else super().next_frame_in()

    def _draw_panel(self, panel: dict) -> None:
        if panel.get("dock") == "inputs":
            pressed = self.toolbar(self.help_buttons())
            if pressed == "guide":
                self.start_guide()
            elif pressed == "help":
                self.show_help()
            im.separator()
        draw_sections(panel.get("sections") or [], self.model, self.form)
        self.item_rects.update(self.form.rects)

    def serve_dialog_request(self) -> None:
        """Open the folder dialog the model asked for."""
        request = self.model.dialog_request
        if not request or self.dialog is not None:
            return
        self.model.dialog_request = None
        kind = request["kind"]

        def picked(path: str) -> None:
            self.model.finish_dialog(kind, path)
            self.used(kind)
            self.request_frame()

        self.open_file(
            request["title"],
            request.get("filters", ""),
            picked,
            current=self.model.data_folder,
            folder=True,
        )

    def take_drop(self, paths: list[str]) -> bool:
        """A dropped folder (or a file inside one) holding the three tables is the data folder."""
        for path in paths:
            folder = path if os.path.isdir(path) else os.path.dirname(path)
            if all(os.path.isfile(os.path.join(folder, n)) for n in DATA_FILES):
                return self.model.open_folder(folder)
        self.model.say(tr("No measurement folder among the dropped paths."), True)
        return False

    # ---- plots

    def draw_plot(self, target: str, section: dict) -> None:
        """One ``analysis_plot`` section: the implot drawing named by its ``target``."""
        draw = getattr(self, f"_plot_{target}", None)
        height = PLOT_HEIGHTS.get(target, PLOT_HEIGHT)
        drawn = False
        if draw is not None:
            try:
                drawn = bool(draw(height))
            except Exception as exc:  # noqa: BLE001 - one bad plot must not blank the page
                im.text_disabled(tr("Plot failed: {error}").format(error=exc))
                drawn = True
        if not drawn:
            im.text_disabled(tr(EMPTY_TEXT.get(target, "Nothing to plot yet: press Run.")))
        if section.get("description"):
            im.set_item_tooltip(tr(str(section["description"])))
        self.remember(target)

    def _begin(
        self, target: str, height: float, x: str, y: str, logx=False, logy=False, legend=None
    ) -> bool:
        if not implot.begin_plot(f"##{target}", (-1, height)):
            return False
        implot.setup_axes(tr(x), tr(y))
        if logx:
            implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
        if logy:
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
        implot.setup_legend(implot.LOCATION_NORTH_WEST if legend is None else legend)
        return True

    def _title(self, text: str) -> None:
        im.text(text)

    @staticmethod
    def _categories(axis: int, labels: list[str]) -> None:
        """Category ticks on *axis*, half a step of room at both ends."""
        implot.setup_axis_ticks(axis, list(range(len(labels))), labels=list(labels))
        implot.setup_axis_limits(axis, -0.6, len(labels) - 0.4, implot.COND_ALWAYS)

    @staticmethod
    def _err(
        label: str, xs, ys, neg, pos=None, colour=GREY, horizontal=False, whisker=0.0, weight=1.0
    ) -> None:
        """Error bars in *colour* (vertical, or along x when *horizontal*); *pos* defaults to *neg*."""
        spec = implot.PlotSpec(
            line_color=colour,
            line_weight=weight,
            size=whisker,
            flags=implot.ERROR_BARS_FLAGS_HORIZONTAL if horizontal else 0,
        )
        neg = np.nan_to_num(_arr(neg))
        pos = neg if pos is None else np.nan_to_num(_arr(pos))
        implot.plot_error_bars(label, _arr(xs), _arr(ys), neg, pos, spec=spec)

    def _plot_stern_volmer(self, height: float) -> bool:
        series = self.model.stern_volmer()
        if not series:
            return False
        self._title(tr("Stern-Volmer: {dye}").format(dye=self.model.data_dye))
        if self._begin("stern_volmer", height, "Concentration (M)", "tau0/tau - 1"):
            for i, s in enumerate(series):
                colour = _colour(i)
                implot.set_next_marker_style(implot.MARKER_CIRCLE, 4.0, colour)
                implot.plot_scatter(s["amino_acid"], s["x"], s["y"])
                if np.isfinite(s["ksv"]) and len(s["x"]):
                    xs = np.array([0.0, float(np.nanmax(s["x"]))])
                    implot.set_next_line_style(colour, 2.0)
                    implot.plot_line(s["amino_acid"], xs, s["ksv"] * xs)
            implot.end_plot()
        return True

    def _plot_hyper_posterior(self, height: float) -> bool:
        data = self.model.data
        if data is None:
            return False
        post = data.posterior
        w = np.asarray(post.weight, float)
        a, r = np.asarray(post.day_abs, float), np.asarray(post.day_rel, float)
        if w.size == 0:
            return False
        self._title(tr("Day-to-day error: hyper-posterior"))
        if self._begin(
            "hyper_posterior", height, "log10 relative day error", "log10 absolute day error (1/M)"
        ):
            la, lr = np.log10(a), np.log10(r)
            # row 0 at the top: the largest absolute error first
            values = (w / w.max())[::-1, :]
            implot.push_colormap(implot.COLORMAP_VIRIDIS)
            implot.plot_heatmap(
                "##posterior",
                values,
                values.shape[0],
                values.shape[1],
                0.0,
                1.0,
                None,
                (float(lr[0]), float(la[0])),
                (float(lr[-1]), float(la[-1])),
            )
            implot.pop_colormap()
            implot.end_plot()
        return True

    def _plot_water_bars(self, height: float) -> bool:
        rows = self.model.water_rows()
        if not rows:
            return False
        self._title(tr("Water quenching per site: {dye}").format(dye=self.model.data_dye))
        sites = sorted({r["site"] for r in rows})
        if self._begin("water_bars", height, "Site", "kq_w (1/ns)"):
            self._categories(implot.AXIS_X1, [str(s) for s in sites])
            for j, state in enumerate(("APO", "HOLO")):
                here = {r["site"]: r["kq_w"] for r in rows if r["state"] == state}
                xs = [i + (j - 0.5) * 0.36 for i, s in enumerate(sites) if s in here]
                ys = [here[s] for s in sites if s in here]
                if xs:
                    implot.set_next_fill_style(_colour(j))
                    implot.plot_bars(state, xs, ys, bar_size=0.34)
            implot.end_plot()
        return True

    def _plot_kq_bars(self, height: float) -> bool:
        kq = self.model.kq
        if kq is None:
            return False
        quenchers = list(kq.quenchers)
        n = max(len(kq.dyes), 1)
        width = 0.8 / n
        self._title(tr("kQ at contact per dye"))
        if self._begin(
            "kq_bars", height, "Quenching residue", "kQ (1/ns)", legend=implot.LOCATION_NORTH_EAST
        ):
            self._categories(implot.AXIS_X1, quenchers)
            for i, dye in enumerate(kq.dyes):
                xs = np.arange(len(quenchers)) + (i - (n - 1) / 2) * width
                colour = DYE_COLOURS.get(dye, _colour(i))
                implot.set_next_fill_style(colour)
                implot.plot_bars(dye, xs, kq.value[i], bar_size=width * 0.9)
                self._err(
                    dye,
                    xs,
                    kq.value[i],
                    kq.sd[i],
                    colour=(220, 220, 220, 255),
                    whisker=4.0,
                    weight=1.5,
                )
            implot.end_plot()
        return True

    def _plot_site_exposure(self, height: float) -> bool:
        e = self.model.selected_site_exposure()
        if e is None or not len(e):
            return False
        dye, state, site = self.model.selected_site
        self._title(
            tr("Exposure of {state} {site} ({dye}): {n} positions").format(
                state=state, site=site, dye=dye, n=len(e)
            )
        )
        if self._begin("site_exposure", height, "Water exposure", "Positions"):
            counts, edges = np.histogram(e, bins=20, range=(0.0, 1.0))
            implot.set_next_fill_style(_colour(0))
            implot.plot_bars(
                "positions", 0.5 * (edges[1:] + edges[:-1]), counts.astype(float), bar_size=0.045
            )
            implot.end_plot()
        return True

    def _plot_parity(self, height: float) -> bool:
        p = self.model.stage_plot(f"parity:{self.model.view_block}")
        if not p:
            return False
        measured, predicted = _arr(p["measured"]), _arr(p["predicted"])
        sx, sy = _arr(p["sigma_total"]), _arr(p["pred_sd"])
        solvent = np.asarray(p["solvent"], str)
        state = np.asarray(p["state"], str)
        outlier = np.asarray(p["outlier"], bool)
        self._title(tr("Predicted against measured: {block}").format(block=self.model.view_block))
        if self._begin("parity", height, "Measured lifetime (ns)", "Predicted lifetime (ns)"):
            both = np.concatenate([measured, predicted])
            lo, hi = float(np.nanmin(both)), float(np.nanmax(both))
            pad = 0.05 * (hi - lo or 1.0)
            implot.set_next_line_style(GREY, 1.0)
            implot.plot_line(
                "y = x", np.array([lo - pad, hi + pad]), np.array([lo - pad, hi + pad])
            )
            for s in sorted(set(solvent)):
                for st, marker in (("APO", implot.MARKER_CIRCLE), ("HOLO", implot.MARKER_SQUARE)):
                    m = (solvent == s) & (state == st)
                    if not m.any():
                        continue
                    label = f"{s} {st.lower()}"
                    colour = SOLVENT_COLOURS.get(s, _colour(0))
                    faint = (*colour[:3], 150)
                    self._err(
                        label, measured[m], predicted[m], sx[m], colour=faint, horizontal=True
                    )
                    self._err(label, measured[m], predicted[m], sy[m], colour=faint)
                    implot.set_next_marker_style(marker, 4.0, colour)
                    implot.plot_scatter(label, measured[m], predicted[m])
            if outlier.any():
                implot.set_next_marker_style(
                    implot.MARKER_CIRCLE, 10.0, (0, 0, 0, 0), 2.0, (220, 20, 60, 255)
                )
                implot.plot_scatter(tr("outlier"), measured[outlier], predicted[outlier])
                site = np.asarray(p["site"])
                for x, y, s in zip(measured[outlier], predicted[outlier], site[outlier]):
                    implot.plot_text(str(s), float(x), float(y), (14.0, -10.0))
            for i, (s, t0) in enumerate(sorted((p.get("tau0") or {}).items())):
                colour = SOLVENT_COLOURS.get(s, _colour(i))
                implot.set_next_line_style(colour, 1.0)
                implot.plot_inf_lines(
                    f"tau0 {s}",
                    [float(t0)],
                    spec=implot.PlotSpec(dash=(4.0, 4.0), line_color=colour),
                )
            implot.end_plot()
        return True

    def _estimates(self) -> list[dict]:
        return list(self.model.stage_plot(f"estimates:{self.model.view_block}") or [])

    def _plot_forest(self, height: float) -> bool:
        rows = [
            r
            for r in self._estimates()
            if (str(r["parameter"]).startswith("s_") or r["parameter"] in ("scale", "static"))
            and r.get("value") is not None
            and float(r["value"]) > 0
        ]
        if not rows:
            return False
        self._title(
            tr("Estimates with 68 % intervals: {block}").format(block=self.model.view_block)
        )
        if self._begin(
            "forest", height, "Value (log)", "", logx=True, legend=implot.LOCATION_SOUTH_EAST
        ):
            names = [str(r["parameter"]) for r in rows]
            self._categories(implot.AXIS_Y1, names)
            ys = np.arange(len(rows), dtype=float)
            v = np.array([float(r["value"]) for r in rows])
            lo = np.array(
                [float(r["low_68"]) if r.get("low_68") is not None else np.nan for r in rows]
            )
            hi = np.array(
                [float(r["high_68"]) if r.get("high_68") is not None else np.nan for r in rows]
            )
            self._err(
                "68 %",
                v,
                ys,
                v - lo,
                hi - v,
                colour=_colour(0),
                horizontal=True,
                whisker=6.0,
                weight=1.5,
            )
            implot.set_next_marker_style(implot.MARKER_DIAMOND, 5.0, _colour(0))
            implot.plot_scatter("estimate", v, ys)
            implot.set_next_line_style(GREY, 1.0)
            implot.plot_inf_lines("1", [1.0])
            implot.end_plot()
        return True

    def _plot_loo(self, height: float) -> bool:
        p = self.model.stage_plot(f"loo:{self.model.view_block}")
        if not p or not p.get("site"):
            return False
        order = np.argsort(np.asarray(p["site"]))
        sites = [str(np.asarray(p["site"])[i]) for i in order]
        z = _arr(p["max_abs_z"])[order]
        limit = float(p.get("limit", 3.0))
        self._title(tr("Leave one site out"))
        if self._begin("loo", height, "Site", "max |z|", legend=implot.LOCATION_NORTH_EAST):
            self._categories(implot.AXIS_X1, sites)
            xs = np.arange(len(sites), dtype=float)
            ok = z <= limit
            implot.set_next_fill_style(_colour(0))
            implot.plot_bars("within", xs[ok], z[ok], bar_size=0.6)
            if (~ok).any():
                implot.set_next_fill_style((220, 20, 60, 255))
                implot.plot_bars("outlier", xs[~ok], z[~ok], bar_size=0.6)
            implot.set_next_line_style(GREY, 1.0)
            implot.plot_inf_lines(
                f"limit {limit:g}",
                [limit],
                spec=implot.PlotSpec(
                    flags=implot.INF_LINES_FLAGS_HORIZONTAL, dash=(4.0, 4.0), line_color=GREY
                ),
            )
            implot.end_plot()
        return True

    def _profile_curve(self, label: str, prof: dict | None, laplace: dict | None, colour) -> None:
        if prof:
            x, d = _arr(prof["values"]), _arr(prof["deviance"])
            implot.set_next_line_style(colour, 2.0)
            implot.set_next_marker_style(implot.MARKER_CIRCLE, 3.0, colour)
            implot.plot_line(f"{label}: profile", x, d)
        if laplace:
            implot.set_next_line_style(colour, 1.0)
            implot.plot_inf_lines(
                f"{label}: Laplace 68 %",
                [float(laplace["low"]), float(laplace["high"])],
                spec=implot.PlotSpec(dash=(4.0, 4.0), line_color=colour),
            )

    def _plot_profile(self, height: float) -> bool:
        p = self.model.stage_plot(f"profile:{self.model.view_block}")
        if not p:
            return False
        prof, lap = p.get("profile"), p.get("laplace_summary")
        if not prof and not lap:
            return False
        self._title(tr("Quench scale: profile likelihood"))
        if self._begin("profile", height, "Quench scale", "Deviance", logx=True):
            if prof:
                implot.set_next_line_style(GREY, 1.0)
                implot.plot_inf_lines(
                    "deviance 1",
                    [1.0],
                    spec=implot.PlotSpec(
                        flags=implot.INF_LINES_FLAGS_HORIZONTAL, dash=(2.0, 3.0), line_color=GREY
                    ),
                )
            self._profile_curve(self.model.view_block, prof, lap, _colour(0))
            implot.end_plot()
        return True

    def _plot_k_graph(self, height: float) -> bool:
        rows = self.model.stage_plot("k_graph")
        if not rows:
            return False
        labels = [str(r["amino_acid"]) for r in rows]
        dyes = list(dict.fromkeys(str(r["dye"]) for r in rows))
        self._title(
            tr("Titration slopes: titrations alone (circles) and after the graph fit (squares)")
        )
        if self._begin("k_graph", height, "", "K_SV (1/M)", legend=implot.LOCATION_NORTH_EAST):
            self._categories(implot.AXIS_X1, labels)
            for i, dye in enumerate(dyes):
                idx = [j for j, r in enumerate(rows) if str(r["dye"]) == dye]
                sub = [rows[j] for j in idx]
                xs = np.asarray(idx, dtype=float)
                k0, k0sd = (
                    _arr([r["ksv_titration"] for r in sub]),
                    _arr([r["ksv_titration_sd"] for r in sub]),
                )
                k1 = _arr([r["ksv_graph"] for r in sub])
                lo, hi = _arr([r["low_68"] for r in sub]), _arr([r["high_68"] for r in sub])
                colour = DYE_COLOURS.get(dye, _colour(i))
                self._err(dye, xs - 0.15, k0, k0sd, colour=colour, whisker=4.0, weight=1.5)
                implot.set_next_marker_style(implot.MARKER_CIRCLE, 4.0, colour)
                implot.plot_scatter(dye, xs - 0.15, k0)
                self._err(
                    dye, xs + 0.15, k1, k1 - lo, hi - k1, colour=colour, whisker=4.0, weight=1.5
                )
                implot.set_next_marker_style(implot.MARKER_SQUARE, 4.0, colour)
                implot.plot_scatter(dye, xs + 0.15, k1)
            implot.end_plot()
        return True

    def _plot_water_access(self, height: float) -> bool:
        p = self.model.stage_plot("water_access", "C")
        if not p or not p.get("rows"):
            return False
        rows = p["rows"]
        m, me = _arr([r["measured"] for r in rows]), _arr([r["measured_err"] for r in rows])
        y, ye = _arr([r["model"] for r in rows]), _arr([r["model_err"] for r in rows])
        without = ", ".join(str(s) for s in p.get("without", []))
        self._title(
            tr("Water access: r = {a:.2f} (all), {b:.2f} (without {w})").format(
                a=float(p.get("r_all") or math.nan),
                b=float(p.get("r_without") or math.nan),
                w=without,
            )
        )
        if self._begin("water_access", height, "Measured water access", "Model water access"):
            both = np.concatenate([m, y])
            lo, hi = float(np.nanmin(both)), float(np.nanmax(both))
            implot.set_next_line_style(GREY, 1.0)
            implot.plot_line("y = x", np.array([lo, hi]), np.array([lo, hi]))
            for st, marker in (("APO", implot.MARKER_CIRCLE), ("HOLO", implot.MARKER_SQUARE)):
                mask = np.array([r["state"] == st for r in rows])
                if not mask.any():
                    continue
                colour = SOLVENT_COLOURS["H2O"] if st == "APO" else SOLVENT_COLOURS["D2O"]
                self._err(st.lower(), m[mask], y[mask], me[mask], colour=colour, horizontal=True)
                self._err(st.lower(), m[mask], y[mask], ye[mask], colour=colour)
                implot.set_next_marker_style(marker, 4.0, colour)
                implot.plot_scatter(st.lower(), m[mask], y[mask])
            for r, xv, yv in zip(rows, m, y):
                implot.plot_text(str(r["site"]), float(xv), float(yv), (12.0, -9.0))
            implot.end_plot()
        return True

    def _plot_exposure(self, height: float) -> bool:
        hist = self.model.stage_plot("exposure", "C")
        if not hist:
            return False
        self._title(tr("Time-weighted water exposure of the visible dye"))
        if self._begin("exposure", height, "Water exposure", "Share of visible time"):
            edges = np.linspace(0.0, 1.0, 21)
            for i, (site, h) in enumerate(sorted(hist.items(), key=lambda kv: int(kv[0]))):
                w, _ = np.histogram(_arr(h["exposure"]), bins=edges, weights=_arr(h["weight"]))
                colour = _colour(i)
                implot.set_next_line_style(colour, 2.0)
                implot.plot_stairs(
                    tr("site {site}: visible {v:.2f}").format(site=site, v=float(h["visible"])),
                    edges[:-1],
                    w,
                )
                implot.set_next_line_style(colour, 1.0)
                implot.plot_inf_lines(
                    tr("site {site}: reachable {v:.2f}").format(site=site, v=float(h["reachable"])),
                    [float(h["reachable"])],
                    spec=implot.PlotSpec(dash=(4.0, 4.0), line_color=colour),
                )
            implot.end_plot()
        return True

    def _plot_scale_compare(self, height: float) -> bool:
        stages = self.model.result_stages()
        c, b = stages.get("C"), stages.get("B")
        if c is None:
            return False
        compare = c.plots.get("profiles") or {}
        curves = []
        for stage in (b, c):
            if stage is None:
                continue
            for key, p in stage.plots.items():
                if key.startswith("profile:") and key[len("profile:") :] in compare:
                    curves.append((key[len("profile:") :], p))
        if not curves and not compare:
            return False
        self._title(tr("Quench scale: heavy water alone (B) against heavy and normal water (C)"))
        if self._begin("scale_compare", height, "Quench scale", "Deviance", logx=True):
            for i, (label, p) in enumerate(curves):
                self._profile_curve(
                    label,
                    p.get("profile"),
                    compare.get(label) or p.get("laplace_summary"),
                    _colour(i),
                )
            implot.end_plot()
        return True

    def _plot_summary_scale(self, height: float) -> bool:
        p = self.model.stage_plot("scale", "summary")
        if not p:
            return False
        dyes = list(p)
        xs = np.arange(len(dyes), dtype=float)
        v = _arr([p[d]["value"] for d in dyes])
        lo, hi = _arr([p[d]["low"] for d in dyes]), _arr([p[d]["high"] for d in dyes])
        self._title(tr("Quench scale per dye"))
        if self._begin("summary_scale", height, "", "Quench scale (log)", logy=True):
            self._categories(implot.AXIS_X1, dyes)
            for i, d in enumerate(dyes):
                colour = DYE_COLOURS.get(d, _colour(i))
                self._err(
                    d,
                    xs[i : i + 1],
                    v[i : i + 1],
                    (v - lo)[i : i + 1],
                    (hi - v)[i : i + 1],
                    colour=colour,
                    whisker=6.0,
                    weight=2.0,
                )
                implot.set_next_marker_style(implot.MARKER_DIAMOND, 6.0, colour)
                implot.plot_scatter(d, xs[i : i + 1], v[i : i + 1])
            implot.end_plot()
        return True

    def _plot_summary_stickiness(self, height: float) -> bool:
        p = self.model.stage_plot("stickiness", "summary")
        if not p:
            return False
        dyes = list(p)
        groups = list(next(iter(p.values())))
        n = max(len(dyes), 1)
        self._title(tr("Stickiness per residue group"))
        if self._begin("summary_stickiness", height, "", "Stickiness s (log)", logy=True):
            self._categories(implot.AXIS_X1, groups)
            for i, d in enumerate(dyes):
                xs = np.arange(len(groups)) + (i - (n - 1) / 2) * 0.2
                v = _arr([p[d][g]["value"] for g in groups])
                lo = _arr([p[d][g]["low"] for g in groups])
                hi = _arr([p[d][g]["high"] for g in groups])
                colour = DYE_COLOURS.get(d, _colour(i))
                self._err(d, xs, v, v - lo, hi - v, colour=colour, whisker=4.0, weight=1.5)
                implot.set_next_marker_style(implot.MARKER_CIRCLE, 4.0, colour)
                implot.plot_scatter(d, xs, v)
            implot.set_next_line_style(GREY, 1.0)
            implot.plot_inf_lines(
                "1",
                [1.0],
                spec=implot.PlotSpec(
                    flags=implot.INF_LINES_FLAGS_HORIZONTAL, dash=(2.0, 3.0), line_color=GREY
                ),
            )
            implot.end_plot()
        return True

    # ---- persistence

    def export_settings(self) -> dict:
        return self.model.export_settings()

    def restore_settings(self, settings: dict) -> None:
        self.model.restore_settings(settings)

    def close(self) -> None:
        self.model.cancel_analysis()


#: What an empty drawing says, by target.
EMPTY_TEXT = {
    "stern_volmer": "No titrations yet: press Load example, or pick a data folder.",
    "hyper_posterior": "No titrations yet: press Load example, or pick a data folder.",
    "water_bars": "No lifetimes yet: press Load example, or pick a data folder.",
    "kq_bars": "No kQ yet: press Load example, or pick a data folder.",
    "site_exposure": "Select a site table above (press Build site tables or Run first).",
    "water_access": "Stage C has not run yet (Stages: all or C, then Run).",
    "exposure": "Stage C has not run yet (Stages: all or C, then Run).",
    "scale_compare": "Stages B and C have not run yet (Stages: all, then Run).",
    "summary_scale": "The summary stage has not run yet (Stages: all, then Run).",
    "summary_stickiness": "The summary stage has not run yet (Stages: all, then Run).",
}


def make_card(model: AnalysisModel | None = None, page_bar: Callable | None = None) -> AnalysisCard:
    """The Analysis page on its own (the QuEst window builds it with its page switch)."""
    from chisurf.emtk.i18n import install

    install()
    return AnalysisCard(model, page_bar)


__all__ = ["AnalysisCard", "AnalysisModel", "TableView", "declared_columns", "make_card"]
