#!/usr/bin/env python
"""Generate GUI screenshots for the TTTR-LUT tutorial (headless, offscreen).

Grabs real ChiSurf widgets via ``QWidget.grab()`` under the offscreen Qt platform
so the tutorial shows the actual UI, not mockups. Run with the project on the
path and an offscreen platform::

    QT_QPA_PLATFORM=offscreen PYTHONPATH=. python docs/tutorials/make_screenshots.py

Requires the full GUI environment (the arm64 conda env), unlike
``make_figures.py`` which only needs matplotlib.
"""

from __future__ import annotations

import json
import os
import pathlib
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
from qtpy.QtWidgets import QApplication  # noqa: E402

import chisurf.core.settings  # noqa: E402,F401

FIG = pathlib.Path(__file__).parent / "figures"
FIG.mkdir(exist_ok=True)


def _grab(widget, name):
    """Show *widget*, process events, and save a PNG grab into ``figures/``."""
    widget.show()
    QApplication.instance().processEvents()
    widget.grab().save(str(FIG / name))
    print("wrote", name)


def _grab_fcs_model_editor():
    """Grab the composable FCS model editor (AutoForm) for the FCS guide."""
    import numpy as np

    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.data import DataCurve
    from chisurf.core.models.fcs.general import GeneralFCSModel
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    x = np.logspace(-3, 3, 60)  # 1 us .. 1 s, in ms
    data = DataCurve(name="synthetic-fcs", load_filename_on_init=False, y=np.zeros_like(x), x=x)
    fit = fit_mod.Fit(model_class=GeneralFCSModel, data=data)
    editor = build_model_editor(fit.model)
    editor.resize(560, 760)
    _grab(editor, "fcs_model_editor.png")


def _grab_tcspc_lifetime_editor():
    """Grab the TCSPC multi-exponential lifetime model editor for the TCSPC guide."""
    import numpy as np

    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.data import DataCurve
    from chisurf.core.models.tcspc.lifetime import LifetimeModel
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    x = np.linspace(0, 25, 256)  # ns
    data = DataCurve(x=x, y=np.exp(-x / 4.0) + 1.0)
    fit = fit_mod.Fit(model_class=LifetimeModel, data=data)
    editor = build_model_editor(fit.model)
    editor.resize(560, 760)
    _grab(editor, "tcspc_lifetime_editor.png")


def _grab_parameter_link_menu():
    """Grab the parameter link menu (three levels) for the linking reference.

    Submenus are separate popups, so each level is grabbed on its own and the
    chain is composed side by side — a single grab of the top menu would show
    only the fit list.
    """
    import numpy as np
    from qtpy import QtGui

    import chisurf
    from chisurf.core.data import DataCurve, DataCurveGroup
    from chisurf.core.fitting.fit import FitGroup
    from chisurf.gui.widgets.fitting.fitting_client import install_fitting_client
    from chisurf.gui.widgets.fitting.parameter_widgets import (
        FittingParameterProxyController,
    )
    from chisurf.gui.widgets.models.tcspc.lifetime import LifetimeModelWidget
    from chisurf.server.services.fits import get_fit_info, list_fits
    from chisurf.server.session import SessionState

    def make(name, n_curves=1):
        x = np.linspace(0.1, 25, 128)
        y = 1000.0 * np.exp(-x / 4.0) + 1.0
        curves = [
            DataCurve(x=x, y=y, ey=np.sqrt(y), name=f"{name}-{i}") for i in range(n_curves)
        ]
        return FitGroup(
            data=DataCurveGroup(curves, name=name), model_class=LifetimeModelWidget
        )

    fits = [make("Donor-only"), make("FRET-global", n_curves=2)]
    state = SessionState(fits=fits)

    class _Direct:
        def call(self, method, params):
            if method == "fit.list":
                return list_fits(state)
            return get_fit_info(state, **params)

    install_fitting_client(_Direct())
    chisurf.fits = fits
    try:
        parameter = fits[0].model.parameters_all_dict["sc"]
        menu = FittingParameterProxyController(parameter).build_link_menu()
        menu.setTitle("Link sc to")
        fit_menu = next(a.menu() for a in menu.actions() if a.menu() is not None)
        group_menu = next(
            a.menu() for a in fit_menu.actions()
            if a.menu() is not None and a.text() == "Convolve"
        )

        app = QApplication.instance()
        shots = []
        for popup in (menu, fit_menu, group_menu):
            popup.show()
            app.processEvents()
            popup.resize(popup.sizeHint())
            app.processEvents()
            shots.append(popup.grab())

        gap = 18
        canvas = QtGui.QPixmap(
            sum(s.width() for s in shots) + gap * (len(shots) - 1),
            max(s.height() for s in shots),
        )
        canvas.fill(QtGui.QColor("#f4f4f4"))
        painter = QtGui.QPainter(canvas)
        x_offset = 0
        for shot in shots:
            painter.drawPixmap(x_offset, 0, shot)
            x_offset += shot.width() + gap
        painter.end()
        canvas.save(str(FIG / "parameter_link_menu.png"))
    finally:
        install_fitting_client(None)


