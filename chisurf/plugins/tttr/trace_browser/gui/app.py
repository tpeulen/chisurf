"""Native emtk Trace Browser, in stages: the **Setup** page (card T1), the **Browser** page (T2)
and its trace area (T3b).

The Qt tool opens on a two-page workspace: page 0 is the detector setup (the
``DetectorWizardPage`` plus a *Continue* button), page 1 the trace browser.  This
module draws page 0 with the shared emtk setup editor
(:class:`chisurf.emtk.channel_definition.ChannelDefinitionWidget`); *Continue* hands
the editor's result to :meth:`.model.TraceBrowserModel.accept_setup` (which derives
the selected channels exactly as the Qt tool does) and switches the page.

Page 1 is the form of ``trace_browser_emtk.view.json`` drawn by
:func:`emtk.view_form.draw_form` (back button, folder, Open, include-subfolders,
rating filter, bin window, y range, Clear, Clear caches and the file table, a
``data_table`` section whose rating and notes columns are editable), next to the "Trace
plot" window: the binned trace of the selected file against time with one coloured line per
series (and their sum), a log-scaled counts histogram beside it (both ``emtk.implot``), and
the annotation box under it (the same field as the Notes column).  A trace is loaded on a
:class:`~chisurf.emtk.jobs.SnapshotJob`; the traces of all listed files are precomputed on
another one after a scan.  Scanning a
folder runs on a :class:`chisurf.emtk.jobs.SnapshotJob`; the folder is chosen with
an :class:`emtk.file_dialog.FileDialog` in folder mode or dropped on the window.  Like
the Qt constructor (which calls ``_on_continue()`` itself) the app opens on the Browser
page whenever a setup is available (the last used saved one, or a remembered one).

The buttons under the folder row act on the table's selection (one row, or every row after
*Select all*): *Export* copies the files, *CSV* writes their traces, *DOCX* writes a report,
*Delete* moves them to ``.trash`` after a confirmation drawn here.  *HMM*, *TW* and *NDX* open
the selected trace in another ChiSurf tool: that needs the main window, so the model records a
request (:attr:`~.model.TraceBrowserModel.requests`) and the app hands it to the ``on_request(name,
payload)`` callback of its host; without a host the three buttons are greyed.  Help and Guide
(:class:`~chisurf.emtk.help_guide.EmTkHelpWindow`, :class:`~chisurf.emtk.help_guide.EmTkGuidedTour`)
sit above the form on both pages.

All state is in :class:`~.model.TraceBrowserModel`; this module imports no Qt.
"""

from __future__ import annotations

import json
import re
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from chisurf.core import setup_channel_definition as definition
from chisurf.core.fio import setup_store as store
from chisurf.core.setup_channel_definition import ChannelDefinition
from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.jobs import SnapshotJob

from .model import TraceBrowserModel

HERE = Path(__file__).parent

#: Line colours of the detectors the setups name (the Qt tool's traces are blue; here a
#: detector keeps its own colour), RGBA in 0..1 as ``emtk.implot`` reads them.
DETECTOR_COLOURS = {
    "green": (0.15, 0.78, 0.25, 1.0),
    "red": (0.92, 0.25, 0.22, 1.0),
    "yellow": (0.95, 0.80, 0.10, 1.0),
}
#: Colours of every other label, in order of appearance.
PALETTE = (
    (0.30, 0.55, 0.95, 1.0),
    (0.92, 0.55, 0.15, 1.0),
    (0.70, 0.45, 0.85, 1.0),
    (0.15, 0.75, 0.80, 1.0),
    (0.85, 0.40, 0.60, 1.0),
    (0.65, 0.75, 0.20, 1.0),
)
#: The colour of the ``Sum`` series (the Qt tool draws it as the last row of its plot).
SUM_COLOUR = (0.70, 0.70, 0.70, 1.0)
#: A displayed trace has at most about this many points (min and max of each pixel column).
MAX_POINTS = 4000
#: Bins of the counts histograms (the Qt plot's ``bin_count``).
HIST_BINS = 100
#: Seconds the annotation must rest before it is written to the metadata file (Qt: 300 ms).
NOTES_FLUSH_S = 0.3
#: Height of the annotation box in pixels.
NOTES_HEIGHT = 90.0


