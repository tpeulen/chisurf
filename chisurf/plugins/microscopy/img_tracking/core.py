"""Qt-free orchestration behind the particle-tracking plugin.

Loads an image stack, runs detection → linking → transport analysis from
:mod:`chisurf.core.fluorescence.imaging.tracking`, and packages the result for
the GUI, the CLI and the RPC service alike. Nothing here does maths a headless
caller could not reach directly.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

from chisurf.core.fluorescence.imaging import load_image_stack
from chisurf.core.fluorescence.imaging import tracking as tk

__all__ = [
    "TrackingResult",
    "analyse",
    "load_frames",
    "track_stack",
]


def load_frames(
    filename: str | pathlib.Path,
    channel: int = 0,
    windows: dict | None = None,
    channel_axis=None,
    max_frames: int = 0,
) -> tuple[np.ndarray, dict]:
    """Load one channel of an image stack as a ``(n_frames, ny, nx)`` movie.

    Tracking is a single-channel operation: a particle is followed in the
    channel it is visible in, and combining channels first would blur the spots
    it has to localise. Colocalisation between channels is a separate question,
    answered by the colocalisation tool.

    Parameters
    ----------
    filename : path-like
        TIFF-like image or photon-stream file.
    channel : int
        Channel index to track in.
    windows : dict, optional
        Photon streams only: named detector windows used as channels.
    channel_axis : int or str, optional
        Images only: force which array axis holds the channels.
    max_frames : int
        Track at most this many frames (0 = all). Lower it for a first look at
        a long acquisition.

    Returns
    -------
    frames : numpy.ndarray
        ``(n_frames, ny, nx)`` float movie.
    info : dict
        ``{"filename", "n_frames", "shape", "channel", "channel_names", "kind"}``.

    Raises
    ------
    ValueError
        If *channel* is out of range for the file.
    """
    stack = load_image_stack(filename, windows=windows, channel_axis=channel_axis)
    if not 0 <= int(channel) < stack.n_channels:
        raise ValueError(
            f"channel {channel} does not exist; the file has "
            f"{stack.n_channels} ({', '.join(stack.channel_names)})"
        )
    data = np.asarray(stack.data[:, int(channel)], dtype=float)
    if max_frames and data.shape[0] > int(max_frames):
        data = data[: int(max_frames)]
    info = {
        "filename": str(filename),
        "n_frames": int(data.shape[0]),
        "shape": [int(data.shape[1]), int(data.shape[2])],
        "channel": int(channel),
        "channel_names": list(stack.channel_names),
        "kind": str(stack.kind),
    }
    return data, info


@dataclass
class TrackingResult:
    """Everything one tracking run produced.

    Attributes
    ----------
    detections : tracking.Detections
        Per-frame particle positions.
    tracks : tracking.Tracks
        Linked trajectories.
    fit : tracking.MsdFit or None
        Transport parameters, or ``None`` when no track was long enough.
    info : dict
        Provenance from :func:`load_frames` (or the simulation settings).
    message : str
        Why the transport fit is missing, when it is.
    """

    detections: tk.Detections
    tracks: tk.Tracks
    fit: tk.MsdFit | None = None
    info: dict = field(default_factory=dict)
    message: str = ""

    @property
    def detections_per_frame(self) -> float:
        """Mean number of detections per frame."""
        frames = int(self.info.get("n_frames", 0)) or self.detections.n_frames
        return float(len(self.detections)) / frames if frames else 0.0

    def track_lengths(self) -> np.ndarray:
        """Number of detections in each track."""
        return self.tracks.lengths()

    def report(self) -> str:
        """Return a human-readable summary of the run."""
        lines: list[str] = []
        lines.append(
            f"{self.info.get('n_frames', '?')} frames, "
            f"{len(self.detections):,} detections "
            f"({self.detections_per_frame:.1f} per frame)"
        )
        lengths = self.track_lengths()
        if lengths.size:
            lines.append(
                f"{lengths.size} tracks, median length {int(np.median(lengths))}, "
                f"longest {int(lengths.max())}"
            )
        else:
            lines.append("no tracks")

        if self.fit is None:
            lines.append("")
            lines.append(self.message or "No transport fit.")
            return "\n".join(lines)

        fit = self.fit
        unit = "µm²/s" if self.info.get("calibrated") else "px²/frame"
        lines.append("")
        lines.append(
            f"D = {fit.diffusion_coefficient:.4g} ± "
            f"{fit.diffusion_coefficient_error:.2g} {unit}"
        )
        if fit.alpha_fixed:
            lines.append(f"alpha = {fit.alpha:.3g} (fixed)")
        else:
            lines.append(f"alpha = {fit.alpha:.3g} ± {fit.alpha_error:.2g}")
        length_unit = "µm" if self.info.get("calibrated") else "px"
        lines.append(f"localisation error = {fit.localisation_error:.3g} {length_unit}")
        lines.append(f"from {fit.n_tracks} tracks over {fit.n_points} MSD points")

        notes = fit.warnings()
        if notes:
            lines.append("")
            lines.append("Read with care:")
            lines.extend(f"  - {note}" for note in notes)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Return a JSON-compatible summary of the whole run."""
        lengths = self.track_lengths()
        return {
            "info": dict(self.info),
            "n_detections": int(len(self.detections)),
            "detections_per_frame": self.detections_per_frame,
            "n_tracks": int(lengths.size),
            "track_lengths": lengths.tolist(),
            "fit": None if self.fit is None else self.fit.to_dict(),
            "message": self.message,
            "report": self.report(),
        }

    def tracks_table(self) -> list[dict]:
        """Return one row per track: length, span and net displacement."""
        rows: list[dict] = []
        for identifier in self.tracks.ids():
            frames, positions = self.tracks.track(identifier)
            net = float(np.hypot(*(positions[-1] - positions[0])))
            rows.append(
                {
                    "track": int(identifier),
                    "length": int(frames.size),
                    "first": int(frames[0]),
                    "last": int(frames[-1]),
                    "net": net,
                }
            )
        rows.sort(key=lambda r: -r["length"])
        return rows

    def write_csv(self, path: str) -> str:
        """Write every linked detection to a CSV file.

        Parameters
        ----------
        path : str
            Destination file.

        Returns
        -------
        str
            The path written.
        """
        lines = ["track,frame,y,x,intensity"]
        order = np.lexsort((self.detections.frame, self.tracks.track_id))
        for index in order:
            identifier = int(self.tracks.track_id[index])
            if identifier < 0:
                continue
            lines.append(
                f"{identifier},{int(self.detections.frame[index])},"
                f"{self.detections.y[index]:.4f},{self.detections.x[index]:.4f},"
                f"{self.detections.intensity[index]:.6g}"
            )
        pathlib.Path(path).write_text("\n".join(lines) + "\n")
        return str(path)