def _grab_pda_editor():
    """Grab the PDA (Gaussian-distance) model editor for the PDA guide."""
    import numpy as np
    from scipy import stats

    import chisurf.core.fitting.fit as fit_mod
    import chisurf.core.fluorescence.tcspc as tcspc
    from chisurf.core.data import DataCurve
    from chisurf.core.models.pda2c.pdagauss import Pda2cGaussianDistanceModel
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    nmax, nmin = 60, 5
    n = np.arange(nmax + 1)
    ps = stats.poisson.pmf(n, mu=20.0).astype(float)
    ps /= ps.sum()
    s1s2 = np.zeros((nmax + 1, nmax + 1), dtype=float)
    for N in range(nmin, nmax + 1):
        g = np.arange(N + 1)
        s1s2[g, N - g] += ps[N] * stats.binom.pmf(g, N, 0.6) * 1000.0
    ny, nx = s1s2.shape
    rr, cc = np.indices((ny, nx))
    y = s1s2.ravel(order="C")
    pda = {
        "maximum_number_of_photons": nmax,
        "minimum_number_of_photons": nmin,
        "minimum_time_window_length": 2e-3,
        "channels": ([0], [1]),
        "s1s2": s1s2,
        "ps": ps,
        "row_indices": rr.ravel().tolist(),
        "col_indices": cc.ravel().tolist(),
        "ndim": 2,
        "shape": (ny, nx),
        "size": int(y.size),
        "tttr_indices": None,
    }
    data = DataCurve(
        name="synthetic-pda",
        load_filename_on_init=False,
        pda=pda,
        y=y,
        x=np.arange(y.size),
        ey=tcspc.counting_noise(y),
    )
    fit = fit_mod.Fit(model_class=Pda2cGaussianDistanceModel, data=data)
    editor = build_model_editor(fit.model)
    editor.resize(560, 760)
    _grab(editor, "pda_model_editor.png")


def _grab_pda3c_exchange_panel():
    """Grab the PDA3c exchange-scheme panel for the three-colour guide.

    Driven into a realistic state — three species and a linear 1-2-3 chain — so
    the grid shows a scheme built by *zeroing* the transitions it does not have,
    which is the point the figure has to make.
    """
    import numpy as np
    from qtpy.QtWidgets import QAbstractButton

    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.experiments.pda3c import Pda3cSimulatorReader
    from chisurf.core.models.pda3c.pda3c import Pda3cModel
    from chisurf.gui.autoform import AutoForm

    data = Pda3cSimulatorReader(n_bursts=200, seed=3).read()[0]
    model = fit_mod.Fit(model_class=Pda3cModel, data=data).model
    model.species.append(r_gr=68.0, r_bg=62.0, r_br=80.0)
    model.species.append(r_gr=78.0, r_bg=72.0, r_br=90.0)
    model.dynamic = True
    # A linear chain 1 <-> 2 <-> 3: k13 and k31 left at zero.
    model.rate_matrix = np.array([[0.0, 120.0, 0.0],
                                  [80.0, 0.0, 300.0],
                                  [0.0, 90.0, 0.0]])
    model.find_parameters()

    editor = AutoForm(model)
    # Open the exchange panel and fold the distance tables away, so the figure
    # is the scheme rather than the rows above it.
    for button in editor.findChildren(QAbstractButton):
        if "Exchange" in button.text():
            button.click()
        elif button.isCheckable() and button.isChecked() and "Distance" in button.text():
            button.click()
    editor.resize(600, 620)
    _grab(editor, "pda3c_exchange.png")


