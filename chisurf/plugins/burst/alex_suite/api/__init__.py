"""Qt-free ALEX Suite API: histograms, titration and the legacy CSV export.

Everything the ALEX Suite computes that is not already a ChiSurf analysis lives
here, so the GUI panels, the CLI and a plain script all call the same functions.
"""

from chisurf.plugins.burst.alex_suite.api.histograms import (
    Corrections,
    EsHistograms,
    Thresholds,
    burst_efficiency_stoichiometry,
    es_histograms,
    load_channels,
)
from chisurf.plugins.burst.alex_suite.api.legacy_export import (
    LegacyExport,
    Metadata,
    write_legacy_export,
)
from chisurf.plugins.burst.alex_suite.api.titration import (
    BindingFit,
    Condition,
    SharedGaussianFit,
    Stack,
    TitrationResult,
    build_stack,
    fit_binding,
    fit_shared_gaussians,
    run_titration,
)

__all__ = [
    "BindingFit",
    "Condition",
    "Corrections",
    "EsHistograms",
    "LegacyExport",
    "Metadata",
    "SharedGaussianFit",
    "Stack",
    "Thresholds",
    "TitrationResult",
    "build_stack",
    "burst_efficiency_stoichiometry",
    "es_histograms",
    "fit_binding",
    "fit_shared_gaussians",
    "load_channels",
    "run_titration",
    "write_legacy_export",
]
