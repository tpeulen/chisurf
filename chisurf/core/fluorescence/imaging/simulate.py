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
    irf = _gaussian_irf(n_micro, irf_center, irf_sigma)

    sample = tttrlib.SimSystem()
    for tau in taus:
        sample.add_species(_lifetime_species(tttrlib, tau, irf, dt, [float(brightness)]))
    n_sp = len(taus)
    sample.set_rate_matrices([0.0] * n_sp * n_sp, [0.0] * n_sp * n_sp)
    sample.set_background([0.0])
    for m in mols:
        sample.add_fluorophore(m.ix * pixel_size, m.iy * pixel_size, 0.0, taus.index(m.tau), False)

    tttr, clsm = _run_scan(
        tttrlib, sample, n_channels=1, n_pixel=n_pixel, pixel_size=pixel_size,
        n_micro=n_micro, dt=dt, dwell=dwell, psf_w0=psf_w0, fill_channels=[0],
    )
    return SimulatedImage(
        tttr=tttr, clsm=clsm, molecules=mols, irf=irf,
        n_pixel=n_pixel, pixel_size=pixel_size, n_micro=n_micro, dt=dt,
        laser_period=laser_period,
    )


@dataclasses.dataclass
class DiffusionScan:
    """A raster scan of a freely diffusing population, with its ground truth.

    Attributes
    ----------
    images : numpy.ndarray
        ``(n_frames, n_pixel, n_pixel)`` photon counts per pixel.
    diffusion_coefficient : float
        The ``D`` that was simulated, in um^2/s.
    pixel_time, line_time, frame_time : float
        Scanner timing in **seconds**, as the correlation model needs it.
    pixel_size, w_r, w_z : float
        Geometry in um.
    n_photons : int
        Photons in the scan (markers excluded).
    """

    images: np.ndarray
    diffusion_coefficient: float
    pixel_time: float
    line_time: float
    frame_time: float
    pixel_size: float
    w_r: float
    w_z: float
    n_photons: int = 0

    def to_dict(self) -> dict:
        """Return the ground truth as JSON-compatible values."""
        return {
            "diffusion_coefficient": float(self.diffusion_coefficient),
            "pixel_time": float(self.pixel_time),
            "line_time": float(self.line_time),
            "frame_time": float(self.frame_time),
            "pixel_size": float(self.pixel_size),
            "w_r": float(self.w_r),
            "w_z": float(self.w_z),
            "shape": [int(v) for v in self.images.shape],
            "n_photons": int(self.n_photons),
        }


