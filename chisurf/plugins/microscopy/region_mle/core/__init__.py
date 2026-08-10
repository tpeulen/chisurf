"""Qt-free computational core for region-wise MLE lifetime analysis."""

from __future__ import annotations

from .region_mle import (
    ProgressCallback,
    RegionMleResult,
    RegionMleSettings,
    build_irf_vv_vh,
    compute_g_factor,
    fit_regions,
    fit_regions_from_files,
    region_photon_indices,
    region_preview,
    resolve_labels,
)

__all__ = [
    "RegionMleResult",
    "RegionMleSettings",
    "ProgressCallback",
    "build_irf_vv_vh",
    "compute_g_factor",
    "fit_regions",
    "fit_regions_from_files",
    "resolve_labels",
    "region_photon_indices",
    "region_preview",
]
