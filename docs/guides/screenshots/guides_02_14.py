"""Screenshot grabs for guides 02, 03, 04, 05, 08, 12, 13, 14 (make_screenshots.py style).

Merge into ``docs/guides/make_screenshots.py``: the functions use that module's
``FIG``, ``_grab`` and ``_SPC_FILE`` and ``QApplication``. Standalone, run as::

    QT_QPA_PLATFORM=offscreen CHISURF_SETTINGS_DIR=<scratch> \
    PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." \
    python grabs.py

Two things these grabs must not do to a real installation:

* **write beside the bundled data** — Burst Selection, Burst Fusion and BVA all
  write their output folders next to the files they read, so every grab works
  on a temporary copy of the test data;
* **write a detector setup into the user's settings** — Burst Selection and BVA
  read the setup from the settings store, so ``_bh_setup()`` refuses to run
  unless ``CHISURF_SETTINGS_DIR`` points somewhere explicit.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np  # noqa: E402
from qtpy.QtWidgets import QApplication  # noqa: E402

import chisurf.core.settings  # noqa: E402,F401

FIG = pathlib.Path(__file__).resolve().parents[1] / "figures"
if "SHOTS_FIG" in os.environ:
    FIG = pathlib.Path(os.environ["SHOTS_FIG"])
FIG.mkdir(exist_ok=True)
_SPC_FILE = pathlib.Path("test") / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"
_SM_DNA = pathlib.Path("chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna")
_BH_SETUP = "BH SPC-132"


def _grab(widget, name):
    """Show *widget*, process events, and save a PNG grab into ``figures/``."""
    widget.show()
    QApplication.instance().processEvents()
    widget.grab().save(str(FIG / name))
    print("wrote", name)


def _pump(seconds=0.3):
    """Process events for *seconds* (background tasks finish on the GUI loop)."""
    app = QApplication.instance()
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def _sm_dna_copy() -> pathlib.Path:
    """A throw-away copy of the ten SPC-132 dsDNA files (tools write beside them)."""
    work = pathlib.Path(tempfile.mkdtemp(prefix="sm_dna_"))
    for spc in sorted(_SM_DNA.glob("m00*.spc")):
        shutil.copy(spc, work)
    shutil.copytree(_SM_DNA / "burstwise_All 0.1000#15", work / "burstwise_All 0.1000#15")
    return work


def _bh_setup() -> None:
    """Write the SPC-132 detector setup (green 0/8, red 1/9) into the settings store.

    Also works around the fresh-profile FK failure: the JSON -> MMFDB migration
    stamps setups with ``user_default``, a user a new database does not have.
    """
    if not os.environ.get("CHISURF_SETTINGS_DIR"):
        raise RuntimeError("set CHISURF_SETTINGS_DIR to a scratch dir: this writes a setup")
    import chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_detector_setups as dsetups
    from chisurf.core.data_io.detector_setups import DETECTOR_SETUPS_FILE

    def det(chs):
        return {"chs": chs, "micro_time_ranges": [[0, 4096]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0}

    setup = {
        "setup_name": _BH_SETUP,
        "windows": {"prompt": [0, 4096]},
        "detectors": {"green": det([0, 8]), "red": det([1, 9])},
        "tttr_reading": {"file_type": "SPC-130", "micro_time_binning": 1},
    }
    DETECTOR_SETUPS_FILE.parent.mkdir(parents=True, exist_ok=True)
    DETECTOR_SETUPS_FILE.write_text(json.dumps({"setups": {_BH_SETUP: setup}, "last_used": _BH_SETUP}))
    dsetups.resolve_active_user_id = lambda: ""


def _front_tab(widget, text) -> None:
    """Bring the tab labelled *text* to the front in any tab bar of *widget*."""
    from qtpy.QtWidgets import QTabBar

    for bar in widget.findChildren(QTabBar):
        for i in range(bar.count()):
            if bar.tabText(i) == text:
                bar.setCurrentIndex(i)
    _pump(0.5)


# ── guide 13: burst identification ──────────────────────────────────────


def _grab_13_burst_selection(work: pathlib.Path | None = None, grab: bool = True) -> pathlib.Path:
    """Burst Selection on the ten SPC-132 dsDNA files, searched; returns the burst folder."""
    from chisurf.plugins.burst.burst_selection.gui.tool import BurstSelectionTool

    _bh_setup()
    work = work or _sm_dna_copy()
    tool = BurstSelectionTool()
    tool.resize(1600, 1150)
    tool.show()
    _pump(1)
    tool._add_paths(sorted(work.glob("m00*.spc")))
    tool.file_list.setCurrentRow(0)
    _pump(3)
    tool.analyze_files(force=True)
    _pump(15)
    summary = json.loads(tool.summary.toPlainText())
    print("burst selection:", {k: summary[k] for k in ("n_files", "n_bursts", "n_photons", "n_selected")})
    if grab:
        from qtpy.QtWidgets import QAbstractButton

        _front_tab(tool, "Filter Settings")
        # Fold the Info box (its numbers are the Summary tab's) so the whole
        # burst-search block fits beside the filter mode without scrolling.
        for button in tool.wizard.findChildren(QAbstractButton):
            if button.text().strip().endswith("Info"):
                button.click()
        _pump(0.3)
        _grab(tool, "13_burst_selection_filter.png")
        _front_tab(tool, "MCS")
        _grab(tool, "13_burst_selection_mcs.png")
    tool.close()
    return pathlib.Path(summary["output_folder"])


# ── guide 08: BVA ───────────────────────────────────────────────────────


def _grab_08_bva_tool(folder: pathlib.Path | None = None) -> None:
    """BVA on the burst folder Burst Selection wrote for the ten dsDNA files.

    Needs ``CHISURF_PLOT_BACKEND=pyqtgraph`` until the emtk error-bar update is
    fixed (the default backend paints neither the heat map nor the axes).
    """
    from chisurf.plugins.burst.burst_bva.gui.tool import BVATool

    _bh_setup()
    folder = folder or _grab_13_burst_selection(grab=False)
    tool = BVATool()
    tool.resize(1400, 900)
    tool.show()
    _pump(1)
    tool._set_folder(str(folder))  # Auto update runs the analysis
    _pump(20)
    _grab(tool, "08_bva_tool.png")
    tool.close()


# ── guide 02: RASP ──────────────────────────────────────────────────────


def _grab_02_rasp_p_same(work: pathlib.Path | None = None) -> None:
    """Burst Fusion's P_same curve over the bundled ten-file burst folder."""
    from chisurf.plugins.burst.burst_fusion.gui.tool import BurstFusionTool

    work = work or _sm_dna_copy()
    tool = BurstFusionTool()
    tool.resize(1250, 800)
    tool.show()
    _pump(0.5)
    tool.set_folder(str(work / "burstwise_All 0.1000#15"))
    tool.model.threshold = 0.5
    tool.model.analyze()  # estimate + preview only; writing needs a reading manifest
    _pump(1)
    _front_tab(tool, "Same-molecule probability")
    _grab(tool, "02_rasp_p_same.png")
    tool.close()


