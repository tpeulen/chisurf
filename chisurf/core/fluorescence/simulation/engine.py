"""Building a photon-simulator configuration, once instead of at every call site.

The engine is configured by a nested dictionary. Every caller needs roughly the
same skeleton and differs in a handful of values, so each of them used to write
the whole skeleton out — four copies that drifted, and that each restated defaults
the engine already has.

The functions here are deliberately *blocks*, not a configuration object. A caller
composes the dictionary it wants and can put anything in it the engine
understands; nothing here hides a key or invents one. The engine validates what it
is given and refuses keys it does not know, so a typo is an error rather than a
default — which means this module does not need to validate anything itself.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np

__all__ = [
    "build_engine",
    "decay_spec",
    "default_config",
    "gaussian_focus",
    "have_simulator",
]


def have_simulator() -> bool:
    """Return whether the photon simulator is importable.

    The TTTR library can be built without it, so every consumer has to ask. This
    is the one place that asks, rather than the four that used to.

    Returns
    -------
    bool
    """
    try:
        import tttrlib
    except Exception:
        return False
    return hasattr(tttrlib, "SimEngine")


def default_config() -> dict[str, Any]:
    """Return the engine's own documented starting configuration.

    Taken from the engine rather than restated here, so a default that changes
    there changes here too instead of silently disagreeing.

    Returns
    -------
    dict
        A fresh, mutable copy.

    Raises
    ------
    RuntimeError
        If the simulator is not available.
    """
    import tttrlib

    if not hasattr(tttrlib, "SimEngine"):
        raise RuntimeError(
            "this build of the TTTR library has no photon simulator; "
            "check chisurf.core.fluorescence.simulation.have_simulator() first"
        )
    return json.loads(tttrlib.SimEngine.default_json())


def settings(**overrides: Any) -> dict[str, Any]:
    """Return a ``settings`` block: the engine's defaults with *overrides* applied.

    Parameters
    ----------
    **overrides
        Any key the engine's ``settings`` accepts — ``dt``, ``n_ph_max``,
        ``n_channels``, ``laser_period``, ``seed_diffusion``/``seed_emission``,
        and the rest. An unknown one is refused by the engine when the
        configuration is built, not silently ignored.

    Returns
    -------
    dict
    """
    block = dict(default_config().get("settings", {}))
    block.update({k: v for k, v in overrides.items() if v is not None})
    return block


def gaussian_focus(
    w0: float = 0.3,
    z0: float = 2.0,
    *,
    extent_xy: float = 2.0,
    extent_z: float = 4.0,
    spacing: float = 0.1,
    analytic: bool = False,
    amplitude: float = 1.0,
) -> dict[str, Any]:
    """Return an excitation/detection field block for a separable 3-D Gaussian.

    The focus nearly every ChiSurf simulation uses. A real confocal detection
    volume is better described by the engine's ``gaussian_lorentzian`` field, and
    a measured PSF by its ``radial`` one — both are reached by writing that
    dictionary directly, which is why this returns a plain dict rather than
    wrapping the choice.

    Parameters
    ----------
    w0, z0 : float
        Lateral and axial 1/e² radii, µm.
    extent_xy, extent_z, spacing : float
        The sampled lattice, µm. Ignored when *analytic*.
    analytic : bool
        Evaluate the Gaussian in closed form instead of on a lattice: exact and
        memory-free, at the cost of a function call per step.
    amplitude : float
        Peak value.

    Returns
    -------
    dict
    """
    if analytic:
        return {"type": "analytic_gaussian3d", "w0": float(w0), "z0": float(z0),
                "amplitude": float(amplitude)}
    return {
        "type": "gaussian3d", "w0": float(w0), "z0": float(z0),
        "extent_xy": float(extent_xy), "extent_z": float(extent_z),
        "spacing": float(spacing), "amplitude": float(amplitude),
    }


def decay_spec(
    amplitudes,
    lifetimes,
    *,
    n_bins: int = 4096,
    dt: float = 0.008,
    irf=None,
    t0: float = 0.0,
) -> dict[str, Any]:
    """Return a micro-time ``decay`` block for a species or for the background.

    One grammar serves both, so a scattered-light background is written the way it
    is measured — a lifetime and a prompt — rather than as a hand-built array.

    Parameters
    ----------
    amplitudes, lifetimes : array_like
        The multi-exponential spectrum. Lifetimes in ns.
    n_bins : int
        Micro-time channels in the pattern.
    dt : float
        Micro-time bin width, ns.
    irf : array_like, optional
        Instrument response to convolve the spectrum with.
    t0 : float
        Shift of the whole pattern within the laser period, ns — how a PIE delay
        channel is placed.

    Returns
    -------
    dict
    """
    block: dict[str, Any] = {
        "amplitudes": [float(a) for a in np.atleast_1d(amplitudes)],
        "lifetimes": [float(t) for t in np.atleast_1d(lifetimes)],
        "n_bins": int(n_bins),
        "dt": float(dt),
    }
    if t0:
        block["t0"] = float(t0)
    if irf is not None:
        block["irf"] = [float(v) for v in np.asarray(irf).ravel()]
    return block


def build_engine(config: dict[str, Any]):
    """Return a configured photon simulator.

    A thin call, kept so that every ChiSurf caller reaches the engine through one
    import and so the availability check has somewhere to live. The engine refuses
    a configuration it cannot make sense of — an unknown key, or one rate matrix
    without the other — so there is nothing to validate here.

    Parameters
    ----------
    config : dict
        As built from the blocks in this module, or written out directly.

    Returns
    -------
    tttrlib.SimEngine

    Raises
    ------
    RuntimeError
        If the simulator is not available.
    ValueError
        Propagated from the engine when the configuration is not valid.
    """
    import tttrlib

    if not hasattr(tttrlib, "SimEngine"):
        raise RuntimeError(
            "this build of the TTTR library has no photon simulator; "
            "check chisurf.core.fluorescence.simulation.have_simulator() first"
        )
    return tttrlib.SimEngine.from_dict(config)
