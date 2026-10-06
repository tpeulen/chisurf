"""The native ALEX Suite hub (card AS4): the simple workflow walked with real input.

Two walks. On the simulated µs-ALEX measurement of :mod:`..demo` (written into a temporary folder by the files
step's own Load demo data button), Next presses alone take it from the files to an E–S histogram: the alternation
step converts on arrival, the burst search runs on the converted container with the detected setup, the background
is estimated, Accurate FRET calibrates, and ndX shows E against S. On copies of the in-repository BH SPC-132 PIE files
the alternation step leaves the data alone and the burst search finds the Qt tool's 198 bursts.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.emtk_test_input import Driver

PLUGIN = Path(__file__).parents[1]
GUI = PLUGIN / "gui"
PIE = PLUGIN.parent / "burst_selection" / "tests" / "data" / "bh_spc132_sm_dna"
PROBE = {
    "detectors": {
        "green": {"chs": [0, 1], "micro_time_ranges": []},
        "red": {"chs": [8, 9], "micro_time_ranges": []},
    },
    "windows": {},
    "tttr_reading": {"file_type": "SPC-130"},
}


@pytest.fixture
def settings(tmp_path, monkeypatch):
    for key in ("CHISURF_SETTINGS_DIR", "MMFDB_SETTINGS_DIR", "NDXPLORER_SETTINGS_DIR"):
        (tmp_path / key).mkdir()
        monkeypatch.setenv(key, str(tmp_path / key))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    return tmp_path


@pytest.fixture
def hub(settings):
    from chisurf.plugins.burst.alex_suite.gui.native import create_app

    app = create_app()
    yield app
    app.close()


def settle(drv, timeout=240.0) -> None:
    """Draw until no step is busy and no Next is pending."""
    end = time.monotonic() + timeout
    drv.draw(2)
    while (drv.app._busy() or drv.app._pending_next) and time.monotonic() < end:
        time.sleep(0.05)
        drv.draw(1)
    drv.draw(2)


def press_next(drv) -> None:
    drv.click(drv.app.item_rects["next"])
    settle(drv)


def wait_for(drv, condition, timeout=60.0) -> None:
    end = time.monotonic() + timeout
    while not condition() and time.monotonic() < end:
        time.sleep(0.05)
        drv.draw(1)
    drv.draw(2)


def test_the_rail_is_the_legacy_panel_table():
    """The Qt shell's steps and side tools, in its order; Setup's role is the burst hub's 'setup' (was 'channels')."""
    pytest.importorskip("qtpy")
    from chisurf.plugins.burst.alex_suite.gui.native import STEPS
    from chisurf.plugins.burst.alex_suite.gui.tool import ALEX_PANELS

    legacy = [("setup" if p["role"] == "channels" else p["role"]) for p in ALEX_PANELS if not p.get("separator")]
    native = [p["role"] for p in STEPS if not p.get("separator")]
    assert native == legacy
    numbered = [p["name"] for p in STEPS if p["name"][:1].isdigit()]
    assert [int(n.split(".")[0]) for n in numbered] == list(range(1, 8))
    assert numbered[0] == "1. Setup" and numbered[1] == "2. Files"
    optional = {p["role"] for p in STEPS if p.get("optional")}
    assert optional == {"alternation", "titration", "legacy_export"}
    assert "(optional)" in next(p["name"] for p in STEPS if p.get("role") == "alternation")


def test_every_step_opens_and_draws_empty(hub):
    drv = Driver(hub, (1200, 800))
    for panel in hub.tools:
        hub.select(panel["role"])
        drv.draw(2)
        assert hub.errors.get(panel["role"]) is None, (panel["role"], hub.errors.get(panel["role"]))
        assert hub.child is not None
    Driver(hub, (800, 600)).draw(2)


