"""Every fit-window page of every catalogued model is emtk, and so are its settings.

A fit window is one emtk surface and its pages are not widgets; the main
window's *Plot settings* dock is one emtk surface showing the current page's
settings. This sweep opens the real science of all 42 catalogued models in a
real Main, visits every page, and fails on a page object that is a Qt widget, a
page that declares nothing to draw, or settings that raise while drawn.

Slow (a producer and a GUI child per model): runs with ``--run-slow``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = json.loads((ROOT / "test/project/fixtures/scientific_model_catalogue.json").read_text())

def _run(command, environment, timeout):
    return subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True,
                          timeout=timeout)


@pytest.mark.slow
@pytest.mark.parametrize("case", range(len(CATALOGUE)), ids=[e["configured_path"] for e in CATALOGUE])
def test_every_page_draws_in_emtk(case, tmp_path):
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", MPLBACKEND="Agg", IMP_BFF_GPU="off",
                       CHISURF_SETTINGS_DIR=str(tmp_path / "settings"),
                       MMFDB_SETTINGS_DIR=str(tmp_path / "mmfdb"))
    produced = _run([sys.executable, "-m", "test.project.scientific_catalogue_probe", "--case",
                     str(case), str(tmp_path)], environment, 120)
    assert produced.returncode == 0, produced.stdout + produced.stderr
    environment.update(CHISURF_SETTINGS_DIR=str(tmp_path / "gui-settings"),
                       MMFDB_SETTINGS_DIR=str(tmp_path / "gui-mmfdb"))
    probed = _run([sys.executable, "-m", "test.gui.fit_window_page_probe", str(tmp_path),
                   str(tmp_path), str(case)], environment, 180)
    report = json.loads((tmp_path / f"{case}.json").read_text())
    assert not report["errors"], report["errors"][0] + probed.stderr[-2000:]
    assert report["pages"], "no fit-window pages were opened"
    for page in report["pages"]:
        assert "error" not in page, page["error"]
        assert not page["is_widget"], f"{page['title']} ({page['plot_class']}) is a Qt widget"
        assert page["settings_error"] is None, f"{page['title']}: {page['settings_error']}"
        assert page["missing"] == [], f"{page['title']} ({page['plot_class']}): {page['missing']}"