def _grab_burst_browser():
    """Grab the Burst Browser (per-burst table + E/S histograms) on real .bur data."""
    import glob

    from chisurf.plugins.burst.burst_browser import BurstBrowserWidget

    folders = glob.glob(
        "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/burstwise_All*/bi4_bur"
    )
    if not folders:
        print("SKIP _grab_burst_browser: no sample .bur folder")
        return
    widget = BurstBrowserWidget()
    widget.resize(1100, 720)
    widget.load_folder(folders[0])
    QApplication.instance().processEvents()
    _grab(widget, "burst_browser.png")


def _grab_2cde_tool():
    """Grab the FRET-2CDE tool plot (dynamics score vs proximity ratio)."""
    import numpy as np
    import pandas as pd

    from chisurf.plugins.burst.burst_2cde.core import computation as core
    from chisurf.plugins.burst.burst_2cde.gui.tool import BurstTwoCdeTool

    rng = np.random.default_rng(0)
    # two static populations (low FRET-2CDE ~ 10) + a dynamic bridge (elevated 2CDE)
    pr = np.concatenate(
        [rng.normal(0.15, 0.04, 400), rng.normal(0.75, 0.04, 400), rng.uniform(0.2, 0.7, 200)]
    )
    cde = np.concatenate(
        [rng.normal(10, 1.5, 400), rng.normal(10, 1.5, 400), rng.normal(28, 6, 200)]
    )
    df = pd.DataFrame(
        {
            "First File": ["f0"] * pr.size,
            "Proximity Ratio": np.clip(pr, 0, 1),
            core.COLUMN_FRET_2CDE: cde,
        }
    )
    tool = BurstTwoCdeTool(embedded=True)
    tool._draw(df, core.COLUMN_FRET_2CDE)
    tool.resize(720, 520)
    _grab(tool, "burst_2cde_tool.png")


def _grab_drift_tool():
    """Grab the drift-correction workspace and its projections (guide 43).

    A synthetic stack with a *known* linear drift, so the trace in the figure is
    the ground truth and the before/after projections differ visibly. The real
    confocal test image is a stable acquisition with sub-pixel drift, which
    would make an honest but entirely uninformative screenshot.
    """
    from chisurf.core.fio.image import imwrite
    from chisurf.gui.autoform.sections.builtin import ImageMapWidget
    from chisurf.plugins.microscopy.img_drift.gui.tool import ImgDriftTool

    rng = np.random.default_rng(1)
    yy, xx = np.mgrid[0:64, 0:64]
    base = sum(
        90.0 * np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * 3.0 ** 2))
        for cy, cx in rng.integers(8, 56, size=(14, 2))
    ) + rng.poisson(4.0, (64, 64))
    stack = np.stack(
        [np.roll(base, (2 * k, -k), axis=(0, 1)) for k in range(12)]
    ).astype(np.float32)

    tmp = pathlib.Path(tempfile.mkdtemp()) / "drift_demo.tif"
    imwrite(tmp, stack, axes="TYX")

    tool = ImgDriftTool()
    tool.model.set_filename(str(tmp))
    tool.model.compute()
    tool.resize(1400, 820)
    tool.show()
    tool._refresh()
    QApplication.instance().processEvents()
    _grab(tool, "drift_workspace.png")

    # The projections live on a tab that is not current, so their widgets have
    # never been laid out; grabbing them now yields a collapsed sliver. Raise
    # the tab and let Qt settle first.
    from qtpy.QtWidgets import QTabBar

    for bar in tool.findChildren(QTabBar):
        for i in range(bar.count()):
            if bar.tabText(i) == "Projection":
                bar.setCurrentIndex(i)
    QApplication.instance().processEvents()

    targets = {"before_image": "drift_before.png", "after_image": "drift_after.png"}
    for widget in tool.findChildren(ImageMapWidget):
        name = targets.get(getattr(widget, "_target", ""))
        if name:
            widget.resize(420, 400)
            QApplication.instance().processEvents()
            _grab(widget, name)


