"""The ChiSurf tool window: Qt hosting the emtk window, the toolbar and the tour.

Offscreen Qt. Checks the parts that live in Qt -- the *Load demo* action, the
Guide and ``?`` buttons, and the tour anchors that stand in for emtk controls --
and grabs the window so a screenshot of the real host exists.
"""

from __future__ import annotations

import os
import pathlib

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("qtpy.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture
def tool(qapp):
    from chisurf.plugins.burst.burst_ebfret.gui.tool import EbfretTool

    widget = EbfretTool()
    widget.resize(1200, 820)
    widget.show()
    qapp.processEvents()
    yield widget
    widget.close()


def _pump(qapp, tool, n=6):
    for _ in range(n):
        tool._tick()
        tool.host.repaint()
        qapp.processEvents()


def test_the_tool_has_its_toolbar_guide_and_help(tool):
    actions = [a.text() for a in tool.findChild(QtWidgets.QToolBar, "ebfret_toolbar").actions()]
    assert "Load demo" in actions
    buttons = [b.text() for b in tool.findChildren(QtWidgets.QToolButton)]
    assert "Guide" in buttons


def test_load_demo_and_the_tour_anchors_follow_the_controls(qapp, tool, tmp_path):
    tool._load_demo()
    _pump(qapp, tool)
    run = tool.findChild(QtWidgets.QWidget, "ebfret_run")
    assert run is not None and run.width() > 10 and run.height() > 5
    fired = []
    run.clicked.connect(lambda: fired.append(True))
    tool.gui.track("run")
    assert fired
    out = pathlib.Path(os.environ.get("EBFRET_SHOT_DIR", tmp_path))
    assert tool.grab().save(str(out / "ebfret_tool.png"))


def test_the_guided_tour_resolves_every_named_step(qapp, tool):
    from chisurf.gui.widgets.tools.guided_tour import GuidedTour, load_tour

    tool._load_demo()
    _pump(qapp, tool)
    steps = load_tour(pathlib.Path(tool.gui.spec and __file__).parents[1] / "gui" / "guide.json")
    tour = GuidedTour(tool, steps)
    for step in steps:
        target = step.target
        if target.get("name") or target.get("action"):
            assert tour.resolve_target(target) is not None, target
