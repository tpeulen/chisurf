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
import shutil
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# LLTF's fitter calls plt.show(); keep it off-screen.
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np  # noqa: E402
from qtpy.QtWidgets import QApplication  # noqa: E402

import chisurf.core.settings  # noqa: E402,F401

FIG = pathlib.Path(__file__).parent / "figures"
FIG.mkdir(exist_ok=True)
_SPC_FILE = pathlib.Path("test") / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"
_PDB_148L = pathlib.Path("test/data/atomic_coordinates/pdb_files/148l.pdb").resolve()
_T4L = pathlib.Path("chisurf/plugins/modelling/fret/examples/olga_t4l")
_T4L_TOP = _T4L / "3GUN_NMSim_cl-rep-001.pdb"
_T4L_DCD = _T4L / "3GUN_NMSim_cl-rep_894.dcd"


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
    from chisurf.core.models.description import tcspc_lifetime as LifetimeModel
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
    from chisurf.core.models.description import tcspc_lifetime
    from chisurf.server.services.fits import get_fit_info, list_fits
    from chisurf.server.session import SessionState

    def make(name, n_curves=1):
        x = np.linspace(0.1, 25, 128)
        y = 1000.0 * np.exp(-x / 4.0) + 1.0
        curves = [
            DataCurve(x=x, y=y, ey=np.sqrt(y), name=f"{name}-{i}") for i in range(n_curves)
        ]
        return FitGroup(
            data=DataCurveGroup(curves, name=name), model_class=tcspc_lifetime
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

    from chimol.commands.command import Cmd

    pdb = _pathlib.Path(
        "test/data/atomic_coordinates/pdb_files/148l.pdb"
    ).resolve()

    # -- the object panel: RETIRED UPSTREAM, so nothing is grabbed here ------
    # `chimol_objects_panel.png` and `chimol_groups_panel.png` were grabs of a
    # Qt dock reached through `window.objects.widget`. That dock no longer
    # exists: chimol's WebGPU port moved the object list into the viewport and
    # marked the dock permanently hidden ("Objects is permanently hidden (the
    # list is in the viewport)", chimol/hosts/qt/window.py). The attribute is
    # gone, so this section raised AttributeError and took the accessibility
    # figure below down with it.
    #
    # The two figures are NOT regenerated from the viewport overlay either,
    # because that overlay does not yet list the objects: with obj2/obj3/obj4 in
    # `viewer.objects` it still draws only `all` and `sele`, before and after
    # `refresh_objects()`. Regenerating now would replace two figures that show
    # the old UI correctly with two that show the new UI wrongly.
    # Tracked in okf/references/known-issues.md.

    # -- a ray-traced render, coloured by solvent accessibility ---------------
    # Driven through a bare MolView rather than the plugin window: inside the
    # window `ray` hands the trace to a worker, which a script with no event loop
    # of its own never lets finish ("ray: cancelled").
    import chisurf.core.structure as cs_struct
    from chimol.core.viewer.viewer import Viewer
    from chimol.io.structure import _read_full_model

    view = Viewer()
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
        # `orient`/`zoom` with no target resolve nothing here and fail with
        # "nothing to orient" -- the viewer auto-names the object (obj2), it is
        # not called after the file. Naming `all` is what makes them frame it.
        "orient all",
        "zoom all",
        f"ray {FIG / 'chimol_accessibility.png'}, 900, 650",
    ):
        cmd.do(line)
    print("wrote chimol_accessibility.png")


def _grab_chimol_biofilm():
    """The simulated biofilm, two frames of it, ray-traced.

    Generated the way the demo generates it -- the agent simulator is run and
    ChiMOL opens its RMF -- so the figure cannot drift from what the demo shows.
    Traced rather than grabbed for the reason the accessibility figure is: the
    ray tracer needs no GL context, and this script has no display.

    A frame early in the run and a frame at the end, because the point of the
    demo is the difference between them.
    """
    from chimol.commands.command import Cmd
    from chimol.io.structure import load_structure_payload
    from chimol.plugins.demos.material import generated_demo_path
    from chimol.core.viewer.viewer import Viewer

    rmf = generated_demo_path("biofilm_growth.rmf")
    _reader, payload = load_structure_payload(str(rmf))

    view = Viewer()
    view.resize(900, 650)
    view.add_payload(payload, name="biofilm", source_path=str(rmf))

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
        "bg_color white",
        # As the demo does it: the camera must not follow the frame, or the
        # early figure is framed on the centroid of a colony a fraction of the
        # size and the two pictures cannot be compared.
        "set movie_recenter, off",
        "as spheres",
        "frame 60",
        "turn x, -75",
        "zoom all, 2, 1",
    ):
        cmd.do(line)
    for frame, name in ((30, "chimol_biofilm_early.png"), (60, "chimol_biofilm_late.png")):
        cmd.do(f"frame {frame}")
        cmd.do(f"ray {FIG / name}, 900, 650")
        print(f"wrote {name}")


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


def _grab_ndx_gaussian_panel():
    """ndX's Gaussian-fit panel, with two populations actually fitted.

    Drives the real window: two simulated populations, one component seeded on
    each, one centre held, then the EM. The screenshot therefore shows fitted
    numbers in the parameter table (and the greyed-out held value), not a mockup
    of one.
    """
    import sys

    import pandas as pd
    from qtpy.QtCore import QEventLoop, Qt, QTimer

    root = pathlib.Path(__file__).resolve().parents[2]
    ndx = str(root / "modules" / "ndxplorer")
    if ndx not in sys.path:
        sys.path.insert(0, ndx)
    from ndxplorer.core.data_source import DataSource
    from ndxplorer.core.plot_main import NDXplorer

    app = QApplication.instance()

    def settle(ms=80):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec_()
        app.processEvents()

    blobs = [(0.25, 0.35, 0.04, 0.05), (0.70, 0.70, 0.06, 0.03)]
    rng = np.random.default_rng(0)
    points = np.vstack(
        [
            np.column_stack([rng.normal(cx, sx, 3000), rng.normal(cy, sy, 3000)])
            for cx, cy, sx, sy in blobs
        ]
    )
    frame = pd.DataFrame(
        {"E": points[:, 0], "S": points[:, 1], "z": rng.normal(0, 1, len(points))}
    )
    columns = list(frame.columns)

    win = NDXplorer(data_source=DataSource(columns, frame))
    win.resize(1200, 800)
    win.show()
    app.processEvents()
    control = win.plot_control
    control.update(update_comboboxes=True, update_plots=False)
    control.comboBoxSelX.setCurrentIndex(columns.index("E"))
    control.comboBoxSelY.setCurrentIndex(columns.index("S"))
    control.comboBoxSelZ.setCurrentIndex(columns.index("z"))
    win.update_plots()
    for _ in range(10):
        settle(100)
        if win._histogram.get("2d") is not None:
            break

    panel = win.gaussian_fit
    for cx, cy, sx, sy in blobs:
        panel._append_gaussian_row((cx + 0.04, cy - 0.04), np.diag([sx ** 2, sy ** 2]))
    # The second population's centre is held, to show what a held parameter
    # looks like (greyed, not editable) beside the fitted ones.
    panel.group.parameters_of(1)["x"].fixed = True
    panel._redraw_gaussian_overlays_from_table()
    settle(100)
    panel.on_fit_2d_gaussian()
    settle(150)

    dock = win.dockWidget_Fit
    dock.setFloating(True)
    dock.resize(430, 420)
    settle(120)
    _grab(dock, "ndxplorer_gaussian_panel.png")
    win.close()


def _grab_kappa2_tool():
    """Grab the k2 distribution calculator in the restricted-dye state (guide 61)."""
    from chisurf.plugins.calculator.kappa2_dist import Kappa2Dist

    tool = Kappa2Dist()
    # Not the defaults: a visibly restricted donor, so the panel shows a real
    # distance penalty rather than the near-zero one a mobile dye gives.
    tool._model.r_Dinf = 0.15
    tool._model.r_Ainf = 0.20
    tool._form.sync_fields()
    tool._do_compute()
    tool.resize(560, 820)
    _grab(tool, "kappa2_tool.png")