# ── guide 03: polymer distance distributions ────────────────────────────


def _grab_03_polymer_editors() -> None:
    """TCSPC editors of the SAW-nu and Ising-chain FRET models."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.data import DataCurve
    from chisurf.core.models import description
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    for cls, name in (
        (description.tcspc_fret_saw_nu, "03_saw_nu_editor.png"),
        (description.tcspc_fret_ising_chain, "03_ising_chain_editor.png"),
    ):
        x = np.linspace(0, 25, 256)  # ns
        data = DataCurve(x=x, y=np.exp(-x / 4.0) + 1.0)
        fit = fit_mod.Fit(model_class=cls, data=data)
        editor = build_model_editor(fit.model)
        editor.resize(600, 1100 if "ising" in name else 1060)
        _grab(editor, name)


# ── guide 04: PCH / FIDA ────────────────────────────────────────────────


def _grab_04_pch_tool() -> None:
    """The PCH tool with the histogram of BH_SPC132 (green, 50 us bins) computed."""
    from chisurf.plugins.pch.gui.tool import PCHApp

    tool = PCHApp()
    tool.resize(1400, 850)
    tool.show()
    _pump(0.5)
    tool.centralWidget().setSizes([850, 550])
    tool._load_path(str(_SPC_FILE.resolve()))
    tool.le_ch.setText("0,8")
    tool.spin_bin.setValue(50.0)
    tool._on_compute()
    _pump(5)
    print("PCH:", tool.statusBar().currentMessage())
    _grab(tool, "04_pch_tool.png")
    tool.close()


def _grab_04_fida_editor() -> None:
    """The FIDA model fitted to the BH_SPC132 green PCH (two species, bounds on)."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.data import DataCurve
    from chisurf.core.models.pch.fida_model import FidaModel
    from chisurf.gui.widgets.models.model_editor import build_model_editor
    from chisurf.plugins.pch.gui.client import PCHClient

    result = PCHClient().compute(
        filename=str(_SPC_FILE.resolve()), channels=[0, 8], bin_time_us=50.0,
        micro_time_min=0, micro_time_max=65535,
    )
    counts = np.asarray(result["hist_counts"], dtype=float)
    k = np.arange(counts.size, dtype=float)
    data = DataCurve(
        name="BH_SPC132 green 50 us", load_filename_on_init=False,
        x=k, y=counts / counts.sum(), ey=np.sqrt(np.maximum(counts, 1.0)) / counts.sum(),
    )
    fit = fit_mod.Fit(model_class=FidaModel, data=data)
    model = fit.model
    fit.fit_range = (0, counts.size)
    start = {"q1": 0.5, "N1": 1.0, "q2": 5.0, "N2": 0.01}
    for p in model.parameters_all:
        if p.name[0] in "qN":
            p.bounds_on = True  # off by default: the fit then runs N negative
        if p.name in ("q3", "N3"):
            p.fixed = True
        if p.name in start:
            p.value = start[p.name]
    fit.run()
    print("FIDA chi2r", fit.chi2r, [(p.name, round(p.value, 4)) for p in model.parameters_all])
    editor = build_model_editor(model)
    editor.resize(700, 330)
    _grab(editor, "04_fida_editor.png")