def _grab_precision_tool():
    """Grab the RICS-precision calculator (guide 45).

    The tool needs no data at all -- it answers from the settings alone -- so
    this is simply the default acquisition, predicted. The default deliberately
    sits *beside* the optimum rather than on it, so the figure shows the marker
    off the minimum, which is the thing the tool exists to tell you.
    """
    from chisurf.plugins.calculator.rics_precision.gui.tool import RicsPrecisionTool

    tool = RicsPrecisionTool()
    tool.model.compute()
    tool.resize(1400, 760)
    tool.show()
    tool._refresh()
    QApplication.instance().processEvents()
    _grab(tool, "precision_workspace.png")


def _grab_frc_tool():
    """Grab the FRC resolution panel (guide 51).

    Driven with the real confocal photon stream in the test data, so the figure
    shows an honest curve on honest photons: a 256x256 scan of a cell whose
    even/odd frame halves stop agreeing a few pixels in. The pixel size is the
    80 nm of that acquisition, so the headline is in nanometres.
    """
    from chisurf.plugins.microscopy.img_frc.gui.tool import ImgFrcTool

    tool = ImgFrcTool()
    tool.model.set_filename("test/data/clsm/PQ_Olympus_MFIS.ht3")
    tool.model.pixel_size_nm = 80.0
    tool.model.compute()
    tool.resize(1500, 850)
    tool.show()
    tool._refresh()
    QApplication.instance().processEvents()
    _grab(tool, "frc_workspace.png")


def _grab_burst_gs_tool():
    """Grab the photon-by-photon kinetics tool (guide 49).

    Fitted on simulated photons from a molecule with *known* rates, so the
    figure can be read against the truth: 3000 and 1000 s^-1 at E = 0.25 / 0.75.
    Two grabs — the report with the fitted numbers, and the transition-time
    scan, which is the part of the tool with no binned equivalent.
    """
    from qtpy.QtWidgets import QTabWidget

    from chisurf.plugins.burst.burst_gs.gui.tool import BurstGsTool

    tool = BurstGsTool()
    model = tool.model
    model.use_simulation = True
    model.sim_n_bursts = 250
    model.sim_photons_per_burst = 200
    model.scan_transition_time = True
    model.transit_points = 30
    model.compute()
    tool.resize(1440, 860)
    tool.show()
    tool._refresh()
    QApplication.instance().processEvents()
    _grab(tool, "burst_gs_workspace.png")

    for tabs in tool.findChildren(QTabWidget):
        labels = [tabs.tabText(i) for i in range(tabs.count())]
        if "Transition time" in labels:
            tabs.setCurrentIndex(labels.index("Transition time"))
            QApplication.instance().processEvents()
            tool._refresh()
            QApplication.instance().processEvents()
            _grab(tool, "burst_gs_transition_time.png")
            break


def _grab_tracking_tool():
    """Grab the particle-tracking tool (guide 50).

    Tracked on a simulated movie with a *known* diffusion coefficient, so the
    figure can be read against the truth: 8 particles at D = 0.5 px^2/frame.
    Two grabs -- the report beside the movie with detections marked, and the
    trajectories, which is the view that reveals identity swaps.
    """
    from qtpy.QtWidgets import QTabWidget

    from chisurf.plugins.microscopy.img_tracking.gui.tool import ImgTrackingTool

    tool = ImgTrackingTool()
    model = tool.model
    model.use_simulation = True
    model.sim_n_frames = 60
    model.sim_size = 256
    model.sim_n_particles = 8
    model.sim_diffusion = 0.5
    model.max_distance = 4.0
    model.min_track_length = 15
    model.n_bootstrap = 150
    model.compute()
    tool.resize(1500, 900)
    tool.show()
    tool._refresh()
    QApplication.instance().processEvents()
    _grab(tool, "tracking_workspace.png")

    for tabs in tool.findChildren(QTabWidget):
        labels = [tabs.tabText(i) for i in range(tabs.count())]
        if "Trajectories" in labels:
            tabs.setCurrentIndex(labels.index("Trajectories"))
            QApplication.instance().processEvents()
            tool._refresh()
            QApplication.instance().processEvents()
            _grab(tool, "tracking_trajectories.png")
            break


