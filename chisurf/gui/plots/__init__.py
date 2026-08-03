import chisurf.core.settings
from chisurf.gui import chiplot as cp

cp.configure(
    **chisurf.core.settings.cs_settings['gui']['plot']['pyqtgraph_config']
)

import chisurf.gui.plots.global_fit
try:
    import chisurf.gui.plots.global_tcspc
except Exception:
    pass
from chisurf.gui.plots.distribution import DistributionPlot
from chisurf.gui.plots.lcurve import LCurvePlot
from chisurf.gui.plots.deer_pr import DeerPrCIPlot
from chisurf.gui.plots.fitinfo import *
from chisurf.gui.plots.lineplot import *
from chisurf.gui.plots.parameter_scan import ParameterScanPlot
from chisurf.gui.plots.conditional_scan import ConditionalScanPlot
from chisurf.gui.plots.posterior_graph import PosteriorGraphPlot
from chisurf.gui.plots.sampling_diagnostics import SamplingDiagnosticsPlot
from chisurf.gui.plots.plotbase import *
from chisurf.gui.plots.wr_plot import ResidualPlot
from chisurf.gui.plots.table_plot import FitTablePlot
from chisurf.gui.plots.residual_image import Residual2DPlot
from chisurf.gui.plots.mfd_2d import Mfd2DPlot


def __getattr__(name: str):
    """Lazy-load heavy plotting modules on first access."""
    if name == "molview":
        from chisurf.gui.plots import molview
        return molview
    if name == "proteinMC":
        from chisurf.gui.plots import proteinMC
        return proteinMC
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