def _grab_ask_the_documentation():
    """The help browser's Ask panel, beside the page it cited.

    The conversation is placed directly rather than run: the answer would come
    from whichever model the machine happens to have configured, so the
    screenshot would differ on every machine and could not be regenerated. The
    *rendering* — the answer layout, the citation list, the warning when
    nothing was read — is what the figure documents, and that is ours.
    """
    from chisurf.core.agent import doc_index
    from chisurf.plugins.core.help.gui.tool import HelpWidget

    widget = HelpWidget()
    widget.resize(1500, 900)
    widget.show()
    QApplication.instance().processEvents()

    page = doc_index.resolve("docs/concepts/accurate_fret.md")
    if page is not None:
        widget.navigate(pathlib.Path(page))
    widget.show_ask_panel()
    QApplication.instance().processEvents()

    panel = widget.ask_panel
    panel._turns.append(panel._question_html("What does the gamma correction factor do?"))
    panel._turns.append(
        panel._answer_html(
            {
                "text": (
                    "The γ factor corrects the raw green/red photon ratio for the two "
                    "things that make the two channels not comparable: the detection "
                    "efficiencies of the donor and acceptor detection paths, and the "
                    "fluorescence quantum yields of the two dyes.\n\n"
                    "Without it the proximity ratio is not a FRET efficiency, and the "
                    "populations in an E–S histogram sit in the wrong place. All four "
                    "factors and where each comes from are in "
                    "[The four factors]"
                    "(docs/concepts/accurate_fret.md#The four factors); the workflow "
                    "that determines them is "
                    "[Accurate FRET corrections](docs/guides/41_accurate_fret.md)."
                ),
                "pages": [
                    {
                        "document": "docs/concepts/accurate_fret.md",
                        "title": "Accurate FRET: correction factors, FRET lines, and "
                                 "where they come from",
                        "type": "Concept",
                        "section": "The four factors",
                    },
                    {
                        "document": "docs/guides/41_accurate_fret.md",
                        "title": "Accurate FRET: automatic correction factors",
                        "type": "Guide",
                        "section": "",
                    },
                ],
            }
        )
    )
    panel._render()
    # Resized last: the panel is added to the splitter while the window is
    # already shown, and an earlier resize is undone by the layout settling.
    widget.resize(1500, 900)
    QApplication.instance().processEvents()
    _grab(widget, "ask_the_documentation.png")


def _grab_maxent_decay():
    """MaxEnt decay on a decay whose lifetime distribution is known.

    The decay is built from a *bimodal* distribution (peaks at 1.1 ns and
    3.6 ns) rather than two discrete exponentials, because that is the case MEM
    exists for and the case the figure has to show it solving.

    **The fixture is integrated over each channel, not sampled at its edge.**
    A TCSPC channel counts arrivals during the bin, which is what the solver's
    forward model reproduces; a plain ``np.convolve`` of the decay with the IRF
    point-samples at the channel's left edge and lands **half a channel early**
    (measured: rms 6.5e-3 against a 64x-oversampled reference, versus 2.5e-4 for
    the solver). Feeding that in makes MEM fit a half-channel offset it cannot
    express, costs 0.5 in chi2r, and pushes the answer into the timeshift --
    which reads as a ChiSurf defect and is not one.
    """
    import chisurf
    from chisurf.core.fluorescence.decay_fit_model import build_lifetime_fit
    from chisurf.gui.widgets.fitting.fitting_client import install_fitting_client
    from chisurf.plugins.fluorescence_decay.maxent_decay.gui.gui import MaxentDecayWidget

    n, dt, oversample = 512, 0.0323, 32
    # Build on a fine grid and average each channel down: that integration is
    # what a channel does, and what the solver's design matrix assumes.
    t_fine = (np.arange(n * oversample) + 0.5) * (dt / oversample)
    irf_fine = np.exp(-0.5 * ((t_fine - 1.0) / 0.12) ** 2)
    irf = irf_fine.reshape(n, oversample).mean(1)
    irf /= irf.sum()

    taus = np.linspace(0.2, 6.0, 200)
    weights = np.exp(-0.5 * ((taus - 1.1) / 0.25) ** 2)
    weights += 0.8 * np.exp(-0.5 * ((taus - 3.6) / 0.55) ** 2)
    weights /= weights.sum()
    pure_fine = (weights[:, None] * np.exp(-t_fine[None, :] / taus[:, None])).sum(0)
    conv = np.convolve(pure_fine, irf_fine / irf_fine.sum())[: n * oversample]
    conv = conv.reshape(n, oversample).mean(1)
    rng = np.random.default_rng(3)
    decay = rng.poisson(3.0e4 * conv / conv.max()).astype(float)

    fit = build_lifetime_fit(
        decay, bin_width=dt, irf=irf, n_components=2,
        start_bin=int(1.0 / dt), stop_bin=n - 1,
    )
    fit.data.name = "MEM-demo-decay"
    install_fitting_client(None)
    chisurf.fits = [fit]

    tool = MaxentDecayWidget()
    tool.resize(1400, 900)
    tool.show()
    QApplication.instance().processEvents()
    tool._on_refresh_data()
    # The default grid reaches down to where no decay is left to describe; its
    # first bin then collects an edge spike that dwarfs both real peaks.
    tool.spin_tau_min.setValue(0.4)
    tool.spin_tau_max.setValue(7.0)
    tool.spin_tau_bins.setValue(120)
    # Nuisance fitting is deliberately OFF: with the fixture discretised
    # correctly there is nothing for it to find (it recovers a timeshift of
    # -0.014 channels and improves chi2r by 0.0006, for 160x the run time).
    tool._run_mem()
    QApplication.instance().processEvents()
    _grab(tool, "maxent_distribution.png")


def _grab_global_view():
    """The parameter network with one lifetime shared across three fits.

    Three fits with a *link* between them, not three unrelated ones: the guide
    is about the shared parameter, and an unlinked network has nothing in it
    that a list of fits would not have shown.
    """
    import chisurf
    from chisurf.core.data import DataCurve, DataCurveGroup
    from chisurf.core.fitting.fit import FitGroup
    from chisurf.gui.widgets.fitting.fitting_client import install_fitting_client
    from chisurf.core.models.description import tcspc_lifetime
    from chisurf.plugins.core.globalview.gui.tool import GraphWizard

    def make(name, tau, n_curves=1):
        x = np.linspace(0.1, 25, 256)
        y = 1000.0 * np.exp(-x / tau) + 1.0
        curves = [
            DataCurve(x=x, y=y, ey=np.sqrt(y), name=f"{name}-{i}") for i in range(n_curves)
        ]
        return FitGroup(
            data=DataCurveGroup(curves, name=name), model_class=tcspc_lifetime
        )

    fits = [make("Donor-only", 4.0), make("FRET-low", 2.4, 2), make("FRET-high", 1.3)]
    install_fitting_client(None)
    chisurf.fits = fits
    source = fits[0].model.parameters_all_dict["t0"]
    for fit in fits[1:]:
        fit.model.parameters_all_dict["t0"].link = source

    tool = GraphWizard(fit_list=fits, remember_layout=False)
    tool.resize(1150, 760)
    tool.model.rebuild(force=True)
    _grab(tool, "globalview_network.png")
    tool.model.representation = "factor graph"
    tool.model.relayout()
    _grab(tool, "globalview_factor_graph.png")


def _grab_ebfret_tool():
    """ebFRET after an analysis of its simulated demo: K = 4 with the Viterbi path.

    The run is the real backend loop on the demo's forty four-state traces; the
    window then shows the four-state model, so the Viterbi overlay and the
    posterior curves -- what the guide explains -- are on screen.
    """
    import time

    from chisurf.plugins.burst.burst_ebfret.gui.tool import EbfretTool

    tool = EbfretTool()
    tool.resize(1200, 820)
    tool.show()
    tool._load_demo()
    client = tool.client
    client.set("max_states", 4)
    client.run()
    while client.status()["running"]:
        time.sleep(0.2)
    client.set("ensemble", 4)
    client.set("series", 3)
    for _ in range(4):
        tool._tick()
        QApplication.instance().processEvents()
    _grab(tool, "ebfret_gui.png")


