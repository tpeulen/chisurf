"""Backward-compatibility shim — the LUT algorithms now live in ``..api``.

The pure math moved to :mod:`chisurf.plugins.tttr.tttr_lut_tools.api.lut` and the
file/tttrlib IO to :mod:`...api.io` as part of the api/cli/gui/rpc split. This
module re-exports the historic names so existing imports keep working.
"""

from __future__ import annotations

from ..api.compute import compute_lut_from_counts, compute_lut_from_files  # noqa: F401
from ..api.io import expand_globs, load_microtimes, save_lut  # noqa: F401
from ..api.lut import (  # noqa: F401
    autodetect_linear_region,
    build_linearization_table,
    find_longest_true_run,
    histogram_micro,
    infer_n_bins,
    rolling_mean,
    stochastic_rebin_ntac,
)

__all__ = [
    "autodetect_linear_region",
    "build_linearization_table",
    "compute_lut_from_counts",
    "compute_lut_from_files",
    "expand_globs",
    "find_longest_true_run",
    "histogram_micro",
    "infer_n_bins",
    "load_microtimes",
    "rolling_mean",
    "save_lut",
    "stochastic_rebin_ntac",
]
