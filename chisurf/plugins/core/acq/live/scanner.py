"""Scanning: what a scan is, how its markers look in the photon stream, and a simulated one.

An image is recorded the way SymPhoTime records one: a scanner moves the focus over the sample
(a piezo stage first; galvo/LSM integrations work the same way through their markers) while the TCSPC
device records photons **and markers**. A *line start* marker opens a line, a *line stop* marker
closes it, a *frame* marker starts a new frame; a photon's pixel follows from where its arrival
falls between the two line markers. The marker numbers are PicoQuant's (1-based, ``ImgHdr_LineStart``
/ ``ImgHdr_LineStop`` / ``ImgHdr_Frame``); in the record stream marker *n* arrives as the routing
channel ``1 << (n - 1)`` of an event of type 1 -- exactly what tttrlib's CLSM reader reads.

* :class:`ScanSettings` -- the scan (area, pixels, dwell time, frames, z planes, points) and its
  ``ImgHdr_*`` header tags, both ways.
* :class:`ScannerBackend` -- what a scanner offers the Record tool. :class:`SimScanner` is the
  simulated one; the MT200's PI E-725 piezo stage is ``live.points.PiScanner`` (libphacq's ``pi``
  driver), which also runs point measurements (``live.points.PointSequence``).
* :class:`ImagingSample` -- a simulated specimen (beads with two lifetimes on a dim cell outline,
  two detectors, background, IRF), scanned by tttrlib's ``SimEngine`` (``run_scan``), which emits
  the photons and the markers.
* :class:`ImageSimSource` -- that sample measured: its photons and markers as photon batches at
  measurement pace.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import tttrlib

from .realism import Realism

__all__ = [
    "IMGHDR_TYPES",
    "ImagingSample",
    "PointSimSource",
    "ScanSettings",
    "ScannerBackend",
    "SimScanner",
    "marker_bit",
    "scan_from_tags",
]

#: PicoQuant tag types the ImgHdr tags use.
TY_BOOL8 = 0x00000008
TY_INT8 = 0x10000008
TY_FLOAT8 = 0x20000008

#: ImgHdr tags a recording carries, with their PicoQuant tag type.
IMGHDR_TYPES = {
    "ImgHdr_Dimensions": TY_INT8,
    "ImgHdr_Ident": TY_INT8,
    "ImgHdr_PixX": TY_INT8,
    "ImgHdr_PixY": TY_INT8,
    "ImgHdr_PixResol": TY_FLOAT8,
    "ImgHdr_TimePerPixel": TY_FLOAT8,
    "ImgHdr_X0": TY_FLOAT8,
    "ImgHdr_Y0": TY_FLOAT8,
    "ImgHdr_LineStart": TY_INT8,
    "ImgHdr_LineStop": TY_INT8,
    "ImgHdr_Frame": TY_INT8,
    "ImgHdr_MaxFrames": TY_INT8,
    "ImgHdr_BiDirect": TY_BOOL8,
}

#: ImgHdr_Ident of a piezo scan (SymPhoTime's code for a PI piezo stage).
IDENT_PIEZO = 1


def marker_bit(number: int) -> int:
    """The routing channel PicoQuant's marker *number* (1-based) arrives on: ``1 << (number - 1)``."""
    return 1 << (int(number) - 1)