def _grab_pto_inspector():
    """A container holding an instrument file and two results derived from it.

    A `.pto` with only the raw file in it has no provenance to draw, so the
    fixture writes a burst table derived from the instrument data and a decay
    derived from those bursts -- the two-step lineage the guide describes.
    """
    import shutil

    from chisurf.core.fio.pto import Measurement
    from chisurf.plugins.core.pto_inspector.gui.tool import PtoInspectorTool

    ptu = pathlib.Path("test/data/clsm/Leica_SP5.ptu")
    if not ptu.is_file():
        raise FileNotFoundError(f"instrument test data missing: {ptu}")

    work = pathlib.Path(tempfile.mkdtemp()) / "sample"
    work.mkdir()
    raw = work / "measurement.ptu"
    shutil.copy(ptu, raw)

    n_bursts = 128
    rng = np.random.default_rng(1)
    with Measurement.create(raw) as measurement:
        bursts = measurement.put_table(
            "bursts",
            {
                "First Photon": np.arange(n_bursts, dtype=np.int64),
                "Np": rng.integers(40, 400, n_bursts).astype(np.int32),
            },
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"M": 10, "T": 0.0005, "N": 20},
            derived_from=measurement.instrument_uid,
        )
        t = np.arange(256.0) * 0.032
        measurement.put_curve(
            "decay", t, 3.0e4 * np.exp(-t / 3.2) + 5.0,
            artifact_kind="tcspc_decay",
            operation_type="tcspc_histogram_computation",
            x_units="nanoseconds", y_units="counts",
            derived_from=bursts,
        )

    tool = PtoInspectorTool()
    tool.resize(1400, 900)
    tool.model.set_filename(str(work / "measurement.pto"))
    QApplication.instance().processEvents()
    _grab(tool, "pto_inspector.png")


def _grab_irf_estimator():
    """A blind IRF estimate on a decay that reaches baseline.

    50 ns of range at tau = 4 ns, deliberately: the method fits a *truncated*
    exponential, and with only a few lifetimes of measured tail the offset C is
    degenerate against the exponential -- tau comes back low and the recovered
    IRF grows a tail that is regularisation ringing, not an instrument
    response. The guide says so; this figure is the case where the assumption
    holds.
    """
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui.tool import (
        IRFEstimatorTool,
    )

    n, dt = 500, 0.1002
    t = np.arange(n) * dt
    irf = np.exp(-0.5 * ((t - 5.0) / 0.5) ** 2)
    irf /= irf.sum()
    conv = np.convolve(np.exp(-t / 4.0), irf)[:n]
    rng = np.random.default_rng(5)
    decay = rng.poisson(4.0e4 * conv / conv.max() + 8.0).astype(float)

    tool = IRFEstimatorTool()
    tool.resize(1300, 860)
    tool.show()
    QApplication.instance().processEvents()
    tool._process_decay_data(np.column_stack((t, decay)), dt)
    tool.data_info_label.setText(
        "simulated decay \u2014 \u03c4 = 4.0 ns, IRF FWHM 1.18 ns at 5.0 ns"
    )
    QApplication.instance().processEvents()
    tool.estimate_irf()
    QApplication.instance().processEvents()
    _grab(tool, "irf_estimator.png")


def _grab_console():
    """The console answering a question about two fits that were really run.

    The console echoes nothing on its own -- the prompt shows whatever is in
    the input buffer -- so a transcript has to be "typed" into the buffer
    before each line is executed, or the figure shows bare ``In []:`` prompts.
    """
    import chisurf
    from chisurf.core.fluorescence.decay_fit_model import build_lifetime_fit
    from chisurf.gui.chinsole.widget import Chinsole
    from chisurf.gui.widgets.fitting.fitting_client import install_fitting_client

    n, dt = 512, 0.0323
    t = np.arange(n) * dt
    irf = np.exp(-0.5 * ((t - 1.0) / 0.12) ** 2)
    irf /= irf.sum()
    rng = np.random.default_rng(7)
    fits = []
    for name, tau in (("Donor-only", 3.8), ("FRET-high", 1.6)):
        conv = np.convolve(np.exp(-t / tau), irf)[:n]
        decay = rng.poisson(3.0e4 * conv / conv.max() + 5.0).astype(float)
        fit = build_lifetime_fit(
            decay, bin_width=dt, irf=irf, n_components=2,
            start_bin=int(1.2 / dt), stop_bin=n - 1,
        )
        fit.data.name = name
        fit.run()
        fits.append(fit)
    install_fitting_client(None)
    chisurf.fits = fits

    console = Chinsole()
    console.resize(1000, 320)
    console.show()
    QApplication.instance().processEvents()
    console.push({"cs": chisurf, "np": np})
    for line in (
        "cs.fits",
        "fit = cs.fits[0]",
        "fit.chi2r",
        "[(f.name, round(f.chi2r, 3)) for f in cs.fits]",
        "sorted(fit.model.parameters_all_dict)[:6]",
    ):
        console.view.set_input_buffer(line)
        QApplication.instance().processEvents()
        console.execute(line)
        QApplication.instance().processEvents()
    _grab(console, "console.png")


def _grab_ai_assistant():
    """The assistant in the mode that operates ChiSurf.

    The conversation is placed rather than run, for the same reason as
    :func:`_grab_ask_the_documentation`: a live answer depends on whichever
    model the machine has configured, and the figure could not be re-taken.
    The mode selector is set to *ChiSurf tools* because the transcript is a
    tool-driven run -- "Chat only" beside tool calls is an incoherent figure.
    """
    from chisurf.plugins.core.code_editor.agent_panel import AgentPanelWidget

    panel = AgentPanelWidget()
    panel.resize(980, 720)
    panel.mode_combo.setCurrentIndex(1)
    panel.show()
    QApplication.instance().processEvents()

    panel.transcript.clear()
    panel._append_sys(panel._greeting_for(panel._current_mode()))
    panel._append_user(
        "Fit the decays in test/data/tcspc/ibh and tell me the lifetimes."
    )
    panel._append_sys("load_data(path='test/data/tcspc/ibh')  ->  3 dataset(s)")
    panel._append_sys("add_fit(model='Lifetime', dataset=0..2)  ->  3 fits")
    panel._append_sys("run_fit(all)  ->  chi2r = 1.03, 1.12, 0.98")
    panel._append_assistant(
        "All three converged. The donor-only sample gives 3.81 ns; the two "
        "labelled samples give 2.34 ns and 1.61 ns, so the transfer "
        "efficiencies are 0.39 and 0.58. The fits are in your window \u2014 "
        "chi2r is 0.98-1.12, so none of them is straining. Ask me to add a "
        "second component if the residuals look structured."
    )
    QApplication.instance().processEvents()
    _grab(panel, "ai_assistant.png")


def _grab_lumis_quest():
    """Two screens of the game, rendered through its own capture harness.

    The game draws through wgpu, so ``QWidget.grab()`` returns an empty
    surface -- the frames have to come from the engine's offscreen path. The
    plugin already ships that harness (it is how the game is reviewed), so
    this reuses it rather than re-deriving the scene setup.
    """
    import shutil

    from chisurf.plugins.misc.games.lumis_quest.test import capture as lumis_capture

    staging = pathlib.Path(tempfile.mkdtemp()) / "lumis"
    staging.mkdir()
    lumis_capture.main([str(staging)])
    # Two of the gallery: the map-is-the-documentation screen, and the battle
    # where the fluorophore mechanic is visible.
    for stem in ("lumis_town", "lumis_battle"):
        source = staging / f"{stem}.png"
        if source.is_file():
            shutil.copy(source, FIG / f"{stem}.png")
            print("wrote", f"{stem}.png")


