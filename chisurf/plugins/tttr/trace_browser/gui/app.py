"""Native emtk Trace Browser, in stages: the **Setup** page (card T1) and the **Browser** page (T2).

The Qt tool opens on a two-page workspace: page 0 is the detector setup (the
``DetectorWizardPage`` plus a *Continue* button), page 1 the trace browser.  This
module draws page 0 with the shared emtk setup editor
(:class:`chisurf.emtk.channel_definition.ChannelDefinitionWidget`); *Continue* hands
the editor's result to :meth:`.model.TraceBrowserModel.accept_setup` (which derives
the selected channels exactly as the Qt tool does) and switches the page.

Page 1 is the form of ``trace_browser_emtk.view.json`` drawn by
:func:`emtk.view_form.draw_form` (back button, folder, Open, include-subfolders,
rating filter, bin window, y range, Clear, Clear caches and the file table, a
``data_table`` section whose rating and notes columns are editable), next to a
labelled placeholder window where the trace plot of card T3 will go.  Scanning a
folder runs on a :class:`chisurf.emtk.jobs.SnapshotJob`; the folder is chosen with
an :class:`emtk.file_dialog.FileDialog` in folder mode or dropped on the window.  Like
the Qt constructor (which calls ``_on_continue()`` itself) the app opens on the Browser
page whenever a setup is available (the last used saved one, or a remembered one).

All state is in :class:`~.model.TraceBrowserModel`; this module imports no Qt.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from chisurf.core import setup_channel_definition as definition
from chisurf.core.fio import setup_store as store
from chisurf.core.setup_channel_definition import ChannelDefinition
from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.jobs import SnapshotJob

from .model import TraceBrowserModel

HERE = Path(__file__).parent


def _plain(value: Any) -> Any:
    """Convert numpy scalars/arrays to JSON types (``json.dumps`` ``default=``)."""
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"{type(value).__name__} is not JSON serialisable")


class TraceBrowserApp(ImApp):
    """Trace Browser: setup page (T1), browser page without the plot (T2; the plot is card T3).

    Parameters
    ----------
    model : TraceBrowserModel, optional
        The state; a fresh one by default.
    setups_file : str or Path, optional
        Detector-setups JSON file offered on the setup page; ``None`` is the user's
        canonical file, which is what the Qt setup page reads.
    """

    def __init__(self, model: TraceBrowserModel | None = None, setups_file: Any = None) -> None:
        self.model = model or TraceBrowserModel()
        self.setups_file = str(setups_file) if setups_file else None
        self.editor: ChannelDefinitionWidget | None = None
        self.item_rects: dict[str, tuple] = {}
        self.job = SnapshotJob(self.model)
        self.model.runner = self.queue_job
        self._queue: deque[tuple[str, tuple]] = deque()
        self._reported_error = ""
        self.spec = json.loads(
            (HERE / "trace_browser_emtk.view.json").read_text(encoding="utf-8")
        )
        self.form = FormState()
        self.dialog: FileDialog | None = None
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
            "plot", "Trace plot", self.draw_plot_placeholder, dock="plot", closable=False
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
            if self.job.start(method, *args):
                self.model.busy = True

    def animating(self) -> bool:
        """Keep drawing while a worker runs or a request waits, so the result appears."""
        return self.job.busy or bool(self._queue) or super().animating()

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
        width, height = im.get_main_viewport().size
        box = (0.0, 0.0, float(width), float(height))
        self.form.rects.clear()
        browser = self.model.page != "setup"
        (self.browser_docks if browser else self.setup_docks).draw(box)
        assert self.editor is not None
        self.editor.draw_dialogs(box)
        self._open_requested_dialog()
        self._draw_dialog(box)

    def draw_setup(self, box: Any) -> None:
        """Page 0: *Continue*, then the shared setup editor."""
        if im.button("Continue"):
            self.continue_to_browser()
        im.set_item_tooltip("Accept detector setup and open trace browser")
        self.item_rects["continue"] = im.get_item_rect()
        im.separator()
        assert self.editor is not None
        self.editor.draw()

    def draw_browser(self, box: Any) -> None:
        """Page 1: the form of the spec (controls and the file table)."""
        draw_form(self.spec, self.model, self.form)

    def draw_plot_placeholder(self, box: Any) -> None:
        """Where the intensity trace will be drawn (card T3): a label, no data."""
        im.text("Trace plot: card T3")
        im.separator()
        im.text_wrapped(
            "The intensity trace of the selected file, its channels and the y range are "
            "drawn here by card T3. Nothing is drawn until then."
        )
        im.separator()
        current = self.model.current_file
        im.text(f"Selected file: {current.name if current else '(none)'}")
        im.text(f"Bin window: {self.model.window_ms:g} ms")

    # -- folder dialog ---------------------------------------------------------
    def _open_requested_dialog(self) -> None:
        """Turn the model's ``dialog`` request into a folder :class:`FileDialog`."""
        kind, self.model.dialog = self.model.dialog, ""
        if kind != "folder" or self.dialog is not None:
            return
        folder = self.model.current_folder
        self.dialog = FileDialog(
            "Select folder with PTU/TTTR files",
            mode="folder",
            directory=str(folder) if folder else None,
        )

    def _draw_dialog(self, box: Any) -> None:
        if self.dialog is None:
            return
        if im.begin(self.dialog.title):
            result = self.dialog.draw()
            if result:
                self.dialog = None
                self.model.request("open_folder", Path(result[0]))
            elif result is False:
                self.dialog = None
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
        """Stop the setup editor's reader thread."""
        if self.editor is not None:
            self.editor.close()


def make_app() -> TraceBrowserApp:
    """Factory for the (later) manifest ``entrypoints.emtk``."""
    return TraceBrowserApp()
