"""The QuEst card keeps every control reachable and readable in a narrow window, in every language.

Found by the real-use matrix: at 800 x 600 the *Project JSON* tab ran off the right edge of the results dock,
the Simulation fields began past the edge of the inputs dock and drew empty, and the *Coarse-grained structure*
caption was cut off (the German catalogue's *Costes-Schwellenwerte* at the same width).
"""

from __future__ import annotations

import pytest
from emtk.testing_realistic import RealisticDriver

from chisurf.emtk.i18n import set_locale
from chisurf.emtk.plugins import load_plugin

SIZES = [(1100, 720), (800, 600)]


@pytest.fixture
def quest():
    app = load_plugin("quenching_estimator", persist=False)
    yield app
    set_locale("en")
    app.close()


@pytest.mark.parametrize("lang", ["en", "de", "fr"])
@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_tabs_fields_and_captions_stay_inside_the_window(quest, size, lang):
    set_locale(lang)
    driver = RealisticDriver(quest, (1100, 720))
    driver.settle()
    if size != (1100, 720):
        driver.resize(size)
    driver.frame(4)
    width, height = size
    rects = quest.item_rects
    for tab in ("Plots & Dynamics", "3D Structure", "Quenching Chemistry", "Project JSON"):
        x, y, w, h = rects[f"tab_{tab}"]
        assert x >= 0 and x + w <= width and y + h <= height, (tab, rects[f"tab_{tab}"], size)
    for name in ("attachment_residue", "linker_length", "simulation_time"):
        if name in rects:
            x, y, w, h = rects[name]
            assert w >= 30.0 and x + w <= width, (name, rects[name], size)
    # nothing is drawn past the right edge: a caption cut by the window leaves its text starting inside it
    # and ending outside
    for x, _y, w, *_rest in driver.painter.texts:
        assert x + w <= width + 1.0 or x >= width, "a text runs past the window edge"


def test_the_project_json_tab_can_be_pressed_at_800x600(quest):
    driver = RealisticDriver(quest, (800, 600))
    driver.settle()
    driver.frame(3)
    driver.click("tab_Project JSON")
    driver.frame(3)
    assert quest.tab == "Project JSON"


def test_loading_a_file_that_is_not_a_project_keeps_the_fields_filled(quest, tmp_path):
    """The sweep's stub project is ``{}``: it used to replace the state and blank every number field."""
    model = quest.session.model
    length = model.av_linker_length
    assert length is not None
    stub = tmp_path / "stub.json"
    stub.write_text("{}\n")
    assert quest.session.load_project(str(stub)) is False
    assert model.av_linker_length == length
    assert quest.session.status_error and "missing" in quest.session.message.lower()
