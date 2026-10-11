"""The emtk shell's data and fit docks: Read data, Datasets, Analysis, Plot settings and the fit windows.

These are the Qt shell's ``dockWidgetReadData``, ``dockWidgetDatasets``,
``dockWidgetAnalysis`` and ``dockWidgetPlot`` and its MDI fit sub-windows, drawn
by emtk inside :class:`chisurf.emtk.main_app.EmtkShellApp`. Every panel is a
``view.json`` spec beside this module (``views/``), rendered by
:func:`emtk.view_form.draw_form` over a small model object here; tables are the
spec's ``table`` sections.

Nothing here edits a fit, a dataset or a parameter itself. Changes go through
:class:`chisurf.core.api.ChiSurfAPI` (a JSON-RPC call to the in-process server
of :mod:`chisurf.emtk.session`) on a worker thread -- a fit runs inside one call
and must not freeze the window -- and what changed comes back as server events,
drained once per frame. The cached rows the panels show are re-read after an
event, and only while no call is under way: the server answers one request at a
time, so a read during a running fit would wait for the fit.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from emtk import im
from emtk.i18n import tr
from emtk.view_form import FormState, draw_form

from chisurf.emtk.background_build import BackgroundBuild

_log = logging.getLogger("chisurf.emtk.fit_docks")

VIEWS = Path(__file__).with_name("views")
#: Dock keys of the four panels, in the Qt shell's tab order.
READ_KEY, DATASETS_KEY, ANALYSIS_KEY, PLOT_KEY = (
    "data.read",
    "data.sets",
    "fit.analysis",
    "fit.plot",
)


def load_view(name: str) -> dict:
    """The parsed ``views/<name>.view.json``."""
    return json.loads((VIEWS / f"{name}.view.json").read_text(encoding="utf-8"))


class _Rows(list):
    """Table rows with a ``revision`` the table compares, so a refresh rebinds it once."""

    revision = 0


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


# ── panel models (what the specs read and write) ─────────────────────────────


class ReadDataModel:
    """The Read data panel: experiment, file type, file, and the reader's own settings below."""

    def __init__(self, docks: DataDocks) -> None:
        self.docks = docks
        self.experiment = ""
        self.setup = ""
        self.path = ""

    def experiment_names(self) -> list[str]:
        """The visible experiments."""
        return list(self.docks.experiments())

    def setup_names(self) -> list[str]:
        """The file types (readers) of the selected experiment."""
        experiment = self.docks.experiments().get(self.experiment)
        return [str(r.name) for r in getattr(experiment, "readers", ())] if experiment else []

    def experiment_changed(self, value: str) -> None:
        names = self.setup_names()
        if self.setup not in names:
            self.setup = names[0] if names else ""
        self.docks.datasets.model = ""

    def setup_changed(self, value: str) -> None:
        self.docks.request_frame()

    def reader(self) -> Any:
        """The selected reader object, ``None`` before a session is up."""
        experiment = self.docks.experiments().get(self.experiment)
        for reader in getattr(experiment, "readers", ()) if experiment else ():
            if str(reader.name) == self.setup:
                return reader
        return None

    @property
    def reader_note(self) -> str:
        """What the panel says about the reader's own settings (none drawn, or why not)."""
        if self.docks.session is None:
            return self.docks.session_status()
        return self.docks.reader_settings_error(self.reader())

    def enabled(self, name: str) -> bool:
        if name in ("load", "use_demo", "browse"):
            return self.docks.session is not None and not self.docks.busy
        return True

    def browse(self) -> None:
        """Open the file dialog for the file to read."""
        self.docks.open_file_dialog()

    def use_demo(self) -> None:
        """Write the demo curve and select it with its file type."""
        from chisurf.core.experiments.fcs.demo import DEMO, make_demo

        self.experiment = DEMO["experiment"]
        self.setup = DEMO["reader"]
        self.path = str(make_demo())
        self.docks.datasets.model = DEMO["model"]
        self.docks.status = tr("Demo curve written; press + Data to read it.")

    def load(self) -> None:
        """Read the file with the selected reader and add it to the datasets."""
        self.docks.load(self.reader(), self.path)


