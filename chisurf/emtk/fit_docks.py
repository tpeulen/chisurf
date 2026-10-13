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
from emtk.i18n import mark, tr
from emtk.view_form import FormState, draw_form

from chisurf.core.fitting import prior_families
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
#: The least height the Read data dock gives a reader's settings form, in logical pixels.
MIN_READER_FORM_H = 260.0


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
        #: Every selected dataset row (click, ctrl/shift-click): the table writes it, + Analysis reads it.
        self.selection: list = []
        self.datasets = _Rows()
        self.fits = _Rows()

    def dataset_rows(self) -> list:
        return self.datasets

    def fit_rows(self) -> list:
        return self.fits

    def selected_experiment(self) -> Any:
        """The experiment of the selected dataset (the hidden *Global* one too), else of Read data."""
        name = str(self.selected.get("experiment") or self.docks.read.experiment)
        found = self.docks.experiments().get(name)
        if found is None and self.docks.session is not None:
            lookup = getattr(self.docks.session, "experiment", None)
            found = lookup(name) if callable(lookup) else None
        return found

    def selected_dataset(self) -> Any:
        """The dataset object of the selected row (read only), ``None`` when absent.

        A member of a group stands for its group, which is what a fit is added to.
        """
        uid = str(self.selected.get("parent") or self.selected.get("uid") or "")
        state = getattr(getattr(self.docks.session, "server", None), "state", None)
        for dataset in list(getattr(state, "datasets", None) or ()):
            if uid and str(getattr(dataset, "unique_identifier", "")) == uid:
                return dataset
        return None

    def model_names(self) -> list[str]:
        """The models the selected dataset can be fitted with, as the Qt shell lists them.

        One experiment holds data of more than one shape (PDA reads two- and three-colour data), so
        the experiment's list is filtered by the dataset; models the user disabled are left out.
        """
        experiment = self.selected_experiment()
        if experiment is None:
            return []
        dataset = self.selected_dataset()
        try:
            names = [str(n) for n in experiment.get_model_names(dataset)]
        except Exception:  # noqa: BLE001 - an experiment that cannot filter lists everything
            names = [str(n) for n in getattr(experiment, "model_names", ())]
        try:
            from chisurf.core import settings

            disabled = settings.cs_settings.get("plugins", {}).get("disabled_models", [])
        except Exception:  # noqa: BLE001 - no settings: nothing is disabled
            disabled = []
        return [name for name in names if name not in disabled]

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

    def selected_rows(self) -> list:
        """The rows + Analysis acts on: the table's selection, else (a program chose) the one selected."""
        uid = str(self.selected.get("uid") or "")
        chosen = [r for r in self.selection if isinstance(r, dict) and r.get("uid")]
        if not any(str(r["uid"]) == uid for r in chosen):
            chosen = [self.selected] if uid else []
        live = {str(r["uid"]): r for r in self.datasets}
        # A member of a group stands for its group: a fit, a removal or a save acts on whole datasets.
        tops: dict[str, dict] = {}
        for r in chosen:
            row = live.get(str(r.get("parent") or r["uid"]))
            if row is not None:
                tops.setdefault(str(row["uid"]), row)
        return list(tops.values())

    # -- the context menu (Save, Load, Remove, Group, Ungroup, Refresh) ---------- #
    def remove_selected_row(self, record: Any = None) -> None:
        """*Remove* in the context menu: every selected dataset."""
        self.remove_selected()

    def can_remove(self, record: Any = None) -> bool:
        """Remove acts on the selected datasets."""
        return bool(self.selected_rows()) and not self.docks.busy

    def can_group(self, record: Any = None) -> bool:
        """Group needs two or more selected datasets."""
        return len(self.selected_rows()) > 1 and not self.docks.busy

    def can_ungroup(self, record: Any = None) -> bool:
        """Ungroup acts on selected groups."""
        return any(r.get("group") for r in self.selected_rows()) and not self.docks.busy

    def can_save(self, record: Any = None) -> bool:
        """Save writes one dataset (the first selected)."""
        return bool(self.selected_rows()) and not self.docks.busy

    def save_dataset(self, record: Any = None) -> None:
        """*Save*: the first selected dataset to a pickle file, as the Qt list did."""
        rows = self.selected_rows()
        if rows:
            self.docks.save_dataset(str(rows[0]["uid"]), str(rows[0].get("name", "")))

    def load_dataset(self, record: Any = None) -> None:
        """*Load*: a pickled dataset file into the session."""
        self.docks.load_dataset_file()

    def group_datasets(self, record: Any = None) -> None:
        """*Group*: the selected datasets into one group (a fit over it has one curve per member)."""
        rows = self.selected_rows()
        if len(rows) > 1:
            self.docks.group_datasets([int(r["index"]) for r in rows])

    def ungroup_datasets(self, record: Any = None) -> None:
        """*Ungroup*: the selected groups back into their members."""
        rows = [r for r in self.selected_rows() if r.get("group")]
        if rows:
            self.docks.ungroup_datasets([int(r["index"]) for r in rows])

    def refresh_datasets(self, record: Any = None) -> None:
        """*Refresh*: read the dataset and fit lists from the session again."""
        self.docks.refresh()

    def add_fit(self) -> None:
        """Add a fit of the chosen model to each selected dataset (one fit per curve, as the Qt shell does)."""
        rows = self.selected_rows()
        if rows:
            self.docks.add_fit([int(r["index"]) for r in rows], self.model)

    def remove_selected(self) -> None:
        """Remove every selected dataset (a member of a group removes its group)."""
        rows = self.selected_rows()
        if rows:
            self.docks.remove_datasets([str(r["uid"]) for r in rows])
            self.selected, self.selection = {}, []

    def drag_dataset(self, record: Any, x: float, y: float, dropped: bool) -> None:
        """A dataset row dragged out of the table; dropped on a fit window, the fit takes it."""
        self.docks.dataset_dragged(record if isinstance(record, dict) else None, x, y, dropped)

    def remove_dataset(self, record: Any) -> None:
        """Delete on a row: the whole selection when the row is in it, else that row."""
        if not (isinstance(record, dict) and record.get("uid")):
            return
        uid = str(record.get("parent") or record["uid"])
        rows = self.selected_rows()
        if any(str(r["uid"]) == uid for r in rows):
            self.remove_selected()
        else:
            self.docks.remove_datasets([uid])
            self.selected = {}