def _grab_coloc_tool():
    """Grab the colocalization workspace and its intensity scatter (guide 38)."""
    # Import the tool first: it pulls the GUI packages in the order the app does
    # (importing ``autoform`` cold trips a circular import in the widget layer).
    from chisurf.gui.autoform.sections.builtin import ImageMapWidget
    from chisurf.plugins.microscopy.img_coloc.gui.tool import ImgColocTool

    source = pathlib.Path("test/data/clsm/PQ_Olympus_MFIS.ht3")
    if not source.is_file():
        raise FileNotFoundError(source)
    tool = ImgColocTool()
    # A detector setup as the Detector-Def tool defines it: named windows as channels.
    tool.model.apply_setup_settings(
        {
            "name": "confocal",
            "detectors": {
                "green": {"chs": [0, 1], "micro_time_ranges": []},
                "red": {"chs": [4, 5], "micro_time_ranges": []},
            },
        }
    )
    tool.model.filename = str(source)
    tool.model.channel_a, tool.model.channel_b = "green", "red"
    tool.model.auto_background = True
    tool.model.ccf_max_shift = 12
    tool.model.compute()
    tool.resize(1500, 900)
    tool.show()
    tool._refresh()
    QApplication.instance().processEvents()
    _grab(tool, "coloc_workspace.png")

    for widget in tool.findChildren(ImageMapWidget):
        if getattr(widget, "_target", "") == "histogram_image":
            widget.resize(560, 480)
            _grab(widget, "coloc_scatter.png")
            break

    # Object regime: synthetic puncta, because the real confocal test image is one
    # continuous cell and would segment into a single object.
    _grab_coloc_objects(tool)


def _grab_coloc_objects(tool):
    """Grab the object map + distance histogram on synthetic puncta (guide 38)."""
    import tempfile

    from chisurf.core.fio.image import imwrite
    from chisurf.gui.autoform.sections.builtin import ImageMapWidget, PlotWidget

    shape = (160, 160)
    yy, xx = np.mgrid[: shape[0], : shape[1]]

    def puncta(centres, sigma=2.2, amplitude=120.0):
        """Return an image with Gaussian puncta at *centres*."""
        image = np.zeros(shape, dtype=float)
        for cy, cx in centres:
            image += amplitude * np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * sigma**2))
        return image

    rng = np.random.default_rng(3)
    centres = [tuple(p) for p in rng.integers(12, 148, size=(28, 2))]
    partners = [(cy + 1, cx) for cy, cx in centres[:18]]
    strangers = [tuple(p) for p in rng.integers(12, 148, size=(6, 2))]
    a = puncta(centres) + rng.normal(0, 2, shape)
    b = puncta(partners + strangers) + rng.normal(0, 2, shape)

    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "puncta.tif"
        imwrite(path, np.stack([a, b]).astype(np.float32), axes="CYX")
        tool.model.object_analysis = True
        tool.model.object_distance = 3.0
        tool.model.filename = str(path)
        tool.model.channel_a, tool.model.channel_b = "ch0", "ch1"
        tool.model.compute()
        QApplication.instance().processEvents()
        for widget in tool.findChildren(ImageMapWidget):
            if getattr(widget, "_target", "") == "object_map_image":
                widget.refresh()
                widget.resize(520, 480)
                _grab(widget, "coloc_objects.png")
                break
        for widget in tool.findChildren(PlotWidget):
            if getattr(getattr(widget, "_section", None), "source", "") == "object_distance_series":
                widget.refresh()
                widget.resize(620, 380)
                _grab(widget, "coloc_object_distances.png")
                break