def track_stack(
    frames: np.ndarray,
    method: str = "wavelet",
    threshold: float = 5.0,
    min_area: int = 2,
    min_separation: float = 3.0,
    max_distance: float = 5.0,
    max_frame_gap: int = 1,
    progress: Callable[[float, str], None] | None = None,
) -> tuple[tk.Detections, tk.Tracks]:
    """Detect and link particles in a movie.

    Parameters
    ----------
    frames : numpy.ndarray
        ``(n_frames, ny, nx)`` movie.
    method, threshold, min_area, min_separation
        Detection settings; see
        :func:`chisurf.core.fluorescence.imaging.tracking.detect_particles`.
    max_distance, max_frame_gap
        Linking settings; see
        :func:`chisurf.core.fluorescence.imaging.tracking.link_detections`.
    progress : callable, optional
        ``progress(fraction, message)``.

    Returns
    -------
    detections : tracking.Detections
    tracks : tracking.Tracks
    """
    if progress is not None:
        progress(0.05, "detecting particles")
    detections = tk.detect_particles(
        frames, method=method, threshold=float(threshold), min_area=int(min_area),
        min_separation=float(min_separation),
    )
    if progress is not None:
        progress(0.6, f"linking {len(detections):,} detections")
    tracks = tk.link_detections(
        detections, max_distance=float(max_distance), max_frame_gap=int(max_frame_gap)
    )
    return detections, tracks