def simulate_clsm_diffusion(
    diffusion_coefficient: float = 1.0,
    *,
    n_pixel: int = 64,
    n_frames: int = 30,
    pixel_size: float = 0.05,
    pixel_time: float = 2e-05,
    w_r: float = 0.25,
    w_z: float = 1.0,
    n_molecules: float = 400.0,
    brightness: float = 2e06,
    box_xy: float = 0.0,
    box_z: float = 4.0,
    windows_per_pixel: int = 1,
    seed: int = 1,
) -> DiffusionScan:
    """Raster-scan a freely **diffusing** population, for RICS and friends.

    The companion to :func:`simulate_clsm_molecules`, which places *immobile*
    emitters at known pixels for lifetime imaging. This one is the opposite
    experiment: no molecule has a fixed position, and the observable is how far
    the sample decorrelates between one pixel and the next -- which is exactly
    what raster image correlation spectroscopy measures.

    Three things have to be right for the scan to carry a diffusion
    coefficient at all, and each of them is silently wrong in the obvious
    implementation:

    **Real seconds, not scanner units.** The integrator step is set to
    ``pixel_time / windows_per_pixel``, so the beam spends the dwell on each
    pixel *and* a molecule takes a Brownian step of ``sqrt(2 D dt)`` over the
    same interval. An immobile simulation does not care what the time unit
    means; a diffusing one is nothing but the time unit.

    **Mobile molecules.** ``add_fluorophore`` takes ``mobile=False`` by
    default, and an immobile molecule ignores ``D`` entirely -- the images then
    come out **bit-identical** for every diffusion coefficient, which looks like
    a working simulation until you compare two of them.

    **An open volume.** A fixed set of emitters diffuses out of the box and
    dies, so the concentration falls through the acquisition and the sample is
    not stationary -- the one assumption every correlation analysis makes. A
    population (surface-flux injection) is replenished at the boundary and
    stays stationary.

    Parameters
    ----------
    diffusion_coefficient : float
        ``D`` in um^2/s.
    n_pixel : int
        Image side length in pixels (square).
    n_frames : int
        Number of frames scanned.
    pixel_size : float
        Pixel size in um. It should sample the waist several times over.
    pixel_time : float
        Pixel dwell in **seconds**.
    w_r, w_z : float
        Lateral and axial ``1/e^2`` waists of the focus in um.
    n_molecules : float
        Expected number of molecules in the box (not in the focus).
    brightness : float
        Peak photon rate of one molecule at the focus centre, per second.
    box_xy : float
        Box radius in um; ``0`` picks a radius comfortably beyond the scanned
        field, which it must be, or molecules cannot enter from outside it.
    box_z : float
        Axial box extent in um.
    windows_per_pixel : int
        Integrator steps per pixel. ``1`` samples diffusion at the pixel rate,
        which is all the scan can resolve; raise it only to check that the
        answer does not depend on it.
    seed : int
        Random seed.

    Returns
    -------
    DiffusionScan

    Raises
    ------
    RuntimeError
        If tttrlib's photon simulator is unavailable.
    ValueError
        If a setting cannot produce a usable scan.
    """
    import tttrlib

    if not hasattr(tttrlib, "SimEngine"):
        raise RuntimeError("tttrlib was built without the photon simulator (SimEngine)")
    if diffusion_coefficient < 0.0:
        raise ValueError("the diffusion coefficient cannot be negative")
    if pixel_time <= 0.0:
        raise ValueError("the pixel dwell must be a positive number of seconds")
    windows_per_pixel = max(int(windows_per_pixel), 1)

    scanned = n_pixel * pixel_size
    if box_xy <= 0.0:
        # The focus must be able to see molecules that were never scanned, so
        # the box has to reach past the corner of the field plus a few waists.
        box_xy = 0.5 * scanned * np.sqrt(2.0) + 4.0 * w_r
    window_dt = float(pixel_time) / windows_per_pixel

    sample = tttrlib.SimSystem()
    species = tttrlib.SimSpecies()
    species.D = float(diffusion_coefficient)
    species.q = tttrlib.VectorDouble([float(brightness)])
    species.r0 = 0.0
    sample.add_species(species)
    sample.set_background([0.0])
    sample.set_box(float(box_xy), float(box_z))
    sample.set_population(0, float(n_molecules))

    settings = tttrlib.SimIntegrator()
    settings.dt = window_dt
    settings.n_channels = 1
    settings.n_ph_max = 10 ** 12
    settings.seed_diffusion = int(seed)
    settings.seed_emission = int(seed) + 1
    engine = tttrlib.SimEngine(
        sample,
        tttrlib.SimGrid.gaussian3d(w_r, w_z, 2.0 * box_xy, box_z, 0.05, 1.0),
        tttrlib.VectorSimGrid([]),
        settings,
    )

    scanner = tttrlib.SimScanner.uniform(
        n_pixel, n_pixel, float(pixel_time), pixel_size, pixel_size,
        -0.5 * scanned, -0.5 * scanned, tttrlib.SimMarkerConfig(), False,
    )
    for _ in range(int(n_frames)):
        engine.run_scan(scanner)

    # Markers outnumber photons in a scan (one per pixel, plus line and frame
    # markers), so binning the raw record stream would make an image that is
    # mostly scanner bookkeeping. Event type 0 is a photon.
    event_type = np.asarray(engine.event_type())
    windows = np.asarray(engine.macro_window(), dtype=np.int64)[event_type == 0]

    per_frame = n_pixel * n_pixel * windows_per_pixel
    total = per_frame * int(n_frames)
    windows = windows[(windows >= 0) & (windows < total)]
    counts = np.bincount(windows // windows_per_pixel,
                         minlength=n_pixel * n_pixel * int(n_frames))
    images = counts.astype(float).reshape(int(n_frames), n_pixel, n_pixel)

    line_time = n_pixel * float(pixel_time)
    return DiffusionScan(
        images=images,
        diffusion_coefficient=float(diffusion_coefficient),
        pixel_time=float(pixel_time),
        line_time=line_time,
        frame_time=n_pixel * line_time,
        pixel_size=float(pixel_size),
        w_r=float(w_r),
        w_z=float(w_z),
        n_photons=int(windows.size),
    )


# ---------------------------------------------------------------------------
# Shared simulator helpers
# ---------------------------------------------------------------------------
def _gaussian_irf(n_micro: int, center: float, sigma: float) -> np.ndarray:
    """Return an area-normalised Gaussian IRF kernel of length *n_micro*."""
    irf = np.exp(-0.5 * ((np.arange(n_micro) - center) / sigma) ** 2)
    return irf / irf.sum()