@dataclass
class ScanSettings:
    """One scan: a raster of ``pixels_x`` x ``pixels_y`` over ``area_x_um`` x ``area_y_um``.

    Attributes
    ----------
    pixels_x, pixels_y : int
        Pixels per line, lines per frame.
    area_x_um, area_y_um : float
        The scanned area; a pixel is ``area / pixels`` wide.
    x0_um, y0_um : float
        The scan's origin (the stage position of pixel 0, 0).
    dwell_ms : float
        Time on one pixel; a line takes ``pixels_x * dwell_ms``.
    bidirectional : bool
        Odd lines are scanned right to left.
    frames : int
        Frames per z plane.
    z_planes : int
        Planes of a z stack (1: one plane).
    z_step_um : float
        Distance between planes.
    points : list of (x, y) in um
        A point measurement instead of a raster: the focus parks on each point for ``point_ms``,
        each point one "line" of one pixel. Empty for a raster.
    point_ms : float
        Time per point.
    line_start_marker, line_stop_marker, frame_marker : int
        PicoQuant marker numbers (1-based); ``frame_marker`` 0 means the scan emits none.
    """

    pixels_x: int = 64
    pixels_y: int = 64
    area_x_um: float = 16.0
    area_y_um: float = 16.0
    x0_um: float = 0.0
    y0_um: float = 0.0
    dwell_ms: float = 0.1
    bidirectional: bool = False
    frames: int = 1
    z_planes: int = 1
    z_step_um: float = 0.5
    points: list = field(default_factory=list)
    point_ms: float = 100.0
    line_start_marker: int = 1
    line_stop_marker: int = 2
    frame_marker: int = 3

    # -- geometry and timing -------------------------------------------------------------------
    @property
    def is_points(self) -> bool:
        return bool(self.points)

    @property
    def nx(self) -> int:
        """Pixels per line (1 for a point measurement)."""
        return 1 if self.is_points else int(self.pixels_x)

    @property
    def ny(self) -> int:
        """Lines per frame (the number of points for a point measurement)."""
        return len(self.points) if self.is_points else int(self.pixels_y)

    @property
    def pixel_um(self) -> tuple[float, float]:
        return float(self.area_x_um) / max(1, self.pixels_x), float(self.area_y_um) / max(
            1, self.pixels_y
        )

    @property
    def line_s(self) -> float:
        return (self.point_ms if self.is_points else self.dwell_ms * self.pixels_x) * 1e-3

    @property
    def line_rate_hz(self) -> float:
        return 1.0 / self.line_s if self.line_s > 0 else 0.0

    @line_rate_hz.setter
    def line_rate_hz(self, value: float) -> None:
        """Set the dwell time from a line rate."""
        if value > 0 and not self.is_points:
            self.dwell_ms = 1e3 / (float(value) * max(1, self.pixels_x))

    @property
    def frame_s(self) -> float:
        return self.line_s * self.ny

    @property
    def total_frames(self) -> int:
        return max(1, int(self.frames)) * max(1, int(self.z_planes))

    @property
    def total_s(self) -> float:
        return self.frame_s * self.total_frames

    # -- checks and documents ------------------------------------------------------------------
    def validate(self) -> list[str]:
        """Every problem, each with its field; empty means the scan can run."""
        p: list[str] = []

        def rng(name, lo, hi, integer=False):
            v = getattr(self, name)
            if integer and int(v) != v:
                p.append(f"{name}: {v!r} is not a whole number")
            elif not lo <= float(v) <= hi:
                p.append(f"{name}: {v!r} outside [{lo}, {hi}]")

        rng("pixels_x", 1, 8192, True)
        rng("pixels_y", 1, 8192, True)
        rng("area_x_um", 1e-3, 1e5)
        rng("area_y_um", 1e-3, 1e5)
        rng("dwell_ms", 1e-4, 1e4)
        rng("frames", 1, 1e6, True)
        rng("z_planes", 1, 1e4, True)
        rng("point_ms", 1e-3, 1e7)
        for name in ("line_start_marker", "line_stop_marker"):
            rng(name, 1, 4, True)
        rng("frame_marker", 0, 4, True)
        markers = [self.line_start_marker, self.line_stop_marker] + (
            [self.frame_marker] if self.frame_marker else []
        )
        if len(set(markers)) != len(markers):
            p.append("markers: line start, line stop and frame need different marker numbers")
        for i, pt in enumerate(self.points or []):
            if not (isinstance(pt, (list, tuple)) and len(pt) == 2):
                p.append(f"points[{i}]: expected [x_um, y_um]")
        return p

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["points"] = [list(map(float, pt)) for pt in self.points]
        return d

    @classmethod
    def from_dict(cls, data: dict | None) -> ScanSettings:
        """A scan from its document; unknown keys are ignored, missing ones take the defaults."""
        known = {f for f in cls.__dataclass_fields__}
        kwargs = {k: v for k, v in (data or {}).items() if k in known}
        if "points" in kwargs:
            kwargs["points"] = [tuple(map(float, pt)) for pt in kwargs["points"] or []]
        return cls(**kwargs)

    def imghdr_tags(self) -> dict[str, Any]:
        """The ``ImgHdr_*`` header tags SymPhoTime writes for this scan (typed values)."""
        tags: dict[str, Any] = {
            "ImgHdr_Dimensions": 3,
            "ImgHdr_Ident": IDENT_PIEZO,
            "ImgHdr_PixX": int(self.nx),
            "ImgHdr_PixY": int(self.ny),
            "ImgHdr_PixResol": float(self.pixel_um[0]),
            "ImgHdr_TimePerPixel": float(self.point_ms if self.is_points else self.dwell_ms),
            "ImgHdr_X0": float(self.x0_um),
            "ImgHdr_Y0": float(self.y0_um),
            "ImgHdr_LineStart": int(self.line_start_marker),
            "ImgHdr_LineStop": int(self.line_stop_marker),
            "ImgHdr_MaxFrames": int(self.total_frames),
            "ImgHdr_BiDirect": bool(self.bidirectional),
        }
        if self.frame_marker:
            tags["ImgHdr_Frame"] = int(self.frame_marker)
        return tags


