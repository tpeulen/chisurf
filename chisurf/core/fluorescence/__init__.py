import importlib
from typing import Any

import numpy as np

import chisurf.core.settings
from chisurf.core.settings.settings_utils import build_fret_rda_axis

#: Sub-packages imported on first attribute access rather than eagerly. Pulling
#: all of them in unconditionally meant that importing a single reader (e.g.
#: ``chisurf.core.fluorescence.fcs``) also paid for FRET, TCSPC, burst and the
#: scipy/pandas stack behind them, which dominated GUI startup time.
_LAZY_SUBMODULES = (
    "general",
    "decay",
    "intensity",
    "anisotropy",
    "fcs",
    "fret",
    "tcspc",
    "burst",
)


def __getattr__(name: str) -> Any:
    """Import a fluorescence sub-package on first attribute access."""
    if name in _LAZY_SUBMODULES:
        module = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """List module contents including the lazily-imported sub-packages."""
    return sorted({*globals(), *_LAZY_SUBMODULES})


def rebuild_rda_axis_from_settings() -> np.ndarray:
    """Rebuild the R_DA axis from the current fret settings.

    Parameters
    ----------
    None

    Returns
    -------
    np.ndarray
        The R_DA axis array.
    """
    fret_cfg = getattr(chisurf.core.settings, "fret", {}) or {}
    rda_min = fret_cfg.get("rda_min", 1.0)
    rda_max = fret_cfg.get("rda_max", 130.0)
    rda_res = fret_cfg.get("rda_resolution", 96)
    rda_scale = fret_cfg.get("rda_scale", "log")
    axis = build_fret_rda_axis(rda_min, rda_max, rda_res, rda_scale)
    globals()["rda_axis"] = axis
    return axis


try:
    rda_axis = rebuild_rda_axis_from_settings()
except Exception:
    # Final fallback in case settings or axis construction fail
    rda_axis = build_fret_rda_axis(1.0, 130.0, 96, "log")
