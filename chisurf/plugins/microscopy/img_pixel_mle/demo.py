"""A polarisation-resolved FLIM image with a known lifetime per half, and its IRF, so pixel-wise MLE can teach itself.

``make_demo(folder)`` writes ``mle_demo.ptu`` and ``mle_demo_irf.ptu`` (confocal photon streams
with scanner markers, parallel photons on routing channel 0, perpendicular on channel 2): the left
half of the image decays with :data:`DEMO` ``tau_left_ns`` and the right half with
``tau_right_ns``. Photon arrival times are the sum of a Gaussian instrument response (the second
file records it alone) and an exponential decay, and each photon goes to the parallel or the
perpendicular detector with the probabilities of the model the fit uses
(``r(t) = r0 exp(-t/rho)``, ``I_VV = F(1 + 2r)/3``, ``I_VH = F(1 - r)/3``; the demo is isotropic,
``r0 = 0``, and "Load example" sets the fit's start anisotropy to match), so the fitted lifetime
map has a known answer: two plateaus at the two simulated lifetimes. Nothing here is a measurement.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

STEM = "mle_demo"
IRF_STEM = "mle_demo_irf"
#: The simulation, in one place so the help text, the guide and the tests agree.
DEMO: dict[str, Any] = {
    "version": 1,
    "seed": 20261010,
    "n_pixel": 24,
    "n_frames": 6,
    "photons_per_pixel_frame": 250.0,
    "tau_left_ns": 1.5,
    "tau_right_ns": 3.5,
    "r0": 0.0,
    "rho_ns": 1.0,
    "irf_center_ns": 1.5,
    "irf_sigma_ns": 0.12,
    "n_micro": 256,
    "micro_resolution_ns": 0.05,
    "pixel_dwell_s": 20.0e-6,
    "irf_photons": 200_000,
    "parallel_channel": 0,
    "perpendicular_channel": 2,
}


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.core.settings.path_utils import get_path

    return get_path("settings") / "demos" / "img_pixel_mle"


def _micro_and_channel(rng, tau_ns: np.ndarray):
    """Draw micro times and detector channels for photons of lifetime *tau_ns* (one per photon)."""
    c = DEMO
    period = c["n_micro"] * c["micro_resolution_ns"]
    emission = rng.exponential(tau_ns)
    t = c["irf_center_ns"] + rng.normal(0.0, c["irf_sigma_ns"], tau_ns.size) + emission
    r = c["r0"] * np.exp(-emission / c["rho_ns"])
    to_parallel = rng.random(tau_ns.size) < (1.0 + 2.0 * r) / (2.0 + r)
    micro = np.floor(np.mod(t, period) / c["micro_resolution_ns"]).astype(np.uint16)
    channel = np.where(to_parallel, c["parallel_channel"], c["perpendicular_channel"]).astype(np.int8)
    return micro, channel


def lifetime_map() -> np.ndarray:
    """Return the true lifetime (ns) of every pixel: left half and right half."""
    n = DEMO["n_pixel"]
    truth = np.full((n, n), DEMO["tau_left_ns"])
    truth[:, n // 2 :] = DEMO["tau_right_ns"]
    return truth


def _image_stream():
    """Simulate the scan and return the TTTR object (markers, photons, header)."""
    import tttrlib

    from ..img_pixel_nb.demo import counts_to_tttr

    c = DEMO
    rng = np.random.default_rng(c["seed"])
    n, frames = c["n_pixel"], c["n_frames"]
    counts = rng.poisson(c["photons_per_pixel_frame"], size=(frames, n, n))
    tau_per_photon = np.repeat(np.broadcast_to(lifetime_map(), counts.shape).reshape(-1), counts.reshape(-1))
    scan = counts_to_tttr(counts, c["pixel_dwell_s"], c["seed"])
    photon = np.asarray(scan.event_types) == 0
    micro = np.asarray(scan.micro_times).astype(np.uint16).copy()
    channel = np.asarray(scan.routing_channels).astype(np.int8).copy()
    micro[photon], channel[photon] = _micro_and_channel(rng, tau_per_photon)
    stream = tttrlib.TTTR(
        np.asarray(scan.macro_times, dtype=np.uint64), micro, channel, np.asarray(scan.event_types, dtype=np.int8)
    )
    _timing(stream.header, 0.5 * c["pixel_dwell_s"])
    for name, value in (
        ("ImgHdr_LineStart", 1),
        ("ImgHdr_LineStop", 2),
        ("ImgHdr_Frame", 3),
        ("ImgHdr_PixX", n),
        ("ImgHdr_PixY", n),
        ("ImgHdr_BiDirect", 0),
    ):
        stream.header.set_tag(name, int(value), 0x10000008)
    return stream


def _timing(header, macro_resolution_s: float) -> None:
    """Declare the clocks: macro tick, micro-time channel width and number of channels."""
    header.set_macro_time_resolution(macro_resolution_s)
    header.set_micro_time_resolution(DEMO["micro_resolution_ns"] * 1e-9)
    header.set_number_of_micro_time_channels(DEMO["n_micro"])


def _irf_stream():
    """Simulate the instrument response alone, on both detectors."""
    import tttrlib

    c = DEMO
    rng = np.random.default_rng(c["seed"] + 1)
    n = c["irf_photons"]
    period = c["n_micro"] * c["micro_resolution_ns"]
    t = c["irf_center_ns"] + rng.normal(0.0, c["irf_sigma_ns"], n)
    micro = np.floor(np.mod(t, period) / c["micro_resolution_ns"]).astype(np.uint16)
    channel = np.where(rng.random(n) < 0.5, c["parallel_channel"], c["perpendicular_channel"]).astype(np.int8)
    macro = np.arange(1, n + 1, dtype=np.uint64) * 3
    stream = tttrlib.TTTR(macro, micro, channel, np.zeros(n, dtype=np.int8))
    _timing(stream.header, 1.0e-7)
    return stream


def _digest(folder: Path) -> str:
    """Return a checksum over both generated files."""
    h = hashlib.sha256()
    for name in (f"{STEM}.ptu", f"{IRF_STEM}.ptu"):
        h.update((folder / name).read_bytes())
    return h.hexdigest()


def _cache_is_good(folder: Path) -> bool:
    """Require matching parameters and intact files."""
    try:
        side = json.loads((folder / f"{STEM}.json").read_text(encoding="utf-8"))
        return side.get("demo") == DEMO and side.get("sha256") == _digest(folder)
    except (OSError, ValueError):
        return False


def irf_path(folder: Path | None = None) -> Path:
    """Return the IRF file beside the image in *folder* (default: the demo cache)."""
    return (demo_folder() if folder is None else Path(folder)) / f"{IRF_STEM}.ptu"


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write or reuse the two-lifetime image and its IRF.

    Parameters
    ----------
    folder : pathlib.Path, optional
        Dedicated cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Regenerate even when the stored parameters and checksum match.

    Returns
    -------
    pathlib.Path
        The image PTU; the IRF (:func:`irf_path`) sits beside it, and the JSON sidecar records
        the settings and the true lifetimes.
    """
    folder = demo_folder() if folder is None else Path(folder)
    image = folder / f"{STEM}.ptu"
    if not overwrite and image.is_file() and _cache_is_good(folder):
        return image
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".mle-demo-", dir=folder) as staging:
        for stream, name in ((_image_stream(), image.name), (_irf_stream(), irf_path(folder).name)):
            if not stream.write(str(Path(staging) / name), "PTU"):
                raise OSError(f"could not write {name}")
            (Path(staging) / name).replace(folder / name)
    (folder / f"{STEM}.json").write_text(
        json.dumps(
            {
                "demo": DEMO,
                "sha256": _digest(folder),
                "truth": {"tau_left_ns": DEMO["tau_left_ns"], "tau_right_ns": DEMO["tau_right_ns"]},
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return image
