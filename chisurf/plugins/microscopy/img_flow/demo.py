"""Generate a demo photon stream with a *known* flow, so the tool can teach itself.

A flow map is hard to trust the first time you see one: arrows appear over an
image and there is nothing to check them against. This module removes that
problem by simulating a scan whose velocity field is known analytically —
laminar flow through a channel, parabolic across it — and writing it as an
ordinary PTU file. The tool then opens it like any other measurement, and the
answer can be compared with the truth printed beside it.

The file is a *real* photon stream, not a shortcut: molecules diffuse and are
advected in three dimensions, the beam rasters over them pixel by pixel, and
every photon carries a macro time, a micro time and a detector channel, with
scanner line and frame markers interleaved exactly as a confocal microscope
writes them. It is therefore also a test of the whole read path.

Two details are what make it open without special arguments, and both are easy
to get wrong:

* the **PTU image-header tags** (``ImgHdr_LineStart`` / ``LineStop`` / ``Frame``
  / ``PixX`` / ``PixY``) have to be written, because that is where a reader
  learns which marker means what. Without them the file loads as a few thousand
  frames of nothing, with no error;
* PTU encodes those markers as **bit positions**, so a line-start marker with
  code 1 is written as ``ImgHdr_LineStart = 1`` and read back as ``1 << 0``.

Generation is not instant — a spatially varying flow field switches off the
simulator's coasting optimisation — so the result is cached and reused.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any, Callable

import numpy as np

logger = logging.getLogger(__name__)

#: PTU tag type for a signed 8-byte integer.
_TY_INT8 = 0x10000008

#: The demo's ground truth, in one place so the help text and the tests agree.
DEMO = {
    "n_pixel": 64,
    "n_frames": 50,
    "pixel_size_um": 0.1,
    "pixel_dwell_s": 20.0e-6,
    "diffusion_coefficient": 0.15,
    "v_max": 2.0,
    "w_r": 0.25,
    "w_z": 1.0,
    "n_molecules": 900.0,
    "brightness": 1.2e6,
    "seed": 7,
}


def demo_path(directory: str | pathlib.Path | None = None) -> pathlib.Path:
    """Return where the demo file lives.

    Parameters
    ----------
    directory : str or pathlib.Path, optional
        Folder to hold it. Defaults to ChiSurf's own settings directory, so the
        demo survives between sessions and is not written into the user's data.

    Returns
    -------
    pathlib.Path
        The file path, whether or not it exists yet.
    """
    if directory is None:
        base = None
        try:
            import chisurf.core.settings as settings_mod

            base = getattr(settings_mod, "chisurf_settings_path", None)
        except Exception:  # pragma: no cover - settings unavailable
            base = None
        # An absolute path is required, not merely a truthy one: a missing
        # attribute used to leave this as ``Path("")``, whose ``str`` is ``"."``
        # — so the demo was written *relative to the working directory* and a
        # session started elsewhere could not find the file it had just made.
        base = pathlib.Path(base) if base else pathlib.Path.home() / ".chisurf"
        if not base.is_absolute():
            base = pathlib.Path.home() / ".chisurf"
        directory = base / "demo"
    directory = pathlib.Path(directory)
    return directory / "flow_demo_poiseuille.ptu"


def expected_profile(y_um: np.ndarray, *, v_max: float | None = None,
                     field_um: float | None = None) -> np.ndarray:
    """Return the true flow speed at *y_um*, measured from the top of the image.

    The simulated field is laminar flow along ``+x`` through a channel whose
    walls sit at the edges of the scanned field:
    ``v(y) = v_max * (1 - (y/R)^2)`` with ``R`` the half-width.

    Parameters
    ----------
    y_um : numpy.ndarray
        Distance from the top edge of the image, in µm.
    v_max : float, optional
        Peak speed; defaults to the demo's.
    field_um : float, optional
        Field of view; defaults to the demo's.

    Returns
    -------
    numpy.ndarray
        True ``v_x`` in µm/s.
    """
    v_max = DEMO["v_max"] if v_max is None else float(v_max)
    if field_um is None:
        field_um = DEMO["n_pixel"] * DEMO["pixel_size_um"]
    radius = 0.5 * float(field_um)
    offset = np.asarray(y_um, dtype=float) - radius
    return v_max * np.clip(1.0 - (offset / radius) ** 2, 0.0, None)


def create_demo(
    path: str | pathlib.Path | None = None,
    *,
    overwrite: bool = False,
    progress: Callable[[float, str], None] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """Simulate the demo scan and write it as a PTU file.

    Parameters
    ----------
    path : str or pathlib.Path, optional
        Where to write it; defaults to :func:`demo_path`.
    overwrite : bool
        Regenerate even when the file is already there.
    progress : callable, optional
        Called as ``progress(fraction, text)`` while frames are scanned.
    **overrides
        Any key of :data:`DEMO`, to make a bigger, faster or slower demo.

    Returns
    -------
    dict
        ``path``, ``created`` (whether it was generated now) and the ground
        truth: the settings, the timing the tool should be given, and the peak
        velocity to compare against.

    Raises
    ------
    RuntimeError
        If tttrlib was built without the photon simulator.
    """
    import tttrlib

    if not hasattr(tttrlib, "SimEngine"):
        raise RuntimeError(
            "this tttrlib build has no photon simulator, so the demo cannot be made"
        )

    cfg = {**DEMO, **{k: v for k, v in overrides.items() if k in DEMO}}
    target = pathlib.Path(path) if path is not None else demo_path()
    truth = _truth(cfg, target)
    if not overwrite and _cache_is_good(target, cfg):
        truth["created"] = False
        return truth

    target.parent.mkdir(parents=True, exist_ok=True)
    n_pixel = int(cfg["n_pixel"])
    n_frames = int(cfg["n_frames"])
    pixel = float(cfg["pixel_size_um"])
    dwell = float(cfg["pixel_dwell_s"])
    w_r, w_z = float(cfg["w_r"]), float(cfg["w_z"])
    field = n_pixel * pixel
    # The box has to be comfortably wider than the scanned field, or molecules
    # cannot enter the image from outside it and the edges run dry.
    box_xy = 0.5 * field * 1.6 + 4.0 * w_r
    box_z = 4.0

    sample = tttrlib.SimSystem()
    species = tttrlib.SimSpecies()
    species.D = float(cfg["diffusion_coefficient"])
    species.q = [float(cfg["brightness"])]
    species.r0 = 0.0
    sample.add_species(species)
    sample.set_background([0.0])
    sample.set_box(box_xy, box_z)
    sample.set_population(0, float(cfg["n_molecules"]))
    # Laminar flow along +x, parabolic across y, zero at the channel walls. The
    # lattice must cover the whole box: a SimGrid samples to zero outside itself,
    # so a field that stops short lets the flow stop silently at its edge.
    sample.set_flow_field(
        tttrlib.SimVectorGrid.poiseuille(
            float(cfg["v_max"]), 0.5 * field, 0, box_xy * 1.1, box_z * 1.1, 0.2
        )
    )

    integrator = tttrlib.SimIntegrator()
    integrator.dt = dwell
    integrator.n_channels = 1
    integrator.n_ph_max = 10 ** 12
    integrator.n_microtime_channels = 256
    integrator.microtime_resolution = 0.032
    integrator.laser_period = 256 * 0.032
    integrator.seed_diffusion = int(cfg["seed"])
    integrator.seed_emission = int(cfg["seed"]) + 1
    integrator.fast_grid_bbox = True

    engine = tttrlib.SimEngine(
        sample,
        tttrlib.SimGrid.gaussian3d(w_r, w_z, 4.0 * w_r, min(4.0 * w_z, box_z), 0.05, 1.0),
        [],
        integrator,
    )
    markers = tttrlib.SimMarkerConfig()
    # No pixel markers: a uniform scan divides the line evenly anyway, and one
    # marker per pixel would be four fifths of the file.
    markers.emit_pixel_markers = False
    scanner = tttrlib.SimScanner.uniform(
        n_pixel, n_pixel, dwell, pixel, pixel,
        -0.5 * field, -0.5 * field, markers, False,
    )
    for frame in range(n_frames):
        engine.run_scan(scanner)
        if progress is not None:
            progress((frame + 1) / n_frames, f"Simulating frame {frame + 1}/{n_frames}")

    tttr = tttrlib.TTTR(
        np.asarray(engine.macro_window(), np.uint64),
        np.asarray(engine.micro_time(), np.uint16),
        np.asarray(engine.channel(), np.int8),
        np.asarray(engine.event_type(), np.int8),
    )
    header = tttr.header
    header.set_macro_time_resolution(dwell)
    header.set_micro_time_resolution(0.032e-9)
    # Marker codes as bit *positions*: the simulator emits line start 1, line
    # stop 2 and frame 4, which PTU writes as 1, 2 and 3.
    for name, value in (
        ("ImgHdr_LineStart", 1),
        ("ImgHdr_LineStop", 2),
        ("ImgHdr_Frame", 3),
        ("ImgHdr_PixX", n_pixel),
        ("ImgHdr_PixY", n_pixel),
        ("ImgHdr_BiDirect", 0),
    ):
        header.set_tag(name, int(value), _TY_INT8)
    if not tttr.write(str(target), "PTU"):
        raise RuntimeError(f"could not write the demo photon stream to {target}")
    # Only now, with the file complete on disk, record what it was made with —
    # so an interrupted run leaves a file with no sidecar, which is treated as
    # absent rather than reused.
    import json

    target.with_suffix(".json").write_text(
        json.dumps({"fingerprint": _fingerprint(cfg), **truth["truth"]}, indent=2),
        encoding="utf-8",
    )

    truth["created"] = True
    truth["n_events"] = int(len(tttr))
    if progress is not None:
        progress(1.0, f"Wrote {target.name}")
    return truth


def _fingerprint(cfg: dict[str, Any]) -> str:
    """Return a stable string identifying the settings a demo was made with."""
    import json

    return json.dumps({k: cfg[k] for k in sorted(cfg)}, sort_keys=True)


def _cache_is_good(target: pathlib.Path, cfg: dict[str, Any]) -> bool:
    """Whether an existing demo file can be reused for *cfg*.

    Reusing a cached file on existence alone is how a demo goes quietly wrong:
    a file left over from different settings — or a half-written one from a run
    that was interrupted — loads without complaint and produces a map with no
    arrows in it, which reads as "the tool does not work" rather than as "this
    file is not the demo you asked for". So the settings a file was made with
    are written beside it and checked.

    Parameters
    ----------
    target : pathlib.Path
        The demo file.
    cfg : dict
        The settings the caller wants.

    Returns
    -------
    bool
        Whether *target* is a complete demo made with exactly those settings.
    """
    if not target.is_file() or target.stat().st_size < 10_000:
        return False
    sidecar = target.with_suffix(".json")
    if not sidecar.is_file():
        return False
    try:
        import json

        stored = json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception:
        return False
    return str(stored.get("fingerprint", "")) == _fingerprint(cfg)


def _truth(cfg: dict[str, Any], target: pathlib.Path) -> dict[str, Any]:
    """Assemble the ground-truth descriptor returned alongside the file."""
    n_pixel = int(cfg["n_pixel"])
    pixel = float(cfg["pixel_size_um"])
    dwell = float(cfg["pixel_dwell_s"])
    line_ms = n_pixel * dwell * 1e3
    frame_ms = n_pixel * line_ms
    shift = float(cfg["v_max"]) * frame_ms * 1e-3 / pixel
    return {
        "path": str(target),
        "created": False,
        "settings": dict(cfg),
        "timing": {
            "pixel_duration_us": dwell * 1e6,
            "line_duration_ms": line_ms,
            "frame_duration_ms": frame_ms,
            "pixel_size_nm": pixel * 1e3,
        },
        "truth": {
            "profile": "poiseuille",
            "axis": "x",
            "v_max_um_s": float(cfg["v_max"]),
            "diffusion_coefficient_um2_s": float(cfg["diffusion_coefficient"]),
            "field_um": n_pixel * pixel,
            "peak_shift_px_per_frame": shift,
        },
    }
