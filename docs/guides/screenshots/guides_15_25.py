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

    from chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_detector_setups import (
        save_detector_setups,
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
    save_detector_setups(
        {"setups": {_BH_SETUP: {"detectors": _BH_DETECTORS}}, "last_used": _BH_SETUP}
    )
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
    """Burst Background Estimation on the BH SPC-132 smFRET file (guide 15).

    The file is copied to a scratch folder: the estimate records its rates
    beside the photons, which must not land in ``test/data``.
    """
    from chisurf.plugins.burst.burst_background import BurstBackgroundEstimator

    work = pathlib.Path(tempfile.mkdtemp())
    spc = work / _SPC_FILE.name
    shutil.copy(_SPC_FILE, spc)
    tool = BurstBackgroundEstimator(show_channel_definition=False)
    tool.model.channels_provider = lambda: {
        "green": {"chs": [0, 8], "micro_time_ranges": []},
        "red": {"chs": [1, 9], "micro_time_ranges": []},
    }
    tool._add_tttr_files([str(spc)])
    tool.model.estimate()
    print("status:", tool.model.status)
    print("rates:", tool.model.backgrounds)
    tool.resize(1280, 820)
    _settle()
    if os.environ.get("SHOT_PROBE"):
        _probe_tabs(tool, "15")
    _raise_tab(tool, "Inter-photon time")
    _grab(tool, "15_burst_background.png")
    # The Fit tab on its own, short: four controls do not need 800 px.
    _raise_tab(tool, "Fit")
    tool.resize(900, 600)
    _settle()
    _grab_rect(tool, "15_burst_background_fit.png", 176)
    return tool


# ---------------------------------------------------------------- guide 16
_BURST_FOLDER_GLOB = (
    "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/burstwise_All*"
)


def _grab_16_burst_fcs():
    """Burst-wise FCS on the BH SPC-132 sample burst folder (guide 16).

    A two-detector setup with GG/RR/GR pairs is stored first (isolated MMFDB),
    selected, and *Run* pressed — the tool's own path end to end.
    """
    import glob

    from chisurf.plugins.burst.burst_fcs_correlator.gui.tool import BurstFcsTool

    _ensure_bh_setup()
    folder = sorted(glob.glob(_BURST_FOLDER_GLOB))[0]
    tool = BurstFcsTool()
    tool.setup_selector.refresh()
    combo = tool.setup_selector.combo
    combo.setCurrentIndex(combo.findText(_BH_SETUP))
    _settle()
    print("pairs:", [tool.list_pairs.item(i).text() for i in range(tool.list_pairs.count())])
    tool.file_list.add_paths([folder])
    tool._on_run()
    print("curves", len(tool._curves))
    # Show the longest burst of the first file: a single short burst's
    # correlation is mostly shot noise.
    files = tool._resolve_files()
    ranges = files[0]["ranges"]
    longest = int(np.argmax([b - a for a, b in ranges]))
    print("longest burst", longest, "photons", ranges[longest][1] - ranges[longest][0])
    tool.line_filter.setText(f"b{longest} ")
    tool._refresh_browser_list()
    tool.list_browser.setCurrentRow(0)
    tool.resize(1280, 800)
    _settle()
    if os.environ.get("SHOT_PROBE"):
        _probe_tabs(tool, "16")
    _raise_tab(tool, "Correlation")
    _grab(tool, "16_burst_fcs.png")
    return tool


# ---------------------------------------------------------------- guide 17
def _grab_17_filter_calculator():
    """FCS Filter Calculator on the BH SPC-132 decay: Auto-fit 2 species + Unmix."""
    from chisurf.plugins.fcs.fcs_filter_calculator.gui_parts.main_window import (
        FcsFilterCalculatorWidget,
    )

    _ensure_bh_setup()
    tool = FcsFilterCalculatorWidget()
    tool.resize(1400, 900)
    tool.show()
    _settle()
    print("setup:", tool.setup_selector.current_setup())
    print("detectors:", tool.detector_selection.get_selected())
    print("minsize:", tool.minimumSizeHint(), tool.size())
    tool._set_total_paths([_SPC_FILE.resolve()])
    _settle()
    tool.sb_autofit_n.setValue(2)
    tool._auto_fit_components()
    _settle()
    print("autofit:", tool.lbl_autofit_status.text())
    tool._unmix_total()
    _settle()
    if os.environ.get("SHOT_PROBE"):
        _probe_tabs(tool, "17")
    # The docks stack to ~1450 px minimum height; grab the working half (inputs,
    # components, filters, residuals, reconstruction) and the Auto-fit dock.

    _grab_rect(tool, "17_filter_calculator.png", 550)
    autofit = tool.cb_autofit_kind.parentWidget()
    top = autofit.mapTo(tool, autofit.rect().topLeft()).y() - 30
    _grab_rect(tool, "17_filter_calculator_autofit.png", autofit.height() + 34, top=top)
    return tool


# ---------------------------------------------------------------- guide 18
def _grab_18_lfcs_sim():
    """Lifetime-FCS simulator after *Simulate* with its default two species."""
    from chisurf.plugins.fcs.fcs_lfcs_sim.gui.tool import LifetimeFcsSimWidget

    tool = LifetimeFcsSimWidget()
    tool.resize(1100, 620)
    tool.show()
    _settle()
    from qtpy import QtWidgets

    button = next(
        b for b in tool.findChildren(QtWidgets.QPushButton) if b.text() == "Simulate + Correlate"
    )
    button.click()  # the promoted toolbar button: runs and writes the status line
    m = tool._model
    print("datasets", [d["name"] for d in m.datasets], "cond", m.condition_number)
    _settle()
    _grab(tool, "18_lfcs_sim.png")
    return tool


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
    import time

    from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

    _ensure_bh_setup()
    work, folder = _sm_dna_copy()
    tool = H2mmTool()
    tool.resize(1400, 900)
    tool.show()
    _settle()
    print("detector combos:", [tool.cb_donor.itemText(i) for i in range(tool.cb_donor.count())])
    print("donor/acceptor:", tool.cb_donor.currentText(), tool.cb_acceptor.currentText())
    tool._set_folder(str(folder))
    tool._run_analysis(force=True)
    app = QApplication.instance()
    deadline = time.time() + float(os.environ.get("H2MM_WAIT", "400"))
    while tool._result is None and time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
    r = tool._result
    print("result:", None if r is None else (r.n_states, getattr(r, "populations", None)))
    print("status:", tool.statusBar().currentMessage() if hasattr(tool, "statusBar") else "")
    _settle(30)
    if os.environ.get("SHOT_PROBE"):
        _probe_tabs(tool, "19")
    _raise_tab(tool, "H2MM Settings")
    _grab(tool, "19_h2mm_tool.png")
    return tool


# ---------------------------------------------------------------- guide 21
def _grab_21_burst_mle():
    """Burst MLE wizard on m000.bur of the BH SPC-132 sample, one-click IRF/bg + fit.

    Same drive as ``tests/test_mle_gui_end_to_end.py`` (channels, .bur, Auto
    IRF/background, fit), on the in-repo sample with its own channel map
    (green = routing 0/8, red = 1/9 per the folder's burst-analysis handoff).
    """
    from chisurf.plugins.burst.burst_mle_analysis.wizard import MLELifetimeAnalysisWizard

    work, folder = _sm_dna_copy()
    w = MLELifetimeAnalysisWizard()
    w.resize(1400, 900)
    w.show()
    _settle()
    w.channel_definer.load_data_into_tables(
        {
            "detectors": {
                name: dict(d, g_factor=1.0, l1=0.0308, l2=0.0368)
                for name, d in _BH_DETECTORS.items()
            },
            "windows": {},
            "file_type": "SPC-130",
        }
    )
    w.channel_definer.file_type_combo.setCurrentText("SPC-130")
    w._init_channels_from_wizard()
    w.burst_files_list.add_file(str(folder / "bi4_bur" / "m000.bur"))
    w.load_burst_data()
    w.update_burst_files()
    w.comboBox_window.setCurrentText("green")
    _settle()
    w.auto_extract_irf_bg()
    _settle(30)
    print("tau green:", w.doubleSpinBox_tau_result.value(), "binning", w.micro_time_binning,
          "range", w.micro_time_range)
    if os.environ.get("SHOT_PROBE"):
        _probe_tabs(w, "21")
    _grab(w, "21_burst_mle.png")
    return w


# ---------------------------------------------------------------- guide 22
def _grab_22_trace_browser():
    """Trace Browser on the ten BH SPC-132 smFRET files (copied: it writes a meta file)."""
    from chisurf.plugins.tttr.trace_browser.gui.tool import TraceBrowserTool

    work, _folder = _sm_dna_copy()
    tool = TraceBrowserTool()
    tool.resize(1400, 860)
    tool.show()
    _settle()
    ws = tool._workspace
    # Page 0: the detector definition (green 0/8, red 1/9, SPC-130), then Continue.
    ws.detector_page.load_data_into_tables(
        {"detectors": dict(_BH_DETECTORS), "windows": {}, "file_type": "SPC-130"}
    )
    try:
        ws.detector_page.file_type_combo.setCurrentText("SPC-130")
    except Exception as exc:
        print("file type combo:", exc)
    ws._on_continue()
    print("filetype:", ws.detector_page.filetype, "chs:", ws.selected_channels,
          "exts:", sorted(ws._allowed_exts_for_setup()))
    ws._open_folder(work)
    _settle()
    print("rows (as shipped):", ws.table.rowCount())
    if ws.table.rowCount() == 0:
        # Known defect: _is_clsm_compatible() calls every TTTR an image (an
        # empty (1, 0, 0) CLSMImage has an ``intensity``), so point
        # measurements are filtered out. Seed its cache with the right answer
        # to show what the list does once that probe is fixed.
        for p in work.glob("*.spc"):
            ws._is_image_cache[p] = False
        ws._scan_and_fill()
        _settle()
        print("rows (probe corrected):", ws.table.rowCount())
    ws.table.selectRow(0)
    _settle(40)
    if os.environ.get("SHOT_PROBE"):
        _probe_tabs(tool, "22")
    _grab(tool, "22_trace_browser.png")
    return tool


# ---------------------------------------------------------------- guide 23
def _grab_23_fps_editor():
    """FPS JSON Editor with the HIV-RT labelling project loaded (every tab probed)."""
    from chisurf.plugins.modelling.fps_json_editor.gui.tool import FpsJsonEditorTool

    src = pathlib.Path("chisurf/plugins/modelling/fret/examples/fps_hiv_rt")
    work = pathlib.Path(tempfile.mkdtemp()) / "fps_hiv_rt"
    shutil.copytree(src, work, ignore=shutil.ignore_patterns("dock_out"))
    tool = FpsJsonEditorTool()
    tool.resize(1400, 860)
    tool.show()
    _settle()
    # The shipped project names no structure; point each labelling site at its
    # body (protein body 0 = 1R0A, DNA body 1) so the AVs are computed.
    import json
    import time

    cfg = json.loads((work / "hiv_rt.fps.json").read_text())
    for pos in cfg["Positions"].values():
        pdb = "protein_1R0A.pdb" if int(pos.get("body_id", 0)) == 0 else "dna.pdb"
        pos["pdb_path"] = str((work / pdb).resolve())
    (work / "hiv_rt.fps.json").write_text(json.dumps(cfg, indent=2))
    tool.editor.onLoadJSON(str(work / "hiv_rt.fps.json"))
    panel = tool.editor.position_panel
    deadline = time.time() + 120
    app = QApplication.instance()
    while time.time() < deadline:
        app.processEvents()
        if not getattr(panel, "_active_workers", {}):
            break
        time.sleep(0.05)
    _settle(40)
    print("AV status:", panel.av_preview_label.text(), "cached:", len(getattr(panel, "_av_cache", {})))
    if os.environ.get("SHOT_PROBE"):
        _probe_tabs(tool, "23")
    _raise_tab(tool, "Positions")
    _grab(tool, "23_fps_editor.png")
    _raise_tab(tool, "Distances")
    _grab(tool, "23_fps_editor_distances.png")
    return tool


# ---------------------------------------------------------------- guide 24
def _grab_24_clsm_draw():
    """CLSM-Draw on the Leica SP8 test image: intensity, a brushed region, its decay."""
    from chisurf.plugins.microscopy.clsm.gui.tool import CLSMPixelSelect

    tool = CLSMPixelSelect()
    tool.resize(1400, 860)
    tool.show()
    _settle()
    m = tool.model
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
    try:
        tool.auto_form.sync_fields()
    except Exception:
        pass
    _settle(30)
    if os.environ.get("SHOT_PROBE"):
        _probe_tabs(tool, "24")
    # The docks share one tab group; show Image and Decay side by side.
    from qtpy.QtCore import QRect

    tool.resize(760, 700)
    _settle()
    shots = []
    for tab in ("Image", "Decay"):
        _raise_tab(tool, tab)
        shots.append(tool.grab())
    _compose(shots, "24_clsm_draw.png")
    _raise_tab(tool, "Regions")
    tool.resize(900, 600)
    _settle()
    tool.grab(QRect(0, 0, 900, 130)).save(str(FIG / "24_clsm_draw_rois.png"))
    print("wrote 24_clsm_draw_rois.png")
    return tool


# ---------------------------------------------------------------- guide 25
def _grab_25_accurate_fret():
    """Accurate FRET on simulated PIE/ALEX bursts with the guide's instrument.

    γ = 1.35, α = 0.09, δ = 0.06, β = 0.95; FRET populations at E = 0.30 and
    0.70 plus donor-only and acceptor-only — the same numbers as the guide's
    matplotlib figure, so the tool's recovered factors can be read against them.
    """
    import tempfile as _tf

    from chisurf.core.fluorescence.fret.lines import static_fret_line
    from chisurf.plugins.burst.accurate_fret.gui.tool import AccurateFretTool

    gamma, alpha, beta, delta = 1.35, 0.09, 0.95, 0.06
    tau_d0, r0 = 4.0, 52.0
    line = static_fret_line(tau_d0, r0=r0, sigma=6.0)
    rng = np.random.default_rng(25)
    dd, da, aa, tau = [], [], [], []
    for efficiency, n in ((0.30, 1500), (0.70, 1500)):
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

    table = pathlib.Path(_tf.mkdtemp()) / "rcm_alex_bursts.csv"
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
    _settle()
    if os.environ.get("SHOT_PROBE"):
        _probe_tabs(tool, "25")
    _raise_tab(tool, "E–S")
    _grab(tool, "25_accurate_fret.png")
    _raise_tab(tool, "Correction factors")
    _grab(tool, "25_accurate_fret_factors.png")
    return tool


if __name__ == "__main__":
    app = QApplication.instance() or QApplication([])
    keep = []
    for n in sys.argv[1:]:
        keep.append(globals()[n]())
