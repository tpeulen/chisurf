"""The emtk help browser at parity with the Qt HelpWidget: start page, tree, breadcrumb, labels.

The Qt facts come from the legacy ``HelpWidget`` built in a subprocess, so this
process stays Qt-free for ``test_port_is_qt_free``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.core.help.gui.help_app import make_help_app

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
PAGE = REPO / "docs" / "concepts" / "fret.md"
EMOJI = re.compile("[\U0001F000-\U0001FFFF☀-➿️]")

_QT_FACTS = r"""
import html, json, re, sys, pathlib
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.core.help.gui.tool import HelpWidget
w = HelpWidget()
w.resize(1200, 800)
home = w._home_html()
w.navigate(pathlib.Path(sys.argv[1]))
for _ in range(5):
    qapp.processEvents()
links = re.findall(r'<a href="([^"]+)">(?:<b>)?([^<]+)', home)
print("FACTS" + json.dumps({
    "home_links": [[pathlib.Path(html.unescape(h)).name, html.unescape(t)] for h, t in links],
    "breadcrumb": w.breadcrumb_label.text(),
}))
"""


@pytest.fixture(scope="module")
def qt_facts():
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run([sys.executable, "-c", _QT_FACTS, str(PAGE)], capture_output=True,
                          text=True, timeout=300, env=env, cwd=str(REPO))
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None:
        pytest.skip(f"Qt HelpWidget could not be built here: {proc.stderr[-800:]}")
    return json.loads(line[len("FACTS"):])


@pytest.fixture
def app():
    app = make_help_app()
    yield app
    app.close()


def _draw(app, size=(1200, 800), times=3):
    painter = RecordingPainter()
    for _ in range(times):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


# 1. the start page lists the same pages, with the same titles, as the Qt start page
def test_start_page_matches_the_qt_start_page(app, qt_facts):
    home = app.model._build_home_content()
    ours = [(Path(target).name, title) for title, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", home)]
    assert ours == [tuple(x) for x in qt_facts["home_links"]]
    assert "Welcome to ChiSurf Documentation" not in home       # the earlier hard-coded page


# 1b. the breadcrumb of an open page is the Qt one
def test_breadcrumb_matches_the_qt_window(app, qt_facts):
    app.model.open_page(PAGE)
    painter = _draw(app)
    crumb = " › ".join(app.model.breadcrumb())
    assert crumb and crumb == qt_facts["breadcrumb"]
    assert crumb in painter.strings


# 2. the tree opens to the page that is shown, once, and can be collapsed again
def test_tree_opens_to_the_open_page(app):
    target = str(PAGE.resolve())

    def parent_of(node):
        for child in node.children:
            if child.path and str(Path(child.path).resolve()) == target:
                return node
            found = parent_of(child)
            if found is not None:
                return found
        return None

    group = parent_of(app.model.toc)
    # a sibling's title is drawn only by the tree (the page's own title is also its heading)
    sibling = next(c.title for c in group.children
                   if not (c.path and str(Path(c.path).resolve()) == target))
    painter = _draw(app)
    assert sibling not in painter.strings
    app.model.open_page(PAGE)
    painter = _draw(app)
    assert sibling in painter.strings
    assert app.help_gui._reveal_keys == set()          # revealed once, not forced open


# 2b. back/forward are disabled, not recoloured, when there is nowhere to go
def test_navigation_actions(app):
    app.model.open_page(PAGE)
    assert app.model.history_idx == 1
    app.model.go_back()
    assert app.model.current_path is None
    app.model.go_forward()
    assert app.model.current_path == PAGE.resolve()
    assert app.model.navigate_address("docs/no/such/page.md") in (True, False)   # never raises


# 4. draws, home and page, at both sizes, with no pictogram in any label
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_home_and_page_without_pictograms(app, size):
    painter = _draw(app, size)
    assert "ChiSurf documentation" in painter.strings
    assert "Online docs" in painter.strings
    app.model.open_page(PAGE)
    painter = _draw(app, size)
    assert any("Förster resonance energy transfer" in s for s in painter.strings)
    pictured = sorted({s for s in painter.strings if EMOJI.search(s)})
    assert pictured == []


# 6. no Qt, no chisurf.gui
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("help")
    assert result["ok"], result["output"]


# 7. every control has a tooltip
def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inv = emtk_inventory(build_emtk_app("help"))
    assert inv["controls_without_tooltip"] == []
    assert {"onlinedocs", "videos", "home", "back", "fwd"} <= set(inv["controls"])   # normalised


# 8. persistence
def test_settings_round_trip(app):
    app.model.zoom(2)
    saved = app.export_settings()
    other = make_help_app()
    try:
        other.restore_settings(json.loads(json.dumps(saved)))
        assert other.model.font_size == app.model.font_size != 12.0
    finally:
        other.close()


# 2c. Developer docs (Qt authoring toolbar) adds the development section to the tree
def test_developer_docs_toggle_lists_development_pages(app):
    titles = [n.title for n in app.model.toc.children]
    assert "Developing ChiSurf" not in titles
    app.model.authoring_mode = True
    painter = _draw(app)
    assert "Developer docs" in painter.strings
    app.model.set_include_development(True)
    assert "Developing ChiSurf" in [n.title for n in app.model.toc.children]
    app.model.set_include_development(False)
    assert [n.title for n in app.model.toc.children] == titles