def _mcts_setting(key: str, default: Any) -> Any:
    """One ``optimization.mcts`` user setting, or *default*."""
    from chisurf.core import settings

    try:
        return type(default)(settings.cs_settings["optimization"]["mcts"].get(key, default))
    except (KeyError, TypeError, AttributeError, ValueError):
        return default


class AnalysisModel:
    """The Analysis panel: the current fit, its controller (actions, dataset, result, range) and parameters."""

    def __init__(self, docks: DataDocks) -> None:
        self.docks = docks
        self.info: dict = {}
        self.parameters = _Rows()
        self.xmin = 0
        self.xmax = 0
        self.xmin2 = 0
        self.xmax2 = 0
        self.dataset_index = 0
        self.result_index = 1
        self.local_first = True
        self.search_fit_settings = bool(_mcts_setting("search_fit_settings", False))
        #: Whether BFF can search the current fit's model (MCTS is shown only then).
        self.model_search = False

    def set_info(self, info: dict) -> None:
        """Adopt the server's description of the current fit."""
        self.info = dict(info or {})
        fit_range = self.info.get("fit_range") or [0, 0]
        self.xmin, self.xmax = int(fit_range[0]), int(fit_range[1])
        shape = self.info.get("grid_shape")
        if shape and not (self.xmin2 or self.xmax2):
            self.xmin2, self.xmax2 = int(shape[1]) - 1, int(shape[0]) - 1
        members = self.info.get("members") or []
        selected = next((i for i, m in enumerate(members) if m.get("selected")), 0)
        self.dataset_index = int(self.info.get("selected_member", selected) or 0)
        self.result_index = int(self.info.get("result_idx", 0) or 0) + 1
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
                    "prior": prior_families.describe(entry.get("prior")),
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

    @property
    def has_editor(self) -> bool:
        """Whether the model's own editor is drawn (the flat parameter table is then not)."""
        return self.docks.editor.editor is not None

    @property
    def flat_table_hidden(self) -> bool:
        """The flat parameter table stands in only for a fit whose model has no editor."""
        return self.has_editor or not self.info

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

    @property
    def is_2d(self) -> bool:
        """Whether the fit's data is a 2-D grid (the second range pair applies)."""
        return bool(self.info.get("grid_shape"))

    def dataset_options(self) -> list:
        """The fit's datasets as ``(index, name)``: a global fit's members, else its one dataset."""
        members = self.info.get("members") or []
        if len(members) > 1:
            return [
                (i, str(m.get("dataset_name") or m.get("name") or i)) for i, m in enumerate(members)
            ]
        return [(0, str(self.info.get("dataset_name") or "—"))]

    def enabled(self, name: str) -> bool:
        live = bool(self.info) and not self.docks.busy
        if name in (
            "run_fit",
            "auto_range",
            "remove_fit",
            "xmin",
            "xmax",
            "xmin2",
            "xmax2",
            "sample",
            "select_dataset",
            "dataset_index",
        ):
            return live
        if name == "mcts":
            return live and self.model_search
        if name == "result_index":
            return live and int(self.info.get("n_results", 0) or 0) > 1
        return True

    def dataset_changed(self, value: Any) -> None:
        """Pick which member of a global fit the controls (and the editor) act on."""
        if len(self.info.get("members") or []) > 1:
            self.docks.select_member(int(value))

    def result_changed(self, value: Any) -> None:
        self.docks.set_result(max(0, int(value) - 1))

    def search_fit_settings_changed(self, value: Any) -> None:
        """Keep *Search fit settings* in the user settings, as the Qt controller does."""
        self.docks.store_mcts_setting("search_fit_settings", bool(value))

    def mcts(self) -> None:
        self.docks.run_model_search(bool(self.search_fit_settings))

    def sample(self) -> None:
        self.docks.ask_sampling_folder()

    def settings(self) -> None:
        self.docks.open_settings()

    def select_dataset(self) -> None:
        self.docks.open_dataset_picker()

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
        self.docks.run_fit(local_first=bool(self.local_first))

    def range_changed(self, _value: Any = None) -> None:
        if self.is_2d:
            self.docks.set_grid_range(
                int(self.xmin), int(self.xmin2), int(self.xmax), int(self.xmax2)
            )
        else:
            self.docks.set_range(int(self.xmin), int(self.xmax))

    def auto_range(self) -> None:
        self.docks.auto_range()

    def remove_fit(self) -> None:
        self.docks.remove_fit(str(self.info.get("uid") or ""))


# ── the docks ────────────────────────────────────────────────────────────────


