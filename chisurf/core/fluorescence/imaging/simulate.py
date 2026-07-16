"""Synthetic confocal (CLSM) molecule images for testing and demos.

Builds a raster-scanned CLSM image of immobile single molecules with known
fluorescence lifetimes using tttrlib's photon simulator (``SimEngine`` /
``SimScanner``): each molecule is a bright immobile fluorophore whose micro-time
decay is a mono-exponential convolved with a Gaussian IRF.  The returned
:class:`SimulatedImage` bundles the photon stream, the reconstructed
``CLSMImage`` and the ground truth, so the molecule-wise MLE pipeline (or an
image browser) can be exercised end-to-end headlessly and checked against the
lifetimes that went in.

tttrlib is imported lazily; :func:`have_simulator` reports whether the simulator
build is present so callers/tests can skip cleanly.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import Any

import numpy as np


def have_simulator() -> bool:
    """Return True when tttrlib and its photon simulator are importable."""
    try:
        import tttrlib
    except Exception:
        return False
    return hasattr(tttrlib, "SimEngine")


@dataclasses.dataclass
class Molecule:
    """A single simulated molecule.

    Parameters
    ----------
    ix, iy : int
        Pixel coordinates of the molecule in the image grid.
    tau : float
        Mono-exponential fluorescence lifetime (ns).
    """

    ix: int
    iy: int
    tau: float


@dataclasses.dataclass
class SimulatedImage:
    """A simulated CLSM molecule image with ground truth.

    Attributes
    ----------
    tttr : tttrlib.TTTR
        The marker-annotated photon stream.
    clsm : tttrlib.CLSMImage
        The reconstructed confocal image (filled on channel 0).
    molecules : list of Molecule
        The ground-truth molecules (positions + lifetimes) that were simulated.
    irf : numpy.ndarray
        The Gaussian IRF kernel (length ``n_micro``) used both to convolve the
        simulated decays and — via :meth:`vv_vh_irf` — to fit them.
    n_pixel : int
        Image side length (pixels).
    pixel_size : float
        Pixel size (µm).
    n_micro : int
        Number of micro-time channels.
    dt : float
        Micro-time channel width (ns).
    laser_period : float
        Excitation period (ns).
    """

    tttr: Any
    clsm: Any
    molecules: list[Molecule]
    irf: np.ndarray
    n_pixel: int
    pixel_size: float
    n_micro: int
    dt: float
    laser_period: float

    def vv_vh_irf(self) -> np.ndarray:
        """Return the area-normalised IRF in VV/VH layout (``2 * n_micro``)."""
        norm = self.irf / self.irf.sum() if self.irf.sum() > 0 else self.irf
        return np.concatenate([norm, norm])

    @property
    def intensity(self) -> np.ndarray:
        """The 2-D total-intensity image (sum over frames)."""
        return np.asarray(self.clsm.intensity).sum(axis=0)

    @property
    def true_taus(self) -> list[float]:
        """Ground-truth lifetimes in molecule order."""
        return [m.tau for m in self.molecules]


def _coerce_molecules(molecules) -> list[Molecule]:
    out: list[Molecule] = []
    for m in molecules:
        if isinstance(m, Molecule):
            out.append(m)
        elif isinstance(m, dict):
            out.append(Molecule(int(m["ix"]), int(m["iy"]), float(m["tau"])))
        else:  # (ix, iy, tau) tuple
            ix, iy, tau = m
            out.append(Molecule(int(ix), int(iy), float(tau)))
    return out


def simulate_clsm_molecules(
    molecules: Sequence,
    *,
    n_pixel: int = 32,
    pixel_size: float = 0.5,
    n_micro: int = 256,
    dt: float = 0.032,
    irf_center: float = 10.0,
    irf_sigma: float = 1.6,
    brightness: float = 3000.0,
    dwell: float = 0.12,
    psf_w0: float = 0.3,
) -> SimulatedImage:
    """Simulate a raster-scanned CLSM image of immobile molecules.

    Parameters
    ----------
    molecules : sequence
        The molecules to place, each a :class:`Molecule`, a ``{"ix","iy","tau"}``
        mapping, or an ``(ix, iy, tau)`` tuple.  Molecules sharing a lifetime
        share a simulated species.
    n_pixel : int, optional
        Image side length (pixels).
    pixel_size : float, optional
        Pixel size (µm).
    n_micro : int, optional
        Number of micro-time channels.
    dt : float, optional
        Micro-time channel width (ns); the excitation period is ``n_micro * dt``.
    irf_center, irf_sigma : float, optional
        Centre and width (micro-time channels) of the Gaussian IRF convolved into
        every decay (and used for fitting via :meth:`SimulatedImage.vv_vh_irf`).
    brightness : float, optional
        Per-molecule peak brightness (simulator ``q``).
    dwell : float, optional
        Per-pixel dwell time (simulator macro-time units).
    psf_w0 : float, optional
        Lateral ``1/e²`` radius of the excitation PSF (µm).

    Returns
    -------
    SimulatedImage

    Raises
    ------
    RuntimeError
        If tttrlib's photon simulator is unavailable (see :func:`have_simulator`).
    """
    import tttrlib

    if not hasattr(tttrlib, "SimEngine"):
        raise RuntimeError("tttrlib was built without the photon simulator (SimEngine)")

    mols = _coerce_molecules(molecules)
    taus = sorted({m.tau for m in mols})
    laser_period = n_micro * dt

    t = np.arange(n_micro) * dt
    irf = np.exp(-0.5 * ((np.arange(n_micro) - irf_center) / irf_sigma) ** 2)
    irf = irf / irf.sum()

    sample = tttrlib.SimSystem()
    for tau in taus:
        pattern = np.convolve(np.exp(-t / tau), irf)[:n_micro]
        decay = tttrlib.SimDecay.from_pattern(pattern.tolist(), dt, 0.0)
        species = tttrlib.SimSpecies()
        species.D = 0.0
        species.q = tttrlib.VectorDouble([float(brightness)])
        species.r0 = 0.0
        species.decay = decay
        sample.add_species(species)
    n_sp = len(taus)
    sample.set_rate_matrices([0.0] * n_sp * n_sp, [0.0] * n_sp * n_sp)
    sample.set_background([0.0])
    for m in mols:
        sample.add_fluorophore(m.ix * pixel_size, m.iy * pixel_size, 0.0, taus.index(m.tau), False)

    excitation = tttrlib.SimGrid.gaussian3d(psf_w0, 1.0, 0.8, 1.0, 0.04, 1.0)
    integrator = tttrlib.SimIntegrator()
    integrator.dt = 0.01
    integrator.n_channels = 1
    integrator.n_ph_max = 10**9
    integrator.n_microtime_channels = n_micro
    integrator.microtime_resolution = dt
    integrator.laser_period = laser_period
    engine = tttrlib.SimEngine(sample, excitation, tttrlib.VectorSimGrid([]), integrator)
    engine.run_scan(
        tttrlib.SimScanner.uniform(
            n_pixel, n_pixel, dwell, pixel_size, pixel_size, 0.0, 0.0,
            tttrlib.SimMarkerConfig(), False,
        )
    )

    macro = np.asarray(engine.macro_window(), np.uint64)
    micro = np.asarray(engine.micro_time(), np.uint16)
    routing = np.asarray(engine.channel(), np.int8)
    event = np.asarray(engine.event_type(), np.int8)
    tttr = tttrlib.TTTR(macro, micro, routing, event)

    clsm = tttrlib.CLSMImage(
        tttr_data=tttr, marker_frame_start=[4], marker_line_start=1, marker_line_stop=2,
        n_pixel_per_line=n_pixel, use_pixel_markers=True, marker_pixel=8,
        settings={"n_lines": n_pixel},
    )
    clsm.fill(tttr, channels=[0])

    return SimulatedImage(
        tttr=tttr, clsm=clsm, molecules=mols, irf=irf,
        n_pixel=n_pixel, pixel_size=pixel_size, n_micro=n_micro, dt=dt,
        laser_period=laser_period,
    )
