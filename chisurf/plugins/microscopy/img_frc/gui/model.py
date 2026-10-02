"""Qt-free model of the emtk FRC window.

The measurement is :class:`~.view_model.FrcViewModel` (unchanged, shared with the Qt tool); this adds the action methods the spec's buttons
call, a status line, the file-dialog requests, the worker hand-off and the imaging hub's adapters running off the draw thread.
"""

from __future__ import annotations

import pathlib

import numpy as np

from ...imaging_emtk.model_base import EmtkModelMixin
from .. import core as _core
from .view_model import FrcViewModel

#: Files the Browse dialogs list (the Qt data-source field's filter).
IMAGE_FILE_FILTER = "Images and photon streams (*.pto *.tif *.tiff *.png *.ptu *.ht3 *.spc);;All files (*)"


class FrcModel(EmtkModelMixin, FrcViewModel):
    """The FRC measurement plus the state of its emtk window."""

    SETTINGS = ("split", "criterion", "pixel_size_nm", "bin_width", "smooth", "axis_order", "colormap")

    def __init__(self, client=None) -> None:
        FrcViewModel.__init__(self, client)
        self.status_line = ""
        self._pending_path = ""

    # -- choices --------------------------------------------------------------- #
    def split_choices(self) -> list[str]:
        return list(_core.SPLITS)

    def criterion_choices(self) -> list[str]:
        return ["fixed_1/7", "half_bit", "two_sigma"]

    def axis_order_choices(self) -> list[str]:
        return list(_core.AXIS_ORDERS)

    def colormap_choices(self) -> list[str]:
        return ["magma", "inferno", "viridis", "gray"]

    def second_channel_options(self) -> list[tuple[str, str]]:
        """The channel names, and first of all "next channel": what the measurement uses while none is chosen.

        The Qt combo offered only the names, so an unset second channel showed the first name while the measurement used the channel after the
        first one.
        """
        return [("", "next channel")] + [(name, name) for name in self.channel_names]

    def enabled(self, name: str) -> bool:
        """Actions are greyed while a worker runs (its result replaces the model's state)."""
        return not self.busy

    # -- the files ---------------------------------------------------------------- #
    def open_file(self) -> None:
        self.request_dialog("open")

    def open_database(self) -> None:
        self.request_dialog("database")

    def open_second_file(self) -> None:
        self.request_dialog("open_second")

    def open_second_database(self) -> None:
        self.request_dialog("database_second")

    def open_path(self, path: str) -> None:
        """Select *path* as the acquisition: read its channels on the worker (choosing a file does not measure, as in the Qt tool)."""
        if not path:
            return
        self.remember_folder(path)
        self.filename = str(path)
        self._pending_path = str(path)
        self.status_line = "Reading the image..."
        self.run_job("load_job")

    def commit_filename(self, value: str) -> None:
        """A path typed into the field and committed."""
        self.open_path(str(value))

    def load_job(self) -> None:
        """The worker body: read the file's channel list."""
        self.set_filename(self._pending_path)
        self._normalise_channel()
        self.status_line = self.status

    def _normalise_channel(self) -> None:
        """The channel is an index until the user picks a name: show its name, which measures the same frames."""
        names = self.channel_names
        if isinstance(self.channel, int) and 0 <= self.channel < len(names):
            self.channel = names[self.channel]

    def open_second_path(self, path: str) -> None:
        """Select the second acquisition of a two-file split."""
        if not path:
            return
        self.remember_folder(path)
        self.set_second_filename(str(path))
        self.status_line = f"Second file: {pathlib.Path(path).name}"

    def commit_second_filename(self, value: str) -> None:
        self.open_second_path(str(value))

    def on_paths_dropped(self, paths) -> bool:
        """Files dropped on the window. Qt routed a drop to the field under the pointer; a drop here carries no position, so: with the two-file
        split and a first file already chosen the file is the second one, otherwise the first; two files fill both."""
        paths = [str(p) for p in paths if p]
        if not paths:
            return False
        if self.split == "two_files" and (self.filename or len(paths) > 1):
            if not self.filename:
                self.open_second_path(paths[1])  # before the worker starts: it hands its snapshot back over the model
                self.open_path(paths[0])
            else:
                self.open_second_path(paths[0])
            return True
        self.open_path(paths[0])
        return True

    # -- measuring --------------------------------------------------------------- #
    def measure(self) -> None:
        """Correlate the two halves and read the resolution off the crossing (the Qt Measure)."""
        if not self.filename:
            self.status_line = self.status or "No image loaded."
            return
        self.status_line = "Measuring..."
        self.run_job("compute_job")

    def compute_job(self) -> None:
        """The worker body: measure; the status line carries the model's own message (the Qt bar said only "Measurement failed")."""
        ok = bool(self.compute(progress=self._progress))
        self.status_line = self.status
        if ok:
            self.notify("computed")

    # -- export -------------------------------------------------------------------- #
    def request_export(self) -> None:
        """Choose where to write the curve (the Qt Export CSV)."""
        if self.result is None:
            self.status_line = "Nothing to export yet"
            return
        self.request_dialog("export")

    def dialog_filename(self, kind: str) -> str:
        return "frc_resolution.csv"

    def write_export(self, path: str) -> None:
        try:
            written = self.export_csv(str(path))
        except OSError as exc:
            self.status_line = f"Could not write {path}: {exc}"
            return
        self.remember_folder(path)
        self.status_line = f"Wrote {written}"

    # -- sources named by the emtk spec ---------------------------------------------- #
    def ring_table_rows(self) -> list[dict]:
        """The ring table with numbers (the Qt table held strings), so a header click sorts by value."""
        result = self._result
        if result is None:
            return []
        rows = []
        for i, frequency in enumerate(np.asarray(result.frequency, dtype=float)):
            rows.append({"frequency": float(frequency), "period": float(1.0 / frequency) if frequency else float("inf"),
                         "correlation": float(result.correlation[i]), "threshold": float(result.threshold[i]),
                         "pixels": int(result.counts[i])})
        return rows

    @property
    def summary_text(self) -> str:
        return self.summary_html()

    # -- the imaging hub's adapters (the reads run on the worker) ----------------------- #
    def apply_setup_settings(self, payload: dict) -> None:
        """Adopt the shared detector definition; a loaded photon stream is read again with the named windows."""
        try:
            from chisurf.core.fluorescence.imaging import windows_from_payload

            windows = windows_from_payload(payload)
        except Exception:
            return
        if windows:
            self.detectors = windows
            if self.filename:
                self._pending_path = self.filename
                self.run_job("load_job")

    def apply_pipeline_context(self, payload: dict) -> None:
        """Adopt the hub's current source, so the panel opens on it."""
        source = (payload or {}).get("source")
        if (payload or {}).get("hdf5"):
            self.pipeline_hdf5 = str((payload or {})["hdf5"])
        if source and str(source) != self.filename:
            self.open_path(str(source))
