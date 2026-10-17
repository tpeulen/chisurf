"""Grab functions for guides 26, 27, 29, 30, 31, 32, 33, 35 .

Uses FIG from common.py (run through run.py). The burst
fixture is copied to a temp dir because the tools write output folders beside
their inputs.
"""
import pathlib

from common import FIG  # noqa: F401
import shutil
import tempfile

import numpy as np

_SM_DNA = pathlib.Path("chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna")


def _sm_dna_copy():
    work = pathlib.Path(tempfile.mkdtemp(prefix="sm_dna_"))
    shutil.copytree(_SM_DNA, work / "sm_dna")
    return work / "sm_dna"


#: The SPC-132 DNA sample's detectors: green 0/8 (parallel/perpendicular), red 1/9. Set explicitly -- a detector
#: setup persisted in the settings directory must not decide which photons a guide figure calls donor.
SM_DNA_SETUP = {
    "windows": {},
    "detectors": {
        name: {"chs": chs, "micro_time_ranges": [], "g_factor": 1.0, "l1": 0.0, "l2": 0.0}
        for name, chs in (("green", [0, 8]), ("red", [1, 9]))
    },
    "tttr_reading": {"file_type": "SPC-130", "macro_time_resolution": 0.0,
                     "micro_time_resolution": 0.0, "micro_time_binning": 1},
}


def _grab_h2mm_real():
    """Guides 30/32: the native H2MM window on the real sm-DNA bursts, a 1-4 state scan (~1-2 min)."""
    from emtk.testing import Driver

    from emtk_shot import app_from, show_tabs, wait

    data = _sm_dna_copy()
    app = app_from("burst_h2mm")
    m = app.model
    m.set_setup(SM_DNA_SETUP)
    m.donor, m.acceptor = "green", "red"
    driver = Driver(app, (1600, 1100))
    driver.frame(2)
    m.data_folder = str(data / "burstwise_All 0.1000#15")
    m.max_states = 4
    app.run()
    wait(driver, lambda: not app.job.busy, timeout=900)
    print("status:", m.status_text, flush=True)
    m.dynamic_only, m.nav_burst = True, 3
    show_tabs(driver, "Selection", "Dwell times")
    driver.screenshot(FIG / "30_h2mm_results.png")
    print("wrote 30_h2mm_results.png", flush=True)
    # Guide 32: the donor decay of each FRET state (S1-S3; S0 is the donor-only-like E ~ 0.03).
    show_tabs(driver, "Decays")
    app.nano_states = {1, 2, 3}
    driver.frame(3)
    x, y, _w, _h = driver.rect("Dwell FRET")
    from PIL import Image

    shot = FIG / "32_h2mm_state_decays.png"
    driver.screenshot(shot)
    Image.open(shot).crop((int(x) - 4, int(y) - 2, driver.size[0], int(driver.size[1] * 0.62))).save(shot)
    print("wrote 32_h2mm_state_decays.png", flush=True)
    app.close()


def _grab_h2mm_simulated():
    """Guide 31: H2MM on the plugin's example model, written with a 1 us tick."""
    from chisurf.core.datastore import write_csv_table
    from chisurf.plugins.burst.burst_h2mm.core import h2mm
    from chisurf.plugins.burst.burst_h2mm.core.photons import pack_simulated_bursts
    from chisurf.plugins.burst.burst_h2mm.examples.generate_example_data import default_model
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

    from emtk.testing import Driver

    from emtk_shot import app_from, show_tabs, wait

    app = app_from("burst_h2mm")
    m = app.model
    m.set_setup({
        "windows": {"all": [0, 4095]},
        "detectors": {"donor": {"chs": [0], "micro_time_ranges": []},
                      "acceptor": {"chs": [1], "micro_time_ranges": []}},
        "tttr_reading": {"file_type": "Auto", "macro_time_resolution": 50.0,
                         "micro_time_resolution": 50.0, "micro_time_binning": 1},
    })
    m.donor, m.acceptor = "donor", "acceptor"
    m.data_folder = str(folder)
    m.max_states, m.patience = 4, -1
    driver = Driver(app, (1600, 1100))
    driver.frame(2)
    app.run()
    wait(driver, lambda: not app.job.busy, timeout=300)
    print("status:", m.status_text, flush=True)
    m.dynamic_only = True
    show_tabs(driver, "Selection", "State path")
    driver.screenshot(FIG / "31_h2mm_simulated.png")
    print("wrote 31_h2mm_simulated.png", flush=True)
    app.close()