def _grab_burst_export_table():
    """The per-burst export table, as it actually comes out of `build_tables`.

    The subject of that guide is a *column contract* -- the names are chosen so
    ndX imports them without any mapping -- so the figure has to be the real
    header over real values, not a prose table restating it.

    Driven on a simulated two-state trace whose answer is known: bursts
    alternate between E = 0.25 and E = 0.75, so `Dominant State` in the figure
    must alternate 0/1 in step with `Proximity ratio`. That makes the figure
    check the export *and* the H2MM fit behind it, rather than only showing a
    layout.
    """
    import tttrlib

    from chisurf.core.datastore import column_names, column_values
    from chisurf.gui.widgets.chitable import ArraySource, ChiTableWidget
    from chisurf.plugins.burst.burst_h2mm.core import export as burst_export
    from chisurf.plugins.burst.burst_h2mm.core import engines as h2mm_engines
    from chisurf.plugins.burst.burst_h2mm.core.photons import (
        StreamDef,
        bursts_from_dataframe,
    )

    rng = np.random.default_rng(0)
    macro, micro, channel, rows = [], [], [], []
    clock = 0
    for index in range(40):
        n_photons = int(rng.integers(60, 160))
        efficiency = 0.25 if index % 2 == 0 else 0.75
        start = len(macro)
        for _ in range(n_photons):
            clock += int(rng.integers(1, 40))
            macro.append(clock)
            red = rng.random() < efficiency
            channel.append(1 if red else 0)
            micro.append(
                int(rng.integers(100, 500) if red else rng.integers(200, 900))
            )
        rows.append(("sim.spc", start, len(macro) - 1))
        clock += 5000

    tttr = tttrlib.TTTR()
    tttr.append_events(
        np.asarray(macro, np.uint64),
        np.asarray(micro, np.uint16),
        np.asarray(channel, np.int8),
        np.zeros(len(macro), np.int8),
        False,
        0,
    )

    # A plain mapping of columns, not a DataFrame: the reader takes either, and
    # pandas is not the storage model here (test/test_pandas_seam.py).
    frame = {
        "First File": [row[0] for row in rows],
        "First Photon": np.array([row[1] for row in rows], dtype=np.int64),
        "Last Photon": np.array([row[2] for row in rows], dtype=np.int64),
    }
    data, meta = bursts_from_dataframe(
        frame,
        {"sim.spc": tttr},
        [StreamDef("green", [0]), StreamDef("red", [1])],
        min_photons=1,
        return_meta=True,
    )
    fit = h2mm_engines.fit_states(data, 2, n_restarts=1, max_iter=200, seed=0)
    path, _ = h2mm_engines.viterbi(fit, data)
    tables = burst_export.build_tables(
        data, meta, path, np.array([0.25, 0.75]),
        base_time_s=1e-6, micro_time_ns=0.032,
        stream_groups=[("green", (0,)), ("red", (1,))],
    )

    bursts = tables.bursts
    names = column_names(bursts)
    columns = {
        name: np.asarray(column_values(bursts, index), dtype=float)
        for index, name in enumerate(names)
    }
    widget = ChiTableWidget(source=ArraySource(columns))
    # Wide enough for all ten columns: the last one clipped at 1250.
    widget.resize(1460, 430)
    _grab(widget, "burst_export_table.png")


def _simulate_us_alex(path, *, frac_high=0.5, seed=11, duration=25.0):
    """Write a small synthetic µs-ALEX measurement, with a known alternation.

    Two FRET populations, a background, and the laser alternation encoded in the
    macro time — the shape the ALEX Suite's first step exists to recognise. The
    header is borrowed from a bundled PTU so the macro-time resolution is real.
    """
    import tttrlib

    rng = np.random.default_rng(seed)
    # The header decides what a macro-time unit *is*, so the simulation has to
    # read it rather than assume: writing 50 ns photons under a 20 us header
    # makes the tool report a 80 ms alternation, which is not a thing.
    source = pathlib.Path("test/data/clsm/Leica_SP5.ptu")
    header = tttrlib.TTTR(str(source)).header
    res = float(header.macro_time_resolution)
    period = int(round(200e-6 / res))   # a 200 us alternation
    green = (int(0.05 * period), int(0.45 * period))
    red = (int(0.55 * period), int(0.95 * period))

    def stream(rate, t0, t1, efficiency):
        n = rng.poisson(rate * (t1 - t0))
        return rng.uniform(t0, t1, n), np.full(n, efficiency)

    times, effs = zip(*(
        [stream(1.5e3, 0.0, duration, 0.05)]
        + [stream(90e3, start, start + 1.5e-3, e)
           for start, e in zip(
               rng.uniform(0.0, duration - 2e-3, 900),
               np.where(rng.random(900) < frac_high, 0.68, 0.22))]
    ))
    t = np.concatenate(times)
    e = np.concatenate(effs)
    order = np.argsort(t)
    macro = (t[order] / res).astype(np.uint64)
    e = e[order]

    # Photons are NOT deleted outside the gates. Real µs-ALEX has no laser-off
    # hole in the folded intensity -- both lasers keep the sample emitting, so
    # the total is nearly flat and only the *detector ratio* alternates. A
    # simulation that gates the photons away produces a picture the window
    # detection finds trivially and a reader would not recognise.
    phase = macro % period
    donor_excited = (phase >= green[0]) & (phase < green[1])
    acceptor_excited = (phase >= red[0]) & (phase < red[1])
    p_acceptor = np.where(
        donor_excited, e,                     # donor excitation: E decides
        np.where(acceptor_excited, 0.95,      # acceptor excitation: nearly all
                 0.5))                        # the rise/fall, neither fully on
    routing = np.where(rng.random(macro.size) < p_acceptor, 1, 0).astype(np.int8)

    out = tttrlib.TTTR()
    out.append_events(macro, np.zeros(macro.size, np.uint16), routing,
                      np.zeros(macro.size, np.int8), True, 0)
    out.write(str(path), header)
    return path


def _grab_alex_suite_alternation():
    """Grab the alternation step, run on a simulated µs-ALEX measurement."""
    from chisurf.plugins.burst.alex_suite.gui.tool import AlexSuiteTool

    workdir = pathlib.Path(tempfile.mkdtemp(prefix="alex_suite_"))
    _simulate_us_alex(workdir / "alex_demo.ptu")

    tool = AlexSuiteTool()
    tool.resize(1180, 780)
    tool.show()
    QApplication.instance().processEvents()

    def row(fragment):
        for i in range(tool.nav_list.count()):
            if fragment in tool.nav_list.item(i).text():
                return i
        raise LookupError(fragment)

    tool.nav_list.setCurrentRow(row("1. Files"))
    QApplication.instance().processEvents()
    tool._workflow_panels["data"].add_paths([workdir / "alex_demo.ptu"])
    for _ in range(20):
        QApplication.instance().processEvents()

    tool.nav_list.setCurrentRow(row("2. Alternation"))
    QApplication.instance().processEvents()
    tool._workflow_panels["alternation"].run()
    for _ in range(30):
        QApplication.instance().processEvents()
    _grab(tool, "alex_suite_alternation.png")


def _grab_alex_suite_titration():
    """Grab the titration step, fitted on a simulated concentration series."""
    import csv

    from chisurf.plugins.burst.alex_suite.gui.tool import AlexSuiteTool

    workdir = pathlib.Path(tempfile.mkdtemp(prefix="alex_titration_"))
    rng = np.random.default_rng(5)
    kd, rows = 50.0, []
    for concentration in (0.0, 5.0, 15.0, 50.0, 150.0, 500.0, 2000.0):
        bound = concentration / (kd + concentration)
        n = 4000
        n_high = int(round(n * bound))
        efficiencies = np.concatenate([
            np.full(n - n_high, 0.22), np.full(n_high, 0.68)])
        total = rng.poisson(200, n).astype(float) + 20.0
        green = total * 0.5
        i_da = rng.binomial(green.astype(int), efficiencies).astype(float)
        path = workdir / f"c{concentration:g}.csv"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh, delimiter="\t")
            writer.writerow(["Number of Photons (green)",
                             "Number of Photons (red)",
                             "Number of Photons (yellow)", "Duration (ms)"])
            for a, b, c in zip(green - i_da, i_da, total - green):
                writer.writerow([a, b, c, 1.0])
        rows.append((concentration, path))

    tool = AlexSuiteTool()
    tool.resize(1180, 780)
    tool.show()
    QApplication.instance().processEvents()
    for i in range(tool.nav_list.count()):
        if "Titration" in tool.nav_list.item(i).text():
            tool.nav_list.setCurrentRow(i)
            break
    QApplication.instance().processEvents()

    panel = tool._workflow_panels["titration"]
    panel.model.add_files([str(path) for _, path in rows])
    for index, (concentration, _) in enumerate(rows):
        panel.model.update_series_cell(index, "concentration", concentration)
    panel.model.min_photons = 0
    panel.model.run()
    for _ in range(30):
        QApplication.instance().processEvents()
    # The step is a scrolling page; the plots are its lower half.
    from qtpy.QtWidgets import QScrollArea

    for area in panel.findChildren(QScrollArea):
        bar = area.verticalScrollBar()
        bar.setValue(bar.maximum())
    for _ in range(15):
        QApplication.instance().processEvents()
    _grab(tool, "alex_suite_titration.png")


