"""The native Burst Analysis hub (cards BA0-BA2): the workflow walked with real input on copies of the in-repository
BH SPC-132 files.

The setup is chosen, the files arrive by a host drop on the data step, Next runs Burst Selection (the Qt tool's 198
bursts), and every later step is opened and checked for what the workflow handed it.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.emtk_test_input import Driver

DATA = Path(__file__).parents[2] / "burst_selection" / "tests" / "data" / "bh_spc132_sm_dna"
GUI = Path(__file__).parents[1] / "gui"
SETUP = {
    "detectors": {
        "green": {"chs": [0, 1], "micro_time_ranges": []},
        "red": {"chs": [8, 9], "micro_time_ranges": []},
    },
    "windows": {},
    "tttr_reading": {"file_type": "SPC-130"},
}


from chisurf.plugins.burst.burst_analysis.workflow_context import analysis_path  # noqa: E402


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    (tmp_path / "settings").mkdir()
    (tmp_path / "mmfdb").mkdir()
    data = tmp_path / "data"
    data.mkdir()
    for name in ("m000.spc", "m001.spc"):
        shutil.copy(DATA / name, data / name)
    from chisurf.plugins.burst.burst_selection.gui.model import save_setup

    save_setup("probe", SETUP)
    return [data / "m000.spc", data / "m001.spc"]


@pytest.fixture
def hub(files):
    from chisurf.plugins.burst.burst_analysis.gui.native import create_app

    app = create_app()
    yield app
    app.close()


def _busy(child) -> bool:
    for obj in (child, getattr(child, "controller", None), getattr(child, "job", None)):
        for name in ("running", "busy"):
            if getattr(obj, name, False) is True:
                return True
    return False


def settle(drv, timeout=240.0) -> None:
    end = time.monotonic() + timeout
    drv.draw(2)
    while (
        any(_busy(c) for c in drv.app.children.values()) or drv.app._pending_next
    ) and time.monotonic() < end:
        time.sleep(0.05)
        drv.draw(1)
    drv.draw(2)


def walk_to_bursts(hub, files) -> Driver:
    """Setup 'probe', Next, hand the photon streams over (as the Datasets workspace does), Next, Next
    (runs the search): the bursts are in the context. Advanced: every step is on the rail."""
    drv = Driver(hub, (1200, 800))
    hub.set_advanced(True)
    drv.draw(3)
    hub.children["setup"].select_setup("probe")
    drv.draw(2)
    drv.click(hub.item_rects["next"])
    drv.draw(2)
    assert hub.selected == "data"
    from chisurf.plugins.burst.burst_analysis.gui.native import receive_photons

    receive_photons(hub, {"files": [str(f) for f in files]})
    assert [str(p) for p in hub.children["data"]._paths()] == [str(f) for f in files]
    drv.draw(2)
    drv.click(hub.item_rects["next"])
    drv.draw(2)
    assert hub.selected == "selection"
    drv.click(hub.item_rects["next"])  # Next runs the search, then moves on once it is done
    settle(drv)
    return drv


def test_the_rail_is_simple_unless_advanced(hub):
    """Simple: the required steps (setup, data, burst selection, MLE) and the side tools; BVA and
    2CDE run unseen, Fusion and H2MM are Advanced; one MLE step (its split by H2MM state is a
    switch of that step, in Advanced)."""
    from chisurf.plugins.burst.burst_analysis.gui.native import STEPS

    roles = [p["role"] for p in STEPS if not p.get("separator")]
    assert "segment_mle" not in roles
    pipeline = roles[: roles.index("h2mm") + 1]
    assert pipeline == ["setup", "data", "selection", "fusion", "bva", "two_cde", "mle", "h2mm"]
    assert hub.shown_roles()[:4] == ["setup", "data", "selection", "mle"]
    hub.set_advanced(True)
    assert hub.shown_roles()[: len(pipeline)] == pipeline
    hub.set_advanced(False)
    assert "fusion" not in hub.shown_roles() and "bva" not in hub.shown_roles()


def test_every_step_opens_and_draws_empty(hub):
    drv = Driver(hub, (1200, 800))
    for panel in hub.tools:
        hub.select(panel["role"])
        drv.draw(2)
        assert hub.errors.get(panel["role"]) is None, (panel["role"], hub.errors.get(panel["role"]))
        assert hub.child is not None
    Driver(hub, (800, 600)).draw(2)


def test_the_workflow_hands_every_step_its_input(hub, files):
    drv = walk_to_bursts(hub, files)
    selection = hub.children["selection"]
    assert selection.model.n_bursts == 198, selection.model.status_text
    assert hub.selected == "fusion"  # Next ran the search and moved on
    ctx = hub.context
    assert ctx.setup_name == "probe"
    assert [p.name for p in ctx.raw_files] == ["m000.spc", "m001.spc"]
    # the later steps read the run the search wrote, by its address (m000.pto/<run>)
    assert ctx.burst_folder is not None and ctx.burst_folder.parent.name == "m000.pto"
    assert ctx.burst_folder.name.startswith("sliding_window_All 0.1500#60")  # "(2)" when one exists
    assert [p.parent.name for p in ctx.bur_files] == ["m000.pto", "m001.pto"]
    assert "2. Burst Selection ✓" in [p["name"] for p in hub.tools]  # the rail checks the step

    for role in (
        "bva",
        "two_cde",
        "mle",
        "h2mm",
        "browser",
        "accurate_fret",
        "burst_fcs",
        "burst_gs",
        "background",
        "irf_bg",
    ):
        hub.select(role)
        settle(drv)
        assert hub.errors.get(role) is None, (role, hub.errors.get(role))
    c = hub.children
    # The search writes no legacy folder: every step reads the run of the analysis container.
    assert ctx.legacy_burst_folder is None
    run = analysis_path(ctx)  # the search's run, named as the search names it
    assert run.parent.name == "m000.pto" and run.name.startswith("sliding_window_All 0.1500#60")
    assert str(c["bva"].model.analysis_folder) == str(run)
    assert (c["bva"].model.donor_channels_text, c["bva"].model.acceptor_channels_text) == (
        "0,1",
        "8,9",
    )
    assert c["two_cde"].model.folder == str(run)
    assert (c["two_cde"].model.donor_channels_text, c["two_cde"].model.file_type) == (
        "0,1",
        "SPC-130",
    )
    assert c["mle"].model.n_bursts == 198, (hub.status, c["mle"].model.status_text)
    assert c["mle"].model.detector_names() == ["green", "red"]
    assert c["mle"].model.split_by_state is False
    assert Path(c["h2mm"].model.data_folder) == run
    assert c["browser"].model.table is not None
    # ... and the container readers: accurate FRET reads the newest run of m000.pto
    # ... and accurate FRET reads the named run of the container
    assert Path(c["accurate_fret"].model.filename).parts[-2].endswith(".pto")
    assert Path(c["accurate_fret"].model.filename).parts[-1] == run.name  # the run the search wrote
    assert c["accurate_fret"].model.setup_name == "probe"
    # the setup's detector names pick the photon counts, not "First Photon (green)"
    assert (c["accurate_fret"].model.column_i_dd, c["accurate_fret"].model.column_i_da) == (
        "Number of Photons (green)",
        "Number of Photons (red)",
    )
    assert c["burst_fcs"].controller.files == [str(ctx.burst_folder)]
    assert [p["pair_name"] for p in c["burst_fcs"].controller._pair_presets] == [
        "green_ACF",
        "red_ACF",
    ]
    assert c["burst_gs"].model.bur_files == [str(run)]
    assert (c["burst_gs"].model.donor_channels, c["burst_gs"].model.acceptor_channels) == (
        "0, 1",
        "8, 9",
    )
    assert [Path(p).name for p in c["background"].model.files] == ["m000.spc", "m001.spc"]
    assert c["background"].model.diagnostics  # estimated on arrival, as the Qt step does
    assert [Path(p).name for p in c["irf_bg"].model.files] == ["m000.spc", "m001.spc"]
    assert "bursts: m000.pto" in hub.status


def test_a_fused_run_redirects_the_later_steps(hub, files):
    drv = walk_to_bursts(hub, files)
    hub.select("bva")
    settle(drv)
    from chisurf.core.fio.fluorescence import burst_tree

    container = analysis_path(hub.context)
    source = burst_tree.list_runs(container)[-1]
    fused = container / f"{source} fused p0.50"  # the run the step writes into the same container
    hub.select("fusion")
    drv.draw(2)
    fusion = hub.children["fusion"]
    assert fusion.model.folder_written is not None
    fusion.model.folder_written(str(fused))  # what the step's Fuse button announces
    assert hub.context.burst_folder == fused and hub.context.legacy_burst_folder is None
    assert hub.context.bur_files == [fused]  # the MLE steps read the fused run too
    assert str(hub.children["bva"].model.analysis_folder) == str(fused)  # an open step follows
    # a new search supersedes the fusion
    hub._selection_done(hub.children["selection"].model)
    assert hub.context.burst_folder.parent.name == "m000.pto" and hub.context.burst_folder != fused


def test_send_to_mle_reaches_the_mle_step(hub, files):
    drv = walk_to_bursts(hub, files)
    hub.select("mle")
    drv.draw(2)
    n = (
        hub.children["mle"].model.session.decay.size
        if hub.children["mle"].model.session.decay is not None
        else 64
    )
    patterns = {"green": {"irf": np.ones(n), "bg": np.full(n, 0.5)}}
    assert hub.apply_irf_background_to_mle(patterns) == 1
    session = hub.children["mle"].model.session
    np.testing.assert_array_equal(session.irf_np["green"], np.ones(n))
    np.testing.assert_array_equal(session.bg_np["green"], np.full(n, 0.5))
    assert hub.context.irf_background_patterns == patterns


def test_guide_steps_point_at_real_controls(hub):
    steps = json.loads((GUI / "guide.json").read_text(encoding="utf-8"))["steps"]
    drv = Driver(hub, (1200, 800))
    drv.draw(2)
    for step in steps:
        key = hub.tour._target_key(step.get("target"))
        if key:
            assert hub._target_rect(key), key


def test_hub_controls_have_tooltips(hub):
    sys.modules.pop("test", None)
    from test.gui.emtk_port_parity import emtk_inventory

    inventory = emtk_inventory(hub)
    assert inventory["controls_without_tooltip"] == []


def test_settings_round_trip(hub):
    drv = Driver(hub, (1200, 800))
    hub.select("data")
    drv.draw(2)
    state = hub.export_settings()
    assert state["selected"] == "data"
    from chisurf.plugins.burst.burst_analysis.gui.native import create_app

    again = create_app()
    try:
        again.restore_settings(state)
        # restored without data (no files: the shell reopens tools without them) the workflow
        # starts at its first step; its setup is restored
        assert again.selected == "setup"
        assert again.context.setup_name == hub.context.setup_name
    finally:
        again.close()


def test_fret_detectors_reads_the_green_and_red_detectors():
    from chisurf.core.fluorescence.burst.table import fret_detectors

    assert fret_detectors(SETUP) == {
        "donor": {"chs": [0, 1], "micro_time_ranges": []},
        "acceptor": {"chs": [8, 9], "micro_time_ranges": []},
    }
    assert fret_detectors({}) == {}


def test_native_hub_is_qt_free():
    sys.modules.pop("test", None)
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("burst_analysis", "chisurf.plugins.burst.burst_analysis.gui.native:create_app")
    assert result["ok"], result["output"]


def test_every_step_of_the_hub_opens_without_qt(tmp_path):
    """Not only the first step: each child app the rail opens is made and drawn in an interpreter that forbids Qt."""
    import os
    import subprocess

    repo = Path(__file__).resolve().parents[5]
    script = """
