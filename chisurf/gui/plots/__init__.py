"""Plot classes and submodules loaded only when their public names are used."""

from importlib import import_module

import chisurf.core.settings
from chisurf.gui import chiplot as cp

cp.configure(**chisurf.core.settings.cs_settings["gui"]["plot"]["pyqtgraph_config"])

_EXPORTS = {
    "ConditionalScanPlot": "conditional_scan",
    "DeerPrCIPlot": "deer_pr",
    "DistributionPlot": "distribution",
    "DropTable": "fitinfo",
    "FitInfo": "fitinfo",
    "LCurvePlot": "lcurve",
    "LinePlot": "lineplot",
    "LinePlotControl": "lineplot",
    "Mfd2DPlot": "mfd_2d",
    "MfdMarginalPlot": "mfd_2d",
    "MfdMapPlot": "mfd_map",
    "ParameterScanPlot": "parameter_scan",
    "Plot": "plotbase",
    "PosteriorGraphPlot": "posterior_graph",
    "Residual2DPlot": "residual_image",
    "SamplingDiagnosticsPlot": "sampling_diagnostics",
    "FitTablePlot": "table_plot",
    "ResidualPlot": "wr_plot",
}
_MODULES = frozenset(_EXPORTS.values()) | {
    "global_fit",
    "global_tcspc",
    "molview",
    "proteinMC",
}
__all__ = list(_EXPORTS)


def __getattr__(name: str):
    """Resolve and cache a public plot class or submodule on first access."""
    if name in _EXPORTS:
        value = getattr(import_module(f"{__name__}.{_EXPORTS[name]}"), name)
    elif name in _MODULES:
        value = import_module(f"{__name__}.{name}")
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value
    return value


def __dir__():
    """Include unresolved public names in introspection without importing them."""
    return sorted(set(globals()) | set(__all__) | _MODULES)