def _lifetime_species(tttrlib, tau: float, irf: np.ndarray, dt: float, q):
    """Build an immobile ``SimSpecies`` with a mono-exponential decay + IRF.

    The decay pattern comes from the single canonical generator
    ``chisurf.core.fluorescence.decay.synthetic_decay`` (rather than a local
    exp/convolve), so all simulators share one decay model.
    """
    from chisurf.core.fluorescence.decay import synthetic_decay

    pattern = synthetic_decay(int(irf.size), float(tau), bin_width=float(dt), irf=irf)
    species = tttrlib.SimSpecies()
    species.D = 0.0
    species.q = tttrlib.VectorDouble([float(v) for v in q])
    species.r0 = 0.0
    species.decay = tttrlib.SimDecay.from_pattern(pattern.tolist(), dt, 0.0)
    return species


def _run_scan(tttrlib, sample, *, n_channels, n_pixel, pixel_size, n_micro, dt,
              dwell, psf_w0, fill_channels, window_dt: float = 0.01):
    """Raster-scan *sample* and reconstruct a filled ``CLSMImage``.

    ``window_dt`` is the integrator step, in the same time unit as *dwell*: the
    scanner spends ``round(dwell / window_dt)`` windows on each pixel (at least
    one), and that is also the interval over which a mobile molecule takes one
    Brownian step. It therefore sets **both** the macro-time scale and the
    diffusion granularity, which is why it cannot stay hard-coded once the
    sample moves — see :func:`simulate_clsm_diffusion`.
    """
    excitation = tttrlib.SimGrid.gaussian3d(psf_w0, 1.0, 0.8, 1.0, 0.04, 1.0)
    integrator = tttrlib.SimIntegrator()
    integrator.dt = float(window_dt)
    integrator.n_channels = int(n_channels)
    integrator.n_ph_max = 10**9
    integrator.n_microtime_channels = n_micro
    integrator.microtime_resolution = dt
    integrator.laser_period = n_micro * dt
    engine = tttrlib.SimEngine(sample, excitation, tttrlib.VectorSimGrid([]), integrator)
    engine.run_scan(
        tttrlib.SimScanner.uniform(
            n_pixel, n_pixel, dwell, pixel_size, pixel_size, 0.0, 0.0,
            tttrlib.SimMarkerConfig(), False,
        )
    )
    tttr = tttrlib.TTTR(
        np.asarray(engine.macro_window(), np.uint64),
        np.asarray(engine.micro_time(), np.uint16),
        np.asarray(engine.channel(), np.int8),
        np.asarray(engine.event_type(), np.int8),
    )
    clsm = tttrlib.CLSMImage(
        tttr_data=tttr, marker_frame_start=[4], marker_line_start=1, marker_line_stop=2,
        n_pixel_per_line=n_pixel, use_pixel_markers=True, marker_pixel=8,
        settings={"n_lines": n_pixel},
    )
    clsm.fill(tttr, channels=list(fill_channels))
    return tttr, clsm


# ---------------------------------------------------------------------------
# Load image/lifetime maps + simulate from maps
# ---------------------------------------------------------------------------
def load_image_map(path: str) -> np.ndarray:
    """Load a 2-D intensity or lifetime map from ``.npy``/``.npz`` or an image.

    ``.npy``/``.npz`` load with numpy (first array of an ``.npz``); ``.tif`` and
    other image formats load with ``tifffile`` (falling back to ``skimage.io``).
    A 3-D stack is collapsed to 2-D by summing over the leading axis.
    """
    p = str(path)
    low = p.lower()
    if low.endswith(".npy"):
        arr = np.load(p)
    elif low.endswith(".npz"):
        with np.load(p) as data:
            arr = data[list(data.keys())[0]]
    else:
        try:
            import tifffile

            arr = tifffile.imread(p)
        except Exception:
            from skimage import io as skio

            arr = skio.imread(p)
    arr = np.asarray(arr, dtype=float)
    if arr.ndim == 3:
        arr = arr.sum(axis=0) if arr.shape[0] <= arr.shape[-1] else arr[..., 0]
    if arr.ndim != 2:
        raise ValueError(f"expected a 2-D map, got shape {arr.shape} from {p}")
    return arr


