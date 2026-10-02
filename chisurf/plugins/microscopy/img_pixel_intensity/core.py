"""Qt-free compute for the Intensity imaging plugin (delegates to shared core)."""

from __future__ import annotations

from typing import Any

from chisurf.core.fluorescence.imaging import build_clsm, intensity_maps


def compute_intensity(filename: str, channels=(0,)) -> dict[str, Any]:
    """Compute the per-pixel summed-intensity map from a TTTR imaging file.

    Parameters
    ----------
    filename : str
        TTTR imaging file (PTU/HT3/...); CLSM markers auto-detected.
    channels : sequence of int
        Detector channel(s).

    Returns
    -------
    dict
        ``{"maps": {"intensity": (ny, nx)}, "shape": (ny, nx)}``.
    """
    from chisurf.core.fio.staging import open_tttr
    from chisurf.core.fluorescence.imaging import clsm_intensity_counts

    tttr = open_tttr(filename)
    clsm = build_clsm(tttr, channels=tuple(channels))
    stack = clsm_intensity_counts(clsm)
    maps = intensity_maps(stack)
    return {"maps": maps, "shape": maps["intensity"].shape}