def test_next_alone_takes_the_demo_from_files_to_an_es_histogram(hub, settings):
    drv = Driver(hub, (1200, 800))
    drv.draw(3)
    assert hub.selected == "setup"
    assert "Pick your setup" in hub.status

    press_next(drv)  # 1. Setup -> 2. Files (nothing to run)
    assert hub.selected == "data"
    data = hub.children["data"]
    drv.click(hub._target_rect("demo"))  # the files step's own Load demo data button
    drv.draw(2)
    demo = [Path(p) for p in hub.context.raw_files]
    assert [p.name for p in demo] == ["alex_demo.spc"]

    press_next(drv)  # -> 3. Alternation, which converts on arrival (Next waited for it)
    assert hub.selected == "alternation"
    alternation = hub.children["alternation"].model
    wait_for(drv, lambda: not alternation.running)
    assert alternation.decision == "convert"
    assert alternation.period == 8000, alternation.status_text  # the planted 100 µs alternation
    assert (alternation.donor_text, alternation.acceptor_text) == ("0", "1")
    assert 0 <= alternation.windows["green"][0] < alternation.windows["green"][1] <= 3900
    assert 4000 <= alternation.windows["red"][0] < alternation.windows["red"][1] <= 7900
    assert alternation.phase_hist["donor"].sum() > 0
    ctx = hub.context
    assert ctx.setup_name == "ALEX Suite (auto)"
    assert [p.suffix for p in ctx.raw_files] == [".pto"], "the later steps analyse the converted container"
    assert ctx.channel_settings["windows"] == {"prompt": alternation.windows["green"],
                                               "delayed": alternation.windows["red"]}
    assert data.model.paths() == demo, "the files step keeps the measurement the user chose"

    press_next(drv)  # -> 4. Burst search (holds the container and the ALEX setup)
    assert hub.selected == "selection"
    selection = hub.children["selection"]
    assert [p.name for p in selection.model.files] == ["alex_demo_alex.pto"]
    assert selection.model.setup_name == "ALEX Suite (auto)"
    assert list(selection.model.detectors) == ["green", "red", "yellow"]

    press_next(drv)  # Next runs the search, waits, then opens 5. Background
    assert selection.model.n_bursts > 300, selection.model.status_text
    assert hub.selected == "background"
    assert ctx.burst_folder is not None and ctx.burst_folder.suffix == ".pto"
    background = hub.children["background"]
    assert [Path(p).name for p in background.model.files] == ["alex_demo_alex.pto"]
    wait_for(drv, lambda: bool(background.model.diagnostics))
    assert background.model.diagnostics, "estimated on arrival"

    press_next(drv)  # -> 6. Accurate FRET, its table loaded from the container run
    assert hub.selected == "accurate_fret"
    fret = hub.children["accurate_fret"]
    wait_for(drv, lambda: not fret.controller.running)
    assert "sliding_window" in fret.model.filename
    assert fret.model.column_i_dd.startswith("S prompt green")
    assert fret.model.column_i_aa.startswith("S delayed yellow")

    press_next(drv)  # Next calibrates, then opens 7. E–S histogram
    assert fret.model.result is not None, fret.controller.status
    assert hub.selected == "es"
    es = hub.children["es"]
    wait_for(drv, lambda: es.model.has_data)
    assert es.model.has_data, es.model.error
    drv.draw(3)
    assert "FRET efficiency" in es.model.x.name and "Stoichiometry" in es.model.y.name
    assert es.model.source.size > 300
    assert not hub._neighbour(1) or hub.panel["role"] == "es"

    # the side tools read the same bursts
    hub.select("titration")
    drv.draw(2)
    assert len(hub.children["titration"].model.rows) == 1
    assert hub.children["titration"].model.gamma == pytest.approx(hub._calibration()["gamma"])
    hub.select("legacy_export")
    drv.draw(2)
    export = hub.children["legacy_export"]
    assert len(export.model.bur_files) == 1
    written = export.model.run_export(str(export.model.bur_files[0]), "demo", "TE", dict(export.export_gui.parts))
    assert len(written) == 4 and all(p.is_file() and p.parent == demo[0].parent for p in written)
    hub.select("browser")
    settle(drv)
    assert hub.children["browser"].model.table is not None
    hub.select("bva")
    settle(drv)
    assert hub.errors.get("bva") is None


def test_pie_data_is_left_alone_and_searched_as_before(hub, settings):
    data = settings / "data"
    data.mkdir()
    for name in ("m000.spc", "m001.spc"):
        shutil.copy(PIE / name, data / name)
    from chisurf.plugins.burst.burst_selection.gui.model import save_setup

    save_setup("probe", PROBE)
    drv = Driver(hub, (1200, 800))
    drv.draw(3)
    hub.children["setup"].select_setup("probe")
    drv.draw(2)
    press_next(drv)
    assert drv.drop(data / "m000.spc", data / "m001.spc")
    drv.draw(2)
    press_next(drv)
    assert hub.selected == "alternation"
    alternation = hub.children["alternation"].model
    assert alternation.decision == "pie" and not alternation.converted
    assert "already has a micro-time" in alternation.status_text
    assert [p.name for p in hub.context.raw_files] == ["m000.spc", "m001.spc"]
    assert hub.context.setup_name == "probe"
    press_next(drv)
    press_next(drv)  # runs the search
    assert hub.children["selection"].model.n_bursts == 198
    assert hub.selected == "background"


