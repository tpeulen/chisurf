"""The native Burst Selection app (cards BS1 to BS6): emtk over :class:`.model.BurstSelectionModel`, no Qt behind it.

Files, output, the burst search, the filter, the display, the histogram, the scatter, the bursts and the summary are
the spec ``native.view.json`` (tables as ``data_table`` / ``table`` sections); the parameters of the selected search
are generated from the JSON Schema tttrlib publishes; the detector definition is the shared one-page detector editor.
The plots draw only what the model computed from the photons, or say there is nothing. A run goes through
:class:`chisurf.emtk.jobs.SnapshotJob`; the diagnostics of the visible window are recomputed (debounced) after every
change, as the Qt tool does.
"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.i18n import tr
from emtk.im_core import get_current_context
from emtk.view_form import FormState, draw_form, draw_sections
from emtk.widgets.view_spec import load_view_spec

from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.display_units import ScaledParameters, scaled_sections
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.emtk.jobs import SnapshotJob
from chisurf.plugins.core.metadata_editor.core import flrcif_schema
from chisurf.plugins.core.metadata_editor.gui.widget import MetadataEditorWidget
from chisurf.plugins.emtk_layout import (
    LabelColumn,
    action_caption,
    action_tooltip,
    button_row,
    cap_widths,
    labelled,
    window_size,
)

from .model import BurstSelectionModel

#: The parameters of each burst search that Simple mode shows (the rest are Advanced, folded
#: under "More search parameters"); a search not listed shows its first three.
ESSENTIAL_SEARCH_PARAMETERS = {
    "sliding_window": ("L", "m", "T"),
    # the background rate is prefilled with the Background tool's estimate (Advanced shows it)
    "cusum_sprt": ("min_photons", "signal_to_background_ratio"),
    "kalman": ("L", "dt", "z_thresh"),
    "bocpd": ("L", "dt", "changepoint_prob"),
    "maxtree": ("L", "m", "min_significance"),
    "bayesian_blocks": ("L", "m", "min_significance"),
    "coincident": ("channel_groups", "algorithm", "min_groups", "L"),
}

#: Toolbar buttons a pipeline step does not show: its files are step 1's, and the legacy exports
#: (flrCIF and its metadata) live in File > Data > Legacy Export.
PIPELINE_HIDDEN_BUTTONS = frozenset({"load_example", "toolAction_clear", "export_cif", "metadata"})

if TYPE_CHECKING:
    from emtk.dialog_window import DialogWindow
    from emtk.file_dialog import FileDialog

    from chisurf.emtk.dataset_picker import DatasetPicker

HERE = Path(__file__).parent
#: Seconds without a change before the visible window is filtered again.
DIAGNOSTICS_DELAY = 0.35


def _sections(spec: dict, *titles: str) -> list[dict]:
    return [s for s in spec["sections"] if s.get("title") in titles]


class BurstSelectionNativeApp(TourTarget, ImApp):
    """Immediate-mode Burst Selection: files, detector editor, search, filter, run, diagnostics, features, output.

    Parameters
    ----------
    model : BurstSelectionModel, optional
        The state (default: a new model that restores the last settings).
    on_run_done : callable, optional
        Called with the model after a run finished (the Burst Analysis hub hands the bursts on).
    restore : bool
        Read the settings remembered by the previous session (default ``True``).
    """

    DIALOGS = {
        "export_cif": ("Export as flrCIF", "save"),
        "save_settings": ("Save Burst Selection settings", "save"),
    }
    FILTERS = {
        "export_cif": [("flrCIF", ["*.cif", "*.mmcif"]), ("All files", ["*"])],
        "save_settings": [("JSON", ["*.json"])],
    }

    def __init__(
        self,
        model: BurstSelectionModel | None = None,
        *,
        on_run_done: Callable[[BurstSelectionModel], None] | None = None,
        restore: bool = True,
        pipeline: bool = False,
    ) -> None:
        self.model = model or BurstSelectionModel()
        self.example_folder: Path | None = None  # None: the plugin's demo cache
        #: A step of the Burst Analysis pipeline: the files are step 1's (Data Selection), all of
        #: them, handed over by the hub (:meth:`use_files`); this step has no Input of its own.
        self.pipeline = bool(pipeline)
        self.model.files_from_pipeline = self.pipeline  # rows are not removed here then
        #: Simple / Advanced (the spec hides the expert inputs when False); standalone shows all.
        self.model.advanced = not self.pipeline
        if model is None and restore:
            self.model.restore()
            if self.pipeline:
                self.model.files.clear()  # the settings are restored, the files are step 1's
        self.on_run_done = on_run_done
        self.job = SnapshotJob(self.model)
        # The Input section: the workspace's photon streams (manifest ``accepts`` ``photons``).
        from chisurf.plugins.burst.workspace_io import NamedWorkspaceInput, input_spec

        self.input = NamedWorkspaceInput("burst_selection", "photons", app=self)
        self.input_spec = input_spec(
            Path(__file__).resolve().parents[1] / "manifest.json", "photons"
        )
        self.input_form = FormState()
        #: Which workspace dataset each searched file came from (its runs become its children).
        self.sources: dict[str, str] = {}
        self.model.sources = self.sources  # the model writes each file into its dataset's container
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.form = FormState()
        # The search's own parameters get their own forms (their own widget ids and edit buffers):
        # a search parameter named like a filter field -- CUSUM's min_photons beside the burst
        # size cut -- shared one id with it, so every keystroke typed into both ("00") and
        # select-all went to the other one.
        self.search_form = FormState()
        self.inner_search_form = FormState()
        spec = load_view_spec(str(HERE / "native.view.json"))
        self.window_size = window_size(spec, (1100, 720))
        cap_widths(spec["sections"])
        self.files_sections = _sections(spec, "Files")
        self.output_sections = _sections(spec, "Output")
        self.search_sections = _sections(spec, "Burst search")
        self.filter_sections = _sections(spec, "Channel selection", "Macro time interval", "Filter")
        self.display_sections = _sections(spec, "Display")
        self.hist_sections = _sections(spec, "Histogram")
        self.gmm_table = _sections(spec, "GMM")
        self.burst_table = _sections(spec, "Bursts")
        self.summary_table = _sections(spec, "Summary")
        self.gmm_settings_sections = _sections(spec, "GMM settings")
        #: The one metadata editor (core plugin): typed flrCIF fields + extras.
        self.metadata_editor = MetadataEditorWidget(on_apply=self._apply_metadata)
        self.labels = LabelColumn()
        self.dialog: FileDialog | None = None
        self.dialog_action = ""
        self._dialog_window: DialogWindow | None = None
        self.panel_dialog = ""
        self._panel_window: DialogWindow | None = None
        self.picker: DatasetPicker | None = None
        self._ndx_window = None
        self._diag_due: float | None = time.monotonic()
        #: (active file, processed, file count) the diagnostics last ran for
        self._signature: tuple[str, bool, int] | None = None
        self.message = ""
        self.editor = ChannelDefinitionWidget(
            self._editor_settings(),
            on_changed=self._setup_changed,
            host_app=self,
        )
        if self.model.setup_name:
            try:
                self.editor.model.select_setup(self.model.setup_name)
            except Exception:  # noqa: BLE001 - the editor shows its own default
                pass
        else:
            try:  # the last used setup, as the Qt tool opens it
                self.editor.model.refresh_setups()
                self.editor.model.open_last_used()
            except Exception:  # noqa: BLE001 - no store: the editor starts empty
                pass
        self.help_window = EmTkHelpWindow(
            title="Burst Selection - Help & Reference",
            resource=HERE / "help.md",
            owner=self.model,
            on_start_guide=self.start_guide,
            size=(720.0, 540.0),
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=lambda k: self.item_rects.get(k) or self.form.rects.get(k),
            on_step_change=self._tour_step,
            owner=self.model,
            wait_for_controls=True,
        )
        self.form.on_used = self._used
        self.search_form.on_used = self._used
        self.inner_search_form.on_used = self._used
        self.on_used = self.tour.notify_used
        self.editor.on_used = self.tour.notify_used
        self.docks = DockManager(
            Split(
                "h",
                0.38,
                Region("controls"),
                Split("v", 0.52, Region("plots_a"), Region("plots_b")),
            ),
            name="burst_selection",
        )
        add = self.docks.add_window
        add("files", "Burst Selection", self._files, dock="controls", closable=False)
        add("settings", "Filter settings", self._settings, dock="controls", closable=False)
        add("detectors", "Detector setup", self._detectors, dock="controls", closable=False)
        add("summary", "Summary", self._summary, dock="controls", closable=False)
        add("trace", "Count rate", self._trace, dock="plots_a", closable=False)
        add("dt", "Inter-photon time", self._dt, dock="plots_a", closable=False)
        add("decay", "Micro-time decay", self._decay, dock="plots_a", closable=False)
        add("duration", "Burst duration", self._duration, dock="plots_a", closable=False)
        add("histogram", "Histogram", self._histogram, dock="plots_b", closable=False)
        add("table", "Bursts", self._bursts, dock="plots_b", closable=False)
        super().__init__(gui=self._render)

    # -- tour / help ----------------------------------------------------------------------------------------- #
    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()

    def track(self, name: str) -> None:
        self.on_used(name)

    def _tour_step(self, _index: int, step: dict) -> None:
        """A step's target names the dock window of its control (``"tab"``); bring that tab to the front."""
        window = (step.get("target") or {}).get("tab")
        if window and self.docks.window(window) is not None:
            self.docks.focus(window)

    def _used(self, name: str) -> None:
        self.tour.notify_used(name)
        self._diag_due = time.monotonic() + DIAGNOSTICS_DELAY

    # -- detector setup -------------------------------------------------------------------------------------- #
    def _editor_settings(self) -> dict:
        return {
            "detectors": copy.deepcopy(self.model.detectors),
            "windows": copy.deepcopy(self.model.windows),
            "tttr_reading": {"file_type": self.model.file_type or "auto"},
            "setup_name": self.model.setup_name,
        }

    def _setup_changed(self, settings: dict) -> None:
        name = getattr(self.editor.model, "current_name", "") if hasattr(self, "editor") else ""
        self.model.set_setup({**settings, "setup_name": name or settings.get("setup_name", "")})
        self._diag_due = time.monotonic() + DIAGNOSTICS_DELAY

    def apply_setup(self, settings: dict, name: str = "") -> None:
        """Take a detector definition from outside (the Burst Analysis workflow)."""
        if name:
            try:
                self.editor.model.select_setup(name)
                return
            except Exception:  # noqa: BLE001 - not in the store: take the definition as given
                pass
        self.editor.model.data = copy.deepcopy({**settings, "setup_name": name})
        self.model.set_setup({**settings, "setup_name": name})

    # -- actions --------------------------------------------------------------------------------------------- #
    @property
    def running(self) -> bool:
        return bool(self.job.busy)

    def run(self, force: bool = False) -> bool:
        """Run (or, with *force*, Restart) the search over every file; ``False`` when it did not start."""
        if self.pipeline:  # the pipeline writes .pto only; zipped folders are Legacy Export's
            self.model.zip_output = self.model.remove_folder = False
        why = self.model.prepare_run(force=force)
        if why is not None:
            self.model.status_text = why
            return False
        self.job.start("run")
        return True

    def set_advanced(self, advanced: bool) -> None:
        """The pipeline's Simple / Advanced mode: Simple shows only the essential inputs -- the
        detector setup is step 0's, the burst table is for the expert -- Advanced shows them."""
        self.model.advanced = bool(advanced)
        for key in ("detectors", "table"):
            if key not in self.docks.windows:
                continue
            if advanced:
                self.docks.show(key)
            else:
                self.docks.hide(key)
        if not advanced:
            self.docks.focus("files")

    def use_files(self, paths, uids=()) -> bool:
        """Make the files exactly *paths* (in order) -- the pipeline's hand-off from Data Selection.

        Returns whether the list changed; a change drops the results of the files that left.
        """
        wanted = [Path(p).resolve() for p in paths]
        if wanted == [Path(p).resolve() for p in self.model.files]:
            return False
        for index in reversed(range(len(self.model.files))):
            if Path(self.model.files[index]).resolve() not in wanted:
                self.model.remove_index(index)
        self.take_photons([str(p) for p in wanted], uids)
        order = {p: i for i, p in enumerate(wanted)}
        self.model.files.sort(key=lambda p: order.get(Path(p).resolve(), len(order)))
        self.model.notify("files")
        return True

    def take_photons(self, paths, uids=()) -> int:
        """Add photon files from the workspace; remember which dataset each came from (its runs
        become that dataset's children)."""
        added = self.model.add_paths([Path(p) for p in paths])
        for path, uid in zip(paths, uids):
            if uid:
                self.sources[str(Path(path).resolve())] = str(uid)
        if added:
            self._diag_due = time.monotonic()
        return added

    def _register_runs(self) -> None:
        """Show the newest burst run of each searched measurement in the workspace: a child of the
        photon dataset, read from that dataset's analysis container in the project (the run is not
        stored as a dataset; the container is its record)."""
        from chisurf.core.api import dataset_objects
        from chisurf.core.fio.classify import container_entries
        from chisurf.core.plugin.workspace_input import register_result

        known = {str(getattr(d, "address", "")) for d in dataset_objects()}
        folders = self.model.container_dirs()
        for path in self.model.files:
            container = Path(folders[str(path)]) / f"{Path(path).stem}.pto"
            if not container.exists():
                continue
            try:
                runs = [a for kind, a in container_entries(container) if kind == "bursts"]
            except Exception:  # noqa: BLE001 - written either way; the row is a view of it
                continue
            if runs and runs[-1] not in known:
                register_result(
                    runs[-1], kind="bursts", result_of=self.sources.get(str(Path(path).resolve()), "")
                )

    def load_example(self) -> None:
        """Add the simulated stream with its known twelve bursts and select the matching detectors."""
        from ..demo import SETUP, make_demo

        try:
            path = make_demo(self.example_folder)
        except Exception as exc:  # noqa: BLE001 - shown in the status line
            self.model.status_text = f"Cannot build the example: {exc}"
            return
        self.apply_setup(SETUP)
        from chisurf.core.plugin.workspace_input import register_result

        try:  # the example enters the workspace like a dropped file, then feeds this tool
            stream = register_result(str(path), kind="photons", name=Path(path).name)
            uid = str(getattr(stream, "unique_identifier", ""))
        except Exception:  # noqa: BLE001 - the search still runs on the file
            uid = ""
        self.take_photons([path], [uid])
        self.track("load_example")
        self.model.status_text = (
            "Example added: a simulated stream with 12 planted bursts of about 200 photons. "
            "Press Run: the search must find all 12."
        )

    def run_step(self) -> bool:
        """The workflow hub's Next: run unless an identical search is already displayed."""
        if (
            self.model.has_processed
            and self.model.prepare_run() is not None
            and self.model.unchanged
        ):
            return False
        return self.run()

    def browse(self, action: str) -> None:
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        title, mode = self.DIALOGS[action]
        options: dict[str, Any] = {}
        if self.model.files:
            options["directory"] = str(self.model.files[0].parent)
        filters = self.FILTERS.get(action)
        if filters:
            options["filters"] = filters
        filename = ""
        if action == "export_cif":
            filename = "bursts.cif"
        elif action == "save_settings":
            filename = "burst_selection_settings.json"
        # not-input: flrCIF export and saved settings (outputs); saved settings come back as setup rows
        self.dialog = FileDialog(title, mode=mode, filename=filename, **options)
        self.dialog_action = action
        window = DialogWindow(title, size=(660.0, 470.0), key="burst-selection-file")
        self._dialog_window = window
        window.show()

    def _dialog_done(self, result: list[str]) -> None:
        action = self.dialog_action
        try:
            if action == "export_cif":
                self.model.export_flr_cif(result[0])
            elif action == "save_settings":
                self.model.save_settings(result[0])
                self.model.status_text = f"Settings saved to {result[0]}"
        except Exception as exc:  # noqa: BLE001 - shown in the status line
            self.model.status_text = f"Error: {exc}"

    def open_panel(self, name: str) -> None:
        from emtk.dialog_window import DialogWindow

        titles = {"metadata": "Metadata", "gmm": "GMM settings"}
        self.panel_dialog = name
        window = DialogWindow(titles[name], size=(460.0, 420.0), key=f"burst-selection-{name}")
        self._panel_window = window
        window.show()

    def send_to_ndx(self) -> bool:
        """Open the last run's burst output in ndX (needs a run)."""
        path = self.model.output_path()
        if not path:
            self.model.status_text = "No burst output to send: run the search first."
            return False
        try:
            from chisurf.plugins.ndxplorer.mmfdb_launcher import open_path_in_ndxplorer

            self._ndx_window = open_path_in_ndxplorer(path)
        except Exception as exc:  # noqa: BLE001 - ndX is optional
            self.model.status_text = f"Could not send to ndX: {exc}"
            return False
        if self._ndx_window is None:
            self.model.status_text = "ndX could not be opened."
            return False
        self.model.status_text = f"Opened {path} in ndX."
        return True

    def _press(self, key: str) -> None:
        m = self.model
        self.track(key)
        try:
            if key == "toolAction_run":
                self.run()
            elif key == "toolAction_restart":
                self.run(force=True)
            elif key == "toolAction_clear":
                m.clear()
            elif key == "toolAction_refresh":
                self._diag_due = time.monotonic()
            elif key in self.DIALOGS:
                self.browse(key)
            elif key == "metadata":
                self.open_panel("metadata")
            elif key == "ndx_current":
                self.send_to_ndx()
            elif key == "guide":
                self.start_guide()
            elif key == "help":
                self.show_help()
        except Exception as exc:  # noqa: BLE001 - shown in the status line
            m.status_text = f"Error: {exc}"

    # -- windows --------------------------------------------------------------------------------------------- #
    def _files(self, box=None) -> None:
        m = self.model
        busy = self.running
        self.input_form.rects.clear()
        if self.pipeline:
            # In the pipeline the files are step 1's, all of them: no Input to pick from (Simple
            # does not repeat them at all -- step 1 chose them).
            if getattr(m, "advanced", True):
                im.text(f"Files: all {len(m.files)} from 1. Data Selection")
                im.set_item_tooltip("Add or remove files in step 1 (Data Selection); this step searches all of them.")
        else:
            im.begin_disabled(busy)
            self.input.workspace_input_on_used = self.track
            draw_form(self.input_spec, self.input, self.input_form)
            im.end_disabled()
        for name, rect in self.input_form.rects.items():
            self.item_rects[name] = tuple(rect)
        has_files = bool(m.files)
        has_result = m.has_processed
        shown = m.display_frame is not None
        buttons = [
                {
                    "label": action_caption("example"),
                    "key": "load_example",
                    "enabled": not busy and not self.pipeline,
                    "tip": "Add a simulated photon stream with 12 planted bursts and select its detectors."
                    if not self.pipeline
                    else "In the pipeline the files come from 1. Data Selection.",
                },
                {
                    "label": action_caption("run"),
                    "key": "toolAction_run",
                    "enabled": has_files and not busy,
                    "tip": "Search the bursts of every file and write the burst tables."
                    if has_files
                    else "Pick photon streams in the Input section first.",
                },
                {
                    "label": action_caption("restart"),
                    "key": "toolAction_restart",
                    "enabled": has_files and not busy,
                    "tip": "Search again even though files and settings are unchanged.",
                },
                {
                    "label": "Clear",
                    "key": "toolAction_clear",
                    "enabled": has_files and not busy and not self.pipeline,
                    "tip": "Remove every file and result (the settings stay)."
                    if not self.pipeline
                    else "In the pipeline the files are step 1's: remove them in 1. Data Selection.",
                },
                {
                    "label": "Refresh plots",
                    "key": "toolAction_refresh",
                    "enabled": has_files and not busy,
                    "tip": "Filter the visible window again and redraw the plots.",
                },
                {
                    "label": "Export flrCIF",
                    "key": "export_cif",
                    "enabled": shown,
                    "tip": "Write the displayed table and the metadata as flrCIF.",
                },
                {
                    "label": "Metadata",
                    "key": "metadata",
                    "tip": "Edit the analysis metadata written with the flrCIF export.",
                },
                {
                    "label": "Open in ndX",
                    "key": "ndx_current",
                    "enabled": has_result and not busy,
                    "tip": "Open the last run's burst folder in ndXplorer."
                    if has_result
                    else "Run the search first.",
                },
                {
                    "label": "Save settings",
                    "key": "save_settings",
                    "tip": "Write the filter, search, display and GMM settings to a JSON file.",
                },
                {
                    "label": action_caption("guide"),
                    "key": "guide",
                    "tip": action_tooltip("guide"),
                },
                {
                    "label": action_caption("help"),
                    "key": "help",
                    "tip": action_tooltip("help"),
                },
            ]
        if self.pipeline:
            # Not on the pipeline: its files are step 1's (no example, no Clear), and the legacy
            # exports (flrCIF + its metadata, zipped folders) are File > Data > Legacy Export's.
            buttons = [b for b in buttons if b["key"] not in PIPELINE_HIDDEN_BUTTONS]
        simple = self.pipeline and not getattr(m, "advanced", True)
        if simple:
            # Simple: no buttons -- Next (or >>) runs the search; the rest is Advanced
            buttons = []
        pressed = button_row(buttons, remember=self.remember) if buttons else None
        if pressed == "load_example":
            self.load_example()
        elif pressed:
            self._press(pressed)
        if busy or self.job.progress:
            im.text_wrapped(self.job.progress or m.status_text)
        elif self.job.error:
            im.text_colored(f"Error: {self.job.error}", (0.9, 0.4, 0.4, 1.0))
        else:
            im.text_wrapped(m.status_text)
        self.remember("status")
        if simple:
            return  # the setup is step 0's; the file and run tables and the output are Advanced
        im.text_wrapped(m.setup_text())
        im.separator()
        im.begin_disabled(busy)
        draw_sections(self.files_sections, m, self.form)
        draw_sections(self.output_sections, m, self.form)
        im.end_disabled()

    def _settings(self, box=None) -> None:
        m = self.model
        busy = self.running
        target = copy.copy(m) if busy else m  # edits during a run go nowhere
        # times the searches keep in seconds are shown in µs / ms / s (0.5 ms, not 0.0005)
        params, factors = scaled_sections(m.search_sections(), m.search_schema())
        nested, nested_factors = scaled_sections(m.nested_sections(), m.nested_schema())
        static = self.search_sections + self.filter_sections + self.display_sections
        if not self.labels.ready:
            self.labels.measure([f["label"] for f in labelled(static + params + nested)])
            self.labels.pad(static)
        self.labels.pad(params + nested)
        im.begin_disabled(busy)
        draw_sections(self.search_sections, target, self.form)
        self.remember("search", None)
        if params:
            essential, more = self._split_search(params)
            search = ScaledParameters(m.search, factors)
            self._cusum_background()
            draw_sections(essential, search, self.search_form)
            if more and getattr(m, "advanced", True):
                fold = {"type": "panel", "title": "More search parameters", "collapsible": True,
                        "collapsed": True, "sections": more,
                        "description": "The other parameters of this search; their defaults suit most data."}
                draw_sections([fold], search, self.search_form)
                self._background_hint()
        if nested:
            im.text(tr("Per-group search parameters"))
            draw_sections(nested, ScaledParameters(m.inner_search, nested_factors), self.inner_search_form)
        for prefix, form in (("search", self.search_form), ("inner_search", self.inner_search_form)):
            for name, rect in form.rects.items():
                self.item_rects[f"{prefix}.{name}"] = tuple(rect)
        if getattr(m, "advanced", True):
            if im.button(tr("Save as setup default")):
                self.track("save_defaults")
                try:
                    m.save_defaults_to_setup()
                except Exception as exc:  # noqa: BLE001 - shown in the status line
                    m.status_text = f"Error: {exc}"
            im.set_item_tooltip(
                tr(
                    "Store the current filter and search as the defaults of the selected detector setup "
                    "(read again whenever the setup is chosen)."
                )
            )
            self.remember("save_defaults")
        draw_sections(self.filter_sections, target, self.form)
        draw_sections(self.display_sections, target, self.form)
        im.end_disabled()

    def _split_search(self, params: list[dict]) -> tuple[list[dict], list[dict]]:
        """The search's parameters Simple shows, and the rest (Advanced, folded)."""
        names = ESSENTIAL_SEARCH_PARAMETERS.get(str(self.model.algorithm))
        if names is None:
            names = tuple(p.get("attr") for p in params[:3])
        essential = sorted((p for p in params if p.get("attr") in names), key=lambda p: names.index(p["attr"]))
        return essential, [p for p in params if p.get("attr") not in names]

    def _selecting_detectors(self) -> dict:
        """The detectors the bursts are selected on: the one picked in Channel selection, else all."""
        m = self.model
        detectors = {
            str(name): {"chs": [int(c) for c in (d or {}).get("chs", [])],
                        "micro_time_ranges": [list(r) for r in (d or {}).get("micro_time_ranges") or []]}
            for name, d in (m.detectors or {}).items()
            if (d or {}).get("chs")
        }
        picked = getattr(m, "detector", None)
        return {picked: detectors[picked]} if picked in detectors else detectors

    def _cusum_background(self) -> None:
        """CUSUM/SPRT: search the photons of the selecting detectors, its background prefilled with
        their Background-tool estimate (summed) -- refilled when the file or detectors change,
        until the user types a rate of their own."""
        from chisurf.core.fluorescence.burst.tttrlib_search import SEARCH_DETECTORS

        m = self.model
        if str(m.algorithm) != "cusum_sprt":
            return
        detectors = self._selecting_detectors()
        if m.parameters.get(SEARCH_DETECTORS) != detectors:
            m.parameters[SEARCH_DETECTORS] = detectors
            m.settings_changed()
        tttr = (m.diagnostic or {}).get("tttr")
        if tttr is None or not detectors:
            return
        key = (id(tttr), len(tttr), json.dumps(detectors, sort_keys=True))
        if getattr(self, "_background_key", None) != key:
            self._background_key, self._background = key, None
            self._estimate_background(tttr, detectors, key)
        found = self._background
        if found is None:
            ctx = get_current_context()
            ctx.request_frame_at(ctx.io.now + 0.1)  # the estimate lands in a thread: look again
            return
        total = sum(found.values())
        typed = float(m.search.background_cps or 0.0)
        prefilled = getattr(self, "_prefilled_cps", None)
        if total > 0 and (typed <= 0 or (prefilled is not None and abs(typed - prefilled) < 1e-6)):
            if abs(typed - total) > 1e-6:
                m.search.background_cps = total
                m.settings_changed()
            self._prefilled_cps = total

    def _background_hint(self) -> None:
        """Advanced: where the prefilled background rate comes from, per detector."""
        m = self.model
        found = getattr(self, "_background", None)
        if str(m.algorithm) != "cusum_sprt" or not found:
            return
        shares = ", ".join(f"{name} {cps / 1e3:.2f}" for name, cps in sorted(found.items()))
        typed = float(m.search.background_cps or 0.0)
        own = getattr(self, "_prefilled_cps", None)
        source = (tr("the Background tool's estimate") if own is not None and abs(typed - own) < 1e-6
                  else tr("typed; the Background tool estimates {:.2f}").format(sum(found.values()) / 1e3))
        im.push_text_wrap_pos(0.0)
        im.text_disabled(tr("Background rate: {} (kcps per channel: {}). The search reads the photons "
                            "of the detectors the bursts are selected on.").format(source, shares))
        im.pop_text_wrap_pos()
        im.set_item_tooltip(tr(
            "The detectors the bursts are selected on (Channel selection; all by default). Each of their "
            "routing channels is fitted to the tail of its inter-photon times in one shared window, as "
            "the Background tool does; the search tests against the sum. Type a rate to use that "
            "instead."))

    def _estimate_background(self, tttr, detectors: dict, key) -> None:
        """The Background tool's per-detector estimate of *tttr*, in a thread (~1 s on 300 MB)."""
        import threading

        from chisurf.core.fluorescence.burst.tttrlib_search import detector_backgrounds_cps

        def work() -> None:
            try:
                found = detector_backgrounds_cps(tttr, detectors)
            except Exception:  # noqa: BLE001 - no prefill rather than a broken panel
                found = None
            if getattr(self, "_background_key", None) == key:
                self._background = found

        threading.Thread(target=work, name="background-estimate", daemon=True).start()

    def _detectors(self, box=None) -> None:
        self.remember("detectors", box)
        self.editor.draw()

    def _summary(self, box=None) -> None:
        m = self.model
        if not m.has_processed and m.display_frame is None:
            im.text_wrapped(
                tr(
                    "No search yet: add TTTR files and press Run. The key figures of the run appear here."
                )
            )
            return
        draw_sections(self.summary_table, m, self.form)

    def _empty(self, text: str) -> None:
        im.text_wrapped(text)

    def _trace(self, box=None) -> None:
        self.remember("trace", box)
        m = self.model
        curves = m.trace_curves()
        if not curves:
            self._empty(
                "No count-rate trace: add TTTR files. The trace of the visible window of the active file "
                "(all photons and the selected burst photons) appears here."
            )
            return
        if implot.begin_plot(f"Count rate ({m.trace_bin_ms:g} ms bins)", (-1, -1)):
            implot.setup_axes("Time in the window (s)", "Count rate (kHz)")  # count rates read in kHz
            for key, name in (("all", tr("All photons")), ("selected", tr("Selected photons"))):
                if key in curves:
                    x, y = curves[key]
                    implot.plot_line(name, x, np.asarray(y, dtype=float) / 1e3)
            implot.end_plot()

    def _dt(self, box=None) -> None:
        self.remember("dt", box)
        m = self.model
        curves = m.dt_curves()
        if not curves:
            self._empty(
                "No inter-photon times: add TTTR files. dT of every photon of the visible window appears here."
            )
            return
        if implot.begin_plot("Inter-photon time", (-1, -1)):
            implot.setup_axes("Photon index", "dT (ms)")
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            collapse_legend = len(curves) > 8
            for key in ("all", "selected"):
                if key in curves:
                    implot.plot_line(
                        tr("All photons") if key == "all" else tr("Selected photons"),
                        *curves[key],
                    )
            for key, data in curves.items():
                if key not in ("all", "selected"):
                    name = key.split(" · ")[0] if collapse_legend and " · " in key else key
                    implot.plot_line(name, *data)
            limits = m.thresholds()
            for n, key in enumerate(("dt_min", "dt_max")):
                limit = limits[key]
                if limit is not None:
                    moved = implot.drag_line_y(700 + n, float(limit), None, 1.5)
                    if moved.modified and moved.value > 0:
                        setattr(m, key, float(moved.value))
                        self._used(key)
            implot.end_plot()

    def _decay(self, box=None) -> None:
        self.remember("decay", box)
        curves = self.model.decay_curves()
        if not curves:
            self._empty(
                "No micro-time decay: add TTTR files. The decay of the file and of the burst photons appears here."
            )
            return
        if implot.begin_plot("Micro-time histogram", (-1, -1)):
            implot.setup_axes("Micro time (ns)", "Counts")
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            if "all" in curves:
                implot.plot_line(tr("All photons"), *curves["all"])
            if "selected" in curves:
                implot.plot_line(tr("Selected photons"), *curves["selected"])
            implot.end_plot()

    def _duration(self, box=None) -> None:
        self.remember("duration", box)
        m = self.model
        if not m.show_selected_photons:
            self._empty("Selected photons are hidden (Display): burst durations are not drawn.")
            return
        hist = m.duration_histogram()
        if hist is None:
            self._empty("No bursts in the visible window: their duration histogram appears here.")
            return
        centres, counts, width = hist
        # Above the plot: the plot fills the rest of the dock, so a line drawn after it fell outside the panel and
        # nothing said that these are the bursts of the visible window, not of the file.
        im.text(f"Total bursts in the window: {int(counts.sum())}")
        if implot.begin_plot("Burst duration", (-1, -1)):
            implot.setup_axes("Burst duration (ms)", "Bursts")
            implot.plot_bars("Bursts", centres, counts, bar_size=width * 0.9)
            implot.end_plot()

    def _histogram(self, box=None) -> None:
        self.remember("histogram", box)
        m = self.model
        simple = self.pipeline and not getattr(m, "advanced", True)
        if not simple:  # Simple: the histogram alone; its feature, range and GMM are Advanced
            draw_sections(self.hist_sections, m, self.form)
        pressed = None if simple else button_row(
            [
                {
                    "label": "Auto range",
                    "key": "auto_range",
                    "tip": "Set the range to the data range of the feature.",
                },
                {
                    "label": "Fit GMM",
                    "key": "fit_gmm",
                    "enabled": m.display_frame is not None,
                    "tip": "Fit the histogram with a Gaussian mixture (components above).",
                },
                {
                    "label": "GMM settings",
                    "key": "gmm_settings",
                    "tip": "Advanced Gaussian-mixture settings.",
                },
            ],
            remember=self.remember,
        )
        if pressed == "auto_range":
            m.auto_range()
        elif pressed == "fit_gmm":
            self.track("fit_gmm")
            try:
                result = m.fit_gmm()
                if result.get("error"):
                    m.status_text = result["error"]
            except Exception as exc:  # noqa: BLE001
                m.status_text = f"GMM fitting failed: {exc}"
        elif pressed == "gmm_settings":
            self.open_panel("gmm")
        hist = m.histogram()
        if hist is None:
            self._empty(
                "No burst table yet: the histogram of the chosen feature appears after a run or a preview."
            )
            return
        centres, counts, width = hist
        if implot.begin_plot(f"Histogram of {m.hist_feature}", (-1, -112 if m.gmm_rows() else -1)):
            implot.setup_axes(m.hist_feature, "Bursts")
            if (m.gmm_result or {}).get("x") is not None:
                # Beside the plot: inside, five entries covered the peaks of a histogram the GMM table leaves short.
                implot.setup_legend(implot.LOCATION_EAST, implot.LEGEND_FLAGS_OUTSIDE)
            if m.hist_log:
                implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            implot.plot_bars("Bursts", centres, counts, bar_size=width * 0.9)
            gmm = m.gmm_result or {}
            if gmm.get("x") is not None:
                implot.plot_line("GMM fit", gmm["x"], gmm["total"])
                for i, comp in enumerate(gmm["components"]):
                    implot.plot_line(f"Gaussian {i + 1}", gmm["x"], comp)
            implot.end_plot()
        if m.gmm_rows():
            draw_sections(self.gmm_table, m, self.form)

    def _bursts(self, box=None) -> None:
        self.remember("bursts", box)
        m = self.model
        if m.display_frame is None:
            self._empty("No bursts yet: press Run (or wait for the preview of the visible window).")
            return
        im.text(
            ("Preview of the visible window" if m.preview else "Bursts of the active file")
            + (f": {m.active_file.name}" if m.active_file else "")
        )
        draw_sections(self.burst_table, m, self.form)

    def _apply_metadata(self, entries: dict[str, str]) -> None:
        """The shared editor applied: every entry set, every dropped key removed."""
        for key in [k for k in self.model.metadata if k not in entries]:
            self.model.delete_metadata(key)
        for key, value in entries.items():
            self.model.set_metadata(key, value)
        self.model.status_text = f"Metadata updated. {len(entries)} entries."

    def _panel(self, frame) -> None:
        window = self._panel_window
        if not self.panel_dialog or window is None:
            return
        pressed = window.begin(frame)
        if self.panel_dialog == "metadata":
            # The common experiment fields as typed inputs; anything else (the
            # PDBx keys among them -- thousands) joins as a free-form entry.
            if not self.metadata_editor.visible:
                self.metadata_editor.open(flrcif_schema(), dict(self.model.metadata))
            self.metadata_editor.draw()
            self.item_rects.update(self.metadata_editor.item_rects)
        else:
            draw_sections(self.gmm_settings_sections, self.model.gmm, self.form)
            if im.button(tr("Fit GMM with these settings"), role="primary"):
                try:
                    self.model.fit_gmm()
                except Exception as exc:  # noqa: BLE001
                    self.model.status_text = f"GMM fitting failed: {exc}"
            im.set_item_tooltip(tr("Refit the histogram with the settings above."))
        window.end()
        if pressed == "close" or (
            self.panel_dialog == "metadata" and not self.metadata_editor.visible
        ):
            self.panel_dialog = ""

    # -- the frame ------------------------------------------------------------------------------------------- #
    def _diagnostics_tick(self) -> None:
        """Filter the visible window again once the settings have been still for a moment."""
        m = self.model
        if self.running or not m.files:
            return
        signature = (str(m.active_file), m.has_processed, len(m.files))
        if signature != self._signature:
            self._signature = signature
            self._diag_due = self._diag_due or time.monotonic()
        if self._diag_due is None or time.monotonic() < self._diag_due:
            return
        if self.diagnostics_running:
            return  # the next one starts once this one has landed (the due time stays)
        self._diag_due = None
        # Opening the measurement, filtering and searching the visible window takes seconds on a large
        # file: off the UI thread, or every settled edit froze the window that long.
        import threading

        from chisurf.emtk.background_build import track

        def work() -> None:
            try:
                m.load_diagnostics()
            except Exception as exc:  # noqa: BLE001 - shown in the status line
                m.status_text = f"Diagnostics unavailable: {exc}"

        self._diag_thread = track(threading.Thread(target=work, daemon=True, name="burst-diagnostics"))
        self._diag_thread.start()

    @property
    def diagnostics_running(self) -> bool:
        """The visible window's preview is being computed on its worker thread."""
        thread = getattr(self, "_diag_thread", None)
        return thread is not None and thread.is_alive()

    def _render(self) -> None:
        self.editor.poll()
        ctx = get_current_context()
        if self.job.poll():
            self.model.remember()
            self._diag_due = time.monotonic()
            if not self.job.error:
                self._register_runs()
            if self.on_run_done is not None and not self.job.error:
                self.on_run_done(self.model)
        if self.job.busy or self._diag_due is not None or self.diagnostics_running:
            ctx.request_frame_at(ctx.io.now + 0.1)
        self._diagnostics_tick()
        w, h = im.get_main_viewport().size
        frame = (0.0, 0.0, float(w), float(h))
        self.docks.draw(frame)
        self.editor.draw_dialogs(frame)
        self._panel(frame)
        window = self._dialog_window
        if self.dialog is not None and window is not None:
            pressed = window.begin(frame)
            result = self.dialog.draw()
            window.end()
            if result:
                self._dialog_done(result)
                self.dialog = None
            elif result is False or pressed == "close":
                self.dialog = None
        if self.picker is not None:
            self.picker.render(frame)
            if not getattr(self.picker, "is_open", True):
                self.picker = None
        if self.help_window.open:
            self.help_window.draw(frame)
        if self.tour.active:
            self.tour.draw(w, h)

    # -- persistence ----------------------------------------------------------------------------------------- #
    def export_settings(self) -> dict[str, Any]:
        return self.model.export_settings()

    def restore_settings(self, state: dict[str, Any] | None) -> None:
        if state:
            self.model.import_settings(state)

    def close(self) -> None:
        self.model.remember()
        self.editor.close()


