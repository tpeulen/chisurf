"""Grab functions for guides 15-25 (screenshot pass 2).

Written in ``docs/guides/make_screenshots.py`` style: each ``_grab_*`` uses the
module constants ``_SPC_FILE``, ``FIG`` and ``_grab`` of that file, so the
functions can be pasted in unchanged. Run standalone from the repo root with::

    QT_QPA_PLATFORM=offscreen PYTHONPATH=modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:. \
        python <scratch>/shots2/grabs.py _grab_15_background ...
"""

from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np  # noqa: E402
from qtpy.QtWidgets import QApplication  # noqa: E402

import chisurf.core.settings  # noqa: E402,F401

FIG = pathlib.Path(__file__).resolve().parents[1] / "figures"
_SPC_FILE = pathlib.Path("test") / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"


def _grab(widget, name):
    """Show *widget*, process events, and save a PNG grab into ``figures/``."""
    widget.show()
    QApplication.instance().processEvents()
    widget.grab().save(str(FIG / name))
    print("wrote", name)


def _grab_rect(widget, name, height, width=None, top=0):
    """Grab a band ``[top, top+height)`` (and left *width* px) of *widget*.

    For tools whose minimum size leaves a short panel mostly empty, or whose
    stacked docks make one grab too tall to read.
    """
    from qtpy.QtCore import QRect

    widget.show()
    _settle()
    w = width or widget.width()
    widget.grab(QRect(0, top, w, height)).save(str(FIG / name))
    print("wrote", name)


def _compose(pixmaps, name, gap=12):
    """Save *pixmaps* side by side as one PNG in ``figures/``."""
    from qtpy import QtGui

    canvas = QtGui.QPixmap(
        sum(p.width() for p in pixmaps) + gap * (len(pixmaps) - 1),
        max(p.height() for p in pixmaps),
    )
    canvas.fill(QtGui.QColor("#f0f0f0"))
    painter = QtGui.QPainter(canvas)
    x = 0
    for p in pixmaps:
        painter.drawPixmap(x, 0, p)
        x += p.width() + gap
    painter.end()
    canvas.save(str(FIG / name))
    print("wrote", name)


def _settle(n=10):
    """Process events a few times so docks and plots lay out."""
    app = QApplication.instance()
    for _ in range(n):
        app.processEvents()


def _raise_tab(widget, title):
    """Bring every tab whose text is *title* to the front (dock tab groups too)."""
    from qtpy import QtWidgets

    hit = False
    for bar in widget.findChildren(QtWidgets.QTabBar):
        for i in range(bar.count()):
            if bar.tabText(i).strip() == title:
                bar.setCurrentIndex(i)
                hit = True
    _settle()
    if not hit:
        print("tab not found:", title)
    return hit


def _tab_titles(widget):
    """All tab texts under *widget* (for probing)."""
    from qtpy import QtWidgets

    return [
        [bar.tabText(i) for i in range(bar.count())]
        for bar in widget.findChildren(QtWidgets.QTabBar)
    ]


def _probe_tabs(widget, stem):
    """Grab every tab of *widget* into the scratch dir as ``<stem>_<tab>.png``."""
    from qtpy import QtWidgets

    out = pathlib.Path(os.environ.get("SHOT_PROBE", "/tmp"))
    for bar in widget.findChildren(QtWidgets.QTabBar):
        for i in range(bar.count()):
            bar.setCurrentIndex(i)
            _settle()
            name = "".join(c if c.isalnum() else "_" for c in bar.tabText(i))
            widget.grab().save(str(out / f"{stem}_{name}.png"))
    print("tabs:", _tab_titles(widget))


_BH_SETUP = "BH SPC-132 smFRET"
_BH_DETECTORS = {
    "green": {"chs": [0, 8], "micro_time_ranges": []},
    "red": {"chs": [1, 9], "micro_time_ranges": []},
}