def _grab_accurate_fret_tool():
    """Grab the accurate-FRET workspace and its E-S / E-lifetime plots (guide 39)."""
    import tempfile

    import pyqtgraph as pg

    from chisurf.core.fluorescence.fret.lines import static_fret_line
    from chisurf.plugins.burst.accurate_fret.gui.tool import AccurateFretTool

    gamma, alpha, beta, delta = 0.65, 0.08, 1.4, 0.06
    tau_d0, r0 = 4.0, 52.0
    line = static_fret_line(tau_d0, r0=r0, sigma=6.0)
    rng = np.random.default_rng(7)
    dd, da, aa, tau = [], [], [], []
    for efficiency, n in ((0.28, 1500), (0.72, 1500)):
        photons = rng.poisson(400, n).astype(float)
        dd.append(rng.poisson((1 - efficiency) * photons))
        aa.append(rng.poisson(beta * gamma * photons))
        da.append(
            rng.poisson(
                gamma * efficiency * photons
                + alpha * (1 - efficiency) * photons
                + delta * beta * gamma * photons
            )
        )
        tau.append(rng.normal(float(line.lifetime_at(efficiency)), 0.15, n))
    photons = rng.poisson(400, 500).astype(float)  # donor-only
    dd.append(rng.poisson(photons))
    da.append(rng.poisson(alpha * photons))
    aa.append(rng.poisson(2.0, 500))
    tau.append(rng.normal(tau_d0, 0.15, 500))
    photons = rng.poisson(400, 500).astype(float)  # acceptor-only
    dd.append(rng.poisson(2.0, 500))
    aa.append(rng.poisson(beta * gamma * photons))
    da.append(rng.poisson(delta * beta * gamma * photons))
    tau.append(np.full(500, np.nan))

    table = pathlib.Path(tempfile.gettempdir()) / "accurate_fret_demo_bursts.csv"
    np.savetxt(
        table,
        np.column_stack([np.concatenate(c).astype(float) for c in (dd, da, aa, tau)]),
        delimiter=",",
        comments="",
        header="Green Count Rate (KHz),Red Count Rate (KHz),S delayed yellow (kHz),Tau (green)",
    )

    tool = AccurateFretTool()
    tool.model.donor_lifetime = tau_d0
    tool.model.forster_radius = r0
    tool.model.n_bootstrap = 20
    tool.model.set_filename(str(table))
    tool.model.compute()
    tool._refresh()
    tool.resize(1500, 900)
    _grab(tool, "accurate_fret_tool.png")

    # The two diagnostic plots on their own, large enough to read.
    for name, plot in zip(
        ("accurate_fret_es.png", "accurate_fret_etau.png"),
        tool.findChildren(pg.PlotWidget),
    ):
        plot.resize(820, 560)
        _grab(plot, name)
    table.unlink(missing_ok=True)


def _grab_chimol_viewer():
    """Figures for the molecular-viewer guide: a ray-traced render and the panel.

    Two mechanisms, because neither covers both:

    * the **panel** is an ordinary widget grab;
    * the **render** goes through chimol's own ray tracer, which needs no GPU and
      no display -- the same path the plugin's visual tests use. A GL grab is not
      an option: ``QWidget.grab()`` reads the backing store and never sees OpenGL
      content, and ``grabFramebuffer`` returns black without a display session, so
      a window grab shows the panels over an empty viewport.

    Note ``objects.widget`` is a **property**; calling it raises ``TypeError``
    rather than doing anything useful.
    """
    import pathlib as _pathlib

    from chisurf.plugins.chimol.chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )
    from chisurf.plugins.chimol.chimol.cmd.command import Cmd

    pdb = _pathlib.Path(
        "test/data/atomic_coordinates/pdb_files/148l.pdb"
    ).resolve()

    window = MolViewPluginWindow()
    window.resize(1180, 700)
    window.show()
    app = QApplication.instance()
    for _ in range(20):
        app.processEvents()
    window._load_structure_from_path(pdb)
    for _ in range(30):
        app.processEvents()

    # -- the object panel, with a couple of derived objects to show rows ------
    panel_cmd = Cmd(window)
    panel_cmd.set_message_callback(lambda _m: None)
    panel_cmd.set_error_callback(lambda m: print("  chimol:", m))
    panel_cmd.do("create peptidoglycan, chain S")
    panel_cmd.do("create ligand, resn NAG")
    for _ in range(30):
        app.processEvents()

    panel = window.objects.widget       # a property, not a method
    panel.resize(900, 250)
    for _ in range(20):
        app.processEvents()
    panel.grab().save(str(FIG / "chimol_objects_panel.png"))
    print("wrote chimol_objects_panel.png")

    # -- the same panel with groups, one open and one collapsed --------------
    panel_cmd.do("create nag, resn NAG")
    panel_cmd.do("group ligands, ligand nag")
    panel_cmd.do("group parts, peptidoglycan")
    panel_cmd.do("group parts, close")
    for _ in range(30):
        app.processEvents()
    panel.resize(900, 250)
    for _ in range(20):
        app.processEvents()
    panel.grab().save(str(FIG / "chimol_groups_panel.png"))
    print("wrote chimol_groups_panel.png")
    # Leave the panel ungrouped: later figures in this function read the same
    # window, and a collapsed group would hide rows they expect to be drawn.
    panel_cmd.do("ungroup ligands")
    panel_cmd.do("ungroup parts")
    panel_cmd.do("delete nag")
    for _ in range(20):
        app.processEvents()

    # -- a ray-traced render, coloured by solvent accessibility ---------------
    # Driven through a bare MolView rather than the plugin window: inside the
    # window `ray` hands the trace to a worker, which a script with no event loop
    # of its own never lets finish ("ray: cancelled").
    import chisurf.core.structure as cs_struct
    from chisurf.plugins.chimol.chimol.io.structure import _read_full_model
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    view = MolView()
    view.resize(900, 650)
    view.add_structure(
        _read_full_model(cs_struct.Structure, pdb),
        name="148l",
        source_path=str(pdb),
    )

    class _Host:
        viewer = view

        def _refresh_objects_from_viewer(self):
            pass

        def windowTitle(self):
            return "chimol"

    cmd = Cmd(_Host())
    cmd.set_message_callback(lambda _m: None)
    cmd.set_error_callback(lambda m: print("  chimol:", m))
    for line in (
        "hide everything",
        "show spheres, all",
        "set dot_solvent, on",
        "set dot_density, 3",
        "get_area all, 1, 1",
        # An explicit range rather than the data's own: the most exposed atom is
        # an outlier, so an automatic range leaves the whole surface reading blue.
        "spectrum b, blue_white_red, all, 0, 25",
        "orient",
        "zoom",
        f"ray {FIG / 'chimol_accessibility.png'}, 900, 650",
    ):
        cmd.do(line)
    print("wrote chimol_accessibility.png")