def create_app(**kwargs) -> BurstSelectionNativeApp:
    """Factory named by ``entrypoints.emtk``."""
    from chisurf.emtk.i18n import install

    install()
    return BurstSelectionNativeApp(**kwargs)


def receive_settings(app: BurstSelectionNativeApp, payload: dict) -> None:
    """Hand-off receiver (manifest ``accepts`` ``settings``): apply a saved settings file, a setup
    row of the Datasets workspace (``payload["settings"]``)."""
    from chisurf.core.plugin.workspace_input import read_address

    address = payload.get("settings")
    if not address:
        raise ValueError("no settings picked")
    path = read_address(str(address))
    app.model.load_settings(path)
    app.model.status_text = f"Settings loaded from {path}"
    app._diag_due = time.monotonic()


def receive_photons(app: BurstSelectionNativeApp, payload: dict) -> None:
    """Hand-off receiver (manifest ``accepts`` ``photons``): search the photon streams
    ``payload["files"]`` of the Datasets workspace; the runs found become their children."""
    from chisurf.core.plugin.workspace_input import read_address

    files = payload.get("files") or []
    files = files if isinstance(files, list) else [files]
    paths = [read_address(str(f)) for f in files]
    uids = list(payload.get("datasets") or [])
    if not app.take_photons(paths, uids) and not set(map(str, paths)) & {
        str(p) for p in app.model.files
    }:
        raise ValueError("nothing new to add (already listed, or not a photon file)")