def _ensure_bh_setup():
    """Store a two-detector setup (+ FCS pairs) for the BH SPC-132 file.

    Goes into the MMFDB of the *isolated* settings dir (``CHISURF_SETTINGS_DIR``),
    never the user's: the tools that read setups from the shared store show an
    empty selector otherwise.
    """
    from chisurf.core.fluorescence.fcs.channel_setups import save_fcs_channel_setups
    from chisurf.gui.widgets.wizard.tttr_channeldefinition.setup_client import (
        DetectorSetupClient,
    )

    # Two stores: the RPC service reads/writes settings/detector_setups.json,
    # the SetupSelector reads MMFDB. Write both so every tool sees the setup.
    client = DetectorSetupClient()
    client.save_setup(_BH_SETUP, {"detectors": _BH_DETECTORS})
    client.set_current({"detectors": _BH_DETECTORS, "name": _BH_SETUP})
    # A fresh isolated MMFDB has no row for the active user, and the FCS-pair
    # store references one (the detector store does not).
    from chisurf.core.fio import setup_store

    uid = setup_store.resolve_active_user_id()
    db = setup_store.get_db()
    if uid and db is not None:
        db.conn.execute(
            "INSERT OR IGNORE INTO flr_sample_users (user_id, user_uuid, display_name) "
            "VALUES (?, ?, ?)",
            (uid, "00000000-0000-0000-0000-0000000000aa", uid),
        )
        db.conn.commit()
        db.close()
    save_fcs_channel_setups(
        {
            "setups": {
                _BH_SETUP: {
                    "pairs": [
                        {"name": "GG", "channel_a": "green", "channel_b": "green"},
                        {"name": "RR", "channel_a": "red", "channel_b": "red"},
                        {"name": "GR", "channel_a": "green", "channel_b": "red"},
                    ]
                }
            },
            "last_used_setup": _BH_SETUP,
        }
    )
    print("setups:", client.list_setups())


# ---------------------------------------------------------------- guide 15
def _grab_15_background():
    """Native Burst Background Estimation on the BH SPC-132 smFRET file (guide 15).

    The file is copied to a scratch folder: the estimate records its rates beside
    the photons, which must not land in ``test/data``. The detectors are applied
    explicitly (green 0/8, red 1/9, ungated) -- the window's own default gates
    them by micro time, and a grabber that inherits whatever setup the settings
    dir holds draws someone else's channels.
    """
    import json

    from emtk.testing import Driver
    from screenshots.emtk_shot import app_from, wait

    work = pathlib.Path(tempfile.mkdtemp())
    spc = work / _SPC_FILE.name
    shutil.copy(_SPC_FILE, spc)
    app = app_from("burst_background")
    driver = Driver(app, (1280, 820))
    driver.frame(2)
    assert app.controller.apply_detectors(json.dumps(_BH_DETECTORS)), app.controller.status
    app.controller.add_files([spc])
    driver.frame(2)
    app.controller.run()
    wait(driver, lambda: (app.controller.poll(), not app.controller.running)[1], timeout=600)
    print("status:", app.controller.status, "|", app.model.status, flush=True)
    print("rates:", app.model.backgrounds, flush=True)
    driver.screenshot(FIG / "15_burst_background.png")
    print("wrote 15_burst_background.png", flush=True)
    # The Fit dock on its own: the four controls, not the whole window.
    from PIL import Image

    _, top, _, _ = driver.rect("Fit Settings")
    x, run_y, w, run_h = driver.rect("bg_run")
    shot = Image.open(FIG / "15_burst_background.png")
    scale = shot.width / 1280
    box = (0, top - 6, x + w + 8, run_y + run_h + 6)
    shot.crop(tuple(int(v * scale) for v in box)).save(FIG / "15_burst_background_fit.png")
    print("wrote 15_burst_background_fit.png", flush=True)
    app.close()
    return app


# ---------------------------------------------------------------- guide 16
_BURST_FOLDER_GLOB = (
    "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/burstwise_All*"
)


def _grab_16_burst_fcs():
    """Burst-wise FCS on its demonstration data (guide 16): the emtk app, populated and drawn headlessly."""
    import time

    from emtk.testing import PixelPainter, RecordingPainter, png_encode

    from chisurf.plugins.burst.burst_fcs_correlator.gui.app import create_app

    app = create_app()
    app.load_example()
    app.controller._on_run()
    while app.controller.running or app.controller._future is not None:
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
        time.sleep(0.05)
    for _ in range(3):
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
    painter = PixelPainter(1200, 800)
    for _ in range(2):
        painter = PixelPainter(1200, 800)
        app.draw(painter, 0, 0, 1200, 800)
    (FIG / "16_burst_fcs.png").write_bytes(png_encode(painter.width, painter.height, painter.px))
    print("wrote 16_burst_fcs.png")
    app.close()