def _grab_tttr_generate_decay():
    """Grab **TTTR: Generate Decay** with two decays histogrammed from a real SPC file.

    Two curves (detectors 0 and 8) at TAC div 1: at larger divisors the tool
    draws the decay on a wrong time axis (okf/references/known-issues.md).
    """
    from qtpy.QtCore import Qt
    from qtpy.QtTest import QTest

    from chisurf.plugins.tttr.tttr_histogram.gui import HistogramTTTR

    tool = HistogramTTTR()
    setup = tool.tcspc_setup_widget
    setup.spcFileWidget.onLoadSample(None, filenames=[str(_SPC_FILE)], file_type="bh132")
    # the File widget's Load action also fires onLoadFile; a programmatic load does not
    setup.onLoadFile()
    setup.lineEdit.setText("(ROUT==0)")
    setup.comboBox.setCurrentIndex(setup.comboBox.findText("1"))
    setup.checkBox.setChecked(False)
    QTest.mouseClick(setup.pushButton, Qt.LeftButton)
    setup.lineEdit.setText("(ROUT==8)")
    QTest.mouseClick(setup.pushButton, Qt.LeftButton)
    # add_curve refreshes the list and the plot *before* it appends the new
    # curve, so the view lags one click behind; refresh once more.
    tool.curve_selector.update()
    tool.plot_curves()
    for c in tool._curves:
        print(c.name, "photons", int(c.y.sum()), "bins", c.y.size, "dt[ns]", c.x[1] - c.x[0])
    tool.resize(1280, 760)
    tool.splitter.setSizes([560, 720])
    _grab(tool, "tttr_generate_decay.png")
    return tool


def _grab_tttr_correlate():
    """Grab **TTTR: Correlate** after a real cross-correlation of channels 0 and 8."""
    from chisurf.plugins.tttr.tttr_correlate.gui import CorrelateTTTR

    tool = CorrelateTTTR()
    tool.fileWidget.onLoadSample(None, filenames=[str(_SPC_FILE)], file_type="bh132")
    corr = tool.correlator
    corr.ch1, corr.ch2 = "0", "8"
    corr.correlator_thread.run()  # synchronous: the thread's body
    tool.add_curve()
    c = tool._curves[0]
    print("tau[ms]", c.x[:3], "...", c.x[-1], "G", c.y[:3], "...", c.y[-3:], "ey", c.ey[:3], c.ey[-3:])
    corr.progressBar.setValue(100)
    if os.environ.get("PROBE_FINE"):
        corr.fine = True
        corr.correlator_thread.run()
        f = corr.data
        print("FINE tau[ms]", f.x[:3], "...", f.x[-1], "G", f.y[-3:])
        corr.fine = False
    tool.resize(1280, 760)
    tool.splitter.setSizes([560, 720])
    _grab(tool, "tttr_correlate.png")
    return tool


def _grab_intensity_trace():
    """Intensity-trace tool on a real smFRET TTTR file, binned and HMM-decoded.

    The file is copied to a scratch folder first: *Compute HMM* writes its
    ``<stem>_HMM#<n>_<w>ms/`` output folder beside the TTTR file, and that must
    not land in ``test/data``.
    """
    from chisurf.plugins.tttr.intensity_trace import IntensityTrace

    src = pathlib.Path("test/data/tttr/BH/132/BH_SPC132.spc")
    if not src.is_file():
        raise FileNotFoundError(f"instrument test data missing: {src}")
    work = pathlib.Path(tempfile.mkdtemp(dir="/tmp")) / "smfret"
    work.mkdir()
    spc = work / src.name
    shutil.copy(src, spc)

    tool = IntensityTrace()
    tool.resize(1280, 900)
    # Two detectors as the detector setup would define them: green = routing
    # channels 0/8 (parallel/perpendicular), red = 1/9.
    tool._detector_settings = {
        "detectors": {
            # acceptor first: the per-bin ratio n0/(n0+n1) is then the
            # proximity ratio rather than its complement
            "red": {"chs": [1, 9], "micro_time_ranges": []},
            "green": {"chs": [0, 8], "micro_time_ranges": []},
        }
    }
    tool._refresh_detector_checkboxes()
    tool.window_spin.blockSignals(True)
    tool.window_spin.setValue(5.0)
    tool.window_spin.blockSignals(False)
    tool.hist_max_input.setValue(100.0)
    tool.hmm_components_spinner.setValue(2)
    tool.load_file(file_path=str(spc))
    tool.perform_hmm()
    tool.show()
    QApplication.instance().processEvents()
    # zoom the time axis onto a 6 s stretch so single bursts are resolved
    try:
        tool.plot_widget.plots[0][0].setXRange(20.0, 26.0, padding=0)
    except Exception:
        pass
    QApplication.instance().processEvents()
    _grab(tool, "intensity_trace.png")
    return tool, work


def _grab_file_tools():
    """File-tools hub: Split / Convert with a file loaded, and Time Windows run.

    Writes ``file_tools.png`` (TTTR -> Time Windows after *Process*, preview
    tab showing the trace with its window boundaries) and
    ``file_tools_split.png`` (TTTR Split / Convert with a file loaded).
    """
    import tttrlib
    from qtpy.QtWidgets import QWidget

    from chisurf.plugins.tttr.filetools.gui.tool import FileToolsTool
    from chisurf.plugins.tttr.tttr_splitter.gui.view_model import SplitterViewModel
    from chisurf.plugins.tttr.tttr_time_windows.gui.tool import TTTRTimeWindowTool

    src = pathlib.Path("test/data/tttr/BH/132/BH_SPC132.spc")
    if not src.is_file():
        raise FileNotFoundError(f"instrument test data missing: {src}")
    work = pathlib.Path(tempfile.mkdtemp(dir="/tmp")) / "smfret"
    work.mkdir()
    spc = work / src.name
    shutil.copy(src, spc)
    app = QApplication.instance()

    tool = FileToolsTool()
    tool.resize(1300, 800)
    tool.show()
    app.processEvents()

    def _panel(row, cls):
        tool.nav_list.setCurrentRow(row)
        app.processEvents()
        inst = tool.panels[row].get("instance")
        if isinstance(inst, cls):
            return inst
        # an embedded QMainWindow is flattened; the window itself is kept here
        for child in [inst, *inst.findChildren(QWidget)]:
            mw = getattr(child, "_embedded_mainwindow", None)
            if isinstance(mw, cls):
                return mw
        found = inst.findChildren(cls) if inst is not None else []
        return found[0] if found else None

    # 1) Split / Convert (row 0)
    tool.nav_list.setCurrentRow(0)
    app.processEvents()
    inst = tool.panels[0].get("instance")
    model = None
    for obj in [inst, *inst.findChildren(object)]:
        m = getattr(obj, "model", None) or getattr(obj, "_model", None)
        if isinstance(m, SplitterViewModel):
            model = m
            break
    model.output_folder = str(work / "split")
    model.set_tttr(tttrlib.TTTR(str(spc)), str(spc))
    model.update()
    app.processEvents()
    _grab(tool, "file_tools_split.png")

    # 2) TTTR -> Time Windows (row 4): queue the file, process, show preview
    tw = _panel(4, TTTRTimeWindowTool)
    tw.tws_spin.blockSignals(True)
    tw.tws_spin.setValue(1000.0)
    tw.tws_spin.blockSignals(False)
    tw._file_model.files = [str(spc)]
    tw._on_files_changed()
    tw._process_all()
    tw.dock_area.setCurrentIndex(2)
    app.processEvents()
    _grab(tool, "file_tools.png")
    return tool