class DatasetsModel:
    """The Datasets panel: datasets, fits, the model to fit with and *+ Analysis*."""

    def __init__(self, docks: DataDocks) -> None:
        self.docks = docks
        self.model = ""
        self.selected: dict = {}
        self.datasets = _Rows()
        self.fits = _Rows()

    def dataset_rows(self) -> list:
        return self.datasets

    def fit_rows(self) -> list:
        return self.fits

    def selected_experiment(self) -> Any:
        """The experiment of the selected dataset, else of the Read data panel."""
        experiments = self.docks.experiments()
        name = str(self.selected.get("experiment") or self.docks.read.experiment)
        return experiments.get(name)

    def model_names(self) -> list[str]:
        experiment = self.selected_experiment()
        return [str(n) for n in getattr(experiment, "model_names", ())] if experiment else []

    def select_dataset(self, record: Any) -> None:
        self.selected = dict(record) if isinstance(record, dict) else {}
        names = self.model_names()
        if self.model not in names:
            self.model = names[0] if names else ""

    def select_fit(self, record: Any) -> None:
        if isinstance(record, dict) and record.get("uid"):
            self.docks.show_fit(str(record["uid"]))

    def enabled(self, name: str) -> bool:
        if name == "add_fit":
            return bool(self.selected and self.model) and not self.docks.busy
        if name == "remove_selected":
            return bool(self.selected) and not self.docks.busy
        return True

    def add_fit(self) -> None:
        """Add a fit of the chosen model to the selected dataset."""
        if self.selected:
            self.docks.add_fit(int(self.selected["index"]), self.model)

    def remove_selected(self) -> None:
        self.remove_dataset(self.selected)

    def remove_dataset(self, record: Any) -> None:
        if isinstance(record, dict) and record.get("uid"):
            self.docks.remove_dataset(str(record["uid"]))
            self.selected = {}


class AnalysisModel:
    """The Analysis panel: the current fit's range, χ², *Fit* and its parameter table."""

    def __init__(self, docks: DataDocks) -> None:
        self.docks = docks
        self.info: dict = {}
        self.parameters = _Rows()
        self.xmin = 0
        self.xmax = 0

    def set_info(self, info: dict) -> None:
        """Adopt the server's description of the current fit."""
        self.info = dict(info or {})
        fit_range = self.info.get("fit_range") or [0, 0]
        self.xmin, self.xmax = int(fit_range[0]), int(fit_range[1])
        rows = _Rows()
        # The model's own order (``parameters_all``); the name-keyed dict only for an older server.
        listed = (self.info.get("model") or {}).get("parameters_all") or [
            {"name": name, **entry} for name, entry in (self.info.get("parameters") or {}).items()
        ]
        for entry in listed:
            bounds = entry.get("bounds") or (None, None)
            rows.append(
                {
                    "uid": str(entry.get("uid") or entry.get("name")),
                    "name": str(entry.get("name", "")),
                    "value": _number(entry.get("value")),
                    "fixed": bool(entry.get("fixed")),
                    "lo": _number(bounds[0]) if len(bounds) > 0 else None,
                    "hi": _number(bounds[1]) if len(bounds) > 1 else None,
                    "bounds_on": bool(entry.get("bounds_on")),
                    "error": _number(entry.get("error_estimate")),
                    "linked": str(entry.get("linked_to") or ""),
                    "output": bool(entry.get("is_output")),
                    "muted": bool(entry.get("fixed") or entry.get("is_output")),
                }
            )
        rows.revision = self.parameters.revision + 1
        self.parameters = rows

    def parameter_rows(self) -> list:
        return self.parameters

    def fit_title(self) -> str:
        if self.docks.session is None:
            return self.docks.session_status()
        if not self.info:
            return tr("No fit. Add one in the Datasets panel (+ Analysis).")
        return str(self.info.get("name") or "")

    def fit_summary(self) -> str:
        if not self.info:
            return ""
        chi2r = _number(self.info.get("chi2r_current"))
        if chi2r is None:
            chi2r = _number(self.info.get("chi2r"))
        text = tr("χ²ᵣ {chi2r}   points {n}   free {free}").format(
            chi2r="—" if chi2r is None else f"{chi2r:.4g}",
            n=self.info.get("n_points", "—"),
            free=self.info.get("n_free", "—"),
        )
        return text

    def enabled(self, name: str) -> bool:
        if name in ("run_fit", "auto_range", "remove_fit", "xmin", "xmax"):
            return bool(self.info) and not self.docks.busy
        return True

    def cell_editable(self, record: Any, key: str) -> bool:
        record = record or {}
        return (
            bool(self.info)
            and not self.docks.busy
            and not record.get("linked")
            and not record.get("output")
        )

    def edit_parameter(self, record: Any, key: str, value: Any) -> None:
        """A cell of the parameter table was changed: send it to the server."""
        if isinstance(record, dict):
            self.docks.edit_parameter(str(record["name"]), key, value, record)

    def run_fit(self) -> None:
        self.docks.run_fit()

    def range_changed(self, _value: Any = None) -> None:
        self.docks.set_range(int(self.xmin), int(self.xmax))

    def auto_range(self) -> None:
        last = max(0, int(self.info.get("n_data", 0) or 0) - 1)
        self.docks.set_range(0, last, auto=True)

    def remove_fit(self) -> None:
        self.docks.remove_fit(str(self.info.get("uid") or ""))


