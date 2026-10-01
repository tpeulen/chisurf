"""Qt-free model behind the native LUT Tools window.

:class:`LutToolModel` is the one object the ``lut_tools_emtk.view.json`` spec
reads and writes. It wraps :class:`~.controller.LutWorkspace` (which holds the
compute view-model of tab 1 and the assign/preview state of tab 2) and adds what
a form needs: flat parameter attributes, the three table sources, action methods
that take no argument, ``enabled(name)``, and the *requests* (a file dialog to
open, a background job to run) the app services once per frame, so the model
itself never touches a window or a thread.

Slow work (reading photon files, computing a LUT for every channel, exporting)
runs as a method on a snapshot of this model
(:class:`chisurf.emtk.jobs.SnapshotJob`); ``__copy__`` gives the job its own copy
of the workspace so the displayed state is never mutated from the worker.
"""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np

from ..api import lut as _lut
from .controller import LutWorkspace

STAGES = ("Compute LUT", "settings.tttr.json (optional)")
READING_ROUTINES = (
    ("Auto", None),
    ("PTU", 0),
    ("HT3", 1),
    ("SPC-130", 2),
    ("SPC-600_256", 3),
    ("SPC-600_4096", 4),
    ("PHOTON-HDF5", 5),
)
#: Parameters of tab 1, forwarded to the compute view-model (the Qt tool's names).
_PARAMS = (
    "linear_start",
    "linear_stop",
    "ntac_required",
    "noffset",
    "preview_photons",
    "seed",
    "normalize",
    "mitigate_wrap",
    "eps",
    "threshold",
)
FLOW_HINT = (
    "1. Load a flat-light file, then Add all channels to setup (one LUT per routing channel). "
    "2. settings.tttr.json is optional: it only saves / loads a settings.tttr.json file."
)


def _forward(name):
    def getter(self):
        return getattr(self.ws.compute, name)

    def setter(self, value):
        setattr(self.ws.compute, name, value)

    return property(getter, setter)


