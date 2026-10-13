"""Screenshot grabs for guides 39 (parameter uncertainty) and 53 (reusing results).

make_screenshots.py style: uses the module constants ``FIG``, ``_SPC_FILE`` and
``_grab`` of that file; the ``__main__`` block below supplies them when run
standalone.
"""

from __future__ import annotations

import os
import pathlib
import tempfile

import numpy as np
from common import _SPC_FILE, FIG, _grab, _pump  # noqa: F401,E402


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


def _page_host(page, width=900, height=620):
    """*page* on a fit-window surface, as the fit window draws it (emtk)."""
    from emtk.qt_host import ControlHost

    from chisurf.emtk.fit_pages.surface import make_surface

    surface = make_surface()
    surface.add_page("0:" + type(page).name, type(page).name, lambda: page)
    host = ControlHost(surface)
    host.resize(width, height)
    host._keep = (surface, page)
    host.show()
    return host


def _grab_39_posterior_plots():
    """Dependence tab of the posterior graph and the rank tab of chain diagnostics, after sampling."""
    from qtpy import QtWidgets

    from chisurf.emtk.fit_pages.pages.posterior_graph import PosteriorGraphPlot
    from chisurf.emtk.fit_pages.pages.sampling_diagnostics import SamplingDiagnosticsPlot

    fit = _quadratic_fit_39(sample=True)
    graph = PosteriorGraphPlot(fit)
    graph.update()
    graph.tabs.select(1)  # Dependence
    host = _page_host(graph)
    _pump(0.3)
    _grab(host, "39_posterior_dependence.png")

    diag = SamplingDiagnosticsPlot(fit)
    diag.update()
    host = _page_host(diag)
    _pump(0.3)
    _grab(host, "39_chain_diagnostics.png")
    diag.tabs.select(1)
    host.repaint()
    _pump(0.3)
    _grab(host, "39_chain_ess.png")
    QtWidgets.QApplication.instance().processEvents()


_BURST_FIXTURE_53 = pathlib.Path(
    "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/burstwise_All 0.1000#15"
)


def _grab_53_bva_unchanged():
    """Native Burst Analysis on step 4 (BVA): computed once, then Run again -> 'Unchanged'.

    The fixture burst folder (10 BH SPC-132 files of a DNA sample) is copied to a
    scratch directory first, because BVA writes ``bv4/`` and its stamp beside the
    bursts. The detector setup is handed over explicitly (green 0/8, red 1/9).
    """
    import shutil

    from emtk.testing import Driver
    from guides_26_36 import SM_DNA_SETUP
    from screenshots.emtk_shot import app_from, wait

    work = pathlib.Path(tempfile.mkdtemp(prefix="g53-")) / _BURST_FIXTURE_53.name
    shutil.copytree(_BURST_FIXTURE_53.resolve(), work)
    # The tables name their measurements relative to the folder's parent.
    for spc in _BURST_FIXTURE_53.parent.resolve().glob("m*.spc"):
        shutil.copy2(spc, work.parent / spc.name)
    hub = app_from("burst_analysis")
    driver = Driver(hub, (1400, 860))
    driver.frame(2)
    hub.context.channel_settings = SM_DNA_SETUP
    hub.context.setup_name = "SPC-132 sm-DNA"
    hub.context.raw_files = sorted(work.parent.glob("m*.spc"))
    hub.context.set_burst_folder(work)
    bva = hub.select("bva")
    driver.frame(3)
    # Arriving at the step starts a preview; let it finish.
    wait(driver, lambda: not bva.controller.running, timeout=900)
    bva.controller.run()
    wait(driver, lambda: not bva.controller.running, timeout=900)
    print("bva:", bva.model.status_text, flush=True)
    bva.controller.run()  # nothing changed: kept, with Restart outlined
    driver.frame(4)
    print("bva again:", bva.model.status_text, flush=True)
    driver.screenshot(FIG / "53_bva_unchanged.png")
    print("wrote 53_bva_unchanged.png", flush=True)


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
