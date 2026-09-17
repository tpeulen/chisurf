"""Qt-free compute for the flow-map tool: a velocity field from an image stack.

Reads a TIFF stack or a photon stream through the shared image-source seam and
turns it into a **map of velocity vectors** — the arrows a flow measurement is
actually for. There is no model and no fit here: the velocity is read off where
a correlation peak *is*, not off a parameter released in a transport model.

Two estimators, kept side by side because they fail differently:

* ``stics`` — tile the field, correlate each tile over frame lags, and track how
  far its correlation peak travels. Two-dimensional, direct, and blind to a flow
  too slow to shift the peak inside the tile.
* ``pcf`` — for each position, correlate it with the point ±δ away and see which
  direction produces a transit-time peak. One-dimensional along the fast scan
  axis, but resolved per pixel, and the only one that can say *no transport*
  rather than *slow transport* — which is what a barrier looks like.

The GUI, the CLI, the RPC services and the tests all call the functions here.
"""

from __future__ import annotations

import dataclasses
import pathlib
from typing import Any

import numpy as np

from chisurf.core.experiments.ics import IcsTiming, pcf_flow_map, stics_flow_map
from chisurf.core.fluorescence.imaging import load_image_stack

#: The two estimators, in the order they appear in the UI.
METHODS = ("stics", "pcf")

#: Default frame lags for the STICS estimator.
DEFAULT_LAGS = 5


@dataclasses.dataclass
class FlowAnalysis:
    """One velocity field, with everything a caller might display or save.

    Attributes
    ----------
    x, y : numpy.ndarray
        Tile centres in µm, shape ``(n_rows, n_columns)``.
    vx, vy : numpy.ndarray
        Velocity components in µm/s, same shape. ``NaN`` marks a tile that was
        refused — most often because its correlation peak left the tile.
    quality : numpy.ndarray
        Goodness of the straight-line fit the velocity came from, ``[0, 1]``.
    amplitude : numpy.ndarray
        Zero-lag correlation amplitude per tile.
    image : numpy.ndarray
        The time-averaged image the arrows belong on, shape ``(ny, nx)``.
    method : str
        Which estimator produced the field.
    timing : IcsTiming
        The scanner timing used; the frame time and pixel size are what turn a
        peak displacement into a velocity.
    n_escaped : int
        Tiles refused because the peak travelled past the tile edge. Not a
        warning to ignore: a wrapped peak fits a clean line through a
        sign-flipped displacement, so it produces a confident backwards arrow.
    meta : dict
        Free-form provenance (source file, settings, channel).
    """

    x: np.ndarray
    y: np.ndarray
    vx: np.ndarray
    vy: np.ndarray
    quality: np.ndarray
    amplitude: np.ndarray
    image: np.ndarray
    method: str = "stics"
    timing: IcsTiming = dataclasses.field(default_factory=IcsTiming)
    n_escaped: int = 0
    meta: dict[str, Any] = dataclasses.field(default_factory=dict)

    @property
    def speed(self) -> np.ndarray:
        """Speed of every tile in µm/s."""
        return np.hypot(self.vx, self.vy)

    def kept(self, min_quality: float = 0.5) -> np.ndarray:
        """Return the boolean mask of tiles worth drawing.

        Parameters
        ----------
        min_quality : float
            Threshold on the straight-line fit.

        Returns
        -------
        numpy.ndarray
            Mask of shape ``(n_rows, n_columns)``.
        """
        mask = np.isfinite(self.vx) & np.isfinite(self.vy)
        return mask & (self.quality >= float(min_quality))

    def arrows(self, min_quality: float = 0.5):
        """Return ``(x, y, vx, vy)`` for the tiles that pass *min_quality*."""
        mask = self.kept(min_quality)
        return (
            self.x[mask].ravel(),
            self.y[mask].ravel(),
            self.vx[mask].ravel(),
            self.vy[mask].ravel(),
        )

    def summary(self, min_quality: float = 0.5) -> dict[str, float]:
        """Return the headline numbers over the tiles that pass *min_quality*.

        Returns
        -------
        dict
            ``n_tiles``, ``n_kept``, ``n_escaped``, ``mean_speed`` (µm/s),
            ``mean_vx``, ``mean_vy``, ``max_speed``, ``angle_deg`` and
            ``coherence`` — the length of the mean unit vector, 1 for a field
            that points one way everywhere and 0 for arrows at random. A low
            coherence with a high mean speed is a *structured* flow, not a
            failed one; both together being low means there is no flow.
        """
        _, _, vx, vy = self.arrows(min_quality)
        out = {
            "n_tiles": float(self.vx.size),
            "n_kept": float(vx.size),
            "n_escaped": float(self.n_escaped),
        }
        if vx.size == 0:
            out.update(
                mean_speed=float("nan"),
                mean_vx=float("nan"),
                mean_vy=float("nan"),
                max_speed=float("nan"),
                angle_deg=float("nan"),
                coherence=float("nan"),
            )
            return out
        speed = np.hypot(vx, vy)
        safe = np.where(speed > 0, speed, 1.0)
        out.update(
            mean_speed=float(speed.mean()),
            mean_vx=float(vx.mean()),
            mean_vy=float(vy.mean()),
            max_speed=float(speed.max()),
            angle_deg=float(np.degrees(np.arctan2(vy.mean(), vx.mean()))),
            coherence=float(np.hypot((vx / safe).mean(), (vy / safe).mean())),
        )
        return out