class LutToolModel:
    """State and actions of the LUT Tools window, without any drawing."""

    def __init__(self, apply_callback=None):
        self.ws = LutWorkspace(apply_callback)
        self.stage = 0
        self.message = ""
        self.busy = False
        self.job_request = None
        self.dialog_request = None
        self.show_json = False
        self.help_requested = False
        self.guide_requested = False
        self.selected_file = ""
        self._preview_key = None
        self._preview = None
        self._observers = []

    # -- observers (SnapshotJob contract) -------------------------------- #
    def add_observer(self, callback):
        """Register *callback*, called with an event name on every change."""
        self._observers.append(callback)

    def notify(self, event="changed"):
        """Tell observers that *event* happened."""
        for callback in list(self._observers):
            callback(event)

    def __copy__(self):
        """A copy a worker thread may mutate: it gets its own workspace containers."""
        new = self.__class__.__new__(self.__class__)
        new.__dict__.update(self.__dict__)
        ws = copy.copy(self.ws)
        compute = copy.copy(self.ws.compute)
        compute.files = list(compute.files)
        compute._loaded_files = list(compute._loaded_files)
        compute.available_channels = list(compute.available_channels)
        compute._observers = []
        ws.compute = compute
        for name in ("files",):
            setattr(ws, name, list(getattr(ws, name)))
        for name in ("channel_luts", "channel_shifts", "loaded_luts", "raw", "corrected"):
            setattr(ws, name, dict(getattr(ws, name)))
        ws.visible = set(ws.visible)
        new.ws = ws
        new._observers = []
        return new

    # -- tab 1 parameters --------------------------------------------------- #
    @property
    def channel(self):
        """The routing channel previewed in tab 1 (a string, as the choice needs)."""
        return self.ws.compute.channel

    @channel.setter
    def channel(self, value):
        self.ws.compute.channel = str(value)

    def channels_options(self):
        """Routing channels found in the loaded file(s)."""
        return self.ws.compute.channels_options()

    # -- stage -------------------------------------------------------------- #
    @property
    def stage_name(self):
        """Name of the shown tab; the choice that replaces the Qt tab bar."""
        return STAGES[self.stage]

    @stage_name.setter
    def stage_name(self, value):
        self.stage = STAGES.index(value)

    @property
    def has_apply(self):
        """True when a detector setup supplied a callback for Apply."""
        return self.ws.apply_callback is not None

    # -- tab 2 fields ------------------------------------------------------- #
    @property
    def reading_name(self):
        """Reading routine as the label the choice shows."""
        for label, value in READING_ROUTINES:
            if value == self.ws.reading_routine:
                return label
        return "Auto"

    @reading_name.setter
    def reading_name(self, label):
        self.ws.reading_routine = dict(READING_ROUTINES)[label]

    @property
    def reading_options(self):
        """Labels of the reading routines."""
        return [label for label, _ in READING_ROUTINES]

    @property
    def shift(self):
        """Photon-level shift of the active channel."""
        return int(self.ws.channel_shifts.get(self.ws.active_channel, 0))

    @shift.setter
    def shift(self, value):
        self.ws.set_shift(int(value))

    @property
    def show_lut(self):
        """Show the cumulative-LUT plots of the active channel."""
        return self.ws.show_lut

    @show_lut.setter
    def show_lut(self, value):
        self.ws.show_lut = bool(value)

    @property
    def log_y(self):
        """Logarithmic count axis of the tab 2 histogram."""
        return self.ws.log_y

    @log_y.setter
    def log_y(self, value):
        self.ws.log_y = bool(value)

    # -- table sources -------------------------------------------------------- #
    @property
    def input_files(self):
        """Files of the shown tab: uniform-illumination files, or preview files."""
        return list(self.ws.compute.files if self.stage == 0 else self.ws.files)

    @property
    def file_rows(self):
        """One record per input file."""
        return [{"name": Path(p).name, "path": p} for p in self.input_files]

    @property
    def lut_rows(self):
        """One record per loaded LUT, with the channels it is assigned to."""
        rows = []
        for name, lut in self.ws.loaded_luts.items():
            channels = sorted(
                ch for ch, value in self.ws.channel_luts.items() if np.array_equal(value, lut)
            )
            rows.append(
                {
                    "name": name,
                    "entries": int(len(lut)),
                    "channels": ", ".join(str(c) for c in channels),
                }
            )
        return rows

    @property
    def channel_rows(self):
        """One record per routing channel of the preview files."""
        rows = []
        for ch in sorted(self.ws.raw):
            rows.append(
                {
                    "channel": ch,
                    "show": ch in self.ws.visible,
                    "photons": int(np.sum(self.ws.raw[ch])),
                    "lut": "yes" if ch in self.ws.channel_luts else "",
                    "shift": int(self.ws.channel_shifts.get(ch, 0)),
                }
            )
        return rows

    def select_file(self, record):
        """Remember the selected file row (the Remove button acts on it)."""
        self.selected_file = record["path"] if record else ""

    def delete_file(self, record):
        """Delete / Backspace on a file row removes it."""
        self.select_file(record)
        if self.selected_file:
            self.remove_file()

    def delete_lut(self, record):
        """Delete / Backspace on a LUT row removes it from the import list."""
        self.select_lut(record)
        self.remove_lut()

    def select_lut(self, record):
        """Select the LUT the Assign buttons use."""
        if record:
            self.ws.selected_lut = record["name"]

    def select_channel(self, record):
        """Make a channel the active one (the shift field and the LUT plots follow it)."""
        if record:
            self.ws.active_channel = int(record["channel"])

    def edit_channel(self, record, key, value):
        """A cell of the channel table was edited: only ``show`` is editable."""
        if key == "show":
            ch = int(record["channel"])
            if value:
                self.ws.visible.add(ch)
            else:
                self.ws.visible.discard(ch)

    # -- status ---------------------------------------------------------------- #
    @property
    def info_text(self):
        """One-line summary of the current LUT (what the Qt label under the plots shows)."""
        return self.ws.compute.info_text()

    flow_hint = FLOW_HINT

    @property
    def status_text(self):
        """The last message, or what to do next."""
        return self.message or (
            "Compute a LUT per routing channel, then Add all channels to setup. "
            "Saving a file is optional."
        )

    def enabled(self, name):
        """Whether the control *name* is usable now (a running job disables all)."""
        if self.busy:
            return False
        compute = self.ws.compute
        rules = {
            "autodetect": compute.counts is not None,
            "save_lut": compute.current_table is not None,
            "export_corrected": compute.current_table is not None,
            "add_all": compute.counts is not None,
            "remove_file": bool(self.selected_file),
            "clear_files": bool(self.input_files),
            "remove_lut": bool(self.ws.selected_lut),
            "clear_luts": bool(self.ws.loaded_luts or self.ws.channel_luts),
            "assign_selected": bool(self.ws.loaded_luts and self.ws.selected_lut)
            and bool(self.ws.raw),
            "assign_all": bool(self.ws.loaded_luts and self.ws.selected_lut) and bool(self.ws.raw),
            "save_json": bool(self.ws.channel_luts),
            "show_json": True,
            "apply_setup": self.has_apply,
            "shift": self.ws.active_channel is not None,
            "channel": bool(compute.available_channels),
        }
        return rules.get(name, True)

    # -- requests the app services ------------------------------------------------ #
    def _job(self, method, *args):
        self.job_request = (method, args)

    def _dialog(self, kind, **options):
        self.dialog_request = {"kind": kind, **options}

    def request_add_files(self):
        """Ask for photon files to add to the shown tab."""
        self._dialog("add_files", mode="open", multiselect=True)

    def request_add_folder(self):
        """Ask for a folder; its photon files are added."""
        self._dialog("add_files", mode="folder")

    def request_database(self):
        """Ask the app to open the MMFDB picker."""
        self._dialog("database")

    def request_save_lut(self):
        """Ask where to save the LUT of the shown channel."""
        self._dialog("save_lut", mode="save")

    def request_export_corrected(self):
        """Ask where to export the corrected micro-times."""
        self._dialog("export_corrected", mode="save")

    def request_load_lut(self):
        """Ask for a LUT file to import."""
        self._dialog("load_lut", mode="open")

    def request_load_json(self):
        """Ask for a settings.tttr.json to load."""
        self._dialog("load_json", mode="open")

    def request_save_json(self):
        """Ask where to save settings.tttr.json."""
        self._dialog("save_json", mode="save")

    def show_help(self):
        """Open the help window."""
        self.help_requested = True

    def start_guide(self):
        """Start the guided tour."""
        self.guide_requested = True

    def toggle_json(self):
        """Show or hide the settings.tttr.json preview."""
        self.show_json = not self.show_json

    def finish_dialog(self, kind, paths):
        """Carry out what a file dialog chose; errors become the status message."""
        paths = [str(p) for p in paths]
        if not paths:
            return
        try:
            if kind == "add_files":
                self.add_files(paths)
            elif kind == "save_lut":
                self.message = f"LUT saved to {self.ws.compute.save_lut(paths[0])}"
            elif kind == "export_corrected":
                self._job("export_corrected_job", paths[0])
            elif kind == "load_lut":
                self.ws.import_lut(paths[0])
                self.message = f"Loaded LUT '{Path(paths[0]).name}'."
            elif kind == "load_json":
                self._job("import_settings_job", paths[0])
            elif kind == "save_json":
                self.message = f"Saved {self.ws.export_settings(paths[0])}"
        except Exception as error:  # noqa: BLE001 - shown to the user
            self.message = str(error)

    # -- actions --------------------------------------------------------------------- #
    def add_files(self, paths):
        """Add photon files (or folders) to the shown tab; reads them as a job."""
        added = self.ws.expand(paths)
        if not added:
            self.message = "No supported TTTR files."
            return
        self._job("load_files_job", self.ws.expand([*self.input_files, *added]))

    def remove_file(self):
        """Remove the selected input file."""
        remaining = [p for p in self.input_files if p != self.selected_file]
        self.selected_file = ""
        self._job("load_files_job", remaining)

    def clear_files(self):
        """Unload the input files of the shown tab; assigned LUTs stay."""
        self.selected_file = ""
        self._job("load_files_job", [])

    def load_files_job(self, paths):
        """Read *paths* into the shown tab (runs on a snapshot)."""
        if self.stage == 0:
            if paths:
                self.ws.load_compute(paths)
                compute = self.ws.compute
                self.message = (
                    f"Loaded {len(paths)} file(s): channel(s) "
                    f"{', '.join(str(c) for c in compute.available_channels)}."
                )
            else:
                self.ws.compute.clear()
                self.message = ""
        else:
            self.ws.load_preview(paths)
            self.message = f"Loaded {len(paths)} preview file(s)." if paths else ""
        self._preview_key = None

    def reading_changed(self, _value=None):
        """The reading routine changed: read the preview files again."""
        if self.ws.files:
            self._job("load_files_job", list(self.ws.files))

    def param_changed(self, _value=None):
        """A tab 1 parameter changed: rebuild the LUT of the shown channel."""
        self.ws.compute.compute()

    def channel_changed(self, _value=None):
        """The preview channel changed: histogram it and seed its region."""
        self.ws.compute._select_channel()

    def autodetect(self):
        """Find the flat plateau of the shown channel's histogram."""
        compute = self.ws.compute
        if compute.counts is None:
            self.message = "Load a uniform-illumination file first."
            return
        try:
            compute.linear_start, compute.linear_stop = _lut.autodetect_linear_region(
                compute.counts
            )
        except Exception as error:  # noqa: BLE001 - the Qt tool swallows this silently
            self.message = f"Auto-detect failed: {error}"
            return
        compute.compute()
        self.message = f"Auto-detected region [{compute.linear_start}, {compute.linear_stop})."

    def add_all(self):
        """Compute a LUT for every routing channel and assign them all."""
        self._job("add_all_job")

    def add_all_job(self):
        """The work of :meth:`add_all` (runs on a snapshot)."""
        luts = self.ws.bridge()
        channels = ", ".join(str(c) for c in sorted(luts))
        tail = "press Apply to detector setup." if self.has_apply else "save settings.tttr.json."
        self.message = f"Added LUTs for channel(s) {channels} to the setup; {tail}"

    def export_corrected_job(self, path):
        """Write the corrected micro-times (runs on a snapshot)."""
        self.message = f"Exported corrected micro-times to {self.ws.compute.export_corrected(path)}"

    def import_settings_job(self, path):
        """Load a settings.tttr.json (runs on a snapshot)."""
        self.ws.import_settings(path)
        self.message = f"Loaded settings from {Path(path).name}."

    def remove_lut(self):
        """Remove the selected LUT from the import list; assignments stay."""
        self.ws.remove_lut()

    def clear_luts(self):
        """Remove every loaded and assigned LUT; shifts stay."""
        self.ws.clear_luts()
        self.message = "Cleared all LUTs."

    def assign_selected(self):
        """Assign the selected LUT to the active channel."""
        self._run(self.ws.assign)

    def assign_all(self):
        """Assign the selected LUT to every channel of the preview."""
        self._run(lambda: self.ws.assign(True))

    def apply_setup(self):
        """Send LUTs and shifts to the detector setup that opened the tool."""
        self._run(self.ws.apply)
        if not self.message:
            self.message = "Applied the correction to the detector setup."

    def _run(self, callback):
        self.message = ""
        try:
            callback()
        except Exception as error:  # noqa: BLE001 - shown to the user
            self.message = str(error)

    # -- plot data ---------------------------------------------------------------------- #
    def raw_plot(self):
        """``(x, y, y_label)`` of the raw TAC plot, as the Qt plot draws it, or ``None``.

        ``y`` is the histogram after the low-count threshold, divided by the region mean
        when *Normalize by region mean* is on.
        """
        compute = self.ws.compute
        counts = compute.counts_effective()
        if counts is None:
            return None
        x = np.arange(compute.n_bins)
        if compute.normalize:
            region = counts[int(compute.linear_start) : int(compute.linear_stop)]
            mean = float(region.mean()) if region.size else 1.0
            return x, counts / (mean if mean > 0 else 1.0), "Counts / ⟨region⟩"
        return x, counts.astype(float), "Counts"

    def corrected_plot(self):
        """``(x, counts)`` of the corrected preview, cached until its inputs change."""
        compute = self.ws.compute
        if compute.current_table is None or compute.micro is None:
            return None
        key = (
            id(compute.current_table),
            id(compute.micro),
            int(compute.seed),
            int(compute.preview_photons),
            bool(compute.mitigate_wrap),
            float(compute.eps),
            int(compute.ntac_required),
        )
        if self._preview is None or self._preview_key != key:
            self._preview = (compute.current_table, compute.micro, compute.corrected_after_hist())
            self._preview_key = key
        return self._preview[2]

    # -- persistence ---------------------------------------------------------------------- #
    def get_state(self):
        """Everything worth remembering (the workspace and the shown tab)."""
        return {"workspace": self.ws.get_state(), "stage": self.stage}

    def set_state(self, state):
        """Restore :meth:`get_state`."""
        self.ws.set_state(state.get("workspace", state))
        self.stage = max(0, min(int(state.get("stage", 0)), len(STAGES) - 1))
        self._preview_key = None


for _name in _PARAMS:
    setattr(LutToolModel, _name, _forward(_name))
