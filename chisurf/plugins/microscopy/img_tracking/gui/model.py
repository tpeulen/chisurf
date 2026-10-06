"""Qt-free model of the emtk particle-tracking window.

The analysis is :class:`~.view_model.ImgTrackingViewModel` (unchanged, shared with the Qt tool); this adds
what a window without a toolbar and a status bar needs: the action methods the spec's buttons call, a status
line, the file-dialog requests and a worker hand-off.
"""

from __future__ import annotations

import pathlib

from ...imaging_emtk.model_base import EmtkModelMixin
from .view_model import ImgTrackingViewModel

#: Files the Open dialog lists (the Qt dialog's filter).
IMAGE_FILE_FILTER = (
    "Images and photon streams (*.pto *.tif *.tiff *.ptu *.ht3 *.spc *.hdf *.h5);;All files (*)"
)


class TrackingModel(EmtkModelMixin, ImgTrackingViewModel):
    """The tracking analysis plus the state of its emtk window."""

    SETTINGS = (
        "channel",
        "max_frames",
        "use_simulation",
        "sim_n_frames",
        "sim_size",
        "sim_n_particles",
        "sim_diffusion",
        "sim_amplitude",
        "sim_background",
        "sim_seed",
        "pixel_size",
        "frame_interval",
        "method",
        "threshold",
        "min_area",
        "min_separation",
        "max_distance",
        "max_frame_gap",
        "min_track_length",
        "fit_alpha",
        "n_bootstrap",
        "max_drawn_tracks",
    )

    def __init__(self) -> None:
        ImgTrackingViewModel.__init__(self)
        self.status_line = ""

    # -- the buttons --------------------------------------------------------- #
    def enabled(self, name: str) -> bool:
        """Actions are greyed while a run is in flight (the Qt actions stayed live and queued a second run)."""
        return not self.busy

    def track(self) -> None:
        """Detect, link and fit (the Qt toolbar's Track): say why when it cannot run."""
        reason = self.can_run()
        if reason:
            self.status_line = reason
            return
        self.status_line = "Tracking..."
        self.run_job("compute_job")

    def compute_job(self) -> None:
        """The worker body: run, then say what came out (the Qt ``_on_finished`` messages)."""
        ok = bool(self.compute(progress=self._progress))
        result = self.result
        if ok and result is not None:
            if result.fit is not None:
                self.status_line = (
                    f"{len(result.tracks)} tracks, D = {result.fit.diffusion_coefficient:.4g} "
                    f"± {result.fit.diffusion_coefficient_error:.2g}"
                )
            else:
                self.status_line = (
                    f"{len(result.tracks)} tracks — no transport fit; see the report."
                )
        else:
            self.status_line = "Tracking did not produce a result — see the report."

    def open_file(self) -> None:
        """Choose an image stack or photon-stream file (the Qt Open)."""
        self.request_dialog("open")

    def open_path(self, path: str) -> None:
        """Select *path* as the movie (a dialog, a drop or a typed path); it is read when Track runs."""
        if not path:
            return
        self.remember_folder(path)
        self.set_filename(path)
        self.status_line = f"Loaded {pathlib.Path(path).name}. Press Track."

    def commit_filename(self, value: str) -> None:
        """A path typed into the field and committed."""
        self.open_path(str(value))

    def request_export(self) -> None:
        """Choose where to write the linked detections (the Qt Export CSV)."""
        if self.result is None:
            self.status_line = "Run the tracker first."
            return
        self.request_dialog("export")

    def dialog_filename(self, kind: str) -> str:
        """The name the save dialog proposes: the movie's name with ``.tracks.csv``."""
        if self.filename:
            return pathlib.Path(self.filename).with_suffix(".tracks.csv").name
        return ""

    def write_export(self, path: str) -> None:
        """Write the linked detections; a failure is reported on the status line."""
        try:
            self.export_csv(path)
        except (OSError, ValueError) as exc:
            self.status_line = f"Could not write {path}: {exc}"
            return
        self.remember_folder(path)
        self.status_line = f"Wrote {path}"

    # -- sources named by the emtk spec -------------------------------------- #
    def method_choices(self) -> list[str]:
        return self.method_options()

    @property
    def report_text(self) -> str:
        """The report, as plain text for the ``info`` section."""
        return self.results_text

    def track_table_rows(self) -> list[dict]:
        """The per-track table with numbers, so a header click sorts by value (the Qt table held strings)."""
        if self.result is None:
            return []
        return [
            {
                "track": int(r["track"]),
                "length": int(r["length"]),
                "frames": f"{r['first']}–{r['last']}",
                "net": float(r["net"]),
            }
            for r in self.result.tracks_table()[:500]
        ]

    # -- the imaging hub's adapters ------------------------------------------- #
    def apply_setup_settings(self, payload: dict) -> None:
        """Tracking has no detector setup: accepted and ignored, as the Qt tool did."""

    def apply_pipeline_context(self, payload: dict) -> None:
        """The hub's current source: the Qt tracking tool did not adopt it either."""