def scan_timing(
    n_lines: int,
    *,
    pixel_duration_us: float = 20.0,
    line_duration_ms: float = 0.0,
    frame_duration_ms: float = 0.0,
    pixel_size_nm: float = 100.0,
) -> IcsTiming:
    """Build a timing, filling in whatever the caller left at zero.

    The line time defaults to ``n_lines * pixel_dwell`` and the frame time to
    ``n_lines * line_time``, which is exact for a scanner without dead time
    between lines or frames.

    Parameters
    ----------
    n_lines : int
        Lines per frame; also taken as pixels per line for the default line
        time, which is right for a square scan.
    pixel_duration_us : float
        Pixel dwell in microseconds.
    line_duration_ms : float
        Line time in milliseconds; ``0`` derives it.
    frame_duration_ms : float
        Frame time in milliseconds; ``0`` derives it.
    pixel_size_nm : float
        Pixel size in nanometres.

    Returns
    -------
    IcsTiming
        A timing with a usable frame time and pixel size.

    Raises
    ------
    ValueError
        If the pixel dwell or the pixel size is not positive — without both, a
        peak displacement is not a velocity.
    """
    if pixel_duration_us <= 0.0:
        raise ValueError("the pixel dwell must be positive")
    if pixel_size_nm <= 0.0:
        raise ValueError("the pixel size must be positive; without it there is no µm/s")
    line_ms = float(line_duration_ms)
    if line_ms <= 0.0:
        line_ms = int(n_lines) * float(pixel_duration_us) * 1e-3
    frame_ms = float(frame_duration_ms)
    if frame_ms <= 0.0:
        frame_ms = int(n_lines) * line_ms
    return IcsTiming(
        pixel_duration_us=float(pixel_duration_us),
        line_duration_ms=line_ms,
        frame_duration_ms=frame_ms,
        pixel_size_nm=float(pixel_size_nm),
    )


