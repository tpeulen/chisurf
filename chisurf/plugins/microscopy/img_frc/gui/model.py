"""Qt-free model of the emtk FRC window.

The measurement is :class:`~.view_model.FrcViewModel` ; this adds the action methods the spec's buttons
call, a status line, the file-dialog requests, the worker hand-off and the imaging hub's adapters running off the draw thread.
"""

from __future__ import annotations

import pathlib

import numpy as np

from chisurf.core.fluorescence.excitation import WindowsPreflightMixin

from ...imaging_emtk.model_base import EmtkModelMixin
from .. import core as _core
from .view_model import FrcViewModel

#: Files the Browse dialogs list.
IMAGE_FILE_FILTER = (
    "Images and photon streams (*.pto *.tif *.tiff *.png *.ptu *.ht3 *.spc);;All files (*)"
)


class FrcModel(WindowsPreflightMixin, EmtkModelMixin, FrcViewModel):
    """The FRC measurement plus the state of its emtk window."""

    SETTINGS = (
        "split",
        "criterion",
        "pixel_size_nm",
        "bin_width",
        "smooth",
        "axis_order",
        "colormap",
    )

    def __init__(self, client=None) -> None:
        FrcViewModel.__init__(self, client)
        self.status_line = ""
        self._pending_path = ""
        #: The Setup's PIE windows, checked with the detector gates.
        self.setup_windows: dict = {}
        self.windows_check = None

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

        Without that entry an unset second channel would show the first name while the measurement uses the channel after the first one.
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
        """Select *path* as the acquisition: read its channels on the worker (choosing a file does not measure)."""
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
        self._check_windows()
        self.status_line += self._windows_status()

    # -- the excitation-window pre-flight ------------------------------------------------------- #
    def _check_windows(self) -> str | None:
        """Check the detector gates against the photon stream just read; the warning, or None."""
        from chisurf.core.fluorescence.imaging.image_source import is_photon_stream

        gated = any((d or {}).get("micro_time_ranges") for d in (self.detectors or {}).values())
        if not (gated and self.filename and is_photon_stream(self.filename)):
            self.windows_check = None
            return None
        return self.run_windows_preflight(self.filename)

    def _windows_status(self) -> str:
        """The pre-flight's headline for the status line (the info line below says the whole of it)."""
        text = self.windows_check_text()
        return f" -- {text.split(':')[0]} (see below)" if text else ""

    def preflight_setup(self) -> dict:
        """The gates the stream is binned through (in the data's channels) and the Setup's windows."""
        return {"windows": dict(self.setup_windows or {}), "detectors": dict(self.detectors or {})}

    def take_preflight_setup(self, setup: dict) -> None:
        """Bin through the detected gates from now on and read the file again (the Setup is unchanged)."""
        self.detectors = {k: dict(v) for k, v in (setup.get("detectors") or {}).items()}
        self.setup_windows = dict(setup.get("windows") or {})
        if self.filename:
            self._pending_path = self.filename
            self.status_line = "Reading the image with the detected windows..."
            self.run_job("load_job")

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

    # -- measuring --------------------------------------------------------------- #
    def measure(self) -> None:
        """Correlate the two halves and read the resolution off the crossing."""
        if not self.filename:
            self.status_line = self.status or "No image loaded."
            return
        self.status_line = "Measuring..."
        self.run_job("compute_job")

    def compute_job(self) -> None:
        """The worker body: measure; the status line carries the model's own message, not a bare "Measurement failed"."""
        ok = bool(self.compute(progress=self._progress))
        self.status_line = self.status
        if ok:
            self.status_line += self._windows_status()
        if ok:
            self.notify("computed")

    # -- export -------------------------------------------------------------------- #
    def request_export(self) -> None:
        """Choose where to write the curve."""
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
        """The ring table with numbers, so a header click sorts by value."""
        result = self._result
        if result is None:
            return []
        rows = []
        for i, frequency in enumerate(np.asarray(result.frequency, dtype=float)):
            rows.append(
                {
                    "frequency": float(frequency),
                    "period": float(1.0 / frequency) if frequency else float("inf"),
                    "correlation": float(result.correlation[i]),
                    "threshold": float(result.threshold[i]),
                    "pixels": int(result.counts[i]),
                }
            )
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
            self.setup_windows = dict((payload or {}).get("windows") or {})
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