def simulate_clsm_from_maps(
    intensity: np.ndarray,
    lifetime,
    *,
    pixel_size: float = 0.5,
    n_micro: int = 256,
    dt: float = 0.032,
    irf_center: float = 10.0,
    irf_sigma: float = 1.6,
    brightness_scale: float = 2000.0,
    n_lifetime_levels: int = 12,
    n_intensity_levels: int = 8,
    dwell: float = 0.05,
    psf_w0: float = 0.3,
) -> SimulatedImage:
    """Simulate a CLSM image from an intensity image + per-detector lifetime map(s).

    Each pixel emits photons at a rate set by *intensity* and with a mono-
    exponential decay set by the *lifetime* map of each detector.  Pixel
    intensities and lifetimes are quantised (``n_intensity_levels`` ×
    ``n_lifetime_levels`` per detector) into ``SimSpecies``, and one immobile
    fluorophore is placed per non-empty (pixel, detector); detector ``d``'s
    species emit only into routing channel ``d``.

    Parameters
    ----------
    intensity : numpy.ndarray
        2-D relative brightness per pixel (``(H, W)``); scaled to
        ``brightness_scale`` at its maximum.
    lifetime : numpy.ndarray or sequence of numpy.ndarray
        A single 2-D lifetime map (ns) shared by one detector, or one map per
        detector channel (each ``(H, W)`` matching *intensity*).
    pixel_size, n_micro, dt, irf_center, irf_sigma, dwell, psf_w0 : float/int
        Acquisition parameters (see :func:`simulate_clsm_molecules`).
    brightness_scale : float, optional
        Peak per-pixel brightness (the brightest pixel's ``q``).
    n_lifetime_levels, n_intensity_levels : int, optional
        Quantisation levels for the lifetime and intensity axes.

    Returns
    -------
    SimulatedImage
        With ``molecules=[]`` (the emitters are per-pixel, not discrete).

    Raises
    ------
    RuntimeError
        If tttrlib's photon simulator is unavailable.
    ValueError
        If a lifetime map's shape does not match *intensity*.
    """
    import tttrlib

    if not hasattr(tttrlib, "SimEngine"):
        raise RuntimeError("tttrlib was built without the photon simulator (SimEngine)")

    intensity = np.asarray(intensity, dtype=float)
    if intensity.ndim != 2:
        raise ValueError(f"intensity must be 2-D, got {intensity.shape}")
    maps = [np.asarray(lifetime, dtype=float)] if np.ndim(lifetime) == 2 else \
        [np.asarray(m, dtype=float) for m in lifetime]
    for m in maps:
        if m.shape != intensity.shape:
            raise ValueError(f"lifetime map shape {m.shape} != intensity {intensity.shape}")
    n_det = len(maps)
    h, w = intensity.shape
    n_pixel = max(h, w)

    inorm = intensity / intensity.max() if intensity.max() > 0 else intensity
    irf = _gaussian_irf(n_micro, irf_center, irf_sigma)

    # Quantisation grids for lifetime (per map) and intensity.
    all_tau = np.concatenate([m[(np.isfinite(m)) & (m > 0)].ravel() for m in maps]) \
        if any(np.isfinite(m).any() for m in maps) else np.array([1.0])
    tau_lo, tau_hi = float(all_tau.min()), float(max(all_tau.max(), all_tau.min() + 1e-6))
    life_levels = np.linspace(tau_lo, tau_hi, n_lifetime_levels)
    bright_levels = np.linspace(brightness_scale / n_intensity_levels, brightness_scale, n_intensity_levels)

    # One species per (detector, lifetime level, intensity level).
    sample = tttrlib.SimSystem()
    species_index: dict[tuple[int, int, int], int] = {}
    for d in range(n_det):
        for li, tau in enumerate(life_levels):
            for bi, bright in enumerate(bright_levels):
                q = [0.0] * n_det
                q[d] = float(bright)
                species_index[(d, li, bi)] = len(species_index)
                sample.add_species(_lifetime_species(tttrlib, float(tau), irf, dt, q))
    n_sp = len(species_index)
    sample.set_rate_matrices([0.0] * n_sp * n_sp, [0.0] * n_sp * n_sp)
    sample.set_background([0.0] * n_det)

    for iy in range(h):
        for ix in range(w):
            if inorm[iy, ix] <= 0:
                continue
            bi = min(int(inorm[iy, ix] * n_intensity_levels), n_intensity_levels - 1)
            for d, tmap in enumerate(maps):
                tau = tmap[iy, ix]
                if not np.isfinite(tau) or tau <= 0:
                    continue
                li = int(np.argmin(np.abs(life_levels - tau)))
                sp = species_index[(d, li, bi)]
                sample.add_fluorophore(ix * pixel_size, iy * pixel_size, 0.0, sp, False)

    tttr, clsm = _run_scan(
        tttrlib, sample, n_channels=n_det, n_pixel=n_pixel, pixel_size=pixel_size,
        n_micro=n_micro, dt=dt, dwell=dwell, psf_w0=psf_w0, fill_channels=list(range(n_det)),
    )
    return SimulatedImage(
        tttr=tttr, clsm=clsm, molecules=[], irf=irf,
        n_pixel=n_pixel, pixel_size=pixel_size, n_micro=n_micro, dt=dt,
        laser_period=n_micro * dt,
    )
