"""Screenshot grabs for guides 39 (parameter uncertainty) and 53 (reusing results).

make_screenshots.py style: uses the module constants ``FIG``, ``_SPC_FILE`` and
``_grab`` of that file; the ``__main__`` block below supplies them when run
standalone.
"""

from __future__ import annotations

from common import FIG, _SPC_FILE, _grab, _pump  # noqa: F401,E402

import os
import pathlib
import tempfile

import numpy as np


def _quadratic_fit_39(sample=True):
    """The guide-39 fit: c + a x + b x^2 with a normal prior on c, sampled 4 x 5000."""
    import chisurf.core.data
    import chisurf.core.fitting.fit
    import chisurf.core.models.parse
    from chisurf.core.fitting.priors import LogNormalPrior, NormalPrior

    rng = np.random.default_rng(0)
    x = np.linspace(1.0, 2.0, 96)
    y = 1.0 + 2.0 * x + 0.5 * x**2 + rng.normal(0.0, 0.02, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.full_like(y, 0.02))
    data.name = "quadratic.txt"
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = "c+a*x+b*x**2"
    fit.model.find_parameters()
    fit.run()
    params = fit.model.parameters_all_dict
    params["c"].prior = NormalPrior(mu=1.0, sigma=0.05)
    params["b"].prior = LogNormalPrior(mu=0.0, sigma=1.0)
    fit.run()
    if sample:
        chisurf.core.fitting.fit.sample_fit(
            fit=fit,
            target_directory=tempfile.mkdtemp(prefix="g39-sampling-"),
            method="blocked",
            steps=5000,
            thin=1,
            n_runs=4,
        )
    return fit


def _grab_39_sampling_controls():
    """Fit controller (Sample, gear) beside the gear's sampling/fitting settings form."""
    from qtpy import QtWidgets

    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.widgets.fitting import FittingControllerWidget
    from chisurf.gui.widgets.fitting.fitting_controls import OptimizationSettingsModel

    fit = _quadratic_fit_39(sample=False)
    host = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(host)
    left = QtWidgets.QVBoxLayout()
    left.addWidget(QtWidgets.QLabel("<b>Fit controller</b>"))
    controller = FittingControllerWidget(fit=fit)
    left.addWidget(controller)
    left.addStretch(1)
    lay.addLayout(left, 1)
    right = QtWidgets.QVBoxLayout()
    right.addWidget(QtWidgets.QLabel("<b>⚙ Sampling and fitting settings</b>"))
    model = OptimizationSettingsModel()
    form = AutoForm(model, parent=host)
    model.set_rebuild_callback(form.rebuild)
    right.addWidget(form)
    right.addStretch(1)
    lay.addLayout(right, 1)
    host.resize(1280, 470)
    host._keep = (controller, form, model, fit)
    _grab(host, "39_sampling_controls.png")


def _grab_39_posterior_plots():
    """Dependence tab of the posterior graph and the rank tab of chain diagnostics, after sampling."""
    from qtpy import QtWidgets

    from chisurf.gui.plots.posterior_graph import PosteriorGraphPlot
    from chisurf.gui.plots.sampling_diagnostics import SamplingDiagnosticsPlot

    fit = _quadratic_fit_39(sample=True)
    graph = PosteriorGraphPlot(fit)
    graph.update()
    graph.tabs.setCurrentIndex(1)  # Dependence
    graph.resize(900, 620)
    _grab(graph, "39_posterior_dependence.png")

    diag = SamplingDiagnosticsPlot(fit)
    diag.update()
    diag.resize(900, 620)
    _grab(diag, "39_chain_diagnostics.png")
    diag.tabs.setCurrentIndex(1)
    _grab(diag, "39_chain_ess.png")
    QtWidgets.QApplication.instance().processEvents()


_BURST_FIXTURE_53 = pathlib.Path(
    "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/burstwise_All 0.1000#15"
)


def _pump_53(seconds):
    """Process events for *seconds* so worker results reach the GUI thread."""
    import time

    from qtpy.QtWidgets import QApplication

    end = time.time() + seconds
    while time.time() < end:
        QApplication.instance().processEvents()
        time.sleep(0.02)


def _grab_53_bva_unchanged():
    """Burst workflow on step 4 (BVA): computed once, then Run again -> 'Unchanged'.

    The fixture burst folder (10 BH SPC-132 files of a DNA sample) is copied to a
    scratch directory first, because BVA writes ``bv4/`` and its stamp beside the
    bursts.
    """
    import shutil

    from chisurf.gui.chiplot import backends as chiplot_backends
    from chisurf.plugins.burst.burst_analysis.gui.tool import BurstAnalysisTool

    # The default emtk backend drops the error-bar extents on set_data and the
    # paint pass then raises, losing the density image and the axes (known
    # defect); the pyqtgraph backend draws the BVA plot whole.
    chiplot_backends.set_backend("pyqtgraph")

    work = pathlib.Path(tempfile.mkdtemp(prefix="g53-")) / _BURST_FIXTURE_53.name
    shutil.copytree(_BURST_FIXTURE_53.resolve(), work)
    # The tables name their measurements relative to the folder's parent.
    for spc in _BURST_FIXTURE_53.parent.resolve().glob("m*.spc"):
        shutil.copy2(spc, work.parent / spc.name)
    # Undefined count rates are written as empty cells; the BVA reader types
    # such a column as text in the files that have one and as float64 in the
    # files that do not, and then refuses to stack them (known defect). Keep the
    # four tables whose green columns are all numeric.
    for name in ("m001", "m002", "m003", "m005", "m007", "m009"):
        (work / "bi4_bur" / f"{name}.bur").unlink()
    tool = BurstAnalysisTool()
    tool.resize(1400, 860)
    tool.workflow_context.burst_folder = work
    tool.workflow_context.bur_files = sorted((work / "bi4_bur").glob("*.bur"))
    tool.workflow_context.raw_files = sorted(work.parent.glob("m*.spc"))
    tool.show()
    _pump_53(0.5)
    row = next(i for i, p in enumerate(tool.panels) if p.get("role") == "bva")
    tool.nav_list.setCurrentRow(row)
    _pump_53(1.0)
    bva = tool._panel_widget(row)
    # Arriving at the step starts a preview; let it finish.
    for _ in range(600):
        _pump_53(0.1)
        if getattr(bva, "_task", None) is None:
            break
    # compute_bva appends its columns to the cached burst table in place, so a
    # second computation on that table fails (known defect). Drop the cache so
    # the Run below reads the folder afresh.
    bva._burst_df = bva._tttrs = None
    bva._run_analysis()
    for _ in range(600):
        _pump_53(0.1)
        if getattr(bva, "_task", None) is None:
            break
    _pump_53(1.0)
    bva._run_analysis()  # nothing changed: kept, with Restart outlined
    _pump_53(0.5)
    tool._keep = (bva, work)
    _grab(tool, "53_bva_unchanged.png")
    chiplot_backends.set_backend("emtk")


if __name__ == "__main__":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("MPLBACKEND", "Agg")
    import sys

    from qtpy.QtWidgets import QApplication

    import chisurf.core.settings  # noqa: F401

    app = QApplication.instance() or QApplication([])
    FIG = pathlib.Path(os.environ.get("FIGDIR", "docs/guides/figures"))
    _SPC_FILE = pathlib.Path("test") / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"

    def _grab(widget, name):
        widget.show()
        QApplication.instance().processEvents()
        widget.grab().save(str(FIG / name))
        print("wrote", name)

    for name in sys.argv[1:]:
        globals()[name]()