def _grab_fcs_toolbox():
    """Grab the unified FCS tool (Spectroscopy:FCS): every correlator step.

    Loads the BH SPC-132 test stream, defines a two-detector setup, turns on
    the photon filter, correlates the green channels against the red ones in
    ten chunks and hands them to the merger — the state a user reaches after
    one pass through the rail.
    """
    from chisurf.plugins.fcs.fcs_toolbox.tool import FcsTool

    app = QApplication.instance()
    spc = _SPC_FILE.resolve()
    setup_name = "SPC-132 (2 detectors)"
    setup = {
        "windows": {"prompt": [0, 4095]},
        "detectors": {
            "Green": {"chs": [0, 8], "micro_time_ranges": [[0, 4095]]},
            "Red": {"chs": [1, 9], "micro_time_ranges": [[0, 4095]]},
        },
    }

    tool = FcsTool()
    tool.resize(1280, 800)
    tool.show()
    app.processEvents()

    def go(role):
        tool.nav_list.setCurrentRow(tool._nav_row_for_role(role))
        for _ in range(3):
            app.processEvents()

    # 1. Channel definitions: a detector setup and its correlation pairs.
    go("channel_def")
    chdef = tool._workflow_panels["channel_def"]
    chdef.model._detector_setups = {setup_name: setup}
    chdef.model._fcs_cfg = {"setups": {setup_name: {"pairs": []}}}
    chdef.model.current_setup = setup_name
    chdef.model.add_pair("Green", "Green")
    chdef.model.add_pair("Red", "Red")
    chdef.model.add_pair("Green", "Red")
    chdef.auto_form.rebuild()
    app.processEvents()
    _grab(tool, "fcs_toolbox_channels.png")

    # 2. Files & steps: one photon stream, photon filter on, merger on.
    go("files")
    files = tool._workflow_panels["files"]
    files.file_list.set_paths([str(spc)])
    files.cb_photon_filter.setChecked(True)
    app.processEvents()
    _grab(tool, "fcs_toolbox_files.png")

    # 3. Photon / burst filter: default count-rate burst selection.
    go("filter")
    fm = tool._filter_model
    fm.channel_numbers = "0, 1, 8, 9"
    fm.max_dmt = 0.5
    fm.min_ph = 30
    fm.mcs_bin_width = 10.0
    tool._filter_form.sync_fields()
    tool._filter_form.refresh_plots()
    app.processEvents()
    _grab(tool, "fcs_toolbox_filter.png")

    # 4. Correlator: green x red cross-correlation, ten chunks.
    files.cb_photon_filter.setChecked(False)  # correlate the whole stream
    go("correlator")
    cm = tool._correlator_model
    cm.channel_a = "0, 8"
    cm.channel_b = "1, 9"
    cm.n_bins = 4
    cm.n_casc = 26
    cm.n_splits = 10
    tool._correlator_form.sync_fields()
    from chisurf.plugins.fcs.fcs_correlator.correlator_panel import _CorrelateControls

    for ctl in tool._correlator_form.findChildren(_CorrelateControls):
        ctl.btn.click()  # the real button: status label + plot refresh
    app.processEvents()
    print("chunks", len(cm._correlations))
    _grab(tool, "fcs_toolbox_correlator.png")

    # 5. Merger: the chunks averaged; drop one to show the dashed style.
    go("merger")
    mm = tool._merger_model
    if len(mm._correlations) > 3:
        mm._toggle_curve(3)
    mm._form.sync_fields()
    for w in mm._form.findChildren(object):
        if getattr(w, "AUTOFORM_REFRESH", False) and hasattr(w, "refresh"):
            w.refresh()
    print("merger folder:", repr(mm.folder_path), "target:", mm.target_filepath())
    app.processEvents()
    mean = mm.compute_mean()
    if mean is not None:
        print("merged", mean["n_curves"], "curves, dur", mean["duration"], "CR", mean["count_rate"])
    _grab(tool, "fcs_toolbox_merger.png")

    # Visit every optional tool once so a broken panel shows up here.
    for role in ("flc_2d", "lfcs_sim", "burst_fcs", "diffusion_calc", "filter_calc"):
        go(role)
        row = tool._nav_row_for_role(role)
        print(role, "loaded:", tool.panels[row].get("instance") is not None)
    tool.close()


def _pump(seconds):
    app = QApplication.instance()
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def _grab_lltf():
    """Grab the Decay Analysis hub on its Lazy Lifetime Analysis panel.

    Loads the plugin's bundled donor-only decay and IRF, runs the real Fit
    button (a child ``lltf fit`` process) with a two-lifetime model and waits
    for the Results tab.
    """
    from chisurf.plugins.fluorescence_decay.lifetime_analysis.gui.tool import (
        LifetimeAnalysisTool,
    )
    from chisurf.plugins.fluorescence_decay.lltf.lltf_gui import LLTFGUIWizard

    ex = pathlib.Path("chisurf") / "plugins" / "fluorescence_decay" / "lltf" / "example"
    out = pathlib.Path(tempfile.mkdtemp(prefix="lltf_"))
    hub = LifetimeAnalysisTool()
    hub.resize(1280, 900)
    hub.show()
    _pump(0.3)
    _grab(hub, "decay_analysis_hub.png")

    hub.resize(1280, 1350)
    hub.nav_list.setCurrentRow(2)  # 3. Lazy Lifetime Analysis
    _pump(0.5)
    lltf = hub.findChildren(LLTFGUIWizard)[0]
    lltf.decay_file = str(ex / "5-44_D0.dat")
    lltf.decay_file_edit.setText(lltf.decay_file)
    lltf.irf_file = str(ex / "IRF_D0.dat")
    lltf.irf_file_edit.setText(lltf.irf_file)
    lltf.output_dir = str(out)
    lltf.output_dir_edit.setText(str(out))
    lltf._update_fit_button_state()
    lltf.n_lifetimes_spin.setValue(2)
    _pump(0.2)
    lltf.fit_button.click()
    for _ in range(600):  # the child process: ~5 s for one fixed-n fit
        _pump(0.1)
        if not lltf.analysis_tab.running:
            break
    _pump(0.5)
    lltf.tab_widget.setCurrentIndex(1)
    _pump(0.2)
    _grab(hub, "lltf_output.png")
    lltf.tab_widget.setCurrentWidget(lltf.results_tab)
    from qtpy import QtWidgets
    for sp in lltf.results_tab.findChildren(QtWidgets.QSplitter):
        sp.setSizes([230, 520])
    _pump(0.3)
    _grab(hub, "lltf_results.png")

    lltf.on_edit_config()
    ed = lltf.settings_editor
    ed.resize(560, 940)
    _pump(0.3)
    _grab(ed, "lltf_settings.png")


