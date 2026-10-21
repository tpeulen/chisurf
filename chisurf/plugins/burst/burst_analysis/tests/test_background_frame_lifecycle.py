"""The Background step's results reach the plot through one frame of a lazy host.

The regression: a Background estimate handed its files by the workflow used to refuse silently
(no detectors — the reason was dropped), and a host that draws no frames while the worker runs
published nothing, so the step opened permanently blank. Now the refusal is surfaced, and the
frame the host owes the step (its own wake rule asks for one) publishes and draws.

Driver-based and ``__main__``-runnable on purpose: during an e2e lane that owns pytest it runs
as ``python test_background_frame_lifecycle.py``.

Phases:
  1. pump (as a user's clicks do) through setup -> data -> selection -> background until the
     embedded estimate is running;
  2. LAZY HOST: draw no frames until the worker future is done (expect the publish-blocked
     state: the worker finished, nothing is on the model yet);
  3. one frame: poll() publishes and the same frame draws the plots;
  4. host-rule only: re-run via the button and let every frame come from the native host's own
     wake rule (``animating()`` / ``next_frame_in()``), exactly as ``emtk.native`` schedules.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
#: The hand-off of the Qt tool's SPC-132 run: its ``channel_settings`` are the setup the walk uses,
#: and its ``m000.spc`` is the measurement they were read from (the search writes the container
#: beside the copy in the test's temporary folder).
HANDOFF = (
    HERE.parent.parent
    / "burst_selection"
    / "tests"
    / "data"
    / "bh_spc132_sm_dna"
    / "burst_analysis_handoff"
    / "burst_analysis_handoff.json"
)
MEASUREMENT = HANDOFF.parent.parent / "m000.spc"

if __name__ == "__main__":
    # A scratch settings store before any chisurf import; pytest runs isolate theirs per test.
    _scratch = Path(tempfile.mkdtemp(prefix="bg-frame-lifecycle-"))
    os.environ.setdefault("CHISURF_SETTINGS_DIR", str(_scratch / "settings"))
    os.environ.setdefault("MMFDB_SETTINGS_DIR", str(_scratch / "mmfdb"))
    os.environ.setdefault("MMFDB_DATABASE_PATH", str(_scratch / "db.sqlite"))
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _isolate_settings(tmp: Path) -> None:
    """A private settings/database store, so the test never touches the user's setups."""
    (tmp / "settings").mkdir(parents=True, exist_ok=True)
    os.environ["CHISURF_SETTINGS_DIR"] = str(tmp / "settings")
    os.environ["MMFDB_SETTINGS_DIR"] = str(tmp / "mmfdb")
    os.environ["MMFDB_DATABASE_PATH"] = str(tmp / "db.sqlite")
    os.environ["QT_QPA_PLATFORM"] = "offscreen"


def test_background_publishes_through_a_lazy_host(tmp_path=None):
    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp(prefix="bg-frame-lifecycle-"))
    _isolate_settings(tmp_path)
    sys.path.insert(0, str(REPO))

    from emtk import implot
    from emtk.app import next_frame_in as host_next_frame_in
    from emtk.testing import Driver

    from chisurf.plugins.burst.burst_selection.gui.model import save_setup
    from chisurf.plugins.burst.burst_analysis.gui.native import BurstAnalysisHubApp

    setup = dict(json.loads(HANDOFF.read_text())["channel_settings"])
    setup["setup_name"] = "BS"
    save_setup("BS", setup)
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    data_file = data_dir / MEASUREMENT.name
    shutil.copy2(MEASUREMENT, data_file)
    app = BurstAnalysisHubApp()
    try:
        driver = Driver(app, (1400, 900))

        # ── Phase 1: pump to the estimate running ────────────────────────────
        setup_child = app.ensure_child("setup")
        setup_child.select_setup("BS")
        driver.draw(3)
        app.select("data")
        driver.draw(3)
        app.children["data"].model.add_paths([str(data_file)])
        driver.draw(3)
        app.select("selection")
        driver.draw(5)
        sel = app.children["selection"]
        for attempt in range(3):
            app.next_step()
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                driver.draw(3)
                if getattr(sel.model, "running", False):
                    time.sleep(0.4)
                    continue
                if app.context.burst_folder is not None:
                    break
                time.sleep(0.4)
            if app.context.burst_folder is not None:
                break
        assert app.context.burst_folder is not None, (
            f"the burst search never finished (status: {app.status})"
        )
        app.select("background")
        child = app.children.get("background")
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            driver.draw(2)
            child = app.children.get("background")
            if child is not None and getattr(child.controller, "running", False):
                driver.draw(1)  # the priming frame: the running child books its +0.1 s wake
                break
            time.sleep(0.1)
        assert child is not None and child.controller.running, (
            f"the estimate never started (status: {app.status}; "
            f"model.status: {getattr(child.model, 'status', '') if child else ''})"
        )
        assert app._busy() is True, "the hub must see the running estimate as busy"

        # ── Phase 2: the lazy host — no frames until the worker is done ──────
        future = child.controller._future
        t0 = time.monotonic()
        while not future.done() and time.monotonic() - t0 < 300:
            time.sleep(0.05)
        assert future.done(), "the worker never finished"
        assert not list(child.model.diagnostics) and child.controller.running, (
            "a finished worker must wait for a frame to publish (the lazy-host state)"
        )

        # ── Phase 3: one frame publishes and draws ───────────────────────────
        begin_calls = []
        real_begin = implot.begin_plot

        def recording_begin(*a, **k):
            begin_calls.append(a[0] if a else "")
            return real_begin(*a, **k)

        implot.begin_plot = recording_begin
        try:
            driver.draw(1)
        finally:
            implot.begin_plot = real_begin
        assert list(child.model.diagnostics) and child.model.iht_series(), (
            "one frame after the worker finished must publish the results"
        )
        assert any("Inter-photon" in str(c) for c in begin_calls), (
            f"the published frame drew no inter-photon plot: {begin_calls}"
        )

        # ── Phase 4: host-rule only — frames exactly when the wake rule says ──
        child.model.diagnostics.clear()
        child.model.backgrounds.clear()
        driver.draw(2)
        driver.click("Estimate Background")
        assert child.controller.running, "the restarted estimate never started"
        frames, idle_polls = 0, 0
        t0 = time.monotonic()
        while time.monotonic() < t0 + 300:
            if driver.surface.animating():
                driver.frame(1)
                frames += 1
                continue
            delay = host_next_frame_in(driver.surface)
            if delay is None:
                idle_polls += 1
                if idle_polls > 50 and not child.controller.running:
                    break
                time.sleep(0.02)
                continue
            time.sleep(min(float(delay), 0.25))
            driver.frame(1)  # the wake: exactly one frame
            frames += 1
            if not child.controller.running and list(child.model.diagnostics):
                break
        assert list(child.model.diagnostics) and child.model.iht_series(), (
            f"the host's own wake rule did not keep the estimate alive and publishing "
            f"({frames} frames)"
        )
        assert not child.controller.running, "the estimate never finished"
        print(
            f"frame lifecycle OK: lazy host -> one frame publishes and draws; "
            f"host-rule-only re-run published after {frames} frames"
        )
    finally:
        app.close()


if __name__ == "__main__":
    test_background_publishes_through_a_lazy_host()
    print("FRAME_LIFECYCLE_TEST_DONE")
