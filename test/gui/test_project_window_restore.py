"""A saved session reopens 1:1 in a fresh process.

Stage A builds a real Main window with two fits, arranges it the way a user would
(main and window geometry, a non-default plot tab, a toggled plot option, a mouse
zoom, the active window on top) and saves a ``.cs.pto``. Stage B is a *new*
interpreter that only opens the file. Both measure the same widget-level facts --
not the stored records -- and they must be equal: geometry, docks, view mode,
active window and stacking, per-window tab, code view, plot dock layout, every
plot's and controller's state, and every panel's visible range.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("restore_probe") / "session_probe.py"


def _run(stage: str, out: Path, variant: str = "") -> None:
    env = os.environ.copy()
    env["CHISURF_RESTORE_VARIANT"] = variant
    env.update(
        QT_QPA_PLATFORM="offscreen", MPLBACKEND="Agg", CHISURF_SETTINGS_DIR=str(out / "settings")
    )
    result = subprocess.run(
        [sys.executable, str(PROBE), str(out), stage],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]


@pytest.mark.parametrize("variant", ["", "maximized", "tabbed"])
def test_a_saved_session_reopens_exactly_as_it_was(tmp_path, variant):
    """Plain, one window maximized, and the window area in tabbed mode."""
    _run("A", tmp_path, variant)
    _run("B", tmp_path, variant)
    before = json.loads((tmp_path / "A.json").read_text())
    after = json.loads((tmp_path / "B.json").read_text())
    zoomed = [
        plot["plot"]["views"]
        for window in before["windows"].values()
        for plot in window["plots"].values()
        if isinstance(plot.get("plot"), dict) and "views" in plot["plot"]
    ]
    assert zoomed, "stage A must leave a zoomed panel for the restore to reproduce"
    assert after["active_fit"] == before["active_fit"]
    assert after["stacking"] == before["stacking"]
    for name, window in before["windows"].items():
        restored = after["windows"][name]
        for key in (
            "geometry",
            "maximized",
            "minimized",
            "current_plot_index",
            "code_shown",
            "dock_layout",
        ):
            assert restored[key] == window[key], (name, key)
        for index, plot in window["plots"].items():
            assert restored["plots"][index] == plot, (name, index)
    for key in ("main_geometry", "main_maximized", "docks", "mdi_view_mode"):
        assert after[key] == before[key], key
