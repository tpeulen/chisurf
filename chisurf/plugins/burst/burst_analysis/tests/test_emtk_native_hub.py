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
    while (any(_busy(c) for c in drv.app.children.values()) or drv.app._pending_next) and time.monotonic() < end:
        time.sleep(0.05)
        drv.draw(1)
    drv.draw(2)


def walk_to_bursts(hub, files) -> Driver:
    """Setup 'probe', Next, drop the files, Next, Next (runs the search): the bursts are in the context."""
    drv = Driver(hub, (1200, 800))
    drv.draw(3)
    hub.children["setup"].select_setup("probe")
    drv.draw(2)
    drv.click(hub.item_rects["next"])
    drv.draw(2)
    assert hub.selected == "data"
    assert drv.drop(*files)
    drv.draw(2)
    drv.click(hub.item_rects["next"])
    drv.draw(2)
    assert hub.selected == "selection"
    drv.click(hub.item_rects["next"])  # Next runs the search, then moves on once it is done
    settle(drv)
    return drv


def test_the_rail_is_the_legacy_panel_table():
    """Same steps, same order, same names and roles as the Qt shell's BURST_PANELS."""
    from chisurf.plugins.burst.burst_analysis.gui.native import STEPS
    from chisurf.plugins.burst.burst_analysis.gui.tool import BURST_PANELS

    native = [(p["role"], p["name"], bool(p.get("optional"))) for p in STEPS if not p.get("separator")]
    legacy = [(p["role"], p["name"], bool(p.get("optional"))) for p in BURST_PANELS if not p.get("separator")]
    assert native == legacy


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
    assert ctx.burst_folder is not None and ctx.burst_folder.name == "sliding_window_All 0.1500#60"
    assert [p.name for p in ctx.bur_files] == ["m000.bur", "m001.bur"]
    assert "2. Burst Selection (2)" in [p["name"] for p in hub.tools]  # the rail's badge

    for role in ("bva", "two_cde", "mle", "h2mm", "segment_mle", "browser", "accurate_fret", "burst_fcs",
                 "burst_gs", "background", "irf_bg"):
        hub.select(role)
        settle(drv)
        assert hub.errors.get(role) is None, (role, hub.errors.get(role))
    c = hub.children
    assert c["bva"].model.analysis_folder == ctx.burst_folder
    assert (c["bva"].model.donor_channels_text, c["bva"].model.acceptor_channels_text) == ("0,1", "8,9")
    assert c["two_cde"].model.folder == str(ctx.burst_folder)
    assert (c["two_cde"].model.donor_channels_text, c["two_cde"].model.file_type) == ("0,1", "SPC-130")
    for role, split in (("mle", False), ("segment_mle", True)):
        assert c[role].model.n_bursts == 198
        assert c[role].model.detector_names() == ["green", "red"]
        assert c[role].model.split_by_state is split
    assert Path(c["h2mm"].model.data_folder) == ctx.burst_folder
    assert c["browser"].model.table is not None
    assert Path(c["accurate_fret"].model.filename).name == "m000.bur"
    assert c["accurate_fret"].model.setup_name == "probe"
    assert c["burst_fcs"].controller.files == [str(ctx.burst_folder)]
    assert [Path(p).name for p in c["burst_gs"].model.bur_files] == ["m000.bur", "m001.bur"]
    assert [Path(p).name for p in c["background"].model.files] == ["m000.spc", "m001.spc"]
    assert c["background"].model.diagnostics  # estimated on arrival, as the Qt step does
    assert [Path(p).name for p in c["irf_bg"].model.files] == ["m000.spc", "m001.spc"]
    assert "bursts: sliding_window_All 0.1500#60" in hub.status


def test_a_fused_folder_redirects_the_later_steps(hub, files, tmp_path):
    drv = walk_to_bursts(hub, files)
    hub.select("bva")
    settle(drv)
    fused = tmp_path / "fused"
    shutil.copytree(hub.context.burst_folder, fused)
    hub.select("fusion")
    drv.draw(2)
    fusion = hub.children["fusion"]
    assert fusion.model.folder_written is not None
    fusion.model.folder_written(str(fused))  # what the step's Fuse button announces when it wrote its folder
    assert hub.context.burst_folder == fused
    assert hub.children["bva"].model.analysis_folder == fused  # an open step follows at once
    # a new search supersedes the fusion
    hub._selection_done(hub.children["selection"].model)
    assert hub.context.burst_folder.name == "sliding_window_All 0.1500#60"


def test_send_to_mle_reaches_both_mle_steps(hub, files):
    drv = walk_to_bursts(hub, files)
    for role in ("mle", "segment_mle"):
        hub.select(role)
        drv.draw(2)
    n = hub.children["mle"].model.session.decay.size if hub.children["mle"].model.session.decay is not None else 64
    patterns = {"green": {"irf": np.ones(n), "bg": np.full(n, 0.5)}}
    assert hub.apply_irf_background_to_mle(patterns) == 1
    for role in ("mle", "segment_mle"):
        session = hub.children[role].model.session
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
    hub.select("bva")
    drv.draw(2)
    state = hub.export_settings()
    assert state["selected"] == "bva"
    from chisurf.plugins.burst.burst_analysis.gui.native import create_app

    again = create_app()
    try:
        again.restore_settings(state)
        assert again.selected == "bva"
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
    done = subprocess.run([sys.executable, "-c", script], cwd=repo, env=env, capture_output=True, text=True)
    assert done.returncode == 0 and "QT-FREE OK" in done.stdout, (done.stdout + done.stderr)[-3000:]
