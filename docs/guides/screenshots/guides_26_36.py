"""Grab functions for guides 26, 27, 29, 30, 31, 32, 33, 35 .

Uses FIG and _grab from common.py (run through run.py). The burst
fixture is copied to a temp dir because the tools write output folders beside
their inputs.
"""
import pathlib

from common import FIG, _grab  # noqa: F401
import shutil
import tempfile
import time

import numpy as np
from qtpy.QtWidgets import QApplication, QTabBar

_SM_DNA = pathlib.Path("chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna")


def _pump(seconds):
    t = time.time()
    while time.time() - t < seconds:
        QApplication.instance().processEvents()
        time.sleep(0.02)


def _select_tab(widget, name):
    for bar in widget.findChildren(QTabBar):
        for i in range(bar.count()):
            if bar.tabText(i) == name:
                bar.setCurrentIndex(i)
                _pump(0.5)
                return True
    return False


def _sm_dna_copy():
    work = pathlib.Path(tempfile.mkdtemp(prefix="sm_dna_"))
    shutil.copytree(_SM_DNA, work / "sm_dna")
    return work / "sm_dna"


def _run_h2mm(tool, timeout=900):
    t0 = time.time()
    tool._run_analysis(force=True)
    while tool._result is None and time.time() - t0 < timeout:
        QApplication.instance().processEvents()
        time.sleep(0.05)
    _pump(1)


def _grab_h2mm_real():
    """Guides 30/32/h2mm: the H2MM window on the real sm-DNA bursts (~1-3 min fit)."""
    from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

    data = _sm_dna_copy()
    tool = H2mmTool()
    tool.resize(1600, 1150)
    tool.show()
    _pump(0.5)
    tool._set_folder(str(data / "burstwise_All 0.1000#15"))
    tool.sb_max_states.setValue(4)
    _run_h2mm(tool)
    tool.cb_dynamic_only.setChecked(True)
    tool.sb_burst.setValue(3)
    _select_tab(tool, "Channel Definitions")
    _grab(tool, "30_h2mm_results.png")
    # Guide 32: the donor decay of each FRET state.
    page = tool._plot_pages["Per-state decay"]
    for state, box in tool._nano_state_boxes.items():
        box.setChecked(state in (1, 2, 3))
    page.resize(900, 560)
    _grab(page, "32_h2mm_state_decays.png")
    tool.close()


def _grab_h2mm_simulated():
    """Guide 31: H2MM on the plugin's example model, written with a 1 us tick."""
    from chisurf.core.datastore import write_csv_table
    from chisurf.plugins.burst.burst_h2mm.core import h2mm
    from chisurf.plugins.burst.burst_h2mm.core.photons import pack_simulated_bursts
    from chisurf.plugins.burst.burst_h2mm.examples.generate_example_data import default_model
    from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

    folder = pathlib.Path(tempfile.mkdtemp(prefix="h2mm_sim_"))
    rng = np.random.default_rng(1)
    times = [np.concatenate([[0], np.cumsum(rng.poisson(4, 119) + 1)]).astype(np.int64)
             for _ in range(400)]
    streams = h2mm.simulate_bursts(default_model(), times, seed=8)
    tttr, frame = pack_simulated_bursts(times, streams, filename="sim_smfret.photon.h5")
    # The example generator writes no macro-time resolution; tttrlib's -1 would
    # become the time base (negative dwell times). Declare 1 us.
    tttr.header.set_macro_time_resolution(1e-6)
    tttr.write_hdf_file(str(folder / "sim_smfret.photon.h5"))
    write_csv_table(folder / "sim_smfret.bur", frame)

    tool = H2mmTool()
    tool.resize(1600, 1150)
    tool.show()
    _pump(0.5)
    tool._set_folder(str(folder))
    tool.detector_page._load_data({
        "windows": {"all": [0, 4095]},
        "detectors": {"donor": {"chs": [0], "micro_time_ranges": []},
                      "acceptor": {"chs": [1], "micro_time_ranges": []}},
        "tttr_reading": {"file_type": "Auto", "macro_time_resolution": 50.0,
                         "micro_time_resolution": 50.0, "micro_time_binning": 1},
    })
    tool._refresh_detector_combos()
    tool.cb_donor.setCurrentText("donor")
    tool.cb_acceptor.setCurrentText("acceptor")
    tool.cb_aex.setCurrentIndex(0)
    tool.sb_max_states.setValue(4)
    tool.sb_patience.setValue(-1)
    _run_h2mm(tool, timeout=120)
    tool.cb_dynamic_only.setChecked(True)
    _select_tab(tool, "Channel Definitions")
    _grab(tool, "31_h2mm_simulated.png")
    tool.close()


