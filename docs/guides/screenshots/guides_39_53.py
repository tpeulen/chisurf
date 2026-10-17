"""Screenshot grabs for guides 39 (parameter uncertainty) and 53 (reusing results).

Run through ``run.py`` (or standalone with the ``__main__`` block below); ``FIG`` and
``_SPC_FILE`` come from ``common.py``.
"""

from __future__ import annotations

import os
import pathlib
import tempfile

import numpy as np
from common import _SPC_FILE, FIG, _pump  # noqa: F401,E402


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


def _page_driver(page, width=900, height=620):
    """*page* on a fit-window surface, as the fit window draws it (emtk), in a Driver."""
    from emtk.testing import Driver

    from chisurf.emtk.fit_pages.surface import make_surface

    surface = make_surface()
    surface.add_page("0:" + type(page).name, type(page).name, lambda: page)
    driver = Driver(surface, (width, height))
    driver._keep = (surface, page)
    driver.frame(3)
    return driver


def _grab_39_posterior_plots():
    """Dependence tab of the posterior graph and the rank tab of chain diagnostics, after sampling."""
    from chisurf.emtk.fit_pages.pages.posterior_graph import PosteriorGraphPlot
    from chisurf.emtk.fit_pages.pages.sampling_diagnostics import SamplingDiagnosticsPlot

    fit = _quadratic_fit_39(sample=True)
    graph = PosteriorGraphPlot(fit)
    graph.update()
    graph.tabs.select(1)  # Dependence
    driver = _page_driver(graph)
    driver.screenshot(FIG / "39_posterior_dependence.png")
    print("wrote 39_posterior_dependence.png")

    diag = SamplingDiagnosticsPlot(fit)
    diag.update()
    driver = _page_driver(diag)
    driver.screenshot(FIG / "39_chain_diagnostics.png")
    print("wrote 39_chain_diagnostics.png")
    diag.tabs.select(1)
    driver.frame(3)
    driver.screenshot(FIG / "39_chain_ess.png")
    print("wrote 39_chain_ess.png")


def _global_fit_39(n_datasets=4, seed=0):
    """Four quadratics ``c + a x^2``, each with its own ``c``, all sharing ``a`` (guide 39, section 11)."""
    import chisurf.core.data
    import chisurf.core.fitting.fit
    import chisurf.core.models.parse

    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 5.0, 48)
    curves = []
    for k in range(n_datasets):
        y = (3.0 + 0.3 * k) + 1.2 * x**2 + rng.normal(0.0, 0.05, x.size)
        curve = chisurf.core.data.DataCurve(x=x, y=y, ey=np.full_like(y, 0.05))
        curve.name = f"data {k + 1}"
        curves.append(curve)
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup(curves),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    for f in fit:
        f.fit_range = 0, len(f.model.y)
        f.model.func = "c+a*x**2"
        f.model.find_parameters()
    fit._model.find_parameters()
    master = [p for p in fit[0].model.parameters_all if p.name == "a"][0]
    for local in list(fit)[1:]:
        [p for p in local.model.parameters_all if p.name == "a"][0].link = master
    for local in fit:
        local.model.find_parameters()
    fit._model.find_parameters()
    fit.run(local_first=False)
    return fit


def _weak_component_fit_39(seed=1):
    """A bi-exponential ``a exp(-x/t) + b exp(-x/s)`` whose second amplitude ``b`` is weak."""
    import chisurf.core.data
    import chisurf.core.fitting.fit
    import chisurf.core.models.parse

    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 12.0, 160)
    y = 1.5 * np.exp(-x / 0.7) + 0.15 * np.exp(-x / 3.2)
    ey = np.full_like(y, 0.01)
    data = chisurf.core.data.DataCurve(x=x, y=y + rng.normal(0.0, 0.01, x.size), ey=ey)
    data.name = "weak_component.txt"
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = "a*exp(-x/s)+b*exp(-x/t)"
    fit.model.find_parameters()
    start = {"a": 1.4, "s": 0.8, "b": 0.2, "t": 3.0}
    for name, p in fit.model.parameters_all_dict.items():
        if name in start:
            p.value = start[name]
    fit.run()
    return fit


def _grab_39_structure_whatif():
    """Structure tab of a four-dataset global fit, and What-if with the re-fit check (emtk pages)."""
    from chisurf.emtk.fit_pages.pages.conditional_scan import ConditionalScanPlot
    from chisurf.emtk.fit_pages.pages.posterior_graph import PosteriorGraphPlot

    out = pathlib.Path(__file__).resolve().parents[2] / "images"
    fit = _global_fit_39()
    graph = PosteriorGraphPlot(fit)
    graph.update()
    graph.tabs.select(0)  # Structure
    host = _page_host(graph)
    _pump(0.3)
    host.grab().save(str(out / "posterior_graph_structure.png"))
    print("wrote posterior_graph_structure.png", flush=True)

    fit = _weak_component_fit_39()
    page = ConditionalScanPlot(fit)
    page.update()
    page.set_parameter(page.parameters.index("t"))
    page.set_held(1.0)
    page._check_exact()
    host = _page_host(page, 1050, 740)
    _pump(0.5)
    host.grab().save(str(out / "whatif_non_gaussian.png"))
    print("wrote whatif_non_gaussian.png", page._validity, flush=True)


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
    import sys

    import chisurf.core.settings  # noqa: F401

    os.environ.setdefault("MPLBACKEND", "Agg")
    for name in sys.argv[1:]:
        globals()[name]()