def _grab_burst_selection_guides():
    """Guides 29, 33, 35: Burst Selection (emtk app) on the ten sm-DNA SPC-130 files (29 and 35 pool all ten)."""
    from emtk.testing import Driver

    from emtk_shot import app_from, render, wait

    data = _sm_dna_copy()
    folder = data.parent / "spc"
    folder.mkdir()
    for spc in data.glob("*.spc"):
        shutil.copy(spc, folder)
    app = app_from("burst_selection")
    # SPC-130 detector channels of the double-labelled DNA sample: green 0/8, red 1/9
    app.apply_setup(
        {
            "windows": {"prompt": [0, 4096]},
            "detectors": {
                name: {"chs": chs, "micro_time_ranges": [[0, 4096]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0}
                for name, chs in (("green", [0, 8]), ("red", [1, 9]))
            },
            "tttr_reading": {"file_type": "SPC-130", "micro_time_binning": 1},
        },
        "BH SPC-130 dsDNA",
    )
    driver = Driver(app, (1400, 860))
    driver.frame(3)
    app.model.add_paths(sorted(folder.glob("*.spc")))
    app.model.select_file(0)
    assert app.run(force=True), app.model.status_text
    wait(driver, lambda: not app.job.busy, timeout=400)
    # 33: the first second of m000.spc
    app.model.window_start_s, app.model.window_length_s = 0.0, 1.0
    app.model.load_diagnostics()
    app.docks.focus("dt")
    render(app, "33_burst_selection_dt.png", size=(1400, 860), driver=driver)
    # 35: the ten files and their burst counts, the bursts of all of them pooled in one histogram
    app.model.window_length_s = 0.0
    app.model.load_diagnostics()
    app.model.pool_files = True
    app.model.hist_feature = "Proximity Ratio"
    app.docks.focus("histogram")
    render(app, "35_burst_selection_files.png", size=(1400, 860), driver=driver)
    # 29: the proximity ratio of all bursts, three Gaussians
    app.model.gmm_components = 3
    app.model.fit_gmm()
    render(app, "29_burst_selection_gmm.png", size=(1400, 860), driver=driver)
    app.close()


def _grab_burst_analysis_pipeline():
    """Guide 27: the native Burst Analysis hub on step 2 after Next searched the ten sm-DNA files."""
    from emtk.testing import Driver

    from chisurf.plugins.burst.burst_analysis.gui.native import create_app
    from chisurf.plugins.burst.burst_selection.gui.model import save_setup
    from emtk_shot import render, wait

    data = _sm_dna_copy()
    # The setup is saved and chosen by name, as on step 0: never the one the settings directory happens to hold.
    save_setup("BH SPC-130 dsDNA", SM_DNA_SETUP)
    hub = create_app()
    driver = Driver(hub, (1400, 860))

    def busy():
        for child in hub.children.values():
            for obj in (child, getattr(child, "controller", None), getattr(child, "job", None)):
                if any(getattr(obj, name, False) is True for name in ("running", "busy")):
                    return True
        return bool(hub._pending_next)

    wait(driver, lambda: "setup" in hub.children, timeout=60)
    hub.children["setup"].select_setup("BH SPC-130 dsDNA")
    driver.click(hub.item_rects["next"])  # 1. Data Selection
    wait(driver, lambda: "data" in hub.children, timeout=60)
    hub.on_files_dropped(sorted(str(p) for p in data.glob("*.spc")))
    driver.click(hub.item_rects["next"])  # 2. Burst Selection
    wait(driver, lambda: "selection" in hub.children, timeout=60)
    driver.click(hub.item_rects["next"])  # Next searches every file, then moves on
    wait(driver, lambda: not busy(), timeout=400)
    print(hub.children["selection"].model.status_text, flush=True)
    hub.select("selection")
    render(hub, "27_burst_analysis_pipeline.png", size=(1400, 860), driver=driver)
    hub.close()


def _grab_burst_shared_setup_mle():
    """Guide 27: the hub's shared setup (step 0) and Burst MLE after Auto IRF/background, two sm-DNA files."""
    import shutil as _shutil

    from emtk.testing import Driver

    from chisurf.plugins.burst.burst_analysis.gui.native import create_app
    from chisurf.plugins.burst.burst_selection.gui.model import save_setup
    from emtk_shot import render, wait

    data = _sm_dna_copy()
    two = data.parent / "two"
    two.mkdir()
    for name in ("m000.spc", "m001.spc"):
        _shutil.copy(data / name, two / name)
    save_setup("BH SPC-130 dsDNA", SM_DNA_SETUP)
    hub = create_app()
    driver = Driver(hub, (1280, 900))

    def busy():
        for child in hub.children.values():
            for obj in (child, getattr(child, "controller", None), getattr(child, "job", None)):
                if any(getattr(obj, name, False) is True for name in ("running", "busy")):
                    return True
        return bool(hub._pending_next)

    wait(driver, lambda: "setup" in hub.children, timeout=60)
    hub.children["setup"].select_setup("BH SPC-130 dsDNA")
    driver.click(hub.item_rects["next"])
    wait(driver, lambda: "data" in hub.children, timeout=60)
    hub.on_files_dropped(sorted(str(p) for p in two.glob("*.spc")))
    driver.click(hub.item_rects["next"])
    wait(driver, lambda: "selection" in hub.children, timeout=60)
    driver.click(hub.item_rects["next"])  # searches both files
    wait(driver, lambda: not busy(), timeout=400)
    print(hub.children["selection"].model.status_text, flush=True)
    hub.select("setup")
    render(hub, "burst_shared_setup.png", size=(1280, 900), driver=driver)
    hub.select("mle")
    wait(driver, lambda: "mle" in hub.children and not busy(), timeout=120)
    driver.click("Auto IRF/background")
    wait(driver, lambda: not busy() and hub.children["mle"].model.session.outcome is not None, timeout=400)
    print(hub.children["mle"].model.model_result_text(), hub.children["mle"].model.status_text, flush=True)
    render(hub, "burst_shared_mle.png", size=(1280, 900), driver=driver)
    hub.close()


def _grab_ndx_2d_gaussians():
    """Guide 26: ndX 2-D Gaussian fit on a simulated four-population E-S table."""
    import ndx_emtk

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
    table = pathlib.Path(tempfile.mkdtemp(prefix="ndx26-")) / "four_populations.csv"
    np.savetxt(table, np.column_stack([e_all, s_all, rng.normal(0, 1, e_all.size)]),
               delimiter=",", header="E,S,n", comments="")

    driver = ndx_emtk.replay(size=(1400, 900))
    ndx_emtk.open_table(driver, table)
    ndx_emtk.axes(driver, "E", "S", "n")
    driver.step({"op": "trigger", "action": "actionFit_Gaussians", "checked": True})
    panel = ndx_emtk.feature(driver, "analysis").gaussians
    for e, s, _n in pops:
        panel.add((e + 0.05, s - 0.05), np.diag([0.08 ** 2, 0.06 ** 2]))
    driver.settle()
    panel.fit()
    driver.settle(3)
    ndx_emtk.save(driver.draw(), FIG, "26_ndx_2d_gaussians.png")
    driver.app.close()