def scan_from_tags(tags: dict) -> tuple[ScanSettings | None, list[str]]:
    """The scan a file's ``ImgHdr_*`` tags describe (``None`` without them), and what was missing.

    *tags* maps tag names to values (index -1). ``ImgHdr_PixResol`` is square pixels in um; a file
    without ``ImgHdr_Frame`` carries no frame markers (its lines fill frames of ``PixY`` lines).
    """
    if not any(str(k).startswith("ImgHdr_") for k in tags):
        return None, ["scan (the file has no ImgHdr tags: not an image)"]
    missing: list[str] = []

    def get(name, default, cast):
        if name in tags and tags[name] is not None:
            try:
                return cast(tags[name])
            except (TypeError, ValueError):
                pass
        missing.append(f"scan: {name}")
        return default

    nx = get("ImgHdr_PixX", 0, int)
    ny = get("ImgHdr_PixY", 0, int)
    resol = get("ImgHdr_PixResol", 0.0, float)
    scan = ScanSettings(
        pixels_x=max(1, nx),
        pixels_y=max(1, ny),
        area_x_um=max(1e-3, resol * max(1, nx)),
        area_y_um=max(1e-3, resol * max(1, ny)),
        x0_um=get("ImgHdr_X0", 0.0, float),
        y0_um=get("ImgHdr_Y0", 0.0, float),
        dwell_ms=max(1e-4, get("ImgHdr_TimePerPixel", 0.0, float) or 1e-4),
        bidirectional=bool(tags.get("ImgHdr_BiDirect", False)),
        frames=max(1, int(tags.get("ImgHdr_MaxFrames", 1) or 1)),
        line_start_marker=get("ImgHdr_LineStart", 1, int),
        line_stop_marker=get("ImgHdr_LineStop", 2, int),
        frame_marker=int(tags.get("ImgHdr_Frame", 0) or 0),
    )
    if "ImgHdr_BiDirect" not in tags:
        missing.append("scan: ImgHdr_BiDirect")
    return scan, missing


class ScannerBackend:
    """What a scanner offers the Record tool. One per scanner; the device layer drives the hardware.

    A scanner is configured with a :class:`ScanSettings`, started and stopped with the TCSPC
    device's measurement, and reports where it is. The markers it emits arrive in the TCSPC device's
    record stream, so the image is built from the photon stream alone.
    """

    name = "scanner"

    def configure(self, scan: ScanSettings) -> list[str]:
        """Take *scan*; returns notes on what was adjusted (empty when taken as is)."""
        raise NotImplementedError

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def status(self) -> dict[str, Any]:
        """``{"running", "frame", "line", "plane"}`` -- where the scan is now."""
        raise NotImplementedError


