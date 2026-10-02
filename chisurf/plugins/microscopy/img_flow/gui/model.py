"""Qt-free model of the emtk flow-map window.

The measurement is :class:`~.view_model.FlowViewModel` (unchanged, shared with the Qt tool); this adds the action methods the spec's buttons call, a
status line, the file-dialog requests, the worker hand-off (the demo scan and the map run off the draw thread) and the imaging hub's adapters.
"""

from __future__ import annotations

import pathlib

import numpy as np

from ...imaging_emtk.model_base import EmtkModelMixin
from .. import core as _core
from .view_model import FlowViewModel

#: Files the Browse dialog lists (the Qt data-source field's filter).
IMAGE_FILE_FILTER = "Images and photon streams (*.pto *.tif *.tiff *.png *.ptu *.ht3 *.spc);;All files (*)"


class FlowModel(EmtkModelMixin, FlowViewModel):
    """The flow-map measurement plus the state of its emtk window."""

    SETTINGS = ("method", "tile", "step", "n_lags", "distance", "subtract_average", "min_quality", "arrow_scale", "pixel_duration_us",
                "line_duration_ms", "frame_duration_ms", "pixel_size_nm")

    def __init__(self, client=None) -> None:
        FlowViewModel.__init__(self, client)
        self.status_line = ""
        self._pending_path = ""

    # -- choices --------------------------------------------------------------- #
    def method_choices(self) -> list[str]:
        return list(_core.METHODS)

    def subtract_choices(self) -> list[str]:
        return ["frame", "stack"]

    def enabled(self, name: str) -> bool:
        """Actions are greyed while a worker runs (its result replaces the model's state)."""
        return not self.busy

    # -- the file ----------------------------------------------------------------- #
    def open_file(self) -> None:
        self.request_dialog("open")

    def open_database(self) -> None:
        self.request_dialog("database")

    def open_path(self, path: str) -> None:
        """Select *path* and read its channels on the worker (choosing a file does not map it, as in the Qt tool)."""
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
        """The channel is an index until the user picks a name: show its name, which maps the same frames."""
        names = self.channel_names()
        if isinstance(self.channel, int) and 0 <= self.channel < len(names):
            self.channel = names[self.channel]

    # -- the demo ------------------------------------------------------------------ #
    def demo(self) -> None:
        """Simulate (or reuse) the demo photon stream and select it (the Qt Load demo): a scan with a known flow, about twenty seconds the first time."""
        self.status_line = "Simulating the demo scan..."
        self.run_job("demo_job")

    def demo_job(self) -> None:
        """The worker body: the model's own ``load_demo`` with a progress line."""
        try:
            self.load_demo(progress=self._progress)
        except Exception as exc:  # the simulator is missing from this tttrlib build, or the settings folder is not writable
            self.status_line = f"Could not make the demo: {exc}"
            return
        self._normalise_channel()
        self.status_line = self.status
        self.notify("demo")

    # -- mapping ------------------------------------------------------------------- #
    def map_flow(self) -> None:
        """Track each tile's correlation peak and read its velocity (the Qt Map flow)."""
        if not self.filename:
            self.status_line = "Load an image first."
            return
        self.status_line = "Mapping..."
        self.run_job("compute_job")

    def compute_job(self) -> None:
        """The worker body: map, then say what came out (the model's status)."""
        ok = bool(self.compute(progress=self._progress))
        self.status_line = self.status
        if ok:
            self.notify("computed")

    # -- export -------------------------------------------------------------------- #
    def request_export(self) -> None:
        """Choose where to write the velocity field (the Qt Export CSV)."""
        if self.result is None:
            self.status_line = "Nothing to export yet"
            return
        self.request_dialog("export")

    def dialog_filename(self, kind: str) -> str:
        return "flow_map.csv"

    def write_export(self, path: str) -> None:
        try:
            written = self.export_csv(str(path))
        except OSError as exc:
            self.status_line = f"Could not write {path}: {exc}"
            return
        self.remember_folder(path)
        self.status_line = f"Wrote {written}"

    # -- sources named by the emtk spec ---------------------------------------------- #
    def tile_table_rows(self) -> list[dict]:
        """The tile table with numbers (the Qt table held strings), so a header click sorts by value."""
        if self._result is None:
            return []
        rows = []
        for row in _core.to_rows(self._result, 0.0):
            rows.append({k: (float(v) if isinstance(v, (float, np.floating)) else v) for k, v in row.items()})
        return rows

    @property
    def summary_text(self) -> str:
        return self.summary_html()

    # -- the imaging hub's adapters (the read runs on the worker) ------------------------- #
    def apply_pipeline_context(self, payload: dict) -> None:
        """Adopt the toolbox pipeline's current source file, as the Qt tool did."""
        if not isinstance(payload, dict):
            return
        self.pipeline_hdf5 = str(payload.get("hdf5") or self.pipeline_hdf5)
        source = str(payload.get("source") or "")
        if source and source != self.filename:
            self.open_path(source)