# ── the docks ────────────────────────────────────────────────────────────────


@dataclass
class _Job:
    """An API call under way on the worker."""

    label: str
    after: Callable[[Any], None] | None = None
    build: BackgroundBuild = field(default_factory=BackgroundBuild)


class DataDocks:
    """The data and fit docks of one shell.

    Parameters
    ----------
    shell : EmtkShellApp
        The shell drawing the docks (its dock manager, frame request and child hosting).
    session_factory : callable, optional
        ``session_factory(wake=...) -> ShellSession``, run on a worker thread when
        the docks are made; without one the docks say there is no session.
    """

    def __init__(self, shell: Any, session_factory: Callable[..., Any] | None = None) -> None:
        self.shell = shell
        self.session: Any = None
        self.status = ""
        self.error = ""
        self.read = ReadDataModel(self)
        self.datasets = DatasetsModel(self)
        self.analysis = AnalysisModel(self)
        self.specs = {name: load_view(name) for name in ("read_data", "datasets", "analysis")}
        self.forms = {name: FormState() for name in self.specs}
        self.windows: dict[str, Any] = {}
        self.current_uid = ""
        self.job: _Job | None = None
        self.file_dialog: Any = None
        self._file_window: Any = None
        #: Data points per dataset uid (groups and their members), for the range's *auto*.
        self._lengths: dict[str, int] = {}
        self._dirty: set[str] = set()
        self._reader_apps: dict[int, Any] = {}
        self._reader_errors: dict[int, str] = {}
        self._starting = BackgroundBuild(wake=self.request_frame)
        if session_factory is not None:
            wake = self.request_frame
            self._starting.start(
                {"session": lambda: session_factory(wake=wake)}, name="chisurf-shell-session"
            )
            self.status = tr("Starting the session…")
        docks = shell.docks
        docks.add_window(READ_KEY, tr("Read data"), self._draw_read, dock="left", closable=False)
        docks.add_window(
            DATASETS_KEY, tr("Datasets"), self._draw_datasets, dock="left", closable=False
        )
        docks.add_window(
            ANALYSIS_KEY, tr("Analysis"), self._draw_analysis, dock="left", closable=False
        )
        docks.add_window(
            PLOT_KEY, tr("Plot settings"), self._draw_plot, dock="left", closable=False
        )

    # -- plumbing ------------------------------------------------------------ #
    def request_frame(self) -> None:
        self.shell.request_frame()

    @property
    def busy(self) -> bool:
        """Whether an API call is under way (or the session is still starting)."""
        return self.job is not None or self._starting.busy

    def experiments(self) -> dict[str, Any]:
        return self.session.experiments() if self.session is not None else {}

    def session_status(self) -> str:
        if self.error:
            return self.error
        if self._starting.busy:
            return tr("Starting the session…")
        return tr("No session: data and fits are not available in this window.")

    def adopt(self, session: Any) -> None:
        """Use *session* (the factory's result, or one a test made): subscribe and read its state."""
        self.session = session
        session.events.wake = self.request_frame
        session.events.subscribe("", self._on_event)
        names = list(self.experiments())
        if names and self.read.experiment not in names:
            self.read.experiment = "FCS" if "FCS" in names else names[0]
            self.read.experiment_changed(self.read.experiment)
        self._dirty |= {"datasets", "fits", "current", "windows"}
        self.status = tr("Ready")

    def poll(self) -> None:
        """Once per frame, before drawing: adopt the session, finish calls, handle events, re-read."""
        if self._starting.busy:
            results = self._starting.collect()
            if results is not None:
                made, error = results.get("session", (None, None))
                if error is not None:
                    self.error = tr("The session could not start: {error}").format(error=error)
                    _log.error("session start failed: %s", error)
                elif made is not None:
                    self.adopt(made)
        if self.job is not None:
            results = self.job.build.collect()
            if results is not None:
                job, self.job = self.job, None
                result, error = results.get("call", (None, None))
                self._finished(job, result, error)
        if self.session is not None:
            self.session.events.drain()
        if self._dirty and self.session is not None and self.job is None:
            self._sync()
        for window in self.windows.values():
            window.poll()

    def _start(self, label: str, call: Callable[[], Any], after=None) -> bool:
        """Run *call* on the worker; one at a time."""
        if self.session is None or self.busy:
            self.status = (
                tr("Busy: {label}").format(label=self.job.label) if self.job else self.status
            )
            return False
        job = _Job(label, after, BackgroundBuild(wake=self.request_frame))
        self.job = job
        self.status = label
        job.build.start({"call": call}, name="chisurf-shell-call")
        return True

    def _finished(self, job: _Job, result: Any, error: BaseException | None) -> None:
        if error is not None:
            self.status = tr("{label} failed: {error}").format(label=job.label, error=error)
            _log.error("%s failed: %s", job.label, error)
        elif isinstance(result, dict) and result.get("ok") is False:
            self.status = tr("{label} failed: {error}").format(
                label=job.label, error=result.get("error", "?")
            )
            _log.error("%s failed: %s", job.label, result.get("error"))
        else:
            self.status = tr("{label} done.").format(label=job.label.rstrip("…"))
            if job.after is not None:
                job.after(result)
        # Whatever the call changed is announced by events; re-read once more regardless.
        self._dirty |= {"datasets", "fits", "current"}
        self.request_frame()

    # -- events ---------------------------------------------------------------- #
    def _on_event(self, payload: dict) -> None:
        topic = str(payload.get("topic", ""))
        uid = str(payload.get("fit_uid") or "")
        if topic.startswith("dataset."):
            self._dirty.add("datasets")
        elif topic in ("fit.created", "fit.added"):
            self._dirty |= {"fits", "windows"}
            if uid:
                self.current_uid = uid
                self._dirty.add("current")
        elif topic in ("fit.removed", "fit.cleared", "fit.reordered"):
            self._dirty |= {"fits", "windows", "current"}
        elif topic in ("fit.ran", "fit.updated") or topic.startswith("parameter."):
            self._dirty |= {"fits", "current"}
            targets = [self.windows[uid]] if uid in self.windows else list(self.windows.values())
            for window in targets:
                window.refresh()
        elif topic.startswith(("session.", "project.")):
            self._dirty |= {"datasets", "fits", "windows", "current"}
        self.request_frame()

    def _sync(self) -> None:
        """Re-read what is dirty from the server (main thread, no call under way)."""
        api = self.session.api
        dirty, self._dirty = self._dirty, set()
        try:
            if "datasets" in dirty:
                listed = api.list_datasets() or []
                rows = _Rows(
                    {
                        "index": int(d.get("index", i)),
                        "uid": str(d.get("uid", "")),
                        "name": str(d.get("name", "")),
                        "experiment": str(d.get("experiment", "")),
                    }
                    for i, d in enumerate(listed)
                )
                rows.revision = self.datasets.datasets.revision + 1
                self.datasets.datasets = rows
                self._lengths = {}
                for d in listed:
                    members = d.get("members") or []
                    for member in members:
                        self._lengths[str(member.get("uid", ""))] = int(member.get("length") or 0)
                    if members:
                        self._lengths[str(d.get("uid", ""))] = int(members[0].get("length") or 0)
                uids = {row["uid"] for row in rows}
                if self.datasets.selected.get("uid") not in uids:
                    self.datasets.selected = {}
                    for row in rows:
                        if row["experiment"] and row["experiment"] != "Global":
                            self.datasets.select_dataset(row)
                if not self.datasets.selected and rows:
                    self.datasets.select_dataset(rows[-1])
            if "fits" in dirty or "windows" in dirty:
                fits = api.list_fits() or []
                rows = _Rows(
                    {
                        "index": int(f.get("index", i)),
                        "uid": str(f.get("uid", "")),
                        "name": str(f.get("name", "")),
                        "data": str(f.get("dataset_name", "")),
                        "model": str(f.get("model_name", "")),
                    }
                    for i, f in enumerate(fits)
                )
                rows.revision = self.datasets.fits.revision + 1
                self.datasets.fits = rows
                live = {row["uid"]: row for row in rows}
                if self.current_uid not in live:
                    self.current_uid = rows[-1]["uid"] if rows else ""
                    dirty.add("current")
                if "windows" in dirty:
                    for uid in [uid for uid in self.windows if uid not in live]:
                        self.close_window(uid)
                    for uid, row in live.items():
                        if uid not in self.windows:
                            self.open_window(uid, row["name"])
            if "current" in dirty:
                if self.current_uid:
                    info = api.get_fit_info(fit_uid=self.current_uid) or {}
                    info = info.get("fit", info) if isinstance(info, dict) else {}
                    info["n_data"] = self._lengths.get(str(info.get("dataset_uid", "")), 0)
                    self.analysis.set_info(info)
                else:
                    self.analysis.set_info({})
        except Exception as exc:  # noqa: BLE001 - a failed read keeps the last rows
            _log.exception("reading the session failed")
            self.status = tr("Reading the session failed: {error}").format(error=exc)

    # -- actions (each one API call on the worker) ------------------------------- #
    def load(self, reader: Any, path: str | list[str]) -> bool:
        """Read *path* with *reader* and add it to the datasets."""
        if reader is None:
            self.status = tr("Select an experiment and a file type first.")
            return False
        filename = getattr(reader, "filename", None) if not path else path
        api = self.session.api if self.session is not None else None
        if api is None:
            return False
        name = Path(str(path)).name if path else str(reader.name)
        kwargs = {"filename": str(filename)} if filename else {}
        return self._start(
            tr("Reading {name}…").format(name=name),
            lambda: api.load_dataset(experiment_reader=reader, **kwargs),
        )

    def add_fit(self, dataset_index: int, model_name: str) -> bool:
        """Add a fit of *model_name* to the dataset at *dataset_index*."""
        api = self.session.api if self.session is not None else None
        if api is None or not model_name:
            return False

        def after(result: Any) -> None:
            uid = str((result or {}).get("uid") or "")
            if uid:
                self.current_uid = uid
                self._dirty |= {"windows", "current"}

        def call() -> Any:
            result = api.add_fit([int(dataset_index)], model_name=model_name)
            uid = str((result or {}).get("uid") or "") if isinstance(result, dict) else ""
            if uid:
                # Compute the model once, so the new window shows its curve and χ² at once.
                api.fit_update(fit_uid=uid)
            return result

        return self._start(tr("Adding a {model} fit…").format(model=model_name), call, after)

    def run_fit(self) -> bool:
        uid = self.current_uid
        if not uid or self.session is None:
            return False
        api = self.session.api
        return self._start(tr("Fitting…"), lambda: api.run_fit(fit_uid=uid))

    def set_range(self, xmin: int, xmax: int, auto: bool = False) -> bool:
        uid = self.current_uid
        if not uid or self.session is None:
            return False
        api = self.session.api
        xmin, xmax = max(0, int(xmin)), max(0, int(xmax))
        if xmax < xmin:
            xmin, xmax = xmax, xmin

        def call() -> Any:
            result = api.set_fit_range(xmin, xmax, fit_uid=uid)
            if isinstance(result, dict) and result.get("ok") is False:
                return result
            return api.fit_update(fit_uid=uid)

        return self._start(tr("Setting the fit range…"), call)

    def edit_parameter(self, name: str, key: str, value: Any, record: dict) -> bool:
        """Send one parameter-table edit to the server, then update the fit."""
        uid = self.current_uid
        if not uid or self.session is None:
            return False
        api = self.session.api
        if key == "value":
            number = _number(value)
            if number is None:
                return False
            change = lambda: api.set_parameter_value(name, number, fit_uid=uid)  # noqa: E731
        elif key == "fixed":
            change = lambda: api.set_parameter_fixed(name, bool(value), fit_uid=uid)  # noqa: E731
        elif key in ("lo", "hi"):
            lo = _number(value) if key == "lo" else _number(record.get("lo"))
            hi = _number(value) if key == "hi" else _number(record.get("hi"))
            change = lambda: api.set_parameter_bounds(name, (lo, hi), fit_uid=uid)  # noqa: E731
        elif key == "bounds_on":
            change = lambda: api.set_parameter_bounds_on(name, bool(value), fit_uid=uid)  # noqa: E731
        else:
            return False

        def call() -> Any:
            result = change()
            if isinstance(result, dict) and result.get("ok") is False:
                return result
            return api.fit_update(fit_uid=uid)

        return self._start(tr("Setting {name}…").format(name=name), call)

    def remove_fit(self, uid: str) -> bool:
        if not uid or self.session is None:
            return False
        api = self.session.api
        return self._start(tr("Removing the fit…"), lambda: api.remove_fits(fit_uids=[uid]))

    def remove_dataset(self, uid: str) -> bool:
        if not uid or self.session is None:
            return False
        api = self.session.api
        return self._start(
            tr("Removing the dataset…"), lambda: api.remove_datasets(dataset_uids=[uid])
        )

    def drop(self, paths: list[str]) -> bool:
        """Files dropped onto the shell: read the first with the selected file type."""
        if not paths or self.session is None:
            return False
        self.read.path = str(paths[0])
        self.shell.docks.focus(READ_KEY)
        return self.load(self.read.reader(), self.read.path)

    # -- fit windows --------------------------------------------------------------- #
    def open_window(self, uid: str, title: str) -> Any:
        """Open (or bring forward) the window of fit *uid*."""
        from chisurf.emtk.fit_window import FitWindow

        if uid in self.windows:
            self.shell.docks.show(self.windows[uid].key)
            return self.windows[uid]
        fit = self.session.presentation_fit(uid) if self.session is not None else None
        if fit is None:
            return None
        window = FitWindow(uid, fit, title, request_frame=self.request_frame)
        self.windows[uid] = window
        self.shell.docks.add_window(
            window.key,
            title,
            lambda box, u=uid: self._draw_window(u, box),
            dock="center",
            scrollable=False,
            padding=0.0,
            min_size=(240.0, 160.0),
            tooltip=title,
        )
        self.shell.docks.focus(window.key)
        return window

    def show_fit(self, uid: str) -> None:
        """Make *uid* the current fit and bring its window forward (reopening a closed one)."""
        self.current_uid = uid
        self._dirty.add("current")
        row = next((r for r in self.datasets.fits if r["uid"] == uid), None)
        window = self.open_window(uid, row["name"] if row else uid)
        if window is not None:
            self.shell.docks.show(window.key)
            self.shell.docks.focus(window.key)
        self.request_frame()

    def close_window(self, uid: str) -> None:
        window = self.windows.pop(uid, None)
        if window is None:
            return
        window.close()
        self.shell.docks.remove_window(window.key)

    def closed_by_user(self) -> None:
        """A fit window closed with its ``×`` only closes the window; the fit stays in the session."""
        for uid, window in list(self.windows.items()):
            dock = self.shell.docks.window(window.key)
            if dock is not None and not dock.visible:
                self.close_window(uid)

    def focused_window(self) -> None:
        """The fit whose window tab is active in the centre becomes the current fit."""
        key = self.shell.docks.active_tab("center")
        for uid, window in self.windows.items():
            if window.key == key and uid != self.current_uid:
                self.current_uid = uid
                self._dirty.add("current")

    def current_window(self) -> Any:
        return self.windows.get(self.current_uid)

    # -- reader settings ----------------------------------------------------------- #
    def reader_settings_app(self, reader: Any) -> Any:
        """The reader's native settings app, or ``None`` when its settings have no native form."""
        if reader is None:
            return None
        key = id(reader)
        if key in self._reader_apps:
            return self._reader_apps[key]
        if key in self._reader_errors:
            return None
        try:
            from chisurf.emtk.reader_settings import ReaderSettingsApp

            app = ReaderSettingsApp(reader)
        except Exception as exc:  # noqa: BLE001 - shown as a note, the reader's defaults are used
            self._reader_errors[key] = str(exc)
            return None
        app.set_frame_request_callback(self.request_frame)
        self._reader_apps[key] = app
        return app

    def reader_settings_error(self, reader: Any) -> str:
        if reader is None:
            return ""
        self.reader_settings_app(reader)
        error = self._reader_errors.get(id(reader))
        if not error:
            return ""
        return tr(
            "{name}: its settings have no native form yet ({error}); its defaults are used."
        ).format(name=reader.name, error=error)

    # -- file dialog ------------------------------------------------------------- #
    def open_file_dialog(self) -> None:
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        start = str(Path(self.read.path).expanduser().parent) if self.read.path else None
        self.file_dialog = FileDialog(tr("Read data"), mode="open", directory=start)
        self._file_window = DialogWindow(tr("Read data"), size=(760, 540))
        self.request_frame()

    def draw_file_dialog(self, box) -> None:
        """The open file dialog over the whole shell (drawn last, on top)."""
        if self.file_dialog is None:
            return
        window = self._file_window
        closed = window.begin(box)
        paths = self.file_dialog.draw()
        window.end()
        if closed or paths is False:
            self.file_dialog = None
        elif paths:
            self.file_dialog = None
            self.read.path = str(paths[0])

    # -- drawing --------------------------------------------------------------- #
    def _form(self, name: str, model: Any, prefix: str) -> None:
        form = self.forms[name]
        draw_form(self.specs[name], model, form, titles=True)
        for key, rect in form.rects.items():
            self.shell.item_rects[f"{prefix}.{key}"] = rect

    def _status_line(self) -> None:
        if self.status:
            im.separator()
            im.text_disabled(self.status)
            self.shell.item_rects["data.status"] = im.get_item_rect()

    def _draw_read(self, box) -> None:
        self._form("read_data", self.read, "read")
        app = self.reader_settings_app(self.read.reader()) if self.session is not None else None
        if app is not None:
            im.separator_text(tr("File parameters"))
            x, y = im.get_cursor_screen_pos()
            w, h = im.get_content_region_avail()
            room = max(1.0, float(h) - 40.0)
            self.shell.host_child(READ_KEY, f"reader.{id(app)}", app, (x, y, float(w), room))
            im.dummy((float(w), room))
        self._status_line()

    def _draw_datasets(self, box) -> None:
        self._form("datasets", self.datasets, "datasets")
        self._status_line()

    def _draw_analysis(self, box) -> None:
        self._form("analysis", self.analysis, "analysis")
        self._status_line()

    def _draw_plot(self, box) -> None:
        window = self.current_window()
        page = window.current_page() if window is not None else None
        if page is None:
            im.text_disabled(tr("No plot selected."))
            return
        has = getattr(page, "has_settings", None)
        if not callable(has) or not has():
            im.text_disabled(tr("{name}: this page has no settings.").format(name=page.name))
            return
        try:
            page.draw_settings()
        except Exception as exc:  # noqa: BLE001 - a broken form must not take the dock down
            _log.exception("drawing the settings of %s failed", page.name)
            im.text_colored(
                (220, 90, 90),
                tr("{name}: settings failed ({error}).").format(name=page.name, error=exc),
            )

    def _draw_window(self, uid: str, box) -> None:
        window = self.windows.get(uid)
        if window is None:
            return
        x, y, w, h = (float(v) for v in box)
        window.box = (x, y, max(1.0, w), max(1.0, h))
        self.shell.host_child(window.key, window.key, window.app, window.box)

    def close(self) -> None:
        """Close the windows, the reader settings and the session."""
        for uid in list(self.windows):
            self.close_window(uid)
        for app in self._reader_apps.values():
            try:
                app.close()
            except Exception:  # noqa: BLE001
                _log.exception("closing reader settings failed")
        self._reader_apps.clear()
        if self.job is not None:
            self.job.build.collect(wait=True)
            self.job = None
        if self._starting.busy:
            results = self._starting.collect(wait=True) or {}
            made, _error = results.get("session", (None, None))
            if made is not None and self.session is None:
                self.session = made
        if self.session is not None:
            self.session.close()
            self.session = None


__all__ = [
    "ANALYSIS_KEY",
    "AnalysisModel",
    "DATASETS_KEY",
    "DataDocks",
    "DatasetsModel",
    "PLOT_KEY",
    "READ_KEY",
    "ReadDataModel",
    "load_view",
]