@dataclass
class _Job:
    """An API call under way on the worker."""

    label: str
    after: Callable[[Any], None] | None = None
    build: BackgroundBuild = field(default_factory=BackgroundBuild)
    #: Called with the error text when the call fails (the status line says it regardless).
    failed: Callable[[str], None] | None = None


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
        from chisurf.emtk.model_editor import ModelEditor

        self.editor = ModelEditor(self)
        self.specs = {name: load_view(name) for name in ("read_data", "datasets", "analysis")}
        self.forms = {name: FormState() for name in self.specs}
        self.windows: dict[str, Any] = {}
        self.current_uid = ""
        self.job: _Job | None = None
        self.file_dialog: Any = None
        self._file_window: Any = None
        #: What the open file dialog's choice is for: ``callback(path)``.
        self._file_done: Callable[[str], None] | None = None
        #: The open sampling/fitting settings dialog (``chisurf.emtk.fit_controls.SettingsDialog``).
        self.settings_dialog: Any = None
        #: The open dataset picker of the controller's ``…`` (or of a curve picker's).
        self.dataset_picker: Any = None
        #: An MMFDB dataset picker opened by a model-editor file list.
        self.model_dialog: Any = None
        #: The MMFDB sample question after a file is chosen (``chisurf.emtk.sample_picker``).
        self.sample_dialog: Any = None
        #: The MMFDB client the sample question lists samples with (``None``: the session's).
        self.sample_client: Any = None
        #: A dataset row being dragged (``(row, x, y)``), drawn under the pointer.
        self.dragged: tuple[dict, float, float] | None = None
        #: A sampling job under way on the server, polled while the docks draw.
        self.sampling_job = ""
        #: The sampling job's percentage as of the last poll (the status strip's bar).
        self.sampling_progress = 0
        self._sampling_polled = 0.0
        #: Data points per dataset uid (groups and their members), for the range's *auto*.
        self._lengths: dict[str, int] = {}
        self._dirty: set[str] = set()
        self._known_datasets: set[str] = set()
        #: ``(focused window, centre tab)`` as of the last frame: a change is the user's choice of a fit.
        self._seen_focus: tuple = (None, None)
        self._reader_apps: dict[int, Any] = {}
        self._reader_errors: dict[int, str] = {}
        self._starting = BackgroundBuild(wake=self.request_frame)
        if session_factory is not None:
            wake = self.request_frame
            # The shell's splash follows the startup stages the session runs through.
            # (and so does the status strip: the shell's ``stage_started`` forwards to both).
            on_stage = getattr(shell, "stage_started", None)
            if not callable(on_stage):
                splash = getattr(shell, "splash", None)
                on_stage = splash.stage_started if splash is not None else None
            self._starting.start(
                {"session": lambda: session_factory(wake=wake, on_stage=on_stage)},
                name="chisurf-shell-session",
            )
            self.status = tr("Starting the session…")
        docks = shell.docks
        docks.add_window(READ_KEY, mark("Read data"), self._draw_read, dock="left", closable=False)
        docks.add_window(
            DATASETS_KEY, mark("Datasets"), self._draw_datasets, dock="left", closable=False
        )
        docks.add_window(
            ANALYSIS_KEY, mark("Analysis"), self._draw_analysis, dock="left", closable=False
        )
        docks.add_window(
            PLOT_KEY, mark("Plot settings"), self._draw_plot, dock="left", closable=False
        )

    # -- plumbing ------------------------------------------------------------ #
    def request_frame(self) -> None:
        self.shell.request_frame()

    @property
    def starting(self) -> bool:
        """Whether the session has not been adopted yet (its worker runs, or its result waits for a frame)."""
        return self._starting.busy

    @property
    def session_settled(self) -> bool:
        """Whether the session's worker has ended (made the session or failed); the next frame adopts it."""
        return not self._starting.running

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
        ensure = getattr(session, "ensure_global_dataset", None)
        if callable(ensure):
            try:
                ensure()
            except Exception:  # noqa: BLE001 - local fits still work without it
                _log.exception("adding the global-fit dataset failed")
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
        self._poll_sampling()
        for window in self.windows.values():
            window.poll()

    def _poll_sampling(self) -> None:
        """Follow a sampling job: its progress in the status line, its verdict when it ends."""
        import time

        if not self.sampling_job or self.session is None or self.job is not None:
            return
        now = time.monotonic()
        if now - self._sampling_polled < 1.0:
            return
        self._sampling_polled = now
        try:
            status = self.session.api.sampling_status(self.sampling_job) or {}
        except Exception as exc:  # noqa: BLE001
            self.status = tr("Sampling: {error}").format(error=exc)
            self.sampling_job = ""
            return
        state = str(status.get("status", ""))
        if state in ("running", "queued", "cancelling"):
            self.sampling_progress = int(status.get("progress") or 0)
            self.status = tr("Sampling… {progress}%").format(progress=self.sampling_progress)
            self.request_frame()
            return
        self.sampling_job = ""
        warnings = list(status.get("warnings") or [])
        if state == "completed" and not warnings:
            self.status = tr("Sampling done; the chains converged.")
        elif state == "completed":
            self.status = tr("Sampling done, but: {warnings}").format(warnings="; ".join(warnings))
        else:
            self.status = tr("Sampling {state}: {error}").format(
                state=state or "?", error=status.get("error", "")
            )
        self._dirty |= {"current"}

    def _start(self, label: str, call: Callable[[], Any], after=None, failed=None) -> bool:
        """Run *call* on the worker; one at a time."""
        if self.session is None or self.busy:
            self.status = (
                tr("Busy: {label}").format(label=self.job.label) if self.job else self.status
            )
            return False
        job = _Job(label, after, BackgroundBuild(wake=self.request_frame), failed)
        self.job = job
        self.status = label
        job.build.start({"call": call}, name="chisurf-shell-call")
        return True

    def _finished(self, job: _Job, result: Any, error: BaseException | None) -> None:
        if error is not None:
            self.status = tr("{label} failed: {error}").format(label=job.label, error=error)
            _log.error("%s failed: %s", job.label, error)
            if job.failed is not None:
                job.failed(str(error))
        elif isinstance(result, dict) and result.get("ok") is False:
            self.status = tr("{label} failed: {error}").format(
                label=job.label, error=result.get("error", "?")
            )
            _log.error("%s failed: %s", job.label, result.get("error"))
            if job.failed is not None:
                job.failed(str(result.get("error", "?")))
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
        elif topic in (
            "fit.ran",
            "fit.updated",
            "fit.dataset_changed",
            "fit.result_idx_changed",
            "fit.mask_changed",
            "fit.group.member_selected",
        ) or topic.startswith("parameter."):
            self._dirty |= {"fits", "current"}
            # A completed run names the fits it moved (a global fit's local fits): their windows too.
            moved = [uid, *(str(m) for m in payload.get("member_fit_uids") or ())]
            targets = [self.windows[u] for u in dict.fromkeys(moved) if u in self.windows]
            for window in targets or list(self.windows.values()):
                window.refresh()
        elif topic.startswith("model."):
            self._dirty |= {"current"}
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
                tree = _Rows()
                for row, d in zip(rows, listed):
                    # A file read is a group of one curve; that is not drawn as a group. A group made by
                    # *Group*, or a file of several curves, is: it unfolds into its members.
                    members = d.get("members") or []
                    if row["experiment"] == "Global" or not (
                        len(members) > 1 or d.get("type") == "ExperimentDataGroup"
                    ):
                        members = []
                    row["group"] = bool(members)
                    row["number"] = str(row["index"])
                    row["parent"] = ""
                    tree.append(row)
                    for position, member in enumerate(members):
                        tree.append(
                            {
                                "index": row["index"],
                                "number": f"{row['index']}.{position + 1}",
                                "uid": str(member.get("uid", "")),
                                "name": str(member.get("name", "")),
                                "experiment": str(member.get("experiment", "")),
                                "parent": row["uid"],
                                "group": False,
                            }
                        )
                tree.revision = self.datasets.datasets.revision + 1
                self.datasets.datasets = tree
                self._lengths = {}
                for d in listed:
                    members = d.get("members") or []
                    for member in members:
                        self._lengths[str(member.get("uid", ""))] = int(member.get("length") or 0)
                    if members:
                        self._lengths[str(d.get("uid", ""))] = int(members[0].get("length") or 0)
                uids = {row["uid"] for row in rows}
                # A dataset just read is the one the next fit is for, as in the Qt shell.
                fresh = [
                    row
                    for row in rows
                    if row["uid"] not in self._known_datasets and row["experiment"] != "Global"
                ]
                self._known_datasets = uids
                if fresh:
                    self.datasets.select_dataset(fresh[-1])
                if (
                    self.datasets.selected.get("parent") or self.datasets.selected.get("uid")
                ) not in uids:
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
                from chisurf.core.fitting.fit_labels import unique_labels

                for row, label in zip(rows, unique_labels([(r["name"], r["data"]) for r in rows])):
                    row["label"] = label
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
                            self.open_window(uid, row["label"])
                        else:
                            self._retitle(uid, row["label"])
            if "current" in dirty:
                if self.current_uid:
                    info = api.get_fit_info(fit_uid=self.current_uid) or {}
                    info = info.get("fit", info) if isinstance(info, dict) else {}
                    info["n_data"] = self._lengths.get(str(info.get("dataset_uid", "")), 0)
                    self.analysis.set_info(info)
                    try:
                        editor = api.model_editor(fit_uid=self.current_uid)
                    except Exception:  # noqa: BLE001 - the flat parameter table stands in
                        _log.exception("reading the model editor failed")
                        editor = None
                    self.editor.set_editor(self.current_uid, editor)
                    try:
                        self.analysis.model_search = bool(
                            api.model_search_available(fit_uid=self.current_uid)
                        )
                    except Exception:  # noqa: BLE001 - no search engine: no MCTS button
                        self.analysis.model_search = False
                else:
                    self.analysis.set_info({})
                    self.editor.set_editor("", None)
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

    def add_fit(self, dataset_index: int | list[int], model_name: str) -> bool:
        """Add a fit of *model_name* to the dataset at *dataset_index*, or one fit to each of a list."""
        api = self.session.api if self.session is not None else None
        indices = (
            [int(i) for i in dataset_index]
            if isinstance(dataset_index, (list, tuple))
            else [int(dataset_index)]
        )
        if api is None or not model_name or not indices:
            return False

        def after(result: Any) -> None:
            uid = str((result or {}).get("uid") or "")
            if uid:
                self.current_uid = uid
                self._dirty |= {"windows", "current"}

        def call() -> Any:
            # One fit per curve: the server's ``fit.create`` with several indices would build one fit
            # over all of them, which is a group, not what + Analysis on a selection means.
            result: Any = None
            for index in indices:
                result = api.add_fit([index], model_name=model_name)
                uid = str((result or {}).get("uid") or "") if isinstance(result, dict) else ""
                if uid:
                    # Compute the model once, so the new window shows its curve and χ² at once.
                    api.fit_update(fit_uid=uid)
                if isinstance(result, dict) and result.get("ok") is False:
                    break
            return result

        return self._start(tr("Adding a {model} fit…").format(model=model_name), call, after)

    def run_fit(self, local_first: bool | None = None) -> bool:
        uid = self.current_uid
        if not uid or self.session is None:
            return False
        api = self.session.api
        return self._start(
            tr("Fitting…"), lambda: api.run_fit(fit_uid=uid, local_first=local_first)
        )

    def auto_range(self) -> bool:
        """The fit range from the data, as the reader chooses it (``fit.range.auto``)."""
        uid = self.current_uid
        if not uid or self.session is None:
            return False
        api = self.session.api
        return self._then_update(
            tr("Choosing the fit range…"), lambda: api.auto_fit_range(fit_uid=uid)
        )

    def set_grid_range(self, x0: int, x1: int, y0: int, y1: int) -> bool:
        """The rectangle of a 2-D grid dataset the fit uses."""
        uid = self.current_uid
        if not uid or self.session is None:
            return False
        api = self.session.api
        return self._then_update(
            tr("Setting the fit range…"),
            lambda: api.set_fit_grid_range(x0, x1, y0, y1, fit_uid=uid),
        )

    def select_member(self, index: int) -> bool:
        """Show and edit member *index* of the current global fit."""
        uid = self.current_uid
        if not uid or self.session is None:
            return False
        api = self.session.api
        return self._then_update(
            tr("Selecting the dataset…"), lambda: api.select_group_member(index, fit_uid=uid)
        )

    def set_result(self, index: int) -> bool:
        """Show stored result *index* (0-based) of the current fit."""
        uid = self.current_uid
        if not uid or self.session is None:
            return False
        api = self.session.api
        return self._start(
            tr("Showing result {n}…").format(n=index + 1),
            lambda: api.set_fit_result_idx(index, fit_uid=uid),
        )

    def store_mcts_setting(self, key: str, value: Any) -> None:
        """Keep one ``optimization.mcts`` user setting for this session and the settings file."""
        from chisurf.core import settings
        from chisurf.core.settings.settings_utils import set_optimization_settings

        try:
            settings.cs_settings.setdefault("optimization", {}).setdefault("mcts", {})[key] = value
            if not set_optimization_settings(mcts={key: value}):
                _log.warning("optimization.mcts.%s could not be written to the settings file", key)
        except Exception:  # noqa: BLE001 - a settings file problem must not break the dock
            _log.exception("could not keep optimization.mcts.%s", key)

    def run_model_search(self, search_fit_settings: bool = False) -> bool:
        """MCTS: search the model structure on the server and apply the winner."""
        uid = self.current_uid
        if not uid or self.session is None:
            return False
        api = self.session.api
        self.store_mcts_setting("search_fit_settings", bool(search_fit_settings))

        def after(result: Any) -> None:
            result = result if isinstance(result, dict) else {}
            outcome = str(result.get("outcome", ""))
            if outcome == "selected":
                self.status = tr("Model search selected {structure} (reward {reward:.4g}).").format(
                    structure=result.get("structure", "?"), reward=float(result.get("reward", 0.0))
                )
            elif outcome == "request_information":
                self.status = tr(
                    "Model search needs {missing} to go further; the fit was not changed."
                ).format(missing=", ".join(result.get("missing") or []) or "?")
            else:
                self.status = tr("Model search cancelled; the fit was not changed.")

        return self._start(
            tr("Searching model space…"),
            lambda: api.model_search(fit_uid=uid, search_fit_settings=search_fit_settings),
            after,
        )

    def start_sampling(self, folder: str) -> bool:
        """Sample the current fit's posterior into *folder* (a server job, followed until it ends)."""
        uid = self.current_uid
        if not uid or self.session is None or not folder:
            return False
        from chisurf.core import settings

        api = self.session.api
        sampling = dict(
            (settings.cs_settings.get("optimization", {}) or {}).get("sampling", {}) or {}
        )
        n_steps = int(sampling.pop("steps", 1000))
        n_runs = int(sampling.pop("n_runs", 10))
        sampling.pop("samplers", None)

        def after(result: Any) -> None:
            job = str((result or {}).get("job_id") or "") if isinstance(result, dict) else ""
            if job:
                self.sampling_job = job
                self.status = tr("Sampling into {folder}…").format(folder=folder)

        return self._start(
            tr("Starting the sampling…"),
            lambda: api.start_sampling(
                folder, fit_uid=uid, n_steps=n_steps, n_runs=n_runs, **sampling
            ),
            after,
        )

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
        elif key == "prior":
            state = self._typed_prior(value, record)
            if state is False:
                return False
            change = lambda: api.edit_parameter(  # noqa: E731
                str(record.get("uid") or name), fit_uid=uid, parameter_name=name, prior=state
            )
        else:
            return False

        def call() -> Any:
            result = change()
            if isinstance(result, dict) and result.get("ok") is False:
                return result
            return api.fit_update(fit_uid=uid)

        return self._start(tr("Setting {name}…").format(name=name), call)

    def _then_update(self, label: str, change: Callable[[], Any]) -> bool:
        """Run *change* on the worker, then update the current fit (its curve and χ²)."""
        uid = self.current_uid
        if not uid or self.session is None:
            return False
        api = self.session.api

        def call() -> Any:
            result = change()
            if isinstance(result, dict) and result.get("ok") is False:
                return result
            return api.fit_update(fit_uid=uid)

        return self._start(label, call)

    def set_model_state(self, key: str, value: Any, label: str = "") -> bool:
        """A control of the model editor changed: ``model.state.set`` on the server."""
        uid, api = self.current_uid, self.session.api if self.session is not None else None
        if not key or api is None:
            return False
        return self._then_update(
            tr("Setting {name}…").format(name=tr(label) if label else key),
            lambda: api.model_state_set({key: value}, fit_uid=uid),
        )

    def _typed_prior(self, text: Any, record: dict) -> Any:
        """A typed *Prior* cell (``Gaussian(4, 0.4)``, ``Box``) as a prior state (``None``: Box).

        ``False`` when the text names no family; the status line then lists them.
        """
        ok, state = prior_families.parse(str(text or ""), _number(record.get("value")) or 1.0)
        if not ok:
            names = ", ".join(["Box"] + [label for label, _k, _p in prior_families.PRIOR_FAMILY_SPECS])
            self.status = tr("Unknown prior {text!r}; use one of: {names}").format(
                text=str(text), names=names
            )
            return False
        return state

    def edit_model_parameter(
        self, record: dict, key: str, value: Any, owner_uid: str | None = None
    ) -> bool:
        """A cell of a model-editor table changed: one ``parameter.*`` call by the parameter's uid."""
        uid, api = self.current_uid, self.session.api if self.session is not None else None
        if api is None:
            return False
        fields: dict[str, Any] = {}
        if key == "value":
            number = _number(value)
            if number is None:
                return False
            fields["value"] = number
        elif key == "fixed":
            fields["fixed"] = bool(value)
        elif key in ("lo", "hi"):
            lo = _number(value) if key == "lo" else _number(record.get("lo"))
            hi = _number(value) if key == "hi" else _number(record.get("hi"))
            if lo is None or hi is None:
                return False
            fields["bounds"] = (lo, hi)
        elif key == "bounds_on":
            fields["bounds_on"] = bool(value)
        elif key == "prior":
            state = self._typed_prior(value, record)
            if state is False:
                return False
            fields["prior"] = state
        else:
            return False
        name = str(record.get("name", ""))
        owner = str(owner_uid or record.get("fit_uid") or uid)
        return self._then_update(
            tr("Setting {name}…").format(name=name),
            lambda: api.edit_parameter(
                str(record["uid"]), fit_uid=owner, parameter_name=name, **fields
            ),
        )

    def model_action(self, action: str) -> bool:
        """A button of the model editor (``model.action``), e.g. the global fit's *Add*."""
        uid, api = self.current_uid, self.session.api if self.session is not None else None
        if not action or api is None:
            return False
        return self._then_update(
            tr("Running {action}…").format(action=action.replace("_", " ")),
            lambda: api.model_action(action, fit_uid=uid),
        )

    def change_components(self, target: str, add: bool, index: int = -1) -> bool:
        """*add* / *del* of a component group of the model editor."""
        uid, api = self.current_uid, self.session.api if self.session is not None else None
        if not target or api is None:
            return False
        if add:
            return self._then_update(
                tr("Adding a component…"), lambda: api.model_component_add(target, fit_uid=uid)
            )
        return self._then_update(
            tr("Removing a component…"),
            lambda: api.model_component_remove(target, int(index), fit_uid=uid),
        )

    # -- the model editor's curve pickers and custom sections ---------------------- #
    def section_call(
        self,
        section: str,
        op: str,
        args: dict,
        label: str,
        after: Callable[[Any], None] | None = None,
        update: bool = True,
        failed: Callable[[str], None] | None = None,
    ) -> bool:
        """``model.section.call`` of the current fit; then the fit is updated unless *update* is off."""
        uid, api = self.current_uid, self.session.api if self.session is not None else None
        if not uid or api is None:
            return False

        def call() -> Any:
            result = api.model_section_call(section, op, dict(args or {}), fit_uid=uid)
            if update and not (isinstance(result, dict) and result.get("ok") is False):
                api.fit_update(fit_uid=uid)
            return result

        return self._start(label, call, after=after, failed=failed)

    def pick_curve(self, curve: str, anchor: Any = None) -> None:
        """``…`` of a curve picker: the session's datasets as a popup; the pick goes to the model."""
        from chisurf.emtk.fit_controls import DatasetPicker

        rows = [r for r in self.datasets.datasets if r["experiment"] != "Global"]
        self.dataset_picker = DatasetPicker(
            rows,
            anchor,
            on_pick=lambda row: self.set_curve(curve, row),
            title=tr("Pick the curve"),
        )
        self.request_frame()

    def set_curve(self, curve: str, row: dict | None) -> bool:
        """Give the curve picker *curve* the dataset *row* (``model.curve.set``)."""
        self.dataset_picker = None
        uid, api = self.current_uid, self.session.api if self.session is not None else None
        if not row or not uid or api is None:
            return False
        dataset = str(row.get("uid", ""))
        return self._then_update(
            tr("Loading {name}…").format(name=row.get("name", "")),
            lambda: api.model_curve_set(curve, dataset, fit_uid=uid),
        )

    def unload_curve(self, curve: str, label: str = "") -> bool:
        """``✕`` of a curve picker (``model.curve.unload``)."""
        uid, api = self.current_uid, self.session.api if self.session is not None else None
        if not uid or api is None:
            return False
        return self._then_update(
            tr("Unloading {name}…").format(name=tr(label) if label else curve),
            lambda: api.model_curve_unload(curve, fit_uid=uid),
        )

    def link_model_parameter(self, record: dict, target_uid: str) -> bool:
        """Link the parameter of *record* to the parameter *target_uid* (any fit's)."""
        uid, api = self.current_uid, self.session.api if self.session is not None else None
        if api is None or not record.get("uid") or not target_uid:
            return False
        owner = str(record.get("fit_uid") or record.get("owner_uid") or uid)
        self._dirty |= {"fits"}
        return self._then_update(
            tr("Linking {name}…").format(name=record.get("name", "")),
            lambda: api.link_parameter(str(record["uid"]), target_uid, fit_uid=owner),
        )

    def unlink_model_parameter(self, record: dict) -> bool:
        """Drop the link of the parameter of *record*."""
        uid, api = self.current_uid, self.session.api if self.session is not None else None
        if api is None or not record.get("uid"):
            return False
        owner = str(record.get("fit_uid") or record.get("owner_uid") or uid)
        return self._then_update(
            tr("Unlinking {name}…").format(name=record.get("name", "")),
            lambda: api.unlink_parameter(str(record["uid"]), fit_uid=owner),
        )

    def read_fits_for_links(self, done: Callable[[list], None]) -> bool:
        """Read every fit with its parameters (``fit.get``), then call *done* with the list."""
        api = self.session.api if self.session is not None else None
        if api is None:
            return False
        uids = [row["uid"] for row in self.datasets.fits]

        def call() -> Any:
            found = []
            for fit_uid in uids:
                info = api.get_fit_info(fit_uid=fit_uid) or {}
                found.append(info.get("fit", info) if isinstance(info, dict) else {})
            return found

        return self._start(tr("Reading the fits…"), call, after=done)

    def reread_current(self) -> None:
        """Re-read the current fit and its editor (a list of candidates may have changed)."""
        self._dirty |= {"current", "fits"}
        self.request_frame()

    def poll_model_job(self, interval_ms: int = 500) -> None:
        """While a model's own job runs (a sampler), re-read the editor every *interval_ms*."""
        import time

        now = time.monotonic()
        if now - getattr(self, "_model_job_polled", 0.0) >= max(0.05, interval_ms / 1000.0):
            self._model_job_polled = now
            self._dirty |= {"current"}
            for window in self.windows.values():
                window.refresh()
        self.request_frame()

    def pick_database_paths(self, kinds: list, done: Callable[[list], None]) -> None:
        """MMFDB's datasets (of *kinds*) as a popup; the picked one's local path goes to *done*."""
        from chisurf.emtk.dataset_picker import DatasetPicker as DatabasePicker

        def picked(paths: Any) -> None:
            if paths:
                done([str(p) for p in paths])

        picker = DatabasePicker(kinds=list(kinds) if kinds else None, on_paths=picked)
        picker.open()
        self.model_dialog = picker
        self.request_frame()

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

    def remove_datasets(self, uids: list[str]) -> bool:
        """Remove the datasets (or groups) with these uids in one call."""
        uids = [u for u in uids if u]
        if not uids or self.session is None:
            return False
        api = self.session.api
        return self._start(
            tr("Removing the dataset…"), lambda: api.remove_datasets(dataset_uids=uids)
        )

    def group_datasets(self, indices: list[int]) -> bool:
        """Group the datasets at *indices* (``dataset.group``, as the Qt list's *Group*)."""
        if len(indices) < 2 or self.session is None:
            return False
        api = self.session.api
        return self._start(
            tr("Grouping the datasets…"), lambda: api.group_datasets(dataset_indices=indices)
        )

    def ungroup_datasets(self, indices: list[int]) -> bool:
        """Ungroup the groups at *indices* (``dataset.ungroup``, as the Qt list's *Ungroup*)."""
        if not indices or self.session is None:
            return False
        api = self.session.api
        return self._start(
            tr("Ungrouping the datasets…"), lambda: api.ungroup_datasets(dataset_indices=indices)
        )

    def refresh(self) -> None:
        """Read the dataset and fit lists again."""
        self._dirty |= {"datasets", "fits"}
        self.request_frame()

    def _live_dataset(self, uid: str) -> Any:
        state = getattr(getattr(self.session, "server", None), "state", None)
        for dataset in list(getattr(state, "datasets", None) or ()):
            if str(getattr(dataset, "unique_identifier", "")) == uid:
                return dataset
        return None

    def save_dataset(self, uid: str, name: str = "") -> None:
        """Ask for a file, then pickle the dataset *uid* into it (the Qt list's *Save*)."""
        if not uid or self.session is None:
            return
        stem = Path(name or "dataset").stem or "dataset"

        def chosen(path: str) -> None:
            target = path if Path(path).suffix else path + ".pkl"
            dataset = self._live_dataset(uid)
            if dataset is None:
                self.status = tr("The dataset is no longer in the session.")
                return

            def write() -> Any:
                from chisurf.core.data_io.dataset_pickle import save_dataset

                save_dataset(dataset, target)
                return {"ok": True}

            self._start(tr("Saving {name}…").format(name=Path(target).name), write)

        self.open_file_dialog(
            tr("Save the dataset"), mode="save", done=chosen, filename=stem + ".pkl"
        )

    def load_dataset_file(self) -> None:
        """Ask for a pickle file, then add the dataset in it to the session (the Qt list's *Load*)."""
        if self.session is None:
            return
        api = self.session.api

        def chosen(path: str) -> None:
            def read() -> Any:
                from chisurf.core.data_io.dataset_pickle import load_dataset

                return api.load_dataset(dataset=load_dataset(path))

            self._start(tr("Loading {name}…").format(name=Path(path).name), read)

        self.open_file_dialog(tr("Load a dataset"), mode="open", done=chosen)

    def drop(self, paths: list[str]) -> bool:
        """Files dropped onto the shell: read the first with the selected file type."""
        if not paths or self.session is None:
            return False
        self.read.path = str(paths[0])
        self.shell.docks.focus(READ_KEY)
        return self.load(self.read.reader(), self.read.path)

    # -- fit windows --------------------------------------------------------------- #
    def _retitle(self, uid: str, title: str) -> None:
        """Give fit *uid*'s window *title* (a second fit of the same name was added or removed)."""
        window = self.windows.get(uid)
        dock = self.shell.docks.window(window.key) if window is not None else None
        if dock is not None and dock.title != title:
            dock.title = dock.tooltip = window.title = title

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
            core=True,
            # A fit window is a document of the workspace: it lives there and nowhere else.
            workspace=True,
        )
        self.shell.docks.focus(window.key)
        return window

    def show_fit(self, uid: str) -> None:
        """Make *uid* the current fit and bring its window forward (reopening a closed one)."""
        self.current_uid = uid
        self._dirty.add("current")
        row = next((r for r in self.datasets.fits if r["uid"] == uid), None)
        window = self.open_window(uid, row["label"] if row else uid)
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
        """The fit window the user last worked in becomes the current fit.

        That is the window pressed in (any tile, floating or tabbed) or named by ``focus``, and the
        tab on top of the centre when it changes; each is acted on once, when it changes, so the
        Datasets panel's own choice of a fit is not undone by the window that was focused before.
        """
        docks = self.shell.docks
        seen = (docks.focused, docks.active_tab("center"))
        before = self._seen_focus
        self._seen_focus = seen
        for index, key in enumerate(seen):
            if key is None or key == before[index]:
                continue
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
            from chisurf.emtk.reader_settings import reader_settings_app

            api = self.session.api if self.session is not None else None
            app = reader_settings_app(reader, context=api)
        except Exception as exc:  # noqa: BLE001 - shown as a note, the reader's defaults are used
            self._reader_errors[key] = str(exc)
            return None
        app.set_frame_request_callback(self.request_frame)
        # A form with its own file list (the PDA reader's) reads it through the dock, as + Data does.
        app.load_files = lambda filename, r=reader: self.load(r, filename)
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
    def open_file_dialog(
        self,
        title: str = "",
        mode: str = "open",
        directory: str | None = None,
        done: Callable[[str], None] | None = None,
        filename: str = "",
    ) -> None:
        """Open a file dialog over the shell; *done* gets the chosen path (default: the file to read)."""
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        title = title or tr("Read data")
        if directory is None and self.read.path:
            directory = str(Path(self.read.path).expanduser().parent)
        self.file_dialog = FileDialog(title, mode=mode, directory=directory, filename=filename)
        self._file_window = DialogWindow(title, size=(760, 540))
        self._file_done = done
        self.request_frame()

    def ask_sampling_folder(self) -> None:
        """*Sample*: ask for the folder the chains, diagnostics and project go to, then start."""
        if not self.current_uid:
            return
        self.open_file_dialog(
            tr("Select the folder for the sampling results"),
            mode="folder",
            done=self.start_sampling,
        )

    def open_settings(self) -> None:
        """⚙: the sampling and fitting settings, written to the user settings on OK."""
        from chisurf.emtk.fit_controls import SettingsDialog

        self.settings_dialog = SettingsDialog(on_close=self._settings_closed)
        self.request_frame()

    def _settings_closed(self, written: bool | None) -> None:
        self.settings_dialog = None
        if written is True:
            self.status = tr("Sampling and fitting settings saved.")
        elif written is False:
            self.status = tr(
                "The settings apply to this session but could not be written to your settings file."
            )

    def open_dataset_picker(self) -> None:
        """``…``: pick another dataset for the current fit."""
        from chisurf.emtk.fit_controls import DatasetPicker

        rows = [r for r in self.datasets.datasets if r["experiment"] != "Global"]
        anchor = self.shell.item_rects.get("analysis.select_dataset")
        self.dataset_picker = DatasetPicker(rows, anchor, on_pick=self.attach_dataset)
        self.request_frame()

    def attach_dataset(self, row: dict | None) -> bool:
        """Attach the dataset *row* to the current fit (``fit.set_dataset``)."""
        self.dataset_picker = None
        uid, api = self.current_uid, self.session.api if self.session is not None else None
        if not row or not uid or api is None:
            return False
        dataset = str(row.get("uid", ""))

        def change() -> Any:
            return api.set_fit_dataset(dataset, fit_uid=uid)

        self._dirty |= {"windows"}
        return self._then_update(tr("Attaching {name}…").format(name=row.get("name", "")), change)

    def window_at(self, x: float, y: float) -> str:
        """The uid of the fit window drawn under (x, y), ``""`` if none."""
        for uid, window in self.windows.items():
            box = window.box
            dock = self.shell.docks.window(window.key)
            if box is None or dock is None or not self.shell.docks.is_shown(window.key):
                continue
            bx, by, bw, bh = box
            if bx <= x <= bx + bw and by - 30.0 <= y <= by + bh:
                return uid
        return ""

    def dataset_dragged(self, row: dict | None, x: float, y: float, dropped: bool) -> None:
        """Follow a dataset dragged out of the Datasets table; on a fit window's drop, attach it."""
        if not dropped:
            self.dragged = (row, x, y) if row else None
            self.request_frame()
            return
        self.dragged = None
        uid = self.window_at(x, y)
        if not row or not uid or row.get("experiment") == "Global":
            return
        self.show_fit(uid)
        self.current_uid = uid
        self.attach_dataset(row)

    def _draw_drag(self) -> None:
        """The dragged dataset's name under the pointer, and the fit it would go to."""
        if self.dragged is None:
            return
        row, x, y = self.dragged
        target = self.window_at(x, y)
        name = str(row.get("name", ""))
        text = (
            tr("{name} → {fit}").format(name=name, fit=self.windows[target].title)
            if target
            else name
        )
        draw = im.get_foreground_draw_list()
        w, h = im.calc_text_size(text)[:2]
        style = im.get_style()
        # Beside the pointer, kept inside the window.
        right = float(im.get_main_viewport().size[0])
        x = max(0.0, min(x + 12.0, right - w - 12.0)) - 12.0
        draw.add_rect_filled(
            (x + 12, y + 8), (x + 20 + w, y + 12 + h), style.color(im.Col.POPUP_BG)
        )
        draw.add_rect((x + 12, y + 8), (x + 20 + w, y + 12 + h), style.color(im.Col.BORDER))
        draw.add_text((x + 16, y + 10), style.color(im.Col.TEXT), text)

    @property
    def modal_open(self) -> bool:
        """Whether a dialog over the shell takes the input (file dialog, settings)."""
        return (
            self.file_dialog is not None
            or self.settings_dialog is not None
            or self.sample_dialog is not None
            or self.model_dialog is not None
            or self.editor.modal_open()
        )

    def draw_file_dialog(self, box) -> None:
        """The open dialogs over the whole shell (drawn last, on top)."""
        self._draw_drag()
        if self.dataset_picker is not None:
            self.dataset_picker.draw()
        if self.settings_dialog is not None:
            self.settings_dialog.draw(box)
        if self.sample_dialog is not None:
            self.sample_dialog.draw(box)
        self.editor.draw_dialogs(box)
        if self.model_dialog is not None:
            self.model_dialog.render(box)
            if not self.model_dialog.is_open:
                self.model_dialog = None
        if self.file_dialog is None:
            return
        window = self._file_window
        closed = window.begin(box)
        paths = self.file_dialog.draw()
        window.end()
        if closed or paths is False:
            self.file_dialog = None
            self._file_done = None
        elif paths:
            self.file_dialog = None
            done, self._file_done = self._file_done, None
            if done is not None:
                done(str(paths[0]))
            else:
                self.read.path = str(paths[0])
                self.ask_sample(self.read.reader())

    def ask_sample(self, reader: Any) -> bool:
        """After a file is chosen: which MMFDB sample it is of, for a reader that records one."""
        if reader is None or not getattr(reader, "asks_sample", False):
            return False
        from chisurf.emtk.sample_picker import SamplePickerDialog

        def closed(_sample_id: str | None) -> None:
            self.sample_dialog = None
            self.request_frame()

        self.sample_dialog = SamplePickerDialog(
            reader, client=self.sample_client, on_close=closed, wake=self.request_frame
        )
        self.request_frame()
        return True

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
            w, _ = im.get_content_region_avail()
            # What the dock has left after the status line under it (measured, not a guessed number of
            # pixels), but never less than a form can be used in: a small window used to leave the reader
            # form one pixel, and its controls were unreachable. The dock scrolls instead -- but the floor
            # is never taller than the dock's own view: a form that overhangs the dock (a short window,
            # 800 x 600) can never be seen whole, its lower half lies under the next dock, and its last
            # control is reached only by trading the dock's scroll against the form's.
            floor = min(MIN_READER_FORM_H, float(box[3]))
            room = im.stretch_height(f"reader.{id(app)}", minimum=floor)
            self.shell.host_child(READ_KEY, f"reader.{id(app)}", app, (x, y, float(w), room))
            im.dummy((float(w), room))
        self._status_line()

    def _draw_datasets(self, box) -> None:
        self._form("datasets", self.datasets, "datasets")
        self._status_line()

    def _draw_analysis(self, box) -> None:
        self._form("analysis", self.analysis, "analysis")
        self.editor.draw(self.shell.item_rects)
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
        # A strip over the surface for the window's own actions: *Code* turns it over.
        label = tr("Plots") if window.code_shown() else tr("Code")
        strip = im.get_frame_height() + 4.0
        bw = im.calc_text_size(label)[0] + 2.0 * im.get_style().frame_padding[0]
        im.set_cursor_screen_pos((x + w - bw - 4.0, y + 2.0))
        if im.button(f"{label}##code-{uid}"):
            self.toggle_code(uid)
        self.shell.item_rects[f"{window.key}.code"] = im.get_item_rect()
        im.set_item_tooltip(
            tr("Show the model's source and view.json, editable; or the plots again.")
        )
        window.box = (x, y + strip, max(1.0, w), max(1.0, h - strip))
        self.shell.host_child(window.key, window.key, window.app, window.box)

    def toggle_code(self, uid: str) -> bool:
        """*Code* / *Plots* of a fit window: the model's files are asked of the server first."""
        window = self.windows.get(uid)
        if window is None or self.session is None:
            return False
        if window.code_shown():
            window.show_code(False)
            return True
        api = self.session.api

        def after(files: Any) -> None:
            if isinstance(files, dict) and files.get("files"):
                window.show_code(
                    True, files, on_apply=lambda path, text: self.apply_code(uid, path, text)
                )
            else:
                self.status = tr("The model's source could not be found.")

        return self._start(
            tr("Opening the model's code…"), lambda: api.model_code_files(fit_uid=uid), after
        )

    def apply_code(self, uid: str, path: str, text: str) -> str:
        """Save and apply an edit made on a window's Code face (``model.code.apply``)."""
        window = self.windows.get(uid)
        api = self.session.api if self.session is not None else None
        if window is None or api is None:
            return tr("No session.")

        def after(result: Any) -> None:
            if window.code_face is not None and isinstance(result, dict):
                window.code_face.status = str(result.get("message", ""))

        def call() -> Any:
            result = api.model_code_apply(path, text, fit_uid=uid)
            api.fit_update(fit_uid=uid)
            return result

        if not self._start(tr("Applying the model's code…"), call, after):
            return tr("Busy: {label}").format(label=self.job.label if self.job else "")
        return tr("Applying…")

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
