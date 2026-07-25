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


def _grab_pda_editor():
    """Grab the PDA (Gaussian-distance) model editor for the PDA guide."""
    import numpy as np
    from scipy import stats

    import chisurf.core.fitting.fit as fit_mod
    import chisurf.core.fluorescence.tcspc as tcspc
    from chisurf.core.data import DataCurve
    from chisurf.core.models.pda.pdagauss import PdaGaussianDistanceModel
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
    fit = fit_mod.Fit(model_class=PdaGaussianDistanceModel, data=data)
    editor = build_model_editor(fit.model)
    editor.resize(560, 760)
    _grab(editor, "pda_model_editor.png")


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
    import tifffile

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
    tifffile.imwrite(tmp, stack)

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
    """Grab the scan-precision planner (guide 45).

    The tool needs no data at all -- it answers from the settings alone -- so
    this is simply the default acquisition, predicted. The default deliberately
    sits *beside* the optimum rather than on it, so the figure shows the marker
    off the minimum, which is the thing the tool exists to tell you.
    """
    from chisurf.plugins.microscopy.img_precision.gui.tool import ImgPrecisionTool

    tool = ImgPrecisionTool()
    tool.model.compute()
    tool.resize(1400, 760)
    tool.show()
    tool._refresh()
    QApplication.instance().processEvents()
    _grab(tool, "precision_workspace.png")


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

    import tifffile

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
        tifffile.imwrite(
            str(path), np.stack([a, b]).astype(np.float32), imagej=True, metadata={"axes": "CYX"}
        )
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

    * the **render** goes through chimol's own ray tracer, which needs no GPU and
      no display -- the same path the plugin's visual tests use. A GL grab is not
      an option here: ``QWidget.grab()`` reads the backing store and never sees
      OpenGL content, and ``grabFramebuffer`` returns black without a display
      session;
    * the **panel** comes from a whole-window grab, cropped afterwards. Grabbing
      the panel widget on its own crashes under the offscreen platform, as does
      ``mapTo`` on it -- see the parity tracker.
    """
    import pathlib as _pathlib

    from PIL import Image

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

    # -- the object panel, cropped out of a full-window grab ------------------
    full = FIG / "_chimol_window_full.png"
    window.grab().save(str(full))
    image = Image.open(full)
    image.crop((262, 58, 640, 190)).resize((756, 264), Image.LANCZOS).save(
        str(FIG / "chimol_objects_panel.png")
    )
    full.unlink(missing_ok=True)
    print("wrote chimol_objects_panel.png")

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


def main():
    """Generate all guide screenshots."""
    app = QApplication.instance() or QApplication([])  # keep a ref alive  # noqa: F841

    for grab in (
        _grab_fcs_model_editor,
        _grab_tcspc_lifetime_editor,
        _grab_pda_editor,
        _grab_burst_browser,
        _grab_2cde_tool,
        _grab_coloc_tool,
        _grab_drift_tool,
        _grab_precision_tool,
        _grab_accurate_fret_tool,
        _grab_chimol_viewer,
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