def series_colour(label: str, index: int) -> tuple:
    """Return the line colour of series *label*: a detector's own colour, else the palette.

    Parameters
    ----------
    label : str
        The series label (a detector name such as ``green``, or any other text).
    index : int
        Position of the series, picking from :data:`PALETTE` for a label without own colour.
    """
    name = re.split(r"[\s,+]", str(label).strip().lower(), maxsplit=1)[0]
    return DETECTOR_COLOURS.get(name, PALETTE[index % len(PALETTE)])


def decimate_minmax(x: Any, y: Any, max_points: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Reduce a trace for display: keep the minimum and the maximum of every pixel column.

    A trace of up to *max_points* points is returned unchanged. A longer one is cut into
    ``max_points // 2`` equal runs of bins and each run keeps its lowest and its highest bin (in
    time order), so a burst or a dip never disappears. Display only: the model keeps all bins.

    Parameters
    ----------
    x, y : array_like
        Time axis and counts of one series.
    max_points : int, optional
        Upper limit of the returned length (default :data:`MAX_POINTS`).

    Returns
    -------
    tuple of numpy.ndarray
        The reduced ``(x, y)``.
    """
    max_points = MAX_POINTS if max_points is None else int(max_points)
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n <= max_points:
        return x, y
    columns = max(1, max_points // 2)
    edges = np.linspace(0, n, columns + 1).astype(np.int64)
    keep: list[int] = []
    for start, stop in zip(edges[:-1], edges[1:]):
        if stop <= start:
            continue
        run = y[start:stop]
        keep.extend(sorted({int(start + np.argmin(run)), int(start + np.argmax(run))}))
    index = np.asarray(keep, dtype=np.int64)
    return x[index], y[index]


def counts_histogram(counts: Any, bins: int = HIST_BINS) -> tuple[np.ndarray, np.ndarray]:
    """Histogram of the positive bin counts of one series, as the Qt plot draws it.

    Parameters
    ----------
    counts : array_like
        Counts per time bin of one series.
    bins : int
        Number of histogram bins.

    Returns
    -------
    tuple of numpy.ndarray
        ``(frequency, centres)``: how many time bins hold a count in each histogram bin, and the
        count at the centre of that bin (the histogram is drawn with the counts on the y axis).
        Both are empty when the series has no positive bin.
    """
    data = np.asarray(counts, dtype=float)
    data = data[data > 0]
    if data.size == 0:
        return np.zeros(0), np.zeros(0)
    freq, edges = np.histogram(data, bins=bins)
    centres = 0.5 * (edges[:-1] + edges[1:])
    keep = freq > 0                                      # a log axis cannot show an empty bin
    return freq[keep].astype(float), centres[keep]


class TraceView:
    """What is drawn for one loaded trace: one entry per series, plus their sum.

    Built once per loaded trace (not per frame): the decimated lines and the histograms.

    Parameters
    ----------
    trace : dict
        The model's :attr:`~.model.TraceBrowserModel.trace`.
    """

    def __init__(self, trace: dict) -> None:
        self.path = str(trace.get("path", ""))
        self.window_ms = float(trace.get("time_window_ms", 0.0))
        time_axis = np.asarray(trace["time_axis"], dtype=float)
        counts = np.asarray(trace["counts"], dtype=float)
        if counts.ndim == 1:
            counts = counts[:, None]
        labels = [str(label) for label in trace["labels"]]
        self.t_end = float(time_axis[-1]) if len(time_axis) else 0.0
        self.n_bins = len(time_axis)
        self.series: list[dict[str, Any]] = []
        columns = [(label, counts[:, i]) for i, label in enumerate(labels[: counts.shape[1]])]
        for i, (label, column) in enumerate(columns):
            self.series.append(self._entry(label, series_colour(label, i), time_axis, column))
        if columns:      # the sum is drawn first, behind the detectors (the Qt plot ends with it)
            total = counts[:, : len(columns)].sum(axis=1)
            self.series.insert(0, self._entry("Sum", SUM_COLOUR, time_axis, total))

    @staticmethod
    def _entry(label: str, colour: tuple, time_axis: np.ndarray, column: np.ndarray) -> dict:
        """One series: label, colour, the decimated line, its histogram and the full-data sum."""
        x, y = decimate_minmax(time_axis, column)
        freq, centres = counts_histogram(column)
        return {
            "label": label,
            "colour": colour,
            "x": x,
            "y": y,
            "freq": freq,
            "centres": centres,
            "total": float(np.sum(column)),
        }


def _plain(value: Any) -> Any:
    """Convert numpy scalars/arrays to JSON types (``json.dumps`` ``default=``)."""
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"{type(value).__name__} is not JSON serialisable")


class _TraceTask:
    """What a trace worker runs: it holds the *real* model and is the only thing a job copies.

    :class:`~chisurf.emtk.jobs.SnapshotJob` copies its target and writes every attribute of the
    copy back when the work ends.  A trace load or a precompute may run for a long time, so its
    target is this small object: the user can select rows and edit notes meanwhile and nothing
    is overwritten.  The result is read from :attr:`result` by the draw loop.
    """

    def __init__(self, model: TraceBrowserModel) -> None:
        self.model = model
        self._observers: list = []
        self.result: tuple | None = None
        self.status_text = ""

    def notify(self, event: Any = "updated") -> None:
        """Tell every observer that *event* happened (the job's progress hook)."""
        for callback in list(self._observers):
            callback(event)

    def load(self, path: Path, window_ms: float) -> None:
        """Load the binned trace of *path* (cache, then compute) into :attr:`result`."""
        self.result = None
        time_axis, counts, labels = self.model.load_trace(path, window_ms)
        self.result = (path, window_ms, time_axis, counts, labels)

    def precompute(self) -> None:
        """Run the model's precompute (progress and cancel live in ``model.precompute``)."""
        self.model.run_precompute()


class TraceBrowserApp(ImApp):
    """Trace Browser: setup page (T1), browser page (T2), trace plot and annotation (T3b).

    Parameters
    ----------
    model : TraceBrowserModel, optional
        The state; a fresh one by default.
    setups_file : str or Path, optional
        Detector-setups JSON file offered on the setup page; ``None`` is the user's
        canonical file, which is what the Qt setup page reads.
    on_request : callable, optional
        ``on_request(name, payload)`` of the host (the ChiSurf main window) that opens the other
        tool of a hand-off (``open_intensity_trace``, ``open_time_window``, ``open_ndxplorer``).
        Called from the draw thread. Without it the HMM, TW and NDX buttons are greyed.
    """

    def __init__(
        self,
        model: TraceBrowserModel | None = None,
        setups_file: Any = None,
        on_request: Callable[[str, dict], Any] | None = None,
    ) -> None:
        self.model = model or TraceBrowserModel()
        self.on_request = on_request
        self.model.host_connected = on_request is not None
        self._delivered = 0
        self.setups_file = str(setups_file) if setups_file else None
        self.editor: ChannelDefinitionWidget | None = None
        self.item_rects: dict[str, tuple] = {}
        self.job = SnapshotJob(self.model)
        self.model.runner = self.queue_job
        # Trace loads and the precompute run on jobs of their own, on a helper that holds the model
        # (see _TraceTask): they never copy the model back over what the user changed meanwhile.
        self.load_task = _TraceTask(self.model)
        self.load_job = SnapshotJob(self.load_task)
        self.pre_task = _TraceTask(self.model)
        self.pre_job = SnapshotJob(self.pre_task)
        self._loading: tuple[Path, float] | None = None
        self._failed: tuple[Path, float] | None = None
        self._view: TraceView | None = None
        self._view_for: int = 0
        self._limits_key: tuple | None = None
        self._notes_dirty_at: float | None = None
        self._notes_dirty_for: Path | None = None
        self._queue: deque[tuple[str, tuple]] = deque()
        self._reported_error = ""
        self.spec = json.loads(
            (HERE / "trace_browser_emtk.view.json").read_text(encoding="utf-8")
        )
        self.form = FormState()
        self.dialog: FileDialog | None = None
        self.dialog_kind = ""
        self._dialog_paths: list[str] = []
        self._outcome: tuple = ()
        self.help_window = EmTkHelpWindow(
            title="Trace Browser — Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        self._new_editor(None)
        self.setup_docks = DockManager(Region("setup"), name="trace_browser_setup")
        self.setup_docks.add_window(
            "setup", "Setup definition", self.draw_setup, dock="setup", closable=False
        )
        # The Qt browser has the file table on the left and the plot on the right.
        self.browser_docks = DockManager(
            Split("h", 0.5, Region("files"), Region("plot")), name="trace_browser_browser"
        )
        self.browser_docks.add_window(
            "files", "Trace browser", self.draw_browser, dock="files", closable=False
        )
        self.browser_docks.add_window(
            "plot", "Trace plot", self.draw_plot, dock="plot", closable=False
        )
        super().__init__(self.render, continuous=True)
        # The Qt constructor calls ``_on_continue()`` itself: with a setup at hand the
        # app opens on the Browser page too (the last used saved setup is selected).
        if self._load_saved_setups(select_last=True):
            self.continue_to_browser()

    # -- jobs ---------------------------------------------------------------------
    def queue_job(self, method: str, *args: Any) -> bool:
        """Run the model method *method* on a snapshot worker, after any job still running.

        The model's ``runner``: the draw loop stays responsive while a folder is scanned.
        A second request for the same method and arguments while one is waiting is dropped.
        """
        item = (method, args)
        if item not in self._queue:
            self._queue.append(item)
        return True

    def _pump_jobs(self) -> None:
        """Collect a finished job and start the next queued one (once per frame)."""
        self.job.poll()
        self.model.busy = self.job.busy
        if self.job.error and self.job.error != self._reported_error:
            self._reported_error = self.job.error
            self.model.error_text = self.job.error
        if self._queue and not self.job.busy:
            method, args = self._queue.popleft()
            self._reported_error = ""
            self.model.error_text = ""
            self._failed = None                       # a new scan: the files may load now
            self.model.precompute["cancel"] = True    # a new scan ends a running precompute
            if self.job.start(method, *args):
                self.model.busy = True

    def _pump_trace(self) -> None:
        """Collect a finished trace load; start the load the selection and bin window ask for.

        The trace area is *declarative*: whatever file is current and whatever bin window is set,
        this loop makes the shown trace match, one load at a time, so a click on another row, a
        changed bin window, a rescan that selects the first row and a finished older load all end
        in the right trace without any of them knowing about the others.
        """
        model = self.model
        was_busy = self.load_job.busy
        self.load_job.poll()
        if was_busy and not self.load_job.busy and self._loading is not None:
            path, window = self._loading
            self._loading = None
            if self.load_job.error:
                self._failed = (path, window)
                if model.current_file == path:
                    model.fail_trace(path, self.load_job.error)
            elif self.load_task.result is not None and model.current_file == path:
                _, _, time_axis, counts, labels = self.load_task.result
                model.set_trace(path, time_axis, counts, labels, window)
        want = self.wanted_trace()
        if want is None or self.load_job.busy or want == self._failed or want == self.shown_trace():
            return
        self._loading = want
        self.load_job.start("load", *want)

    def wanted_trace(self) -> tuple[Path, float] | None:
        """The ``(file, bin window)`` the trace area should show, or ``None`` without a file."""
        current = self.model.current_file
        return None if current is None else (Path(current), float(self.model.window_ms))

    def shown_trace(self) -> tuple[Path, float] | None:
        """The ``(file, bin window)`` of the trace the model holds now, or ``None``."""
        trace = self.model.trace
        if not trace or not trace.get("path"):
            return None
        return Path(trace["path"]), float(trace["time_window_ms"])

    def _pump_precompute(self) -> None:
        """Start the precompute the model asked for, once no scan and no precompute runs."""
        model = self.model
        self.pre_job.poll()
        if (
            model.precompute_pending
            and not self.pre_job.busy
            and not self.job.busy
            and not self._queue
        ):
            model.precompute_pending = False
            if model.rows:
                model.prepare_precompute()
                if not self.pre_job.start("precompute"):
                    model.precompute["running"] = False
        if self.pre_job.error and model.precompute["running"]:
            model.precompute.update(running=False, message=f"Precompute failed: {self.pre_job.error}")

    def animating(self) -> bool:
        """Keep drawing while a worker runs or a request waits, so the result appears."""
        return (
            self.job.busy
            or bool(self._queue)
            or self.load_job.busy
            or self.pre_job.busy
            or self.model.precompute_pending
            or self._notes_dirty_at is not None
            or self.wanted_trace() not in (None, self._failed, self.shown_trace())
            or super().animating()
        )

    # -- the shared setup editor ------------------------------------------------
    def _new_editor(self, settings: dict | None) -> None:
        """Replace the setup editor by a fresh one holding *settings*."""
        if self.editor is not None:
            self.editor.close()
        model = ChannelDefinition(settings, file_path=self.setups_file)
        self.editor = ChannelDefinitionWidget(model=model)

    def _load_saved_setups(self, select_last: bool) -> bool:
        """Offer the saved setups and, if asked, select the last used one.

        Reads the store the Qt setup page reads (the MMFDB, falling back to the
        setups JSON file, with the same one-time import of an old JSON file), so the
        drop-down lists the saved setups and the page starts on the last used one.
        With no saved setup the page starts empty.

        Returns
        -------
        bool
            ``True`` when the last used saved setup was selected.
        """
        assert self.editor is not None
        self.editor.model.refresh_setups()
        name = store.load_setups(self.setups_file, definition.CONFIG).get("last_used")
        if select_last and name in self.editor.model.setups:
            self.editor.select_setup(name)
            return True
        return False

    # -- actions ---------------------------------------------------------------
    def continue_to_browser(self) -> None:
        """Accept the editor's setup and show the browser page (the Qt *Continue*).

        When a folder is open and the setup changed the file types or channels, the folder
        is scanned again (the Qt tool keeps the old list until the next scan).
        """
        assert self.editor is not None
        model = self.model
        before = (model.setup_filetype, model.selected_channels)
        model.accept_setup(self.editor.model.get_settings())
        if model.current_folder is not None and before != (
            model.setup_filetype,
            model.selected_channels,
        ):
            model.request("scan")

    def back_to_setup(self) -> None:
        """Return to the setup page (the Qt *Select setup* button)."""
        self.model.back_to_setup()

    # -- one frame -------------------------------------------------------------
    def render(self) -> None:
        self._pump_jobs()
        self._pump_trace()
        self._pump_precompute()
        self._flush_notes()
        self._deliver_requests()
        width, height = im.get_main_viewport().size
        box = (0.0, 0.0, float(width), float(height))
        self.form.rects.clear()
        browser = self.model.page != "setup"
        (self.browser_docks if browser else self.setup_docks).draw(box)
        assert self.editor is not None
        self.editor.draw_dialogs(box)
        self._open_requested_dialog()
        self._draw_dialog(box)
        self._draw_confirm(box)
        self._tour_outcomes()
        self.help_window.draw(box)
        self.tour.draw(float(width), float(height))

    def _draw_help_buttons(self) -> None:
        """Help and Guide, at the top of both pages."""
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip(
            "Explain the Trace Browser: the setup page, the file table, the trace plot, "
            "exporting, deleting and the hand-offs to other tools."
        )
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip(
            "Walk through accepting a setup, opening a folder, selecting files and exporting them."
        )
        self.item_rects["guide"] = im.get_item_rect()

    def _tour_outcomes(self) -> None:
        """Tell the tour what happened: the browser page is shown, files are listed, several are
        selected, something was exported.

        A step that waits is released by its *outcome*, not by the button press (Open only opens
        a dialog), and by a state that already holds (a folder that is open already).
        """
        model = self.model
        if "choose_folder" in self.form.rects:
            self.item_rects["folder_opened"] = self.form.rects["choose_folder"]
        if "select_all_files" in self.form.rects:
            self.item_rects["several_selected"] = self.form.rects["select_all_files"]
        if "export_selected" in self.form.rects:
            self.item_rects["exported"] = self.form.rects["export_selected"]
        if model.page != "setup":
            self.tour.notify_used("setup_accepted")
        if model.rows:
            self.tour.notify_used("folder_opened")
        if len(model.selection_paths()) > 1:
            self.tour.notify_used("several_selected")
        if self._outcome and model.actions_done > self._outcome[0]:
            self.tour.notify_used("exported")
        self._outcome = (model.actions_done,)

    def _deliver_requests(self) -> None:
        """Pass the hand-off requests the model recorded to the host, once each, on this thread."""
        requests = self.model.requests
        if self._delivered > len(requests):
            self._delivered = 0
        while self._delivered < len(requests):
            request = requests[self._delivered]
            self._delivered += 1
            if self.on_request is None:
                continue
            try:
                self.on_request(str(request["name"]), dict(request.get("payload") or {}))
            except Exception as exc:
                self.model.error_text = f"The host could not open {request['name']}: {exc}"

    def draw_setup(self, box: Any) -> None:
        """Page 0: *Continue*, then the shared setup editor."""
        if im.button("Continue"):
            self.continue_to_browser()
        im.set_item_tooltip("Accept detector setup and open trace browser")
        self.item_rects["continue"] = im.get_item_rect()
        im.same_line()
        self._draw_help_buttons()
        im.separator()
        assert self.editor is not None
        self.editor.draw()

    def draw_browser(self, box: Any) -> None:
        """Page 1: Help and Guide, then the form of the spec (controls and the file table)."""
        self._draw_help_buttons()
        draw_form(self.spec, self.model, self.form)
        self._sync_table_selection()

    def _sync_table_selection(self) -> None:
        """Show the model's selected file in the table (a scan selects the first row itself)."""
        binding = self.form.tables.get("rows")
        if binding is None:
            return
        control = binding.control
        if self.model.select_all_requested:
            self.model.select_all_requested = False
            control.select_all()
        selected = self.model.selected_files
        key = selected[0] if selected else None
        if key != control.selected_key and key not in control.also_selected:
            if key is None:
                control.selected_key = None
                control.also_selected = set()
            else:
                control.select_key(key)
        # The table's selection (one row, or every row after Select all) is what Export, CSV,
        # DOCX, Delete and the hand-offs act on.
        rows = self.model.rows
        self.model.multi_selection = [
            rows[i]["path"] for i in control.selected_indices() if 0 <= i < len(rows)
        ]

    # -- the trace area ------------------------------------------------------------
    def draw_plot(self, box: Any) -> None:
        """The "Trace plot" window: a status line, the trace and its histogram, the annotation."""
        model = self.model
        current = model.current_file
        self._plot_header(current)
        avail_h = float(im.get_content_region_avail()[1])
        plot_h = max(120.0, avail_h - NOTES_HEIGHT - 34.0)
        view = self._current_view()
        if view is not None and view.series:
            self._draw_trace(view, plot_h)
        else:
            self._empty_state(current, plot_h)
        self._draw_notes(current)

    def _plot_header(self, current: Any) -> None:
        """One line above the plot: the file, the bin window, and Loading / the error."""
        model = self.model
        if current is None:
            return
        want = self.wanted_trace()
        if model.trace_error:
            im.text_wrapped(model.trace_error)
        elif want is not None and want != self.shown_trace():
            im.text(f"Loading {Path(current).name}…")
        else:
            trace = model.trace or {}
            n_bins = len(trace.get("time_axis", ()))
            im.text(f"{Path(current).name}  |  {model.window_ms:g} ms bins  |  {n_bins} bins")

    def _empty_state(self, current: Any, height: float) -> None:
        """What the plot area says when there is nothing to draw (never an invented curve)."""
        if current is None:
            if self.model.rows:
                text = "Select a file in the table to show its intensity trace."
            elif self.model.current_folder is not None:
                text = "No file is listed, so there is no trace to show."
            else:
                text = "Open a folder with TTTR files, then select a file to show its trace."
            im.text_wrapped(text)
        elif self.model.trace_error:
            im.text_wrapped("No trace to show for this file.")

    def _current_view(self) -> TraceView | None:
        """The drawn data of the model's trace (rebuilt when the model holds another trace)."""
        trace = self.model.trace
        if not trace:
            self._view, self._view_for = None, 0
        elif id(trace) != self._view_for:
            self._view, self._view_for = TraceView(trace), id(trace)
        return self._view

    def _draw_trace(self, view: TraceView, height: float) -> None:
        """The counts-against-time plot and, to its right, the counts histogram (log axis)."""
        model = self.model
        low, high = model.y_range
        fixed = high > low                         # equal limits: let the plot fit the data
        key = (view.path, view.window_ms, low, high)
        cond = implot.COND_ALWAYS if key != self._limits_key else implot.COND_ONCE
        self._limits_key = key
        y_flags = implot.AXIS_FLAGS_NONE if fixed else implot.AXIS_FLAGS_AUTO_FIT
        width = float(im.get_content_region_avail()[0])
        if implot.begin_subplots(
            "##trace_subplots",
            1,
            2,
            (width, height),
            implot.SUBPLOT_FLAGS_LINK_ROWS | implot.SUBPLOT_FLAGS_NO_TITLE,
            None,
            [0.72, 0.28],
        ):
            if implot.begin_plot("Intensity trace##tb_trace", (-1.0, -1.0), implot.FLAGS_NO_TITLE):
                implot.setup_axes("Time (s)", f"Counts / {view.window_ms:g} ms", 0, y_flags)
                implot.setup_axis_limits(implot.AXIS_X1, 0.0, max(view.t_end, 1e-9), cond)
                if fixed:
                    implot.setup_axis_limits(implot.AXIS_Y1, low, high, cond)
                implot.setup_legend(implot.LOCATION_NORTH_EAST)
                for entry in view.series:
                    implot.set_next_line_style(entry["colour"], 1.0)
                    implot.plot_line(entry["label"], entry["x"], entry["y"])
                implot.end_plot()
            self.item_rects["trace_plot"] = im.get_item_rect()
            if implot.begin_plot(
                "Counts histogram##tb_hist", (-1.0, -1.0), implot.FLAGS_NO_LEGEND | implot.FLAGS_NO_TITLE
            ):
                implot.setup_axes("Counts (log)", "", 0, y_flags | implot.AXIS_FLAGS_NO_TICK_LABELS)
                implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
                if fixed:
                    implot.setup_axis_limits(implot.AXIS_Y1, low, high, cond)
                for entry in view.series:
                    if len(entry["freq"]):
                        implot.set_next_line_style(entry["colour"], 1.0)
                        implot.plot_line(entry["label"], entry["freq"], entry["centres"])
                implot.end_plot()
            implot.end_subplots()
        im.set_item_tooltip(
            "Counts per time bin of the selected file, one line per series and their sum. "
            "Scroll to zoom, drag to pan, double click to fit. The histogram on the right counts "
            "how many bins hold each count."
        )

    def _draw_notes(self, current: Any) -> None:
        """The annotation box: the notes of the current file (the same field as the Notes column)."""
        model = self.model
        im.text("Annotation")
        if current is None:
            im.text_wrapped("Select a file to write an annotation for it.")
            return
        disabled = bool(model.busy)
        if disabled:
            im.begin_disabled()
        changed, text = im.input_text_multiline(
            "##tb_annotation", model.get_notes(current), (-1.0, NOTES_HEIGHT)
        )
        if disabled:
            im.end_disabled()
        im.set_item_tooltip(
            "Free text about the selected file. It is the Notes column of the table: both show and "
            "edit the same text, saved beside the data in the folder's .trace_browser_meta.json "
            "shortly after you stop typing."
        )
        self.item_rects["annotation"] = im.get_item_rect()
        if changed and not disabled:
            model.set_notes(current, text, flush=False)
            self._notes_dirty_at = time.monotonic()
            self._notes_dirty_for = current

    def _flush_notes(self) -> None:
        """Write the metadata file once the annotation has rested (the Qt tool's 300 ms debounce).

        Also called before another file is selected, a folder is opened and when the app closes.
        """
        if self._notes_dirty_at is not None and (
            time.monotonic() - self._notes_dirty_at >= NOTES_FLUSH_S
            or self.model.busy
            or self.model.current_file != self._notes_dirty_for
        ):
            self.model.flush_meta()
            self._notes_dirty_at = None

    # -- folder dialog ---------------------------------------------------------
    #: Title of the folder dialog for each request of the model.
    _DIALOG_TITLES = {
        "folder": "Select folder with PTU/TTTR files",
        "export": "Select destination folder for the exported files",
        "csv": "Select destination folder for the CSV files",
    }

    def _open_requested_dialog(self) -> None:
        """Turn the model's ``dialog`` request into a folder :class:`FileDialog`.

        ``folder`` opens a folder to browse; ``export`` and ``csv`` ask where the selected files
        (or their CSV traces) go. The selection is taken when the dialog opens.
        """
        kind, self.model.dialog = self.model.dialog, ""
        if kind not in self._DIALOG_TITLES or self.dialog is not None:
            return
        folder = self.model.current_folder
        self.dialog_kind = kind
        self._dialog_paths = [str(p) for p in self.model.selection_paths()]
        self.dialog = FileDialog(
            self._DIALOG_TITLES[kind],
            mode="folder",
            directory=str(folder) if folder else None,
        )

    def _draw_dialog(self, box: Any) -> None:
        if self.dialog is None:
            return
        if im.begin(self.dialog.title):
            result = self.dialog.draw()
            if result:
                kind, paths = self.dialog_kind, self._dialog_paths
                self.dialog = None
                if kind == "export":
                    self.model.request("export_files", Path(result[0]), paths)
                elif kind == "csv":
                    self.model.request("export_csv_files", Path(result[0]), paths)
                else:
                    self.model.request("open_folder", Path(result[0]))
            elif result is False:
                self.dialog = None
        im.end()

    def _draw_confirm(self, box: Any) -> None:
        """The confirmation window of a pending delete: what moves, and Move / Cancel."""
        pending = self.model.confirm
        if pending is None:
            return
        width = min(460.0, float(box[2]) - 40.0)
        place = (max(20.0, (box[2] - width) / 2.0), max(60.0, box[3] * 0.25), width, 190.0)
        if im.begin(str(pending["title"]), place):
            im.text(str(pending["title"]))
            im.separator()
            im.text_wrapped(str(pending["message"]))
            im.spacing()
            if im.button(str(pending["yes"]) + "##confirm_yes"):
                self.model.confirm_yes()
            im.set_item_tooltip(
                "Move the listed files to the .trash folder of the opened folder. "
                "They are not deleted for good."
            )
            self.item_rects["confirm_yes"] = im.get_item_rect()
            im.same_line()
            if im.button("Cancel##confirm_no"):
                self.model.confirm_no()
            im.set_item_tooltip("Keep the files where they are. Nothing changes.")
            self.item_rects["confirm_no"] = im.get_item_rect()
        im.end()

    # -- folders dropped on the window ------------------------------------------
    def on_paths_dropped(self, paths: Any) -> None:
        """Open the first dropped folder (a dropped file is ignored, as in the Qt tool)."""
        self.model.on_paths_dropped(list(paths))

    def files_dropped(self, paths: Any) -> bool:
        """Host hook: ``True`` when a folder was taken."""
        return bool(self.model.on_paths_dropped(list(paths)))

    on_files_dropped = files_dropped

    # -- persistence -----------------------------------------------------------
    def export_settings(self) -> dict:
        """What the app remembers.

        The setup page: the setups file, the setup and its name.  The Browser page: folder,
        include-subfolders, rating filter, bin window and y range (the Qt browser kept none of
        these between sessions; the manifest's state schema only names the folder, the setup
        and the channels).
        """
        assert self.editor is not None
        setup = json.loads(json.dumps(self.editor.model.get_settings(), default=_plain))
        state = {
            "setups_file": self.setups_file,
            "setup_name": self.editor.model.current_name,
            "setup": setup,
        }
        state.update(self.model.export_view())
        return state

    def restore_settings(self, state: dict) -> None:
        """Restore :meth:`export_settings`; with a setup at hand open the Browser page.

        A remembered working setup (or, without one, the last used saved setup) is accepted as
        the Qt constructor accepts the setup page's: the app opens on the Browser page.  The
        remembered folder is opened on a worker if it still exists.
        """
        state = state or {}
        self.setups_file = str(state["setups_file"]) if state.get("setups_file") else None
        setup = state.get("setup")
        remembered = isinstance(setup, dict)
        self._new_editor(setup if remembered else None)
        selected = self._load_saved_setups(select_last=not remembered)
        folder = self.model.restore_view(state)
        if remembered or selected:
            self.continue_to_browser()
        else:
            self.model.back_to_setup()
        if folder is not None:
            self.model.request("open_folder", folder)

    def close(self) -> None:
        """Write a pending annotation, stop the precompute and the setup editor's reader thread."""
        self.model.precompute["cancel"] = True
        if self._notes_dirty_at is not None:
            self.model.flush_meta()
            self._notes_dirty_at = None
        if self.editor is not None:
            self.editor.close()


def make_app(on_request: Callable[[str, dict], Any] | None = None) -> TraceBrowserApp:
    """Factory of the manifest ``entrypoints.emtk``.

    Parameters
    ----------
    on_request : callable, optional
        The host's ``on_request(name, payload)``; without it the HMM, TW and NDX buttons are greyed.
    """
    return TraceBrowserApp(on_request=on_request)