def analyse(
    frames: np.ndarray,
    pixel_size: float = 1.0,
    frame_interval: float = 1.0,
    method: str = "wavelet",
    threshold: float = 5.0,
    min_area: int = 2,
    min_separation: float = 3.0,
    max_distance: float = 5.0,
    max_frame_gap: int = 1,
    min_track_length: int = 10,
    fix_alpha: float | None = 1.0,
    n_bootstrap: int = 200,
    info: dict | None = None,
    progress: Callable[[float, str], None] | None = None,
) -> TrackingResult:
    """Run the whole pipeline: detect, link, and fit transport.

    Parameters
    ----------
    frames : numpy.ndarray
        ``(n_frames, ny, nx)`` movie.
    pixel_size : float
        Pixel size in µm. Leave at 1 to report in pixels.
    frame_interval : float
        Time between frames in seconds. Leave at 1 to report per frame.
    method, threshold, min_area, min_separation
        Detection settings.
    max_distance, max_frame_gap
        Linking settings.
    min_track_length : int
        Shortest track admitted to the transport fit.
    fix_alpha : float, optional
        Hold the anomalous exponent fixed; ``1.0`` (the default) is ordinary
        diffusion and is usually the right choice, because ``D`` and ``alpha``
        are nearly degenerate. Pass ``None`` to fit it.
    n_bootstrap : int
        Track resamples behind the uncertainties.
    info : dict, optional
        Provenance carried into the result.
    progress : callable, optional
        ``progress(fraction, message)``.

    Returns
    -------
    TrackingResult
        Always returned; when no track is long enough to fit, ``fit`` is
        ``None`` and ``message`` says why rather than raising — detections and
        tracks are still worth looking at, and are usually what shows *why*
        nothing was long enough.
    """
    detections, tracks = track_stack(
        frames, method=method, threshold=threshold, min_area=min_area,
        min_separation=min_separation, max_distance=max_distance,
        max_frame_gap=max_frame_gap, progress=progress,
    )
    payload = dict(info or {})
    payload["calibrated"] = float(pixel_size) != 1.0 or float(frame_interval) != 1.0
    payload.setdefault("n_frames", int(np.asarray(frames).shape[0]))
    result = TrackingResult(detections=detections, tracks=tracks, info=payload)

    if progress is not None:
        progress(0.8, "fitting transport")
    try:
        result.fit = tk.fit_msd(
            tracks, pixel_size=float(pixel_size), frame_interval=float(frame_interval),
            min_length=int(min_track_length), fix_alpha=fix_alpha,
            n_bootstrap=int(n_bootstrap),
        )
    except ValueError as exc:
        result.message = (
            f"{exc}. Longer tracks come from a larger max linking distance, a "
            "lower detection threshold, or gap closing — but check that they are "
            "still the same particle before trusting the D they give."
        )
    if progress is not None:
        progress(1.0, "done")
    return result


def write_container(source, result, *, parameters=None, out_dir=None) -> str:
    """Write a tracking run into the measurement's container.

    Three grains, and the reason a track table could never be a per-pixel HDF5
    column: a *detection* belongs to a frame, a *track* is a set of detections
    across frames, and the transport fit describes all of them. The detections
    carry the track they were linked into as a key, so the two tables join on a
    declared column instead of on the order they happen to be written in.

    Parameters
    ----------
    source : str or pathlib.Path
        The image or photon file, or the container itself.
    result : TrackingResult
        The run to record.
    parameters : dict, optional
        The settings. Their hash is the identity of the run.
    out_dir : str or pathlib.Path, optional

    Returns
    -------
    str
        Path of the container written.
    """
    from chisurf.core.datastore import store_from_arrays, store_from_rows
    from chisurf.core.fio.fluorescence.imaging_container import write_imaging_table

    rows = result.tracks_table()
    written = write_imaging_table(
        source, store_from_rows(rows) if rows else store_from_arrays({}),
        name="tracks",
        artifact_kind="track_table",
        operation_type="particle_tracking",
        row_grain="track",
        parameters=parameters,
        units={"track": "dimensionless", "length": "counts",
               "first": "dimensionless", "last": "dimensionless",
               "net": "pixels"},
        out_dir=out_dir,
    )

    identifiers, frames, xs, ys = [], [], [], []
    for identifier in result.tracks.ids():
        track_frames, positions = result.tracks.track(identifier)
        identifiers.extend([int(identifier)] * int(track_frames.size))
        frames.extend(np.asarray(track_frames, dtype=np.int64).tolist())
        xs.extend(np.asarray(positions[:, 1], dtype=float).tolist())
        ys.extend(np.asarray(positions[:, 0], dtype=float).tolist())
    if identifiers:
        write_imaging_table(
            source,
            store_from_arrays({
                # The key. A detection is finer than a track, so the join is
                # declared rather than counted.
                "Track": np.array(identifiers, dtype=np.int64),
                "Frame": np.array(frames, dtype=np.int64),
                "x": np.array(xs, dtype=float),
                "y": np.array(ys, dtype=float),
            }),
            name="track detections",
            artifact_kind="localization_table",
            operation_type="particle_tracking",
            row_grain="spot",
            parameters=parameters,
            derived_from="tracks",
            source_row_column="track",
            target_row_column="Track",
            units={"Track": "dimensionless", "Frame": "dimensionless",
                   "x": "pixels", "y": "pixels"},
            out_dir=out_dir,
        )
    return written