import importlib.abc, sys
class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'}:
            raise RuntimeError('Qt imported: ' + fullname)
sys.meta_path.insert(0, BlockQt())
from emtk.testing import RecordingPainter
from chisurf.plugins.burst.burst_analysis.gui.native import create_app
hub = create_app()
for panel in hub.tools:
    hub.select(panel['role'])
    for _ in range(2):
        hub.draw(RecordingPainter(), 0, 0, 1200, 800)
    assert panel['role'] not in hub.errors, (panel['role'], hub.errors[panel['role']])
bad = sorted(m for m in sys.modules if m == 'chisurf.gui' or m.startswith('chisurf.gui.'))
assert not bad, 'chisurf.gui imported: ' + ', '.join(bad[:5])
hub.close()
print('QT-FREE OK')
"""
    env = dict(
        os.environ,
        CHISURF_SETTINGS_DIR=str(tmp_path),
        MMFDB_SETTINGS_DIR=str(tmp_path),
        MMFDB_DATABASE_PATH=str(tmp_path / "mmfdb.sqlite"),
    )
    done = subprocess.run(
        [sys.executable, "-c", script], cwd=repo, env=env, capture_output=True, text=True
    )
    assert done.returncode == 0 and "QT-FREE OK" in done.stdout, (done.stdout + done.stderr)[-3000:]


def test_the_pipeline_selection_shows_no_legacy_exports(hub, files):
    """On the pipeline Burst Selection writes .pto only: no zipped folders, no flrCIF export, no
    example or Clear (its files are step 1's) -- File > Data > Legacy Export has the legacy formats."""
    drv = Driver(hub, (1400, 900))
    hub.context.raw_files = list(files)
    hub.select("selection")
    drv.draw(3)
    selection = hub.children["selection"]
    shown = set(selection.item_rects) | set(selection.form.rects)
    for key in ("export_cif", "metadata", "load_example", "toolAction_clear", "zip_output", "remove_folder"):
        assert key not in shown, key
    assert "toolAction_run" in shown and "mmfdb_output" in shown
    selection.model.zip_output = selection.model.remove_folder = True
    selection.run()
    assert not selection.model.zip_output and not selection.model.remove_folder


def test_the_steps_open_in_order(hub, files):
    """Burst Selection opens once there are files; MLE, BVA, 2CDE, Fusion, H2MM and the burst side
    tools once the bursts are there. A step that cannot open yet says why; Next and the
    fast-forward never land on it."""
    drv = Driver(hub, (1200, 800))
    drv.draw(2)
    assert hub.panel_enabled("setup") and hub.panel_enabled("data")
    for role in ("selection", "mle", "bva", "h2mm", "browser", "background"):
        assert not hub.panel_enabled(role), role
    hub.select("mle")
    assert hub.selected != "mle" and "Burst Selection" in hub.status
    hub.context.raw_files = list(files)
    assert hub.panel_enabled("selection") and hub.panel_enabled("background")
    assert not hub.panel_enabled("mle")
    walk_to_bursts(hub, files)
    for role in ("mle", "bva", "two_cde", "h2mm", "browser", "accurate_fret"):
        assert hub.panel_enabled(role), role


def test_fast_forward_runs_the_simple_pipeline_to_fitted_lifetimes(hub, files):
    """Simple mode, the files in, >>: the search, then Burst MLE takes the bursts, prepares its IRF
    and background in the background and fits -- the walk used to open MLE and stop unfitted."""
    from chisurf.plugins.burst.burst_analysis.gui.native import receive_photons

    drv = Driver(hub, (1200, 800))
    hub.set_advanced(False)
    drv.draw(2)
    hub.children["setup"].select_setup("probe")
    receive_photons(hub, {"files": [str(f) for f in files]})
    drv.draw(2)
    drv.click(hub.item_rects["fast_forward"])
    end = time.monotonic() + 240
    while time.monotonic() < end and not hub.step_done("mle"):
        drv.draw(1)
        time.sleep(0.02)
    settle(drv)
    mle = hub.children["mle"]
    assert hub.step_done("selection") and hub.step_done("mle"), (hub.status, mle.model.status_text, mle.job.error)
    assert mle.model.n_bursts == 198
    assert len(mle.model.burst_results) == 198 * 2  # a row per burst and detector
    assert not hub.errors, hub.errors