def analyse(
    images: np.ndarray,
    timing: IcsTiming,
    *,
    method: str = "stics",
    tile: int = 24,
    step: int = 0,
    n_lags: int = DEFAULT_LAGS,
    distance: int = 4,
    subtract_average: str = "frame",
    meta: dict[str, Any] | None = None,
) -> FlowAnalysis:
    """Compute a velocity field from an image stack.

    Parameters
    ----------
    images : numpy.ndarray
        Stack of shape ``(n_frames, n_lines, n_pixels)``.
    timing : IcsTiming
        Scanner timing; its frame time and pixel size set the velocity scale.
    method : str
        ``'stics'`` or ``'pcf'``.
    tile : int
        Tile size in pixels — the spatial resolution of the map, traded against
        how many molecules each tile holds.
    step : int
        Distance between tile origins; ``0`` uses ``tile // 2`` (overlapping
        tiles, which smooths the field without adding information).
    n_lags : int
        STICS only: number of frame lags, ``0 .. n_lags-1``. The peak must stay
        inside the tile over the whole range.
    distance : int
        pCF only: the pair distance in pixels.
    subtract_average : str
        ``'frame'`` removes each frame's own mean; ``'stack'`` also removes the
        time-averaged image, i.e. the immobile fraction.
    meta : dict, optional
        Provenance merged into the result.

    Returns
    -------
    FlowAnalysis
        The velocity field and the image the arrows belong on.

    Raises
    ------
    ValueError
        If the stack is not a stack, has too few frames, or *method* is unknown.
    """
    stack = np.ascontiguousarray(np.asarray(images, dtype=float))
    if stack.ndim == 4:
        stack = stack.sum(axis=1)
    if stack.ndim != 3:
        raise ValueError(
            f"a flow map needs a (n_frames, n_lines, n_pixels) stack; got {stack.shape}"
        )
    if stack.shape[0] < 3:
        raise ValueError(
            f"{stack.shape[0]} frames is not enough to see anything move; a flow "
            "map tracks the correlation peak *between* frames"
        )
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; use one of {METHODS}")

    tile = max(4, int(tile))
    step_px = int(step) if step else max(1, tile // 2)

    if method == "stics":
        field = stics_flow_map(
            stack,
            tile=tile,
            step=step_px,
            frame_lags=range(0, max(2, int(n_lags))),
            timing=timing,
            subtract_average=subtract_average,
        )
    else:
        field = pcf_flow_map(stack, distance=int(distance), tile=tile, timing=timing)

    return FlowAnalysis(
        x=np.asarray(field.x),
        y=np.asarray(field.y),
        vx=np.asarray(field.vx),
        vy=np.asarray(field.vy),
        quality=np.asarray(field.quality),
        amplitude=np.asarray(field.amplitude),
        image=stack.mean(axis=0),
        method=method,
        timing=field.timing,
        n_escaped=int(field.meta.get("n_escaped", 0)),
        meta={**(meta or {}), **field.meta},
    )


def analyse_file(
    filename: str | pathlib.Path,
    *,
    channel: Any = 0,
    method: str = "stics",
    tile: int = 24,
    step: int = 0,
    n_lags: int = DEFAULT_LAGS,
    distance: int = 4,
    subtract_average: str = "frame",
    pixel_duration_us: float = 20.0,
    line_duration_ms: float = 0.0,
    frame_duration_ms: float = 0.0,
    pixel_size_nm: float = 100.0,
) -> FlowAnalysis:
    """Load *filename* and compute its velocity field.

    Parameters
    ----------
    filename : str or pathlib.Path
        TIFF stack or photon stream.
    channel : int or str
        Image channel to analyse, by index or name.
    method, tile, step, n_lags, distance, subtract_average
        See :func:`analyse`.
    pixel_duration_us, line_duration_ms, frame_duration_ms, pixel_size_nm
        See :func:`scan_timing`.

    Returns
    -------
    FlowAnalysis
        The velocity field.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    ValueError
        If the channel is not in the file, or the stack cannot carry a flow map.
    """
    path = pathlib.Path(filename)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    stack = load_image_stack(str(path))
    names = list(stack.channel_names)
    index = _channel_index(channel, names)
    images = np.asarray(stack.data[:, index], dtype=float)
    timing = scan_timing(
        int(images.shape[1]),
        pixel_duration_us=pixel_duration_us,
        line_duration_ms=line_duration_ms,
        frame_duration_ms=frame_duration_ms,
        pixel_size_nm=pixel_size_nm,
    )
    return analyse(
        images,
        timing,
        method=method,
        tile=tile,
        step=step,
        n_lags=n_lags,
        distance=distance,
        subtract_average=subtract_average,
        meta={
            "filename": str(path),
            "channel": names[index],
            "channel_names": names,
            "n_frames": int(images.shape[0]),
        },
    )


def _channel_index(channel: Any, names: list[str]) -> int:
    """Resolve a channel given by index or name against *names*."""
    if isinstance(channel, str) and channel:
        if channel in names:
            return names.index(channel)
        try:
            channel = int(channel)
        except ValueError as exc:
            raise ValueError(f"no channel {channel!r} in the file; it has {names}") from exc
    index = int(channel or 0)
    if not 0 <= index < len(names):
        raise ValueError(f"channel {index} is out of range; the file has {len(names)}")
    return index


def to_rows(analysis: FlowAnalysis, min_quality: float = 0.0) -> list[dict[str, Any]]:
    """Return the field as one row per tile, for a table or a CSV.

    Parameters
    ----------
    analysis : FlowAnalysis
        The field to flatten.
    min_quality : float
        Drop tiles below this quality. ``0`` keeps every tile, including the
        refused ones — useful when the question is *why* a tile is missing.

    Returns
    -------
    list of dict
        Rows with ``x``, ``y``, ``vx``, ``vy``, ``speed``, ``angle`` and
        ``quality``.
    """
    rows: list[dict[str, Any]] = []
    speed = analysis.speed
    angle = np.degrees(np.arctan2(analysis.vy, analysis.vx))
    for i in range(analysis.vx.shape[0]):
        for j in range(analysis.vx.shape[1]):
            if analysis.quality[i, j] < float(min_quality):
                continue
            rows.append(
                {
                    "x": float(analysis.x[i, j]),
                    "y": float(analysis.y[i, j]),
                    "vx": float(analysis.vx[i, j]),
                    "vy": float(analysis.vy[i, j]),
                    "speed": float(speed[i, j]),
                    "angle": float(angle[i, j]),
                    "quality": float(analysis.quality[i, j]),
                }
            )
    return rows


def write_csv(analysis: FlowAnalysis, path: str | pathlib.Path, min_quality: float = 0.0) -> str:
    """Write the velocity field to a CSV file.

    Parameters
    ----------
    analysis : FlowAnalysis
        The field to write.
    path : str or pathlib.Path
        Destination file.
    min_quality : float
        Threshold passed to :func:`to_rows`.

    Returns
    -------
    str
        The path written.
    """
    import csv

    rows = to_rows(analysis, min_quality)
    columns = ["x", "y", "vx", "vy", "speed", "angle", "quality"]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def write_container(source, analysis, *, parameters=None, out_dir=None) -> str:
    """Write a velocity field into the measurement's container.

    A tile is not a pixel, so the field had nowhere to go in
    `<source>.imaging.h5`. Here it is a table at `pixel` grain — one row per
    tile centre — plus the time-averaged image the arrows belong on, which is
    a raster and travels as a TIFF.

    ``NaN`` marks a refused tile and is written as such rather than dropped: a
    tile whose correlation peak left its own bounds fits a confident line
    through a sign-flipped displacement, so *which* tiles were refused is part
    of the answer.

    Parameters
    ----------
    source : str or pathlib.Path
        The image or photon file, or the container itself.
    analysis : FlowAnalysis
        The field to record.
    parameters : dict, optional
        The settings. Their hash is the identity of the run.
    out_dir : str or pathlib.Path, optional

    Returns
    -------
    str
        Path of the container written.
    """
    from chisurf.core.datastore import store_from_arrays
    from chisurf.core.fio.fluorescence.imaging_container import (
        write_image,
        write_imaging_table,
    )

    written = write_imaging_table(
        source,
        store_from_arrays(
            {
                "x": np.asarray(analysis.x, dtype=float).ravel(),
                "y": np.asarray(analysis.y, dtype=float).ravel(),
                "vx": np.asarray(analysis.vx, dtype=float).ravel(),
                "vy": np.asarray(analysis.vy, dtype=float).ravel(),
                "Speed": np.asarray(analysis.speed, dtype=float).ravel(),
                "Quality": np.asarray(analysis.quality, dtype=float).ravel(),
                "Amplitude": np.asarray(analysis.amplitude, dtype=float).ravel(),
            }
        ),
        name="flow",
        artifact_kind="velocity_field",
        operation_type="flow_field_estimation",
        row_grain="pixel",
        parameters=dict(
            parameters or {}, method=analysis.method, n_escaped=int(analysis.n_escaped)
        ),
        units={
            "x": "micrometres",
            "y": "micrometres",
            # µm/s has no term of its own; the components are recorded with the
            # length unit their magnitude is in and the frame time is in the
            # settings, which is what makes them reconstructible.
            "Quality": "dimensionless",
            "Amplitude": "dimensionless",
        },
        out_dir=out_dir,
    )
    image = np.asarray(analysis.image)
    if image.size:
        written = write_image(
            source,
            image.astype(np.float32),
            name="flow image",
            operation_type="flow_field_estimation",
            axes="YX",
            parameters=parameters,
            derived_from="flow",
            out_dir=out_dir,
        )
    return written