# ---------------------------------------------------------------- guide 17
def _grab_17_filter_calculator():
    """FCS Filter Calculator (emtk) on its built-in example: Auto-fit 2 species + Unmix.

    The caption quotes this example's numbers (1.16 ns / 3.38 ns, 66 / 34 %, chi2_r 1.04);
    each step is settled, so the figure never shows a half-finished computation.
    """
    from emtk.testing import PixelPainter, png_encode
    from emtk_shot import app_from

    from chisurf.plugins.fcs.fcs_filter_calculator.test.driving import FilterDriver

    app = app_from("fcs_filter_calculator")
    driver = FilterDriver(app, (1400, 900))
    driver.settle()  # the first computation publishes its model snapshot: edit the live one after it
    model = app.model
    model.components.clear()
    model._auto_fit_settings["n_components"] = 2
    model._auto_fit_components()
    driver.settle()
    print("autofit:", model.message)
    model.unmix()
    driver.settle()
    print("unmix:", model.message)

    def write(name):
        for _ in range(2):
            painter = PixelPainter(1400, 900)
            app.draw(painter, 0, 0, 1400, 900)
        (FIG / name).write_bytes(png_encode(painter.width, painter.height, painter.px))
        print("wrote", name)

    write("17_filter_calculator.png")
    driver.tab("Auto-fit")
    write("17_filter_calculator_autofit.png")
    app.close()
    return app


# ---------------------------------------------------------------- guide 18
def _grab_18_lfcs_sim():
    """Lifetime-FCS simulator after *Simulate* with its default two species."""
    from emtk.testing import Driver

    from emtk_shot import app_from, render, wait

    app = app_from("fcs-lfcs-sim")
    driver = Driver(app, (1100, 620))
    driver.frame(2)
    driver.click("Simulate + Correlate")  # the real button: runs on a worker and writes the status line
    wait(driver, lambda: not app.running)
    m = app.model
    print("datasets", [d["name"] for d in m.datasets], "cond", m.condition_number)
    render(app, "18_lfcs_sim.png", driver=driver)
    return app


def _grab_18_sim_setup():
    """Acquisition simulator setup dialog: two species, green+red, a 2x2 rate grid."""
    from chisurf.plugins.core.acq.tcspc_devices.simulation.setup_dialog import (
        EnhancedSimulationSetupDialog,
    )

    dlg = EnhancedSimulationSetupDialog()
    dlg._apply_parameters(
        {
            "N_species": 2,
            "green_enabled": True,
            "red_enabled": True,
            "species_M": [20.0, 20.0],
            "species_D": [3.0, 3.0],
            "species_q": [60.0, 60.0, 15.0, 15.0, 0.0, 0.0, 20.0, 20.0, 55.0, 55.0, 0.0, 0.0],
            "k_rad": [0.0, 1.0, 0.5, 0.0],
            "decay_lifetimes": [[[1.0, 3.8]], [[1.0, 1.2]]],
        }
    )
    dlg.resize(760, 1000)
    dlg.show()
    _settle()
    from qtpy import QtWidgets

    # Open the collapsed Kinetics panel (its header is a toggle button).
    for b in dlg.findChildren(QtWidgets.QAbstractButton):
        if "Kinetics" in b.text():
            b.click()
    _settle()
    if os.environ.get("SHOT_PROBE"):
        _probe_tabs(dlg, "18setup")
    print("params k_rad", dlg.get_parameters().get("k_rad"), "N", dlg.get_parameters().get("N_species"))
    _grab(dlg, "18_sim_setup.png")
    return dlg


# ---------------------------------------------------------------- guide 19
_SM_DNA = pathlib.Path("chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna")


def _sm_dna_copy():
    """Copy the BH SPC-132 smFRET burst sample to scratch (tools write beside it)."""
    work = pathlib.Path(tempfile.mkdtemp()) / "bh_spc132_sm_dna"
    shutil.copytree(_SM_DNA, work)
    return work, sorted(work.glob("burstwise_All*"))[0]