class SimScanner(ScannerBackend):
    """The simulated scanner: a raster (or point list) at the configured pace, no hardware.

    It knows where the focus is at any time of the run (:meth:`position_at`); the simulated device
    asks it which frame and plane to simulate next.
    """

    name = "Simulated scanner"

    def __init__(self, scan: ScanSettings | None = None):
        self.scan = scan or ScanSettings()
        self._t0: float | None = None

    def configure(self, scan: ScanSettings) -> list[str]:
        problems = scan.validate()
        if problems:
            raise ValueError("; ".join(problems))
        self.scan = scan
        return []

    def start(self) -> None:
        self._t0 = time.monotonic()

    def stop(self) -> None:
        self._t0 = None

    def position_at(self, t_s: float) -> dict[str, int]:
        """The frame, plane and line the scan is in at run time *t_s* (seconds)."""
        s = self.scan
        frame_index = int(t_s // s.frame_s) if s.frame_s > 0 else 0
        frame_index = min(frame_index, s.total_frames - 1)
        line = int((t_s - frame_index * s.frame_s) // s.line_s) if s.line_s > 0 else 0
        return {
            "frame": frame_index % max(1, s.frames),
            "plane": frame_index // max(1, s.frames),
            "line": min(line, s.ny - 1),
        }

    def status(self) -> dict[str, Any]:
        running = self._t0 is not None
        if running and time.monotonic() - self._t0 > self.scan.total_s:
            self._t0 = None  # the raster is done
            running = False
        where = self.position_at(time.monotonic() - self._t0) if running else {}
        return {"running": running, **where}

    # -- point measurements: the focus parked ------------------------------------------------------
    _at = (50.0, 50.0)

    def move_to(self, x_um: float, y_um: float) -> tuple[float, float]:
        """Park the focus on a point (at once); the position reached."""
        self._at = (float(x_um), float(y_um))
        return self._at

    def position(self) -> tuple[float, float]:
        return self._at


def _vd(x) -> Any:
    return tttrlib.VectorDouble([float(v) for v in x])


@dataclass
class ImagingSample:
    """A simulated specimen: beads of two lifetimes on a dim cell outline, seen by two detectors.

    Attributes
    ----------
    n_beads : int
        Bright beads, half with each lifetime.
    tau_ns : (float, float)
        The two bead lifetimes; the cell outline has their mean.
    bead_brightness : float
        Photon rate of one emitter at the focus centre (tttrlib's ``q``, kHz-like); a bead is a few
        emitters.
    cell_brightness : float
        The outline's emitters (many, dim).
    green_fraction : (float, float)
        Share of each bead kind's photons on detector 0 (the rest on detector 1).
    focus_um : float
        The focus radius (1/e^2) in the plane.
    seed : int
    """

    n_beads: int = 24
    tau_ns: tuple = (1.0, 3.5)
    bead_brightness: float = 40.0
    cell_brightness: float = 4.0
    green_fraction: tuple = (0.8, 0.2)
    focus_um: float = 0.25
    seed: int = 1
    #: emitters per spot, ``rng.integers(lo, hi)`` (high exclusive): beads are a few, a single
    #: molecule ``(1, 2)``
    per_spot: tuple = (3, 8)
    #: the dim cell outline under the spots
    cell: bool = True
    #: ``(x0, y0, width, height)`` in µm: the spots spread over this stage area instead of the
    #: scan's (a survey's tiles all see one sample, fixed on the stage)
    area: tuple | None = None
    #: planted emitters ``[(x_um, y_um, species), ...]``: the sample is exactly these (a known
    #: answer), nothing random
    positions: list | None = None

    @classmethod
    def single_molecules(cls, n: int = 24, *, brightness: float = 120.0, seed: int = 1,
                         tau_ns: tuple = (1.0, 3.5)) -> ImagingSample:
        """Immobilised single molecules on a clean coverslip: one emitter per spot, no cell."""
        return cls(n_beads=n, tau_ns=tau_ns, bead_brightness=brightness, seed=seed,
                   per_spot=(1, 2), cell=False)

    def emitters(self, scan: ScanSettings) -> list[tuple[float, float, int]]:
        """Emitter positions (um) and species: beads in clusters, an elliptical cell outline."""
        if self.positions is not None:
            return [(float(x), float(y), int(sp)) for x, y, sp in self.positions]
        rng = np.random.default_rng(self.seed)
        if self.area is not None:
            x0, y0, ax, ay = (float(v) for v in self.area)
        else:
            ax, ay = scan.area_x_um, scan.area_y_um
            x0, y0 = scan.x0_um, scan.y0_um
        out: list[tuple[float, float, int]] = []
        for k in range(int(self.n_beads)):
            cx, cy = x0 + rng.uniform(0.08, 0.92) * ax, y0 + rng.uniform(0.08, 0.92) * ay
            for _ in range(int(rng.integers(int(self.per_spot[0]), int(self.per_spot[1])))):
                out.append((cx + rng.normal(0, 0.06), cy + rng.normal(0, 0.06), k % 2))
        if not self.cell:
            return out
        # the cell: an ellipse of dim emitters (species 2)
        n_cell = int(4 * (ax + ay) / max(self.focus_um, 0.05))
        phi = np.linspace(0, 2 * np.pi, n_cell, endpoint=False)
        for p in phi:
            r = 1.0 + 0.04 * np.sin(5 * p)
            out.append(
                (x0 + ax * (0.5 + 0.36 * r * np.cos(p)), y0 + ay * (0.5 + 0.3 * r * np.sin(p)), 2)
            )
        return out

    def system(
        self,
        scan: ScanSettings,
        realism: Realism,
        *,
        n_micro: int,
        micro_res_ns: float,
        z_um: float = 0.0,
    ):
        """The tttrlib ``SimSystem`` of this sample at focal plane *z_um*."""
        t = np.arange(n_micro) * micro_res_ns
        fwhm = max(float(getattr(realism, "irf_fwhm_ns", 0.0) or 0.0), 2 * micro_res_ns)
        sigma = fwhm / 2.3548
        irf = np.exp(-0.5 * ((t - 1.0) / sigma) ** 2)

        def decay(tau):
            pattern = tttrlib.SimDecay.convolve(_vd(np.exp(-t / tau)), _vd(irf))
            return tttrlib.SimDecay.from_pattern(_vd(pattern), micro_res_ns, 0.0)

        s = tttrlib.SimSystem()
        taus = (float(self.tau_ns[0]), float(self.tau_ns[1]), float(np.mean(self.tau_ns)))
        brightness = (self.bead_brightness, self.bead_brightness, self.cell_brightness)
        green = (self.green_fraction[0], self.green_fraction[1], 0.5)
        for tau, q, g in zip(taus, brightness, green):
            sp = tttrlib.SimSpecies()
            sp.D = 0.0
            sp.q = _vd([q * g, q * (1.0 - g)])
            sp.decay = decay(tau)
            s.add_species(sp)
        zeros = _vd([0.0] * 3)
        s.set_rate_matrices(zeros, zeros)
        # background per detector: kHz -> per ms (tttrlib's rate unit is per window of dt ms)
        bg = (
            float(getattr(realism, "background_donor_khz", 0.0) or 0.0),
            float(getattr(realism, "background_acceptor_khz", 0.0) or 0.0),
        )
        s.set_background(_vd([b * 1e-3 for b in bg]))
        # emitters far outside the scan cannot be seen: a large surveyed sample is simulated
        # only around the tile being scanned
        reach = 3.0 * float(self.focus_um)
        lo_x, hi_x = scan.x0_um - reach, scan.x0_um + scan.area_x_um + reach
        lo_y, hi_y = scan.y0_um - reach, scan.y0_um + scan.area_y_um + reach
        for x, y, sp_index in self.emitters(scan):
            if scan.is_points or (lo_x <= x <= hi_x and lo_y <= y <= hi_y):
                s.add_fluorophore(float(x), float(y), float(z_um), int(sp_index), False)
        return s


class _Scan:
    """One simulated frame: photons and markers, times in seconds from the frame's start."""

    def __init__(self, t: np.ndarray, channel: np.ndarray, micro: np.ndarray, event: np.ndarray):
        self.t, self.channel, self.micro, self.event = t, channel, micro, event


def simulate_frame(
    sample: ImagingSample,
    scan: ScanSettings,
    realism: Realism,
    *,
    frame: int,
    plane: int,
    n_micro: int,
    micro_res_ns: float,
) -> _Scan:
    """Scan the sample once with tttrlib's ``SimEngine`` (photons, line and frame markers)."""
    sim = tttrlib.SimIntegrator()
    sim.dt = 0.01  # ms per simulation window
    sim.n_channels = 2
    sim.n_ph_max = 10**9
    sim.n_microtime_channels = int(n_micro)
    sim.microtime_resolution = float(micro_res_ns)
    sim.laser_period = float(n_micro * micro_res_ns)
    seed = int(sample.seed) * 100003 + frame * 101 + plane
    sim.seed_emission = seed
    sim.seed_diffusion = seed + 1
    focus = tttrlib.SimGrid.gaussian3d(sample.focus_um, 1.0, 0.8, 1.0, 0.04, 1.0)
    system = sample.system(
        scan, realism, n_micro=n_micro, micro_res_ns=micro_res_ns, z_um=-plane * scan.z_step_um
    )
    eng = tttrlib.SimEngine(system, focus, tttrlib.VectorSimGrid([]), sim)
    markers = tttrlib.SimMarkerConfig()
    markers.emit_pixel_markers = False
    markers.marker_line_start = marker_bit(scan.line_start_marker)
    markers.marker_line_stop = marker_bit(scan.line_stop_marker)
    markers.marker_frame = tttrlib.VectorInt32(
        [marker_bit(scan.frame_marker)] if scan.frame_marker else []
    )
    px, py = scan.pixel_um
    if scan.is_points:
        parts = []
        for k, (x, y) in enumerate(scan.points):
            e = tttrlib.SimEngine(system, focus, tttrlib.VectorSimGrid([]), sim)
            point_markers = tttrlib.SimMarkerConfig()
            point_markers.emit_pixel_markers = False
            point_markers.marker_line_start = markers.marker_line_start
            point_markers.marker_line_stop = markers.marker_line_stop
            point_markers.marker_frame = tttrlib.VectorInt32(
                [marker_bit(scan.frame_marker)] if (scan.frame_marker and k == 0) else []
            )
            e.run_scan(
                tttrlib.SimScanner.uniform(
                    1, 1, float(scan.point_ms), px, py, float(x), float(y), point_markers, False
                )
            )
            part = _frame_arrays(e)
            part.t = part.t + k * scan.line_s
            parts.append(part)
        return _Scan(
            *(
                np.concatenate([getattr(p, a) for p in parts])
                for a in ("t", "channel", "micro", "event")
            )
        )
    eng.run_scan(
        tttrlib.SimScanner.uniform(
            int(scan.pixels_x),
            int(scan.pixels_y),
            float(scan.dwell_ms),
            px,
            py,
            # the simulated focus parks on a pixel's start; a real raster sweeps the pixel, whose
            # photons are centred half a pixel further: pixel k is centred on x0 + (k + 1/2) px
            float(scan.x0_um) + 0.5 * px,
            float(scan.y0_um) + 0.5 * py,
            markers,
            bool(scan.bidirectional),
        )
    )
    return _frame_arrays(eng)


def _frame_arrays(eng) -> _Scan:
    window = np.asarray(eng.macro_window(), dtype=np.float64)
    arrival = np.asarray(eng.arrival_time(), dtype=np.float64)  # ms within the window
    t = (window * 0.01 + arrival) * 1e-3
    event = np.asarray(eng.event_type(), dtype=np.int8)
    channel = np.asarray(eng.channel(), dtype=np.int64)
    micro = np.asarray(eng.micro_time(), dtype=np.int64)
    order = np.argsort(t, kind="stable")
    return _Scan(t[order], channel[order], micro[order], event[order])


class ImageSimSource:
    """A simulated scan: the photons and markers :func:`simulate_frame` makes, delivered as
    :class:`~.sources.PhotonBatch` es at measurement pace.
    """

    #: the clocks of a MultiHarp-like unit (a 32 ns sync period in 1600 micro-time channels)
    MICRO_RES_NS = 0.02
    N_MICRO = 1600
    #: each read delivers at most this much measurement time (the image builds line by line)
    SLICE_S = 0.05

    def __init__(self, scan: ScanSettings, sample: ImagingSample, realism: Realism, *,
                 speed: float = 1.0, realtime: bool = True):
        from .sources import SourceInfo

        self.scan, self.sample, self.realism = scan, sample, realism
        self.period_s = self.N_MICRO * self.MICRO_RES_NS * 1e-9
        self.speed, self.realtime = float(speed), bool(realtime)
        self.info = SourceInfo(
            name="Simulator (scan)",
            macro_clock_s=self.period_s,
            micro_res_s=self.MICRO_RES_NS * 1e-9,
            n_micro=self.N_MICRO,
        )
        self._t0: float | None = None
        self._stopped = False
        self._sent_s = 0.0
        self._frames_done = 0
        self._held: list[tuple] = []
        self._total_s = scan.total_s + scan.line_s

    def start(self) -> None:
        self._t0 = time.monotonic()
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    @property
    def finished(self) -> bool:
        return self._stopped or self._sent_s >= self._total_s

    def status(self) -> dict[str, Any]:
        return {"queued": 0, "dropped": 0, "error": ""}

    def _simulate_until(self, upto_s: float) -> None:
        scan = self.scan
        while self._frames_done < scan.total_frames and self._frames_done * scan.frame_s <= upto_s:
            k = self._frames_done
            frame = simulate_frame(
                self.sample, scan, self.realism, frame=k % max(1, scan.frames),
                plane=k // max(1, scan.frames), n_micro=self.N_MICRO,
                micro_res_ns=self.MICRO_RES_NS,
            )  # fmt: skip
            self._held.append((frame.t + k * scan.frame_s, frame.channel, frame.micro, frame.event))
            self._frames_done += 1

    def read(self, timeout: float = 0.2):
        from .sources import PhotonBatch

        if self.finished or self._t0 is None:
            if not self._stopped:
                time.sleep(min(timeout, 0.01))
            return None
        allowed = (time.monotonic() - self._t0) * self.speed if self.realtime else float("inf")
        upto = min(allowed, self._total_s, self._sent_s + self.SLICE_S)
        if upto <= self._sent_s:
            time.sleep(min(timeout, 0.005))
            return None
        self._simulate_until(upto)
        parts, keep = [], []
        for t, c, m, e in self._held:
            cut = int(np.searchsorted(t, upto, side="right"))
            parts.append((t[:cut], c[:cut], m[:cut], e[:cut]))
            if cut < len(t):
                keep.append((t[cut:], c[cut:], m[cut:], e[cut:]))
        self._held = keep
        self._sent_s = upto
        if not parts:
            return None
        t = np.concatenate([p[0] for p in parts])
        order = np.argsort(t, kind="stable")
        macro = np.floor(t[order] / self.period_s).astype(np.uint64)
        # the dtypes the recording writer takes (as the point simulator's batches)
        channel = np.concatenate([p[1] for p in parts])[order].astype(np.int8)
        micro = np.concatenate([p[2] for p in parts])[order].astype(np.uint16)
        event = np.concatenate([p[3] for p in parts])[order].astype(np.int8)
        return PhotonBatch(macro, micro, channel, event=event)


def _emit_overflow(out: list, n: int) -> None:
    while n > 0:
        k = min(n, 1023)
        out.append(0xFE000000 | k)
        n -= k


class PointSimSource:
    """The simulated sample under a parked focus: a point measurement's photons.

    Each :meth:`start` measures where *scanner* stands (``scanner.position()``): every emitter of
    *sample* (laid out over *scan*, the image the points were picked on) shines with its
    brightness weighted by the Gaussian focus at its distance, on its detectors (the sample's
    green fraction) with its lifetime behind the IRF; the background of *realism* comes on top.
    Each emitter bleaches on its own after an exponential time of mean ``bleach_s`` (seeded by
    the point), so a spot of two molecules steps down twice -- the known answer the trace
    analysis must find. :attr:`truth` holds the emitters and bleaching times of the last start.

    Parameters
    ----------
    scanner : object with ``position()``
    scan : ScanSettings
        The raster the sample is laid out on (its area and origin).
    sample : ImagingSample
    realism : Realism
    bleach_s : float
        Mean bleaching time per emitter (seconds); ``0`` never bleaches.
    speed, realtime : as :class:`ImageSimSource`.
    """

    MICRO_RES_NS = ImageSimSource.MICRO_RES_NS
    N_MICRO = ImageSimSource.N_MICRO
    #: measurement time made per read
    SLICE_S = 0.05
    #: emitters further than this many focus radii from the point are dark
    REACH = 3.0

    def __init__(self, scanner, scan: ScanSettings, sample: ImagingSample, realism: Realism, *,
                 bleach_s: float = 3.0, speed: float = 1.0, realtime: bool = True):
        from .sources import SourceInfo

        self.scanner, self.scan, self.sample = scanner, scan, sample
        self.background_hz = (float(realism.background_donor_khz) * 1e3,
                              float(realism.background_acceptor_khz) * 1e3)
        self.irf_sigma_ns = max(float(getattr(realism, "irf_fwhm_ns", 0.0) or 0.0),
                                2 * self.MICRO_RES_NS) / 2.3548
        self.bleach_s = float(bleach_s)
        self.speed, self.realtime = float(speed), bool(realtime)
        self.period_s = self.N_MICRO * self.MICRO_RES_NS * 1e-9
        self.info = SourceInfo(name="Simulator (point)", macro_clock_s=self.period_s,
                               micro_res_s=self.MICRO_RES_NS * 1e-9, n_micro=self.N_MICRO)
        self._emitters = sample.emitters(scan)
        self.position = (0.0, 0.0)
        #: the last start's emitters in reach: ``{"rates_hz", "bleach_s", "species"}``
        self.truth: dict[str, Any] = {}
        self._t0: float | None = None
        self._sent_s = 0.0
        self._stopped = True
        self._rng = np.random.default_rng(sample.seed)

    def start(self) -> None:
        x, y = (float(v) for v in self.scanner.position())
        self.position = (x, y)
        self._rng = np.random.default_rng(
            (int(self.sample.seed), int(round(x * 1000)) & 0xFFFFFFFF,
             int(round(y * 1000)) & 0xFFFFFFFF))
        w0 = float(self.sample.focus_um)
        rates, species, bleach = [], [], []
        for ex, ey, sp in self._emitters:
            r2 = (ex - x) ** 2 + (ey - y) ** 2
            if r2 > (self.REACH * w0) ** 2:
                continue
            q = self.sample.cell_brightness if sp == 2 else self.sample.bead_brightness
            rates.append(float(q) * 1e3 * np.exp(-2.0 * r2 / w0**2))
            species.append(int(sp))
            bleach.append(float(self._rng.exponential(self.bleach_s)) if self.bleach_s > 0
                          else float("inf"))
        self.truth = {"rates_hz": rates, "species": species, "bleach_s": bleach}
        # every point is a run of its own: the device clock starts at zero, as a device's does
        self._sent_s = 0.0
        self._stopped = False
        self._t0 = time.monotonic()

    def stop(self) -> None:
        self._stopped = True

    @property
    def finished(self) -> bool:
        return self._stopped

    def status(self) -> dict[str, Any]:
        return {"queued": 0, "dropped": 0, "error": ""}

    def _micro(self, n: int, tau_ns: float) -> np.ndarray:
        t = self._rng.normal(1.0, self.irf_sigma_ns, n) + self._rng.exponential(tau_ns, n)
        period_ns = self.N_MICRO * self.MICRO_RES_NS
        return (np.mod(t, period_ns) / self.MICRO_RES_NS).astype(np.int64)

    def read(self, timeout: float = 0.2):
        from .sources import PhotonBatch

        if self._stopped or self._t0 is None:
            return None
        allowed = (time.monotonic() - self._t0) * self.speed if self.realtime else float("inf")
        upto = min(allowed, self._sent_s + self.SLICE_S)
        if upto <= self._sent_s:
            time.sleep(min(timeout, 0.005))
            return None
        t0, rng = self._sent_s, self._rng
        parts_t, parts_c, parts_m = [], [], []
        taus = (float(self.sample.tau_ns[0]), float(self.sample.tau_ns[1]),
                float(np.mean(self.sample.tau_ns)))
        green = (self.sample.green_fraction[0], self.sample.green_fraction[1], 0.5)
        for rate, sp, gone in zip(self.truth["rates_hz"], self.truth["species"],
                                  self.truth["bleach_s"]):
            end = min(upto, gone)
            if end <= t0:
                continue
            n = int(rng.poisson(rate * (end - t0)))
            parts_t.append(rng.uniform(t0, end, n))
            parts_c.append((rng.random(n) >= green[sp]).astype(np.int64))
            parts_m.append(self._micro(n, taus[sp]))
        for ch, rate in enumerate(self.background_hz):
            n = int(rng.poisson(rate * (upto - t0)))
            parts_t.append(rng.uniform(t0, upto, n))
            parts_c.append(np.full(n, ch, np.int64))
            parts_m.append(rng.integers(0, self.N_MICRO, n))
        self._sent_s = upto
        t = np.concatenate(parts_t) if parts_t else np.zeros(0)
        order = np.argsort(t, kind="stable")
        macro = np.floor(t[order] / self.period_s).astype(np.uint64)
        channel = (np.concatenate(parts_c)[order] if parts_c else np.zeros(0)).astype(np.int8)
        micro = (np.concatenate(parts_m)[order] if parts_m else np.zeros(0)).astype(np.uint16)
        return PhotonBatch(macro, micro, channel, event=np.zeros(len(macro), np.int8))
