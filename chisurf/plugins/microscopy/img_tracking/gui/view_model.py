"""Qt-free view-model behind the particle-tracking tool.

Holds the settings the AutoForm binds to, runs the Qt-free pipeline from
:mod:`chisurf.plugins.microscopy.img_tracking.core`, and exposes the tables,
plot series and image overlays that ``tracking.view.json`` reads.

Every source named in the view spec is a **method**, never a property:
AutoForm's plot and info widgets skip a source they do not find callable and
render an empty panel with no error anywhere.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Callable

import numpy as np

from chisurf.core.fluorescence.imaging import tracking as tk

from .. import core as _core

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "tracking.view.json"

#: Colours cycled over tracks in the overlay and the trajectory plot.
_TRACK_COLOURS = [
    "#4c9be8",
    "#e8734c",
    "#4ce88a",
    "#c04ce8",
    "#e8d24c",
    "#4ce8e0",
    "#e84c9b",
    "#9be84c",
    "#e8a04c",
    "#7c4ce8",
]


class ImgTrackingViewModel:
    """State and logic of the particle-tracking tool (no Qt)."""

    def __init__(self) -> None:
        #: The authored view spec (also the anchor for view-relative resources).
        self._view_json = _VIEW_JSON

        # ── data source ──
        self.filename: str = ""
        self.channel: int = 0
        self.max_frames: int = 0

        # ── simulation, so the tool is usable and testable with no files ──
        self.use_simulation: bool = False
        self.sim_n_frames: int = 60
        self.sim_size: int = 256
        self.sim_n_particles: int = 8
        self.sim_diffusion: float = 0.5
        self.sim_amplitude: float = 250.0
        self.sim_background: float = 10.0
        self.sim_seed: int = 1

        # ── calibration ──
        self.pixel_size: float = 1.0
        self.frame_interval: float = 1.0

        # ── detection ──
        self.method: str = "wavelet"
        self.threshold: float = 5.0
        self.min_area: int = 2
        self.min_separation: float = 3.0

        # ── linking ──
        self.max_distance: float = 5.0
        self.max_frame_gap: int = 1

        # ── transport ──
        self.min_track_length: int = 10
        self.fit_alpha: bool = False
        self.n_bootstrap: int = 200

        # ── display ──
        self.display_frame: int = 0
        self.max_drawn_tracks: int = 60

        # ── runtime ──
        self._frames: np.ndarray | None = None
        self._result: _core.TrackingResult | None = None
        self.results_text: str = (
            "Drop an image stack (or tick Simulate) and press Track.\n\n"
            "Particles are found in every frame, linked into trajectories, and "
            "the trajectories are turned into a diffusion coefficient."
        )
        self._observers: list[Callable[[str], None]] = []

    # ── observer hook ──
    def add_observer(self, cb: Callable[[str], None]) -> None:
        """Register *cb* to be called with an event name on every change."""
        self._observers.append(cb)

    def notify(self, event: str = "changed") -> None:
        """Notify observers that the state changed."""
        for cb in list(self._observers):
            try:
                cb(event)
            except Exception:
                logger.debug("tracking observer failed", exc_info=True)

    def view_spec(self):
        """Resolve the AutoForm view spec from the authored view.json."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    # ── choices ──
    def method_options(self) -> list[str]:
        """Detection methods offered in the form."""
        return ["wavelet", "quantile"]

    # ── state ──
    @property
    def result(self) -> _core.TrackingResult | None:
        """The most recent tracking run, if any."""
        return self._result

    def can_run(self) -> str:
        """Return why a run is not possible, or an empty string when it is."""
        if self.use_simulation:
            return ""
        if not self.filename:
            return "Load an image stack, or tick Simulate."
        if not pathlib.Path(self.filename).exists():
            return f"{pathlib.Path(self.filename).name} does not exist."
        return ""

    def set_filename(self, path: str) -> None:
        """Set the source file and forget any previous run."""
        path = str(path or "")
        if not path:
            return
        self.filename = path
        self._frames = None
        self._result = None
        self.results_text = f"Loaded {pathlib.Path(path).name}. Press Track."
        self.notify("changed")

    # ── run ──
    def compute(self, progress: Callable[[float, str], None] | None = None) -> bool:
        """Load (or simulate), detect, link and fit; returns whether it worked."""
        try:
            if self.use_simulation:
                self._frames, _ = tk.simulate_particle_movie(
                    n_frames=int(self.sim_n_frames),
                    shape=(int(self.sim_size), int(self.sim_size)),
                    n_particles=int(self.sim_n_particles),
                    diffusion_coefficient=float(self.sim_diffusion),
                    amplitude=float(self.sim_amplitude),
                    background=float(self.sim_background),
                    seed=int(self.sim_seed),
                )
                info = {
                    "source": "simulation",
                    "n_frames": int(self.sim_n_frames),
                    "true_diffusion": float(self.sim_diffusion),
                    "n_particles": int(self.sim_n_particles),
                }
            else:
                self._frames, info = _core.load_frames(
                    self.filename,
                    channel=int(self.channel),
                    max_frames=int(self.max_frames),
                )
        except Exception as exc:
            logger.debug("loading frames failed", exc_info=True)
            self._frames = None
            self._result = None
            self.results_text = f"Could not load the images: {exc}"
            self.notify("computed")
            return False

        try:
            self._result = _core.analyse(
                self._frames,
                pixel_size=float(self.pixel_size),
                frame_interval=float(self.frame_interval),
                method=str(self.method),
                threshold=float(self.threshold),
                min_area=int(self.min_area),
                min_separation=float(self.min_separation),
                max_distance=float(self.max_distance),
                max_frame_gap=int(self.max_frame_gap),
                min_track_length=int(self.min_track_length),
                fix_alpha=None if self.fit_alpha else 1.0,
                n_bootstrap=int(self.n_bootstrap),
                info=info,
                progress=progress,
            )
        except Exception as exc:
            logger.debug("tracking failed", exc_info=True)
            self._result = None
            self.results_text = f"Tracking failed: {exc}"
            self.notify("computed")
            return False

        self.results_text = self._result.report()
        self.display_frame = min(int(self.display_frame), max(int(self._frames.shape[0]) - 1, 0))
        self.notify("computed")
        return True

    # ── view sources ──
    def results_html(self) -> str:
        """Return the report as pre-formatted HTML for the ``info`` section."""
        import html

        return f"<pre style='margin:0'>{html.escape(self.results_text)}</pre>"

    def movie_image(self):
        """Return the loaded movie, for the image dock's frame slider."""
        return self._frames

    def detection_markers(self) -> list[tuple[int, float, float]]:
        """Return every detection as ``(frame, y, x)``.

        The image dock draws only the markers whose ``z`` matches the slice on
        screen, so handing it the whole set is what makes scrubbing the frame
        slider show the detections move with the particles — which is the one
        view that tells you at a glance whether the detector is working.
        """
        if self._result is None:
            return []
        found = self._result.detections
        return [(int(f), float(y), float(x)) for f, y, x in zip(found.frame, found.y, found.x)]

    def track_series(self) -> list[dict]:
        """Plot series drawing each trajectory in image coordinates."""
        if self._result is None:
            return []
        series: list[dict] = []
        # Longest first: those are the tracks that carry the transport fit, and
        # the ones worth seeing when the cap bites.
        rows = self._result.tracks_table()[: max(int(self.max_drawn_tracks), 1)]
        for position, row in enumerate(rows):
            _, points = self._result.tracks.track(row["track"])
            series.append(
                {
                    "x": points[:, 1].tolist(),
                    "y": points[:, 0].tolist(),
                    "name": f"track {row['track']}",
                    "color": _TRACK_COLOURS[position % len(_TRACK_COLOURS)],
                    "width": 1,
                }
            )
        return series

    def msd_series(self) -> list[dict]:
        """Plot series of the ensemble MSD and the fitted model."""
        if self._result is None or self._result.fit is None:
            return []
        fit = self._result.fit
        lags = np.asarray(fit.lags, dtype=float) * float(self.frame_interval)
        if lags.size == 0:
            return []
        model = 4.0 * fit.diffusion_coefficient * np.power(lags, fit.alpha)
        model = model + 4.0 * fit.localisation_error**2
        return [
            {
                "x": lags.tolist(),
                "y": np.asarray(fit.msd, dtype=float).tolist(),
                "name": "measured",
                "color": "#4c9be8",
                "width": 0,
                "symbol": "o",
                "symbol_size": 7,
                "no_line": True,
            },
            {
                "x": lags.tolist(),
                "y": model.tolist(),
                "name": "fit",
                "color": "#e8734c",
                "width": 2,
            },
        ]

    def length_series(self) -> list[dict]:
        """Histogram of track lengths, as a step plot."""
        if self._result is None:
            return []
        lengths = self._result.track_lengths()
        if lengths.size == 0:
            return []
        counts, edges = np.histogram(lengths, bins=min(30, max(int(lengths.max()), 2)))
        centres = 0.5 * (edges[:-1] + edges[1:])
        return [
            {
                "x": centres.tolist(),
                "y": counts.tolist(),
                "name": "tracks",
                "color": "#4ce88a",
                "width": 2,
            }
        ]

    def track_rows(self) -> list[dict]:
        """Rows of the per-track table."""
        if self._result is None:
            return []
        rows = self._result.tracks_table()[:500]
        return [
            {
                "track": str(row["track"]),
                "length": str(row["length"]),
                "frames": f"{row['first']}–{row['last']}",
                "net": f"{row['net']:.2f}",
            }
            for row in rows
        ]

    def export_csv(self, path: str) -> None:
        """Write every linked detection to a CSV file.

        Parameters
        ----------
        path : str
            Destination file.
        """
        if self._result is None:
            raise ValueError("run the tracker before exporting")
        self._result.write_csv(path)


__all__ = ["ImgTrackingViewModel"]