def _grab_19_h2mm():
    """H2MM on the BH SPC-132 smFRET burst folder: a real 1-3 state scan."""
    from emtk.testing import Driver

    from emtk_shot import app_from, render, wait

    work, folder = _sm_dna_copy()
    app = app_from("burst_h2mm")
    m = app.model
    driver = Driver(app, (1400, 900))
    driver.frame(2)
    from guides_26_36 import SM_DNA_SETUP

    m.set_setup(SM_DNA_SETUP)  # explicit: a setup persisted in the settings dir must not pick the photons
    m.donor, m.acceptor = "green", "red"
    print("detectors:", m.detector_names(), "donor/acceptor:", m.donor, m.acceptor)
    m.data_folder = str(folder)
    m.min_states, m.max_states, m.restarts, m.seed = 2, 3, 1, 0
    app.run()
    wait(driver, lambda: not app.job.busy, timeout=float(os.environ.get("H2MM_WAIT", "400")))
    r = m.result
    print("result:", None if r is None else (r.n_states, getattr(r, "populations", None)))
    app.bootstrap()
    wait(driver, lambda: not app.job.busy, timeout=400)
    app.ll_scan()
    wait(driver, lambda: not app.job.busy, timeout=400)
    print("status:", m.status_text)
    render(app, "19_h2mm_tool.png", driver=driver)
    return app


# ---------------------------------------------------------------- guide 21
def _grab_21_burst_mle():
    """Burst MLE (emtk app) on m000.bur of the BH SPC-132 sample, one-click IRF/bg + fit.

    The same drive as ``tests/test_emtk_mle_native.py`` (detectors, a dropped .bur, Auto IRF/background), on the
    in-repo sample with its own channel map (green = routing 0/8, red = 1/9 per the folder's burst-analysis handoff).
    """
    from emtk.testing import Driver

    from emtk_shot import app_from, render, wait

    work, folder = _sm_dna_copy()
    app = app_from("burst_mle_analysis")
    definition = {
        "detectors": {
            name: dict(d, g_factor=1.0, l1=0.0308, l2=0.0368) for name, d in _BH_DETECTORS.items()
        },
        "windows": {},
        "file_type": "SPC-130",
    }
    app.editor.model.data["detectors"] = definition["detectors"]
    app.model.set_setup(definition)
    driver = Driver(app, (1400, 900))
    driver.frame(3)
    assert app.model.add_files([folder / "bi4_bur" / "m000.bur"])
    app.model.current_detector = "green"
    driver.frame(3)
    app.auto_extract()
    wait(driver, lambda: not app.job.busy, timeout=400)
    print("tau green:", app.model.tau_result, "binning", app.model.binning,
          "range", app.model.session.micro_time_range)
    render(app, "21_burst_mle.png", size=(1400, 900), driver=driver)
    return app


# ---------------------------------------------------------------- guide 22
def _grab_22_trace_browser():
    """Trace Browser (emtk window) on the ten BH SPC-132 smFRET files, copied: it writes a meta file."""
    import time

    from emtk.export import save_png

    from chisurf.plugins.tttr.trace_browser.gui.app import make_app

    work, _folder = _sm_dna_copy()
    app = make_app()   # a QApplication runs here, so the HMM / TW / NDX buttons are hosted (enabled)
    app.model.accept_setup(
        {
            "detectors": dict(_BH_DETECTORS),
            "windows": {},
            "tttr_reading": {"file_type": "SPC-130"},
        }
    )
    app.model.precompute_after_scan = False
    app.model.request("open_folder", work)
    from emtk.testing import RecordingPainter

    def frames(n=1):
        for _ in range(n):
            app.draw(RecordingPainter(), 0, 0, 1200, 800)

    deadline = time.time() + 120
    frames()
    while time.time() < deadline and (
        app.job.busy or app._queue or app.load_job.busy or app.model.trace is None
    ):
        time.sleep(0.05)
        frames()
    frames(3)
    print("rows:", len(app.model.rows), "selected:", app.model.current_file)
    save_png(app, str(FIG / "22_trace_browser.png"), size=(1200, 800))
    print("wrote 22_trace_browser.png")
    app.close()


