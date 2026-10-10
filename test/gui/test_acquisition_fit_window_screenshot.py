"""Opening the Acquisition plugin in Main yields a fit window with four populated docks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_acquisition_plugin_opens_a_fit_window_with_four_populated_docks(tmp_path):
    """Start Main, load the plugin, wait for the demo stream; every live dock has curves."""
    out = tmp_path / "out"
    out.mkdir()
    environment = dict(
        os.environ, QT_QPA_PLATFORM="offscreen", MPLBACKEND="Agg", IMP_BFF_GPU="off",
        CHISURF_SETTINGS_DIR=str(tmp_path / "settings"), MMFDB_SETTINGS_DIR=str(tmp_path / "mmfdb"),
    )
    run = subprocess.run(
        [sys.executable, "-m", "test.gui.acquisition_fit_window_probe", str(out)],
        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=240,
    )
    report = json.loads((out / "report.json").read_text())
    assert not report["errors"], report["errors"][0] + run.stderr[-2000:]
    assert report["fit_window"], "the plugin did not open a fit window"
    assert report["title"].startswith("Acquisition")
    assert report["docks"][:4] == ["Decay", "Correlation", "MCS", "Macro time"]
    assert report["photons"] > 10_000
    for title in ("Decay", "Correlation", "MCS", "Macro time"):
        series = report["pages"][title]["series"]
        assert series and all(points > 1 for _label, points in series), (title, report["pages"])
    assert (out / "acquisition.png").stat().st_size > 5_000
    keep = os.environ.get("ACQ_SCREENSHOT_DIR")
    if keep:
        for png in out.glob("*.png"):
            Path(keep, png.name).write_bytes(png.read_bytes())
