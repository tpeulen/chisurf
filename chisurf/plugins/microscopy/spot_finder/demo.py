"""Generate a field whose objects have *known* lifetimes, so the tools teach themselves.

Detection and a per-region lifetime fit are both hard to trust the first time
you see them: regions appear over an image and numbers appear beside them, with
nothing to check either against. This module removes that by simulating a scan
whose answer is written down — four blobs at known places with known lifetimes,
polarisation-resolved over two detectors — and writing it as ordinary PTU files.
The Spot Finder opens it like any measurement, the Region MLE fits it, and both
results can be compared with the truth.

It is a *real* photon stream: molecules are excited by a rastering beam, every
photon carries a macro time, a micro time and a detector channel, scanner
markers are interleaved, and a second file holds the **IRF measurement** that
belongs to it — a simulated scatterer through the same optics, so the fit is not
handed a noiseless instrument response against noisy data.

Two details are load-bearing and neither is physics:

* the scan's **marker layout** is the scanner's, and a written PTU does not
  carry it, so the image is reconstructed through
  :func:`~chisurf.core.fluorescence.imaging.simulate.clsm_from_scan`. Read with
  auto-detection instead, the file opens as an empty image and no error;
* each blob's **brightness is compensated**. tttrlib's simulator gives a
  fluorophore a photon yield that depends on its *index* in the system rather
  than on its physics (see ``okf/references/known-issues.md``), so left alone
  the first blob is 250× dimmer than the third and falls below any threshold.
  The compensation is linear, exact, and written here rather than hidden in the
  simulator, so that removing it is a one-line change once the engine is fixed.

Generation takes a few seconds, so the result is cached and the settings it was
made with are stored beside it — a file left over from *different* settings
loads without complaint and answers a question nobody asked.
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

__all__ = ["DEMO_BLOBS", "create_demo", "demo_paths", "truth_table"]

#: ``(ix, iy, tau_ns)`` of every simulated object. Four lifetimes spanning a
#: factor of six, well separated on the grid so a segmentation failure is a
#: failure and not an ambiguity.
DEMO_BLOBS = ((14, 14, 1.0), (34, 14, 3.6), (14, 34, 2.2), (34, 34, 0.6))

#: Photons one molecule yields at each index, measured at equal brightness.
#: The simulator's, not the sample's — see the module docstring.
_INDEX_YIELD = (659.0, 32336.0, 169099.0, 97421.0)

_CONFIG: dict[str, Any] = {
    "blobs": [list(b) for b in DEMO_BLOBS],
    "n_pixel": 48,
    "n_micro": 128,
    "dt": 0.064,
    "dwell": 2.0,
    "psf_w0": 0.5,
    "seed": 7,
    "irf_seed": 11,
    "target_photons": 60000.0,
    "version": 1,
}


def demo_paths(directory: str | pathlib.Path | None = None) -> tuple:
    """Return ``(sample, irf)`` paths for the demo, whether or not they exist.

    Parameters
    ----------
    directory : str or pathlib.Path, optional
        Folder to hold them. Defaults to ChiSurf's own settings directory, so
        the demo survives between sessions and is never written into the user's
        data.

    Returns
    -------
    tuple of pathlib.Path
    """
    if directory is None:
        base = None
        try:
            import chisurf.core.settings as settings_mod

            base = getattr(settings_mod, "chisurf_settings_path", None)
        except Exception:  # pragma: no cover - settings unavailable
            base = None
        base = pathlib.Path(base) if base else pathlib.Path.home() / ".chisurf"
        if not base.is_absolute():
            base = pathlib.Path.home() / ".chisurf"
        directory = base / "demo"
    directory = pathlib.Path(directory)
    return directory / "spot_demo_mixture.ptu", directory / "spot_demo_mixture_irf.ptu"


def create_demo(directory: str | pathlib.Path | None = None, *, overwrite: bool = False) -> tuple:
    """Write the demo scan and its IRF, reusing a cached pair when it matches.

    Parameters
    ----------
    directory : str or pathlib.Path, optional
        Where to write them.
    overwrite : bool, optional
        Regenerate even when a matching pair is already there.

    Returns
    -------
    tuple of pathlib.Path
        ``(sample, irf)``.
    """
    from chisurf.core.fluorescence.imaging.simulate import (
        Blob,
        simulate_irf_measurement,
        simulate_molecule_mixture,
        write_mixture_ptu,
    )

    sample, irf_path = demo_paths(directory)
    if not overwrite and _cache_is_good(sample, irf_path):
        logger.debug("spot finder demo: reusing %s", sample)
        return sample, irf_path

    sample.parent.mkdir(parents=True, exist_ok=True)
    yields = np.asarray(_INDEX_YIELD, dtype=float)
    brightness = 20000.0 * float(_CONFIG["target_photons"]) / yields
    blobs = [
        Blob(int(ix), int(iy), float(tau), brightness=float(q))
        for (ix, iy, tau), q in zip(DEMO_BLOBS, brightness)
    ]

    scan = simulate_molecule_mixture(
        blobs,
        n_pixel=int(_CONFIG["n_pixel"]),
        n_micro=int(_CONFIG["n_micro"]),
        dt=float(_CONFIG["dt"]),
        dwell=float(_CONFIG["dwell"]),
        psf_w0=float(_CONFIG["psf_w0"]),
        seed=int(_CONFIG["seed"]),
    )
    instrument = simulate_irf_measurement(
        n_pixel=16,
        n_micro=int(_CONFIG["n_micro"]),
        dt=float(_CONFIG["dt"]),
        dwell=float(_CONFIG["dwell"]),
        psf_w0=float(_CONFIG["psf_w0"]),
        brightness=20000.0,
        seed=int(_CONFIG["irf_seed"]),
    )
    write_mixture_ptu(scan, sample)
    write_mixture_ptu(instrument, irf_path)
    sample.with_suffix(".json").write_text(json.dumps(_CONFIG, sort_keys=True, indent=2))
    logger.info("spot finder demo written to %s", sample)
    return sample, irf_path


def truth_table() -> dict:
    """Return what was simulated, for comparing a result against.

    Returns
    -------
    dict
        ``blobs`` (``(ix, iy, tau)`` per object), ``n_pixel``, ``n_micro``,
        ``dt`` and the excitation ``period`` in nanoseconds.
    """
    return {
        "blobs": [tuple(b) for b in DEMO_BLOBS],
        "n_pixel": int(_CONFIG["n_pixel"]),
        "n_micro": int(_CONFIG["n_micro"]),
        "dt": float(_CONFIG["dt"]),
        "period": float(_CONFIG["n_micro"]) * float(_CONFIG["dt"]),
    }


def _cache_is_good(sample: pathlib.Path, irf: pathlib.Path) -> bool:
    """Whether an existing demo pair was made with exactly these settings.

    Existence is not enough. A pair left over from different settings — or a
    half-written one from an interrupted run — loads without complaint and
    produces regions whose lifetimes do not match the truth printed beside
    them, which reads as "the tool is wrong" rather than "this is not the demo
    you asked for".
    """
    if not (sample.is_file() and irf.is_file()):
        return False
    if sample.stat().st_size < 100_000 or irf.stat().st_size < 10_000:
        return False
    sidecar = sample.with_suffix(".json")
    if not sidecar.is_file():
        return False
    try:
        return json.loads(sidecar.read_text()) == _CONFIG
    except Exception:  # noqa: BLE001 - an unreadable sidecar is a stale cache
        return False