# ── guide 05: Enderlein MDF ─────────────────────────────────────────────


def _grab_05_mdf_editor() -> None:
    """The MDF FCS model fitted to the bundled Kristine correlation curve."""
    from qtpy import QtWidgets

    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.data import DataCurve
    from chisurf.core.models.fcs.mdf import MdfFCSModel
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    a = np.loadtxt("test/data/fcs/kristine/Kristine_with_error.cor")
    sel = a[:, 0] > 1e-3  # lag in ms; skip the sub-us antibunching range
    data = DataCurve(
        name="Kristine_with_error.cor", load_filename_on_init=False,
        x=a[sel, 0], y=a[sel, 1], ey=a[sel, 3],
    )
    fit = fit_mod.Fit(model_class=MdfFCSModel, data=data)
    fit.fit_range = (0, int(sel.sum()))
    fit.run()
    print("MDF chi2r", fit.chi2r, [(p.name, round(p.value, 4)) for p in fit.model.parameters_all])
    editor = build_model_editor(fit.model)
    editor.resize(620, 820)
    editor.show()
    _pump(0.3)
    for button in editor.findChildren(QtWidgets.QAbstractButton):
        if any(t in button.text() for t in ("Outputs", "Optics")):
            button.click()
    _pump(0.5)
    _grab(editor, "05_mdf_editor.png")


# ── guide 12: TTTR files ────────────────────────────────────────────────


def _grab_12_tttr_to_pto() -> None:
    """TTTR <-> .pto: three split SPC files packed into one .pto, then unpacked."""
    from chisurf.plugins.core.tttr_to_pto.gui.tool import TttrToPtoTool

    work = pathlib.Path(tempfile.mkdtemp(prefix="pto_"))
    for i in range(3):
        shutil.copy(_SM_DNA / f"m00{i}.spc", work)
    tool = TttrToPtoTool()
    tool.resize(760, 260)
    tool.show()
    _pump(0.3)
    tool._on_dropped([str(work / f"m00{i}.spc") for i in range(3)])
    _pump(0.5)
    tool._on_dropped([str(work / "m000.pto")])
    _pump(0.5)
    _grab(tool, "12_tttr_to_pto.png")
    tool.close()


# ── guide 14: E-S and correction factors ────────────────────────────────


def _grab_14_accurate_fret() -> None:
    """Accurate FRET on a simulated ALEX burst table with known factors, E-S tab.

    There is no ALEX/PIE measurement among the test data, so the populations are
    simulated (alpha 0.08, delta 0.06, gamma 0.65, beta 1.4). Needs
    ``CHISURF_PLOT_BACKEND=pyqtgraph``: the emtk backend joins the scatter points.
    """
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
        da.append(rng.poisson(gamma * efficiency * photons + alpha * (1 - efficiency) * photons
                              + delta * beta * gamma * photons))
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

    table = pathlib.Path(tempfile.mkdtemp(prefix="es_")) / "alex_bursts.csv"
    np.savetxt(
        table,
        np.column_stack([np.concatenate(c).astype(float) for c in (dd, da, aa, tau)]),
        delimiter=",", comments="",
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
    tool.show()
    _front_tab(tool, "E–S")
    _grab(tool, "14_accurate_fret.png")
    tool.close()


def main(names=()):
    """Run the grabs of this file named in *names* (all when empty)."""
    import sys

    app = QApplication.instance() or QApplication([])  # noqa: F841
    work = _sm_dna_copy()
    grabs = {
        "13": lambda: _grab_13_burst_selection(work),
        "08": lambda: _grab_08_bva_tool(_grab_13_burst_selection(work, grab=False)),
        "02": lambda: _grab_02_rasp_p_same(work),
        "03": _grab_03_polymer_editors,
        "04_pch": _grab_04_pch_tool,
        "04_fida": _grab_04_fida_editor,
        "05": _grab_05_mdf_editor,
        "12": _grab_12_tttr_to_pto,
        "14": _grab_14_accurate_fret,
    }
    for name, grab in grabs.items():
        if names and name not in names:
            continue
        try:
            grab()
        except Exception as exc:
            print(f"SKIP {name}: {type(exc).__name__}: {exc}")
        sys.stdout.flush()


if __name__ == "__main__":
    import sys

    main(tuple(sys.argv[1:]))
    os._exit(0)
