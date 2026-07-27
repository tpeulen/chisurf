"""RICS-precision calculator: how well a planned raster scan would measure D."""

from .core import (
    PrecisionSweep,
    default_dwell_range,
    line_time_for,
    predict,
    sweep_dwell,
)

__all__ = [
    "PrecisionSweep",
    "predict",
    "sweep_dwell",
    "line_time_for",
    "default_dwell_range",
]