def _grab_synthetic_decay():
    """Grab the Synthetic Decay Generator in VM and VV/VH mode.

    Two lifetimes (1.2 and 4.0 ns, the defaults) on 1024 bins of 32 ps, the
    LLTF example IRF, 10^6 photons of Poisson noise; then the same spectrum as a
    polarized pair with g = 1.1 and one 2 ns rotation.
    """
    import numpy as np

    from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.tool import (
        SyntheticDecayTool,
    )

    ex = pathlib.Path("chisurf") / "plugins" / "fluorescence_decay" / "lltf" / "example"
    irf = np.loadtxt(ex / "IRF_D0.dat")[:, 1]
    # 8 ps channels -> 32 ps: sum groups of four, keep the first 1024 bins
    irf32 = irf[: 4 * (irf.size // 4)].reshape(-1, 4).sum(axis=1)[:1024]
    irf_file = pathlib.Path(tempfile.mkdtemp(prefix="synth_")) / "irf_32ps.txt"
    np.savetxt(irf_file, irf32)

    tool = SyntheticDecayTool()
    tool.resize(760, 1180)
    m = tool.model
    m.n_bins = 1024
    m.bin_width = 0.032
    m.irf_path = str(irf_file)
    m.shot_noise = True
    m.photon_count = 1e6
    m.seed = 1
    tool.form.sync_fields()
    m.generate()
    _pump(0.3)
    _grab(tool, "synthetic_decay_vm.png")

    from qtpy import QtWidgets

    # Switch mode the way a user does: click the radio button (the choice
    # rebuilds the form), then open the collapsed corrections panel.
    for rb in tool.findChildren(QtWidgets.QRadioButton):
        if rb.text().startswith("VV/VH"):
            rb.click()
    _pump(0.3)
    for b in tool.findChildren(QtWidgets.QAbstractButton):
        if "detection corrections" in b.text():
            b.click()
    _pump(0.2)
    m.g_factor = 1.1
    m.rotation_rows = [{"b": 0.38, "rho": 2.0}]
    tool.form.sync_fields()
    for b in tool.findChildren(QtWidgets.QAbstractButton):
        if b.text().endswith("Generate") and b.isVisible():
            b.click()
            break
    _pump(0.3)
    _grab(tool, "synthetic_decay_vvvh.png")


def _grab_phasor_calculator():
    """Phasor calculator: 80 MHz, grid + ticks, FRET for tau_D0 = 4 ns, a 0.6/5 ns mixture."""
    from chisurf.plugins.calculator.phasor_calculator.gui.tool import PhasorCalculatorTool
    from chisurf.plugins.microscopy.img_pixel_phasor import analysis

    tool = PhasorCalculatorTool()
    m = tool._model
    g1, s1 = analysis.lifetime_to_phasor(0.6, 80.0)
    g2, s2 = analysis.lifetime_to_phasor(5.0, 80.0)
    m.g1, m.s1, m.g2, m.s2 = float(g1), float(s1), float(g2), float(s2)
    m.show_fret = True
    m.tau_d0 = 4.0
    m.show_component = True
    m.show_mixing = True
    m.frac1 = 0.5
    m.show_cursor = True
    gm = 0.5 * g1 + 0.5 * g2
    sm = 0.5 * s1 + 0.5 * s2
    m.cursor_g, m.cursor_s, m.cursor_radius = float(gm), float(sm), 0.04
    tool._form.sync_fields()
    tool._form.refresh_plots()
    from qtpy import QtWidgets
    for b in tool.findChildren(QtWidgets.QPushButton):
        if "Results" in b.text():
            b.click()
    tool.resize(900, 640)
    _grab(tool, "phasor_calculator_controls.png")
    for tb in tool.findChildren(QtWidgets.QTabBar):
        for i in range(tb.count()):
            if tb.tabText(i) == "Phasor plot":
                tb.setCurrentIndex(i)
    tool._form.refresh_plots()
    _grab(tool, "phasor_calculator.png")
    return tool




# ── guide 78: F-test and batch analysis on the ibh donor / donor-acceptor decays ──
_IBH = pathlib.Path("test/data/tcspc/ibh_sample")
_DT = 0.0141 * 8  # ns per channel after 8x rebinning (4096 -> 512)


def _ibh_decay(name):
    """Load an ibh .txt decay (8 header lines + 'Chan Data'), rebinned 8x."""
    import numpy as np

    y = np.loadtxt(_IBH / name, skiprows=9)[:, 1]
    return y.reshape(-1, 8).sum(1)


def _ibh_irf():
    """The shared prompt, its constant background removed, rebinned 8x."""
    import numpy as np

    y = np.loadtxt(_IBH / "Prompt.txt", skiprows=9)[:, 1]
    y = np.clip(y - np.median(y[-800:]), 0, None)
    return y.reshape(-1, 8).sum(1)


def _ibh_fit(decay, n):
    import warnings

    from chisurf.core.fluorescence.decay_fit_model import build_lifetime_fit

    warnings.simplefilter("ignore")
    fit = build_lifetime_fit(
        decay, bin_width=_DT, irf=_ibh_irf(), n_components=n,
        initial_lifetimes=[0.5, 2.0, 4.5][-n:], fit_background=True,
        start_bin=55, stop_bin=480,
    )
    return fit


def _grab_f_test():
    """F-test fed from real fits: 1- vs 2-exponential donor-only decay."""
    from chisurf.plugins.core.f_test.gui.tool import FTestTool

    d0 = _ibh_decay("Decay_577D.txt")
    f1, f2 = _ibh_fit(d0, 1), _ibh_fit(d0, 2)
    f1.run(); f2.run()
    tool = FTestTool()
    tool._load_fit(f1, "model1")
    tool._load_fit(f2, "model2")
    tool._load_fit(f2, "chi2max")
    tool.resize(620, 560)
    _grab(tool, "f_test_tool.png")
    m = tool._model
    print("ftest", m.chi2_1, m.n1, m.chi2_2, m.n2, m.conf_level, m.chi2_min, m.npars, m.dof, m.chi2_max)
    return tool


class _DirectClient:
    """In-process stand-in for the fitting client: writes parameters directly.

    The shipped FittingClient only talks JSON-RPC to the running server, so
    without the main window there is none; run_batch takes any object with
    these three methods.
    """

    def get_fit_objects(self):
        import chisurf as cs

        return list(cs.fits)

    def _param(self, name, fit_index):
        import chisurf as cs

        for p in cs.fits[fit_index].model.parameters_all:
            if p.name == name:
                return p
        return None

    def set_parameter_value(self, parameter_name, value, fit_index):
        p = self._param(parameter_name, fit_index)
        if p is not None and not p.fixed:
            p.value = value

    def set_parameter_fixed(self, parameter_name, fixed, fit_index):
        p = self._param(parameter_name, fit_index)
        if p is not None:
            p.fixed = fixed


def _grab_batch_analysis():
    """Batch wizard: template 2-exp fit on the donor-only decay, run over D0 and DA."""
    import chisurf as cs
    from chisurf.plugins.core.batch_analysis.core import runner
    from chisurf.plugins.core.batch_analysis.gui.tool import BatchProcessingWizard

    d0 = _ibh_decay("Decay_577D.txt")
    da = _ibh_decay("Decay_577D+577A+GTPgS.txt")
    template = _ibh_fit(d0, 2)
    template.run()
    ds_d0 = template.data
    ds_da = _ibh_fit(da, 2).data
    ds_d0.name, ds_da.name = "Decay_577D", "Decay_577D+577A+GTPgS"
    cs.fits[:] = [template]
    cs.imported_datasets[:] = [ds_d0, ds_da]

    import chisurf.gui.widgets.fitting.fitting_client as fc

    fc._FITTING_CLIENT = _DirectClient()  # the GUI installs the RPC client here
    wiz = BatchProcessingWizard()
    vm = wiz.model
    vm.selected_dataset_indices = [0, 1]
    from chisurf.plugins.core.batch_analysis.gui.loaded_datasets import LoadedDatasetSelector

    for sel in wiz.findChildren(LoadedDatasetSelector):
        sel.repopulate()
    vm.selected_fit_name = vm.fit_names()[0] if vm.fit_names() else ""
    vm.save_path = "/data/ibh/batch_results.csv"
    wiz.assistant.auto_form.sync_fields()
    results = runner.run_batch(0, vm.build_items())
    vm._results = results
    vm._status_html = "<p><b>Done.</b></p>"
    for r in results.rows:
        print("batch", r["Run"], r["Filename"], r["Parameter"], r["Fixed"], r["Value"], r["Chi2r"])
    vm.notify("refresh")
    wiz.resize(900, 620)
    from qtpy import QtWidgets

    nav = [w for w in wiz.findChildren(QtWidgets.QListWidget)]
    shots = {
        "Loaded data": "batch_analysis_loaded.png",
        "Files & fit": "batch_analysis_files.png",
        "Run": "batch_analysis_run.png",
        "Results": "batch_analysis_results.png",
    }
    for lw in nav:
        for i in range(lw.count()):
            text = lw.item(i).text()
            for key, png in shots.items():
                if key in text:
                    lw.setCurrentRow(i)
                    wiz.assistant.auto_form.refresh_plots()
                    _grab(wiz, png)
    return wiz


def _grab_hydropro():
    """HydroPro with 148L selected and T4 lysozyme's mass and v-bar entered.

    No HYDROPRO executable exists for macOS, so the grab shows the form ready to
    run, with the structure listed in the results table and no value yet.
    """
    from chisurf.plugins.modelling.hydropro.gui.tool import HydroProTool

    w = HydroProTool()
    m = w._model
    m.exe_path = ""
    m.struct_files = str(_PDB_148L)
    m.rm = 18700.0
    m.vbar = 0.73
    m.status = "Executable not configured"
    w._form.rebuild()
    w._refresh_table_files()
    w.table.setColumnWidth(0, 470)
    w.resize(760, 820)
    _grab(w, "hydropro_tool.png")


def _grab_hydropro_exe_dialog():
    """The dialog Run opens when no executable is configured."""
    from chisurf.plugins.modelling.hydropro.gui.dialogs import DownloadInfoDialog
    from chisurf.plugins.modelling.hydropro.gui.tool import _DOWNLOAD_URL

    d = DownloadInfoDialog(_DOWNLOAD_URL)
    d.resize(560, 200)
    _grab(d, "hydropro_exe_dialog.png")


def _grab_quest_hub():
    """Structure Tools with the QuEst entry selected (its error panel)."""
    from chisurf.plugins.modelling.structure_tools.gui.tool import StructureToolsTool

    w = StructureToolsTool()
    w.resize(1100, 640)
    w.show()
    QApplication.instance().processEvents()
    # select the QuEst panel by role
    nav = getattr(w, "select_role", None)
    if callable(nav):
        nav("quest")
    else:
        from chisurf.plugins.modelling.structure_tools.gui.tool import STRUCTURE_PANELS

        idx = [p.get("role") for p in STRUCTURE_PANELS].index("quest")
        w.nav_list.setCurrentRow(idx)
    for _ in range(5):
        QApplication.instance().processEvents()
    _grab(w, "quest_structure_tools.png")


def _grab_traj_tools():
    """Traj Tools hub on the T4L NMSim trajectory: Align, FRET, Energy Calc, Remove Clashed (guide 81)."""
    from chisurf.core.structure import trajectory_data as md
    from chisurf.gui.widgets.structure import potentialDict
    from chisurf.plugins.traj.traj_tools.gui.tool import TrajectoryToolsTool

    out = pathlib.Path(tempfile.mkdtemp(prefix="traj_tools_"))
    top, dcd = str(_T4L_TOP), str(_T4L_DCD)
    ref = md.load(top)
    ca = ref.top.select("name CA")

    def idx(res, name):
        return int(ref.top.select(f"resSeq {res} and name {name}")[0])

    tool = TrajectoryToolsTool()
    tool.resize(900, 640)
    tools = tool._tools

    align = tools["Align"]
    align.model.set_topology(top)
    align.model.set_trajectory(dcd)
    align.model.atom_selection = ", ".join(str(i) for i in ca)
    align.model.save_aligned(str(out / "t4l_aligned.dcd"))
    align.auto_form.sync_fields()
    tool._select_tool("Align")
    _grab(tool, "traj_tools_align.png")

    fret = tools["FRET"]
    fret.model.set_topology(top)
    fret.model.set_trajectory(dcd)
    section = fret.model.atom_pair_section
    section.set_donor(idx(36, "CA"), idx(36, "CB"))
    section.set_acceptor(idx(132, "CA"), idx(132, "CB"))
    fret.model.forster_radius = 52.0
    fret.model.tau0 = 4.0
    fret.model.t_step = 1.0
    fret.model.calc(str(out / "t4l_36_132.csv"))
    fret.auto_form.sync_fields()
    tool._select_tool("FRET")
    _grab(tool, "traj_tools_fret.png")

    energy = tools["Energy Calc"]
    energy.model.set_topology(top)
    energy.model.set_trajectory(dcd)
    energy.model.stride = 10
    for name in ("Radius of Gyration", "Clash potential"):
        energy.model.add_potential(potentialDict[name](structure=None, parent=None), 1.0, name=name)
    energy.model.process(str(out / "t4l_energy.txt"))
    energy.auto_form.sync_fields()
    tool._select_tool("Energy Calc")
    _grab(tool, "traj_tools_energy.png")

    clash = tools["Remove Clashed"]
    clash.model.set_topology(top)
    clash.model.set_trajectory(dcd)
    clash.model.atom_selection = "name CA"
    clash.model.min_distance = 3.5
    clash.model.save_clash_free(str(out / "t4l_clash_free.dcd"))
    clash.auto_form.sync_fields()
    tool._select_tool("Remove Clashed")
    _grab(tool, "traj_tools_clashes.png")

    conv = tools["Convert"]
    conv.model.set_topology(top)
    conv.model.set_trajectory(dcd)
    conv.model.set_target_directory(str(out))
    conv.model.filename = "t4l_every10"
    conv.model.stride = 10
    conv.model.convert()
    conv.auto_form.sync_fields()
    tool._select_tool("Convert")
    _grab(tool, "traj_tools_convert.png")
    tool.close()


def _grab_fret_line_tool():
    """FRET Line Generator: static line (Gaussian sweep) + dynamic line 40<->70 A (guide 82)."""
    from chisurf.core.fluorescence.fret.fret_line import find_parameter
    from chisurf.plugins.fret_line.gui.tool import FRETLineTool

    tool = FRETLineTool()
    tool.resize(1100, 760)
    # line 1: static line, sweep RDA0 of the one Gaussian component
    tool._refresh_sweep_targets()
    combo = tool._sweep_combo

    def pick(label_part):
        for i in range(combo.count()):
            if label_part in combo.itemText(i):
                combo.setCurrentIndex(i)
                return
        raise KeyError(label_part)

    pick("C0 [FRET: FD (Gaussian)] · RDA0")
    tool._min_spin.setValue(20.0)
    tool._max_spin.setValue(120.0)
    tool._tau_d0_spin.setValue(4.0)
    tool._do_compute()
    # line 2: dynamic line = mixture of two Gaussians (40 A, 70 A), sweep the fraction
    m0 = tool._components[0]["model"]
    find_parameter(m0, "distance.mean.0").value = 40.0
    tool._add_component()
    m1 = tool._components[1]["model"]
    find_parameter(m1, "distance.mean.0").value = 70.0
    tool._refresh_sweep_targets()
    pick("fraction · C0")
    tool._min_spin.setValue(0.0)
    tool._max_spin.setValue(1.0)
    tool._do_compute()
    tool._comp_list.setCurrentRow(1)
    QApplication.instance().processEvents()
    # Editor: scroll past the IRF/convolution block to the FRET and distance groups.
    from qtpy import QtWidgets

    from chisurf.gui.widgets.dock_area.dock_stacked_tab_widget import DockStackedTabWidget

    tool.show()
    QApplication.instance().processEvents()
    editor = tool._components[1]["editor"]
    areas = [editor] if isinstance(editor, QtWidgets.QScrollArea) else []
    areas += editor.findChildren(QtWidgets.QScrollArea) + [tool._editor_scroll]
    area = max(areas, key=lambda a: a.verticalScrollBar().maximum())
    area.verticalScrollBar().setValue(int(area.verticalScrollBar().maximum()))

    def front(page):
        # The dock's tab groups are QTabWidgets; bring *page*'s tab to the front.
        groups = tool._dock.findChildren(QtWidgets.QTabWidget)
        groups += tool._dock.findChildren(DockStackedTabWidget)
        for tabs in groups:
            for i in range(tabs.count()):
                w = tabs.widget(i)
                if w is page or (w is not None and w.isAncestorOf(page)):
                    tabs.setCurrentIndex(i)
                    return
        print("tab not found for", page)

    front(tool._sweep_combo.parentWidget())
    _grab(tool, "fret_line_tool.png")
    front(tool._lines_list.parentWidget())
    _grab(tool, "fret_line_tool_lines.png")
    tool.close()


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
        _grab_kappa2_tool,
        _grab_hmm_tool,
        _grab_chimol_viewer,
        _grab_chimol_biofilm,
        _grab_region_editor,
        _grab_ndx_gaussian_panel,
        _grab_ask_the_documentation,
        _grab_maxent_decay,
        _grab_global_view,
        _grab_ebfret_tool,
        _grab_pto_inspector,
        _grab_irf_estimator,
        _grab_console,
        _grab_ai_assistant,
        _grab_lumis_quest,
        _grab_burst_export_table,
        _grab_alex_suite_alternation,
        _grab_alex_suite_titration,
        _grab_tttr_generate_decay,
        _grab_tttr_correlate,
        _grab_intensity_trace,
        _grab_file_tools,
        _grab_fcs_toolbox,
        _grab_lltf,
        _grab_synthetic_decay,
        _grab_phasor_calculator,
        _grab_f_test,
        _grab_batch_analysis,
        _grab_hydropro,
        _grab_hydropro_exe_dialog,
        _grab_quest_hub,
        _grab_traj_tools,
        _grab_fret_line_tool,
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
