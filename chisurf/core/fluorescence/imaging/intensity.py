"""Read CLSM photon-count maps without the legacy 16-bit overflow."""

from __future__ import annotations

from typing import Any

import numpy as np


def clsm_intensity_counts(clsm: Any) -> np.ndarray:
    """Return full-width per-pixel photon counts as float64.

    tttrlib's historical ``get_intensity()`` accessor can expose a 16-bit
    wrapped buffer. Prefer its 32-bit count accessor whenever it exists; keep
    the old call/property only for tttrlib versions that predate that API.
    """
    getter = getattr(clsm, "get_intensity_u32", None)
    if callable(getter):
        values = getter()
    else:
        getter = getattr(clsm, "get_intensity", None)
        values = getter() if callable(getter) else clsm.intensity
    return np.asarray(values, dtype=np.float64)