def test_a_long_status_does_not_cover_back_and_next(hub):
    """A status wider than its room was one hovered item over the buttons: Next stopped taking clicks."""
    drv = Driver(hub, (1200, 800))
    drv.draw(3)
    hub.status = "Bursts for the later steps: " + "/very/long/path" * 30
    drv.draw(2)
    drv.click(hub.item_rects["next"])
    settle(drv)
    assert hub.selected == "data"
    assert hub.status.endswith("…") or len(hub.status) < 120


def test_guide_steps_point_at_real_controls(hub):
    steps = json.loads((GUI / "guide.json").read_text(encoding="utf-8"))["steps"]
    drv = Driver(hub, (1200, 800))
    where = {"demo": "data", "phase_plot": "alternation"}
    for step in steps:
        key = hub.tour._target_key(step.get("target"))
        if not key:
            continue
        hub.select(where.get(key, hub.selected))
        drv.draw(2)
        assert hub._target_rect(key), key
    assert sum(1 for s in steps if s.get("await")) >= 8, "the tour waits for the user at the real buttons"


def test_the_guide_waits_for_the_real_next_button(hub):
    drv = Driver(hub, (1200, 800))
    drv.draw(2)
    hub.tour.start()
    first = next(i for i, s in enumerate(hub.tour.steps) if hub.tour._target_key(s.get("target")) == "next")
    hub.tour.step_idx = first
    hub.tour._step_used = False
    drv.draw(1)
    assert hub.tour.awaiting
    drv.click(hub.item_rects["next"])
    assert not hub.tour.awaiting


def test_alex_controls_have_tooltips(hub):
    sys.modules.pop("test", None)
    from test.gui.emtk_port_parity import emtk_inventory

    for role in ("setup", "data", "alternation", "titration", "legacy_export"):
        hub.select(role)
        inventory = emtk_inventory(hub)
        assert inventory["controls_without_tooltip"] == [], role


def test_settings_round_trip(hub):
    drv = Driver(hub, (1200, 800))
    hub.select("titration")
    drv.draw(2)
    state = hub.export_settings()
    assert state["selected"] == "titration"
    from chisurf.plugins.burst.alex_suite.gui.native import create_app

    again = create_app()
    try:
        again.restore_settings(state)
        assert again.selected == "titration"
    finally:
        again.close()


def test_the_demo_is_deterministic_and_labelled():
    from chisurf.plugins.burst.alex_suite import demo

    t1, c1, k1 = demo.photon_stream()
    t2, c2, _k2 = demo.photon_stream()
    np.testing.assert_array_equal(t1, t2)
    np.testing.assert_array_equal(c1, c2)
    assert set(np.unique(c1)) == {demo.DONOR_CHANNEL, demo.ACCEPTOR_CHANNEL}
    assert np.all(np.diff(t1.astype(np.int64)) >= 0)
    assert set(np.unique(k1)) == set(range(len(demo.SPECIES)))


def test_every_step_of_the_hub_opens_without_qt(settings):
    """Each child app the rail opens is made and drawn in an interpreter that forbids Qt."""
    repo = Path(__file__).resolve().parents[5]
    script = """
import importlib.abc, sys
class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'}:
            raise RuntimeError('Qt imported: ' + fullname)
sys.meta_path.insert(0, BlockQt())
from emtk.testing import RecordingPainter
from chisurf.plugins.burst.alex_suite.gui.native import create_app
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
    env = dict(os.environ)
    done = subprocess.run([sys.executable, "-c", script], cwd=repo, env=env, capture_output=True, text=True)
    assert done.returncode == 0 and "QT-FREE OK" in done.stdout, (done.stdout + done.stderr)[-3000:]


def test_manifest_opens_the_native_hub():
    manifest = json.loads((PLUGIN / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["entrypoints"]["emtk"] == "chisurf.plugins.burst.alex_suite.gui.native:make_app"


def test_the_setup_steps_proceed_button_names_the_alex_rails_next_step(hub):
    """The shared setup step said "Proceed to Data Selection", a step the ALEX rail does not have."""
    drv = Driver(hub, (1200, 800))
    hub.select("setup")
    strings = drv.draw(3).strings
    assert "Proceed to 2. Files" in strings and "Proceed to Data Selection" not in strings
