"""Qt-free simulation core over tttrlib's photon simulator.

Maps the acquisition plugin's flat ``simulation_params`` dict onto tttrlib
``SimEngine`` objects and produces Becker & Hickl SPC-132 records as a ``uint32``
array — the same word format the streaming ``SimulationDevice`` feeds through
``read_fifo``. Replaces the ctypes/Burbulator-DLL path; no Qt, headless-testable.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Dict

import numpy as np


def tttrlib_available() -> bool:
    """Return whether the photon simulator is importable.

    Delegates: the check lives with the simulation shim so that every consumer
    agrees about what "available" means.
    """
    from chisurf.core.fluorescence.simulation import have_simulator

    return have_simulator()



def _vd(values):
    """Convert numeric values to a ``tttrlib.VectorDouble``.

    Parameters
    ----------
    values : iterable
        Values that can be converted to floats.

    Returns
    -------
    tttrlib.VectorDouble
        C++ vector proxy consumed by ``tttrlib``.
    """
    import tttrlib

    return tttrlib.VectorDouble([float(v) for v in values])


def _flatten(values: Any) -> list[float]:
    """Flatten legacy nested list settings into one numeric vector.

    Parameters
    ----------
    values : object
        Scalar, list, tuple, or NumPy-like object.

    Returns
    -------
    list of float
        Flat list suitable for tttrlib vector construction.
    """
    if values is None:
        return []
    if hasattr(values, "tolist"):
        values = values.tolist()
    if isinstance(values, Iterable) and not isinstance(values, (str, bytes)):
        out = []
        for item in values:
            out.extend(_flatten(item))
        return out
    return [float(values)]


def _sized(values: Any, size: int, default: float = 0.0) -> list[float]:
    """Return a flat list padded or truncated to ``size``.

    Parameters
    ----------
    values : object
        Scalar or sequence value.
    size : int
        Desired output length.
    default : float, optional
        Padding value.

    Returns
    -------
    list of float
        Vector with exactly ``size`` entries.
    """
    flat = _flatten(values)
    if len(flat) < size:
        flat = flat + [float(default)] * (size - len(flat))
    return flat[:size]


def _gaussian_irf_pattern(n_bins: int, dt: float, fwhm_ns: float, center_ns: float) -> "np.ndarray":
    """Return an area-normalized Gaussian IRF on the micro-time axis."""
    from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

    return synthetic_irf(
        np.arange(int(n_bins), dtype=float),
        float(center_ns) / float(dt),
        max(1e-6, float(fwhm_ns) / float(dt)),
        norm=True,
    )


def _species_decay(tttrlib, spectrum, n_bins: int, dt: float, irf=None, t0: float = 0.0):
    """Build a ``SimDecay`` for one species via the canonical decay generator.

    ``spectrum`` is the species' lifetime spectrum: a sequence whose elements are
    either ``[amplitude, lifetime_ns]`` pairs or bare lifetimes (amplitude 1). The
    micro-time decay is produced by the single ChiSurf generator
    ``chisurf.core.fluorescence.decay.synthetic_decay`` (amplitudes + lifetimes →
    optionally IRF-convolved, normalized histogram) and handed to
    ``SimDecay.from_pattern`` — so the acquisition simulator samples arrival times
    from the same decay model as the rest of ChiSurf.
    """
    from chisurf.core.fluorescence.decay import synthetic_decay

    amps, taus = [], []
    for entry in (spectrum or []):
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            amp, tau = float(entry[0]), float(entry[1])
        else:
            amp, tau = 1.0, float(entry)
        if tau > 0.0:
            amps.append(amp)
            taus.append(tau)
    if not taus:
        return None
    pattern = synthetic_decay(
        int(n_bins), taus, amplitudes=amps, bin_width=float(dt), irf=irf, normalize=True
    )
    return tttrlib.SimDecay.from_pattern(pattern.tolist(), float(dt), float(t0))


def build_engine(params: Dict[str, Any]):
    """Build a configured ``tttrlib.SimEngine`` from plugin parameters.

    Parameters
    ----------
    params : dict
        Acquisition simulation parameter dictionary.

    Returns
    -------
    tttrlib.SimEngine
        Configured simulator ready for ``run()``.
    """
    import tttrlib

    ns = int(params.get("N_species", 1))
    nc = int(params.get("N_channels", 2))
    # Per-species fluorescence decay (lifetimes → micro-time decay). Built with the
    # canonical generator and an optional shared Gaussian IRF (``irf_fwhm_ns``).
    n_tac = int(params.get("N_tac_channels", 4096))
    tac_dt = float(params.get("tac_dt", 0.004069))
    decay_lifetimes = params.get("decay_lifetimes")
    decay_pattern_files = params.get("decay_pattern_files")
    irf_pattern = None
    irf_fwhm = params.get("irf_fwhm_ns")
    if irf_fwhm:
        irf_pattern = _gaussian_irf_pattern(
            n_tac, tac_dt, float(irf_fwhm),
            float(params.get("irf_center_ns", 2.0 * float(irf_fwhm))),
        )

    def _loaded_pattern(index: int):
        """Load a per-species measured/saved decay pattern file, if configured."""
        if not isinstance(decay_pattern_files, (list, tuple)) or index >= len(decay_pattern_files):
            return None
        path = decay_pattern_files[index]
        if not path:
            return None
        import pathlib
        p = pathlib.Path(str(path))
        if not p.is_file():
            return None
        arr = np.load(p) if p.suffix.lower() == ".npy" else np.loadtxt(p)
        arr = np.asarray(arr, dtype=float).ravel()
        return arr if arr.size and np.any(arr > 0) else None
    q = _sized(params.get("q", [50.0] * (ns * nc)), ns * nc, 0.0)
    D = _sized(params.get("D", [3.0] * ns), ns, 0.0)
    M = _sized(params.get("M", [50.0] * ns), ns, 0.0)
    box_xy = float(params.get("box_xy", 2.0))
    box_z = float(params.get("box_z", 4.0))
    dt = float(params.get("dt", 0.01))
    focus = list(params.get("focus_param", [0.3, 2.0]))
    w0 = float(focus[0]) if len(focus) > 0 else 0.3
    z0 = float(focus[1]) if len(focus) > 1 else 2.0

    sample = tttrlib.SimSystem()
    for i in range(ns):
        sp = tttrlib.SimSpecies()
        sp.D = float(D[i])
        sp.q = _vd(q[i * nc:(i + 1) * nc])
        sp.r0 = float(params.get("r0", 0.0))
        sp.l1 = float(params.get("l1", 0.0))
        sp.l2 = float(params.get("l2", 0.0))
        sp.D_rot = float(params.get("D_rot", 0.0))
        # Fluorescence decay for this species: a loaded pattern file takes
        # precedence; otherwise build from decay_lifetimes[i] via the generator.
        loaded = _loaded_pattern(i)
        if loaded is not None:
            sp.decay = tttrlib.SimDecay.from_pattern(loaded.tolist(), tac_dt, 0.0)
        elif isinstance(decay_lifetimes, (list, tuple)) and i < len(decay_lifetimes):
            decay = _species_decay(tttrlib, decay_lifetimes[i], n_tac, tac_dt, irf_pattern)
            if decay is not None:
                sp.decay = decay
        sample.add_species(sp)

    k_rad = _sized(params.get("k_rad", [0.0] * (ns * ns)), ns * ns, 0.0)
    k_nrad = _sized(params.get("k_nrad", [0.0] * (ns * ns)), ns * ns, 0.0)
    # Plain sequences, not tttrlib.VectorDouble. SWIG extensions share one global
    # type table, so whichever registers ``std::vector<double>`` first owns the
    # entry; when IMP is imported before tttrlib -- which the documented
    # PYTHONPATH does, since imp-tricks ships a sitecustomize that imports IMP at
    # interpreter start -- a VectorDouble proxy no longer matches a by-value
    # ``std::vector<double>`` argument and raises TypeError. Sequences convert
    # through a different path and are unaffected. Member setters (``species.q``)
    # take a pointer and still need the proxy.
    sample.set_rate_matrices(k_rad, k_nrad)
    sample.set_background(_sized(params.get("q_bg", [0.0] * nc), nc, 0.0))
    sample.set_box(box_xy, box_z)
    for i in range(ns):
        sample.set_population(i, float(M[i]))

    # Excitation focus / point-spread function. Selected by ``psf_type``:
    #   • "gaussian3d"          separable 3D Gaussian (w0, z0) on a trilinear voxel grid;
    #   • "analytic_gaussian3d" the same Gaussian evaluated on the fly (no voxels/construction);
    #   • "gaussian_lorentzian" confocal MDF with a z-expanding waist (w0, Rayleigh range zR);
    #   • "radial"              numeric/measured radially-symmetric PSF from a file (r,z grid).
    # The grid extent defaults to the box, but may be sized to the focus (``excitation_extent``)
    # since the field is ~0 outside it — far fewer voxels, exact, ~50x cheaper to build.
    spacing = max(min(w0, z0) / 4.0, 1e-3)
    ext = params.get("excitation_extent", None)
    ext_xy = float(ext[0]) if isinstance(ext, (list, tuple)) and len(ext) > 0 else box_xy
    ext_z = float(ext[1]) if isinstance(ext, (list, tuple)) and len(ext) > 1 else box_z

    psf_type = str(params.get("psf_type", "gaussian3d")).strip().lower()
    # Legacy: the ``analytic_excitation`` flag selects the analytic Gaussian for the default PSF.
    if params.get("analytic_excitation", False) and psf_type == "gaussian3d":
        psf_type = "analytic_gaussian3d"

    # The name selects the constructor and nothing catches it. This used to be
    # ``elif <name> and hasattr(SimGrid, <constructor>)`` ending in the plain
    # Gaussian, so a typo, a missing file, or a library built without one of the
    # grids silently simulated a *different optical model* than the one asked
    # for: the answer changes and the run does not.
    if psf_type in ("gaussian_lorentzian", "gauss_lorentz"):
        zR = float(params.get("psf_zR", z0))
        excitation = tttrlib.SimGrid.gaussian_lorentzian(w0, zR, ext_xy, ext_z, spacing, 1.0)
    elif psf_type in ("radial", "numeric", "measured"):
        excitation = tttrlib.SimGrid.numeric_from_file(
            str(params["psf_file"]),
            r_step=float(params.get("psf_r_step", spacing)),
            z_step=float(params.get("psf_z_step", spacing)),
            extent_xy=ext_xy, extent_z=ext_z, spacing=spacing,
        )
    elif psf_type == "analytic_gaussian3d":
        excitation = tttrlib.SimGrid.analytic_gaussian3d(w0, z0, 1.0)
    elif psf_type == "gaussian3d":
        excitation = tttrlib.SimGrid.gaussian3d(w0, z0, ext_xy, ext_z, spacing, 1.0)
    else:
        raise ValueError(
            f"unknown psf_type {psf_type!r}; expected one of gaussian3d, "
            f"analytic_gaussian3d, gaussian_lorentzian, radial"
        )

    settings = tttrlib.SimIntegrator()
    settings.dt = dt
    settings.n_channels = nc
    settings.n_ph_max = int(params.get("N_ph_max", 1_000_000))
    settings.max_windows = int(params.get("max_windows", 0))
    settings.seed_diffusion = int(params.get("rmt1seed", 12345))
    settings.seed_emission = int(params.get("rmt2seed", 54321))
    settings.n_microtime_channels = int(params.get("N_tac_channels", 4096))
    settings.microtime_resolution = float(params.get("tac_dt", 0.004069))
    settings.laser_period = float(params.get("laser_period", 13.596))

    # Opt-in throughput knobs (native tttrlib Sim* engine; PRD-007). Guarded with hasattr so
    # an older tttrlib without them still runs — the flag is simply ignored there.
    _throughput = (
        ("per_molecule_skip", "per_molecule_skip", bool, False),
        ("coast_safety", "coast_safety", float, 3.0),
        ("min_coast_windows", "min_coast_windows", int, 8),
        ("focus_threshold", "focus_threshold", float, 1e-3),
        ("fast_grid_bbox", "fast_grid_bbox", bool, False),
        ("independent_molecules", "independent_molecules", bool, False),
        ("active_margin", "active_margin", float, 0.0),
    )
    for attr, key, cast, default in _throughput:
        if hasattr(settings, attr):
            setattr(settings, attr, cast(params.get(key, default)))

    return tttrlib.SimEngine(sample, excitation, tttrlib.VectorSimGrid([]), settings)


def generate_spc132_uint32(params: Dict[str, Any]) -> np.ndarray:
    """Run tttrlib and return encoded SPC records as ``uint32`` words.

    Parameters
    ----------
    params : dict
        Acquisition simulation parameter dictionary.

    Returns
    -------
    numpy.ndarray
        Encoded SPC records viewed as unsigned 32-bit words.
    """
    engine = build_engine(params)
    engine.run()
    return encode_records(engine, params)


def encode_records(engine, params: Dict[str, Any]) -> np.ndarray:
    """Encode an already-run ``SimEngine`` as SPC-132 ``uint32`` words.

    Split out from :func:`generate_spc132_uint32` so callers that already ran the
    engine (e.g. the RPC handler, which also needs ``engine.n_photons()``) encode
    without simulating twice.
    """
    import tttrlib

    enc = tttrlib.SimMicrotimeEncoder()
    enc.pulsed_exc = int(params.get("pulsed_exc", 0))
    enc.n_channels = int(params.get("N_channels", 2))
    enc.tw = float(params.get("dt", 0.01))
    enc.ch_conversion = tttrlib.VectorUint16([
        int(v) for v in params.get("ch_conversion", [8, 0, 9, 1, 10, 2])
    ])
    enc.n_microtime_channels = int(params.get("N_tac_channels", 4096))
    enc.microtime_resolution = float(params.get("tac_dt", 0.004069))
    enc.laser_period = float(params.get("laser_period", 13.596))
    # B&H reverse start-stop: the hardware writes `n_channels-1 - micro_time`
    # into the record and every SPC reader un-reverses it on the way back.
    # Encoding without this produced records that decode to a *time-mirrored*
    # decay — a live acquisition window showing a decay that rises to the end
    # of the TAC range and falls off a cliff, which is what the simulated
    # stream looked like until a screenshot was taken of it.
    if hasattr(enc, "reverse_tac"):
        enc.reverse_tac = True

    rng = tttrlib.SimRandom(int(params.get("rmt2seed", 54321)))
    rec = engine.encode(enc, rng)
    b = bytes(bytearray(rec.bytes))
    # SPC-132 records are 4 bytes; view as uint32 words.
    if len(b) % 4:
        b = b[: len(b) - (len(b) % 4)]
    return np.frombuffer(b, dtype=np.uint32).copy()