def _grab_region_editor():
    """The shared region GUI on the CLSM tool: the list and the shapes.

    Real widgets, a synthetic confocal frame, and one region of every kind the
    editor can hold — a painted mask, a drawn ellipse (inverted) and a
    rectangle switched off — so the guide shows what the columns mean.
    """
    from qtpy import QtWidgets

    from chisurf.core.roi import EllipseROI, RectangleROI
    from chisurf.gui.widgets.roi import RegionEditor
    from chisurf.plugins.microscopy.clsm.gui.tool import CLSMPixelSelect

    tool = CLSMPixelSelect()
    model = tool.model

    ny = nx = 128
    yy, xx = np.mgrid[0:ny, 0:nx]

    def blob(cy, cx, r, soft=6.0):
        return 1 / (1 + np.exp((np.hypot(yy - cy, xx - cx) - r) / soft * 4))

    frame = 900 * (blob(64, 64, 46) - blob(64, 64, 38)) + 500 * blob(58, 70, 18) + 25
    model.current_image = np.random.default_rng(3).poisson(frame).astype(float)
    model.selection_mask = np.zeros_like(model.current_image)
    model.selection_mask[20:40, 20:45] = 1.0
    model.notify("image")

    model.add_roi("membrane ring")
    model.regions.add(EllipseROI(70, 58, 18, 18, name="nucleus"), invert=True)
    model.regions.add(RectangleROI(5, 100, 40, 122, name="empty patch"), enabled=False)
    model.regions.combine = "and"

    editor = tool.auto_form.findChild(RegionEditor)
    editor.refresh()
    tool.region_overlay.refresh()
    editor.select("nucleus")
    tool.region_overlay.select("nucleus")

    def raise_tab(title):
        for bar in tool.findChildren(QtWidgets.QTabBar):
            for i in range(bar.count()):
                if bar.tabText(i) == title:
                    bar.setCurrentIndex(i)

    tool.resize(1020, 780)
    tool.show()
    QApplication.instance().processEvents()
    raise_tab("Image")
    QApplication.instance().processEvents()
    _grab(tool, "regions_overlay.png")
    raise_tab("Regions")
    QApplication.instance().processEvents()
    _grab(tool, "regions_list.png")


def _grab_hmm_tool():
    """Hidden-Markov-model tool fitted on a simulated two-state trace."""
    from chisurf.plugins.core.hmm.gui.tool import HmmTool

    rng = np.random.default_rng(0)
    transmat = np.array([[0.985, 0.015], [0.03, 0.97]])
    means = np.array([[18.0], [55.0]])
    states = np.zeros(4000, dtype=int)
    for t in range(1, len(states)):
        states[t] = rng.choice(2, p=transmat[states[t - 1]])
    trace = means[states] + rng.normal(0, 4, size=(len(states), 1))

    tool = HmmTool()
    tool.resize(1280, 860)
    tool.set_traces([trace], ["simulated"])
    tool.model.time_step = 1e-3
    tool.model.n_states = 2
    tool.model.min_states, tool.model.max_states = 1, 4
    tool.show()
    QApplication.instance().processEvents()
    # Run synchronously: the worker thread would not have finished by the grab.
    tool.model.run()
    tool.model.run_scan()
    tool._refresh()
    QApplication.instance().processEvents()
    _grab(tool, "hmm_workspace.png")


