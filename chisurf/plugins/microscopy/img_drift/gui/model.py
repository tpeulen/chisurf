"""Qt-free model of the emtk drift-correction window.

The measurement is :class:`~.view_model.DriftViewModel` (unchanged, shared with the Qt tool); this adds the action methods
the spec's buttons call, a status line, the file-dialog requests and the worker hand-off.
"""

from __future__ import annotations

import pathlib

import numpy as np

from ...imaging_emtk.model_base import EmtkModelMixin
from .view_model import DriftViewModel

#: Files the Open dialog lists (the Qt data-source field's filter).
IMAGE_FILE_FILTER = "Images and photon streams (*.pto *.tif *.tiff *.png *.ptu *.ht3 *.spc);;All files (*)"

REFERENCES = ("first", "previous", "mean")
MODES = ("wrap", "constant")


class DriftModel(EmtkModelMixin, DriftViewModel):
    """The drift measurement plus the state of its emtk window."""

    SETTINGS = ("reference", "mode", "smooth", "subpixel", "colormap")

    def __init__(self) -> None:
        DriftViewModel.__init__(self)
        self.status_line = ""
        self._pending_path = ""

    # -- choices --------------------------------------------------------------- #
    def reference_choices(self) -> list[str]:
        return list(REFERENCES)

    def mode_choices(self) -> list[str]:
        return list(MODES)

    def colormap_choices(self) -> list[str]:
        return ["magma", "inferno", "viridis", "gray"]

    def enabled(self, name: str) -> bool:
        """Actions are greyed while a worker runs (its result replaces the model's state)."""
        return not self.busy

    # -- the file --------------------------------------------------------------- #
    def open_file(self) -> None:
        """Choose an image stack or photon-stream file (the Qt Browse button)."""
        self.request_dialog("open")

    def open_database(self) -> None:
        """Pick a dataset registered in the database (the Qt Database button)."""
        self.request_dialog("database")

    def open_path(self, path: str) -> None:
        """Select *path* and measure it, as the Qt tool did when a file was chosen or dropped."""
        if not path:
            return
        self.remember_folder(path)
        self.filename = str(path)
        self._pending_path = str(path)
        self.status_line = "Reading the image..."
        self.run_job("load_and_measure")

    def commit_filename(self, value: str) -> None:
        """A path typed into the field and committed."""
        if str(value) != self._pending_path or self._result is None:
            self.open_path(str(value))

    def load_and_measure(self) -> None:
        """The worker body: read the channel list, then (only when the file is usable) measure, like the Qt ``file`` event."""
        if self.set_filename(self._pending_path):
            self._normalise_channel()
            self.compute_job()
        else:
            self.status_line = self.status

    def _normalise_channel(self) -> None:
        """The channel is an index until the user picks a name: show its name, which measures the same frames."""
        names = self.channel_names
        if isinstance(self.channel, int) and 0 <= self.channel < len(names):
            self.channel = names[self.channel]

    # -- measuring --------------------------------------------------------------- #
    def measure(self) -> None:
        """Measure the drift of the loaded file (the Qt Measure); the Qt tool did nothing without a file, this says so."""
        if not self.filename:
            self.status_line = self.status or "No image loaded."
            return
        self.status_line = "Measuring drift..."
        self.run_job("compute_job")

    def compute_job(self) -> None:
        """The worker body: measure, then say what came out (the model's own status carries the reason of a failure)."""
        ok = bool(self.compute(progress=self._progress))
        self.status_line = self.status
        if ok:
            self.notify("computed")

    # -- exports ------------------------------------------------------------------ #
    def _default_path(self, suffix: str) -> str:
        if not self.filename:
            return ""
        return pathlib.Path(self.filename).with_suffix(suffix).name

    def dialog_filename(self, kind: str) -> str:
        """The name the save dialog proposes: the source's name with ``.corrected.tif`` / ``.drift.csv``."""
        return self._default_path(".corrected.tif" if kind == "export_stack" else ".drift.csv")

    def request_export_stack(self) -> None:
        """Choose where to write the drift-corrected stack."""
        if self.result is None:
            self.status_line = "Measure the drift first."
            return
        self.request_dialog("export_stack")

    def request_export_shifts(self) -> None:
        """Choose where to write the per-frame displacements."""
        if self.result is None:
            self.status_line = "Measure the drift first."
            return
        self.request_dialog("export_shifts")

    def write_stack(self, path: str) -> None:
        """Write the corrected stack (re-reads the source: on the worker)."""
        self._pending_path = str(path)
        self.status_line = "Writing corrected stack..."
        self.run_job("write_stack_job")

    def write_stack_job(self) -> None:
        try:
            written = self.export(stack_path=self._pending_path)
        except Exception as exc:  # the file could not be read again or the target is not writable
            self.status_line = f"Could not write the corrected stack: {exc}"
            return
        self.status_line = f"Wrote {written.get('stack', self._pending_path)}"

    def write_shifts(self, path: str) -> None:
        """Write the shift table."""
        try:
            written = self.export(shifts_path=str(path))
        except OSError as exc:
            self.status_line = f"Could not write {path}: {exc}"
            return
        self.remember_folder(path)
        self.status_line = f"Wrote {written.get('shifts', path)}"

    # -- sources named by the emtk spec ----------------------------------------------- #
    def shift_table_rows(self) -> list[dict]:
        """The shift table with numbers (the Qt table held strings), so a header click sorts by value."""
        if self._result is None:
            return []
        shifts = np.asarray(self._result.shifts, dtype=float)
        return [
            {"frame": int(i), "dx": float(shifts[i, 1]), "dy": float(shifts[i, 0]),
             "magnitude": float(np.hypot(shifts[i, 0], shifts[i, 1]))}
            for i in range(len(shifts))
        ]

    def apply_setup_settings(self, payload: dict) -> None:
        """Drift has no detector setup: accepted and ignored, as the Qt tool did."""

    def apply_pipeline_context(self, payload: dict) -> None:
        """The hub's current source: the Qt drift tool did not adopt it either."""