# ---------------------------------------------------------------- guide 23
def _grab_23_fps_editor():
    """FPS JSON Editor (the emtk app) with the HIV-RT labelling project loaded and every AV computed."""
    import time

    from emtk.testing import PixelPainter, RecordingPainter, png_encode

    from chisurf.plugins.modelling.fps_json_editor.gui.app import make_app

    src = pathlib.Path("chisurf/plugins/modelling/fret/examples/fps_hiv_rt")
    work = pathlib.Path(tempfile.mkdtemp()) / "fps_hiv_rt"
    shutil.copytree(src, work, ignore=shutil.ignore_patterns("dock_out"))
    # The shipped project names each site's structure relative to itself
    # (protein body 0 = protein_1R0A.pdb, DNA body 1 = dna.pdb): load it as a user does.
    app = make_app()
    app.load_path(str(work / "hiv_rt.fps.json"))
    app.editor.compute_all()
    deadline = time.time() + 300
    while app.editor.busy and time.time() < deadline:
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
        time.sleep(0.05)
    for _ in range(3):
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
    first = app.editor.rows_pos[0]["row"]
    app.editor.selected_pos = first
    app.editor.selected_dist = app.editor.rows_dist[0]["row"]
    for tab, name in (("Positions", "23_fps_editor.png"), ("Distances", "23_fps_editor_distances.png"),
                      ("3D View", "23_fps_editor_3d.png")):
        app.tab = tab
        painter = PixelPainter(1200, 800)
        for _ in range(6):  # chimol's chrome (3D View) settles over a few frames
            painter = PixelPainter(1200, 800)
            app.draw(painter, 0, 0, 1200, 800)
        (FIG / name).write_bytes(png_encode(painter.width, painter.height, painter.px))
        print("wrote", name)
    print("AV:", app.editor.av_message)
    app.close()


# ---------------------------------------------------------------- guide 24
def _grab_24_clsm_draw():
    """CLSM-Draw on the Leica SP8 test image: intensity, a brushed region, its decay."""
    from emtk_shot import app_from, render

    app = app_from("clsm")
    m = app.model
    m.apply_preset("Leica SP8")
    m.load_file(str(pathlib.Path("test/data/clsm/Leica_SP8.ptu").resolve()))
    m.setup.channels_text = os.environ.get("CLSM_CH", "0,1")
    m.add_clsm()
    m.add_representation()
    img = m.current_image
    print("image", img.shape, "max", img.max(), "mean", img.mean())
    # The brightest 5 % of pixels as the painted selection.
    m.selection_mask = (img >= np.quantile(img, 0.95)).astype(float)
    m.notify("selection")
    d = m.recompute_decay()
    print("decay photons", float(np.sum(d["counts"])))
    m.add_roi("bright patch")
    print("summary:", m.region_summary("bright patch"))
    render(app, "24_clsm_draw.png", size=(1400, 860))
    render(app, "24_clsm_draw_rois.png", size=(900, 600))
    return app


# ---------------------------------------------------------------- guide 25
def _grab_25_accurate_fret():
    """Accurate FRET (native app) on simulated PIE/ALEX bursts with the guide's instrument.

    γ = 1.35, α = 0.09, δ = 0.06, β = 0.95; FRET populations at E = 0.30 and
    0.70 plus donor-only and acceptor-only — the same numbers as the guide's
    matplotlib figure, so the tool's recovered factors can be read against them.
    """
    import tempfile as _tf

    from emtk_shot import FIG, accurate_fret_calibrated, show_tabs, simulated_alex_table

    table = simulated_alex_table(
        pathlib.Path(_tf.mkdtemp()) / "rcm_alex_bursts.csv",
        gamma=1.35, alpha=0.09, beta=0.95, delta=0.06, efficiencies=(0.30, 0.70), seed=25,
    )
    app, driver = accurate_fret_calibrated(table, size=(1500, 900))
    show_tabs(driver, "Report", "E–S populations")
    driver.screenshot(FIG / "25_accurate_fret.png")
    show_tabs(driver, "Correction factors")
    driver.screenshot(FIG / "25_accurate_fret_factors.png")
    print("wrote 25_accurate_fret.png, 25_accurate_fret_factors.png", flush=True)
    return app


if __name__ == "__main__":
    app = QApplication.instance() or QApplication([])
    keep = []
    for n in sys.argv[1:]:
        keep.append(globals()[n]())