def _grab_burst_selection_guides():
    """Guides 29, 33, 35: Burst Selection on the ten sm-DNA SPC-130 files."""
    from chisurf.plugins.burst.burst_selection.gui import sections
    from chisurf.plugins.burst.burst_selection.gui.tool import BurstSelectionTool

    data = _sm_dna_copy()
    folder = data.parent / "spc"
    folder.mkdir()
    for spc in data.glob("*.spc"):
        shutil.copy(spc, folder)
    tool = BurstSelectionTool()
    tool.resize(1400, 860)
    tool.show()
    _pump(1)
    tool._add_paths([folder])
    t0 = time.time()
    tool.analyze_files(force=True)
    while not tool._has_processed and time.time() - t0 < 240:
        QApplication.instance().processEvents()
        time.sleep(0.05)
    _pump(1)
    window = tool.findChildren(sections._TimeWindowSection)[0]
    window.length_spin.setValue(1.0)
    _pump(2)
    _select_tab(tool, "dT")
    _grab(tool, "33_burst_selection_dt.png")
    tool.file_list.selectAll()
    _pump(1)
    window.enabled_box.setChecked(False)
    _pump(3)
    _select_tab(tool, "dT")
    _grab(tool, "35_burst_selection_files.png")
    _select_tab(tool, "Histogram")
    tool.feature_combo.setCurrentText("Proximity Ratio")
    tool.gmm_components_spin.setValue(3)
    tool._fit_gmm()
    _pump(1)
    _grab(tool, "29_burst_selection_gmm.png")
    tool.close()


def _grab_burst_analysis_pipeline():
    """Guide 27: Burst Analysis, step 2 after a search over the ten files."""
    from chisurf.plugins.burst.burst_analysis.gui.tool import BurstAnalysisTool

    data = _sm_dna_copy()
    folder = data.parent / "spc"
    folder.mkdir()
    for spc in data.glob("*.spc"):
        shutil.copy(spc, folder)
    tool = BurstAnalysisTool()
    tool.resize(1600, 1000)
    tool.show()
    _pump(1)
    tool.nav_list.setCurrentRow(0)
    _pump(1)
    tool._panel_widget(0).add_paths(sorted(folder.glob("*.spc")))
    tool.nav_list.setCurrentRow(1)
    _pump(2)
    selection = tool._panel_widget(1)
    t0 = time.time()
    selection.analyze_files(force=True)
    while not getattr(selection, "_has_processed", False) and time.time() - t0 < 240:
        QApplication.instance().processEvents()
        time.sleep(0.05)
    _pump(2)
    _grab(tool, "27_burst_analysis_pipeline.png")
    tool.close()


def _grab_ndx_2d_gaussians():
    """Guide 26: ndX 2-D Gaussian fit on a simulated four-population E-S table."""
    import sys

    from qtpy.QtCore import QEventLoop, QTimer

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

    rng = np.random.default_rng(3)
    pops = [(0.25, 0.5, 900), (0.75, 0.5, 700), (0.03, 0.95, 500), (0.95, 0.08, 300)]
    e_all, s_all = [], []
    for e, s, n in pops:  # binomial shot noise, 20 + Poisson(60) photons per burst
        photons = rng.poisson(60, n) + 20
        n_dex = rng.binomial(photons, s)
        n_da = rng.binomial(n_dex, e)
        e_all.append(n_da / np.maximum(n_dex, 1))
        s_all.append(n_dex / photons)
    e_all, s_all = np.concatenate(e_all), np.concatenate(s_all)
    win = NDXplorer(data_source=DataSource.from_columns(
        {"E": e_all, "S": s_all, "n": rng.normal(0, 1, e_all.size)}))
    win.resize(1400, 900)
    win.show()
    app.processEvents()
    control = win.plot_control
    control.update(update_comboboxes=True, update_plots=False)
    control.comboBoxSelX.setCurrentIndex(0)
    control.comboBoxSelY.setCurrentIndex(1)
    control.comboBoxSelZ.setCurrentIndex(2)
    win.update_plots()
    for _ in range(10):
        settle(100)
        if win._histogram.get("2d") is not None:
            break
    win.actionFit_Gaussians.setChecked(True)  # View > Fit Gaussians
    settle(200)
    panel = win.gaussian_fit
    for e, s, _n in pops:
        panel._append_gaussian_row((e + 0.05, s - 0.05), np.diag([0.08 ** 2, 0.06 ** 2]))
    panel._redraw_gaussian_overlays_from_table()
    settle(100)
    panel.on_fit_2d_gaussian()
    settle(300)
    _grab(win, "26_ndx_2d_gaussians.png")
    win.close()