def _grab_burst_fusion_tool():
    """Burst-fusion tool on its own demo, whose molecule count is declared.

    Uses the plugin's demo rather than a fixture, so the screenshot in the guide
    shows the same numbers a reader gets by pressing the same button.
    """
    from chisurf.plugins.burst.burst_fusion.gui.tool import BurstFusionTool

    tool = BurstFusionTool()
    tool.resize(1250, 800)
    tool.show()
    QApplication.instance().processEvents()
    tool.load_demo()
    tool.model.threshold = 0.7
    tool.model.fuse()
    QApplication.instance().processEvents()
    _grab(tool, "burst_fusion_curve.png")

    # The proximity-ratio comparison is the payoff, so it gets its own figure.
    from qtpy.QtWidgets import QTabBar

    for bar in tool.findChildren(QTabBar):
        for index in range(bar.count()):
            if bar.tabText(index) == "Proximity ratio":
                bar.setCurrentIndex(index)
                QApplication.instance().processEvents()
                _grab(tool, "burst_fusion_proximity.png")


def main():
    """Generate all guide screenshots."""
    app = QApplication.instance() or QApplication([])  # keep a ref alive  # noqa: F841

    for grab in (
        _grab_fcs_model_editor,
        _grab_tcspc_lifetime_editor,
        _grab_parameter_link_menu,
        _grab_pda_editor,
        _grab_pda3c_exchange_panel,
        _grab_burst_browser,
        _grab_2cde_tool,
        _grab_coloc_tool,
        _grab_drift_tool,
        _grab_precision_tool,
        _grab_burst_gs_tool,
        _grab_burst_fusion_tool,
        _grab_frc_tool,
        _grab_tracking_tool,
        _grab_accurate_fret_tool,
        _grab_hmm_tool,
        _grab_chimol_viewer,
        _grab_region_editor,
    ):
        try:
            grab()
        except Exception as exc:  # keep going; report which grab failed
            print(f"SKIP {grab.__name__}: {exc}")

    # ① Compute LUT — the AutoForm panel with a real flat-light file loaded, so
    # the interactive raw/after plots + draggable region are shown.
    from chisurf.plugins.tttr.tttr_lut_tools.gui.tool import TTRLutToolsWidget

    spc = pathlib.Path("test/data/tttr/BH/132/BH_SPC132.spc")
    tool = TTRLutToolsWidget()
    tool.resize(1120, 760)
    if spc.is_file():
        tool.tac_panel.model.load_files([str(spc)])
        QApplication.instance().processEvents()
    tool.dock_area.setCurrentWidget(tool.tac_panel)
    _grab(tool, "lut_tools_workspace.png")

    # Channel-definition editor with the LUT-handling box.
    from chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_channel_definition import (
        DetectorWizardPage,
    )

    data = {
        "windows": {"prompt": [0, 2048]},
        "detectors": {"green": {"chs": [0, 8]}, "red": {"chs": [1, 9]}},
        "tttr_reading": {
            "file_type": "SPC-130",
            "macro_time_resolution": 1.0,
            "micro_time_resolution": 0.032,
            "micro_time_binning": 1,
        },
        "apply_lut": True,
        "channel_luts": {"0": np.linspace(0, 4096, 4096).tolist()},
        "channel_shifts": {"8": 3},
        "channel_lut_sources": {"0": "uniform.spc"},
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(data, fh)
        setup_json = fh.name
    page = DetectorWizardPage(json_file=setup_json, show_setup_selection=False)
    page.resize(680, 900)
    for box in (page._box_reading, page._box_windows, page._box_detectors, page._box_lut):
        box.set_expanded(box is page._box_detectors or box is page._box_lut)
    _grab(page, "lut_channel_box.png")
    os.unlink(setup_json)

    print("screenshots written to", FIG)


if __name__ == "__main__":
    main()
