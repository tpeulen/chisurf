"""The native Calculators hub against the Qt hub it replaces; every control operated with simulated pointer and keys.

Hermetic: settings in a temporary folder, no network, no files. The Qt hub is the committed ``CalculatorHub``
(``gui/tool.py``, untouched); it is built offscreen with the same catalogue and compared entry by entry. The
native window is driven only through ``press`` / ``release`` / ``pointer_move`` / ``key`` at the rectangles the
controls were drawn in (the embedded calculator is reached through the hub's coordinate offset, as a user's
pointer reaches it); the assertions read what is visible or what the embedded calculator's model holds.
The coverage list control -> test is in ``okf/plugins/emtk-ports/calculators/REPORT.md``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from emtk import keys
from emtk.testing import RecordingPainter

from chisurf.plugins.calculator.hub.core.registry import CalculatorEntry, default_calculators
from chisurf.plugins.calculator.hub.gui import app as hub_module
from chisurf.plugins.calculator.hub.gui.app import FACTORIES, CalculatorHubApp, make_app

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
SIZE = (1200, 800)
SMALL = (800, 600)
IDS = [entry.id for entry in default_calculators()]

@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))


@pytest.fixture
def app():
    hub = make_app()
    yield hub
    hub.close()


def draw(app, size=SIZE, frames=3):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def click(app, rect, size=SIZE, fx=0.5):
    x, y, w, h = rect
    app.press(x + w * fx, y + h / 2)
    draw(app, size, frames=1)
    app.release()
    draw(app, size, frames=1)


def click_entry(app, entry_id, size=SIZE):
    draw(app, size)
    click(app, app.item_rects["entry:" + entry_id], size)


def child_rect(app, rect):
    """A rectangle in the embedded calculator's own coordinates, in the hub's."""
    ox, oy = app.child_box[:2]
    return (ox + rect[0], oy + rect[1], rect[2], rect[3])


def text_rect(painter, label, last=True):
    hits = [t[:4] for t in painter.texts if t[5] == label]
    assert hits, f"{label!r} is not drawn: {[t[5] for t in painter.texts][:40]}"
    return hits[-1] if last else hits[0]


def type_into_child(app, rect, text, size=SIZE):
    click(app, child_rect(app, rect), size, fx=0.3)
    assert app.io.want_capture_keyboard or app.child.io.want_capture_keyboard
    app.key(0x41, "a", 0x04000000)
    draw(app, size, frames=1)
    for ch in text:
        app.key(ord(ch), ch)
        draw(app, size, frames=1)
    app.key(keys.KEY_RETURN, "\r")
    draw(app, size, frames=2)


# -- the Qt hub, built from the committed source ------------------------------------------------------- #


@pytest.fixture
def qt_hub():
    QtWidgets = pytest.importorskip("qtpy.QtWidgets")
    from chisurf.plugins.calculator.hub.gui.tool import CalculatorHub

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    hub = CalculatorHub()
    hub._qapp = qapp
    yield hub
    hub.close()


# ── 1. the catalogue and the header equal the Qt hub ---------------------------------------------------- #


def test_the_list_header_and_selection_equal_the_qt_hub_entry_by_entry(app, qt_hub):
    from qtpy import QtCore

    assert qt_hub._list.count() == len(app.entries) == 9
    for row, entry in enumerate(app.entries):
        item = qt_hub._list.item(row)
        assert item.data(QtCore.Qt.UserRole) == entry.id
        assert item.text().strip().endswith(entry.label)  # the Qt row is "<emoji>  label"
        assert item.toolTip() == entry.description
        qt_hub._list.setCurrentRow(row)
        qt_hub._qapp.processEvents()
        assert qt_hub._title.text().strip().endswith(entry.label)
        assert qt_hub._subtitle.text() == entry.description
        click_entry(app, entry.id)
        assert app.selected == entry.id
        strings = draw(app).strings
        assert entry.label in strings and entry.description in " ".join(strings)
    # the first entry is selected at start in both
    fresh = make_app()
    qt_first = type(qt_hub)()
    try:
        assert fresh.selected == default_calculators()[0].id
        assert qt_first._list.currentRow() == 0
    finally:
        qt_first.close()
        fresh.close()


def test_a_calculator_that_cannot_be_built_says_why_like_the_qt_hub(qt_hub, monkeypatch):
    from chisurf.plugins.calculator.hub.gui.tool import CalculatorHub

    entries = [CalculatorEntry(id="broken", label="Broken one", description="Cannot be built.", widget="chisurf.nowhere:Nothing"),
               *default_calculators()[:2]]
    monkeypatch.setitem(FACTORIES, "broken", "chisurf.nowhere:Nothing")
    qt = CalculatorHub(entries=entries)
    page = qt._stack.currentWidget()
    assert page.text() == "Could not load 'Broken one':\nNo module named 'chisurf.nowhere'"
    qt.close()
    hub = CalculatorHubApp(entries=entries)
    strings = " ".join(draw(hub).strings)
    assert "Could not load 'Broken one': No module named 'chisurf.nowhere'" in strings
    assert hub.child is None and hub.error
    hub.close()


def test_no_entries_shows_the_prompt_and_no_child(qt_hub):
    from chisurf.plugins.calculator.hub.gui.tool import CalculatorHub

    qt = CalculatorHub(entries=[])
    assert qt._subtitle.text() == "Select a calculator on the left to get started." and qt._stack.currentWidget().text() == "No calculator selected."
    qt.close()
    hub = CalculatorHubApp(entries=[])
    assert hub.selected is None and "Select a calculator on the left to get started." in draw(hub).strings
    hub.close()


def test_every_registry_entry_has_a_native_factory_and_the_factories_import():
    import importlib

    assert set(FACTORIES) == set(IDS)  # no calculator without a native app, no stale factory
    for spec in FACTORIES.values():
        module, attr = spec.split(":")
        assert callable(getattr(importlib.import_module(module), attr))


def test_children_are_built_lazily_kept_and_every_one_builds_and_draws_at_both_sizes(app):
    assert not app.children
    draw(app)
    assert set(app.children) == {"fret_calculator"}  # only the selected one, on the first draw
    for size in (SIZE, SMALL):
        for id in IDS:
            click_entry(app, id, size)
            assert app.selected == id and app.child is not None and not app.error, (id, app.error)
            painter = draw(app, size)
            assert any(entry.label in painter.strings for entry in app.entries if entry.id == id)
            assert len(painter.strings) > 20, id  # the calculator itself drew, not just the hub
    assert set(app.children) == set(IDS)


@pytest.mark.parametrize("size", [SIZE, SMALL, (520, 480)])
def test_a_long_description_or_error_is_never_clipped_by_the_embedded_calculator(app, size, monkeypatch):
    click_entry(app, "rics_precision", size)
    painter = draw(app, size)
    left = min(240.0, size[0] * 0.25)
    header = [t for t in painter.texts if t[0] >= left - 1 and t[1] < app.child_box[1]]
    assert header and max(t[1] + t[3] for t in header) <= app.child_box[1], (size, app.child_box)
    assert " ".join(t[5] for t in header).count("before acquiring.") == 1  # the whole text is drawn
    monkeypatch.setitem(FACTORIES, "fret_line", "chisurf.nowhere:Nothing")
    click_entry(app, "fret_line", size)
    painter = draw(app, size)
    assert "Could not load" in " ".join(painter.strings)
    assert app.child_box[1] >= 70.0 and app.child is None


def test_no_emoji_in_the_list_and_the_header(app):
    strings = draw(app).strings
    for entry in app.entries:
        assert entry.label in strings  # the plain label; the registry icon is not drawn
    assert not any(ord(ch) > 0x2190 and ch not in "κ²χ" for s in strings[:20] for ch in s), strings[:20]


# ── 2. clicks: the list, the embedded calculator, keys ------------------------------------------------- #


@pytest.mark.parametrize("entry_id", IDS)
def test_clicking_each_list_entry_selects_it_and_shows_its_calculator(app, entry_id):
    other = "kappa2_dist" if entry_id != "kappa2_dist" else "fret_calculator"
    click_entry(app, other)
    assert app.selected == other
    click_entry(app, entry_id)
    assert app.selected == entry_id and app.child is app.children[entry_id]
    entry = next(e for e in app.entries if e.id == entry_id)
    assert entry.description in " ".join(draw(app).strings)


def test_the_embedded_calculator_gets_the_pointer_and_the_keys_and_keeps_its_state_when_another_is_shown(app):
    draw(app)
    fret = app.child
    rect = fret.active.form.rects["R"]
    type_into_child(app, rect, "58")
    assert fret.model.hetero.R == 58.0  # typed through the hub's pointer offset and key forwarding
    click_entry(app, "kappa2_dist")
    kappa = app.child
    assert kappa is not fret
    click_entry(app, "fret_calculator")
    assert app.child is fret and fret.model.hetero.R == 58.0  # the calculator kept its input


def test_a_click_in_the_list_area_does_not_reach_the_calculator_and_one_outside_the_header_does(app):
    draw(app)
    fret = app.child
    before = fret.export_settings()
    click(app, app.item_rects["entry:fret_calculator"])  # the list, left of the child box
    assert fret.export_settings() == before
    click(app, child_rect(app, fret.item_rects["tab_homofret"]) if "tab_homofret" in fret.item_rects else child_rect(app, fret.item_rects["help"]))
    assert fret.active_tab == 1 or fret.help_window.open  # a click in the child box reached the calculator


def test_up_and_down_move_the_selection_unless_a_field_is_being_edited(app):
    draw(app)
    assert app.selected == "fret_calculator"
    app.key(keys.KEY_DOWN, "")
    draw(app, frames=1)
    assert app.selected == "fret_line"
    app.key(keys.KEY_UP, "")
    app.key(keys.KEY_UP, "")  # the first entry stays the first
    draw(app, frames=1)
    assert app.selected == "fret_calculator"
    for _ in range(12):
        app.key(keys.KEY_DOWN, "")
        draw(app, frames=1)
    assert app.selected == IDS[-1]  # and the last one the last
    click_entry(app, "fret_calculator")
    click(app, child_rect(app, app.child.active.form.rects["R"]), fx=0.3)  # a text field takes the keyboard
    app.key(keys.KEY_DOWN, "")
    draw(app, frames=2)
    assert app.selected == "fret_calculator"


def test_the_wheel_and_the_hover_are_forwarded_to_the_calculator_inside_its_box_only(app):
    draw(app)
    seen = {"wheel": [], "move": []}
    app.child.wheel = lambda x, y, steps, modifiers=0: seen["wheel"].append((x, y, steps))
    app.child.pointer_move = lambda x, y, buttons=0, modifiers=0: seen["move"].append((x, y))
    ox, oy = app.child_box[:2]
    app.wheel(ox + 100, oy + 50, 2.0)
    app.wheel(10, 300, 2.0)  # over the list: the hub's, not the calculator's
    app.pointer_move(ox + 30, oy + 40)
    assert seen["wheel"] == [(100.0, 50.0, 2.0)] and seen["move"] == [(30.0, 40.0)]


def test_the_hub_is_asked_for_frames_by_the_embedded_calculator(app):
    draw(app)
    app.wants_frame = False
    app.child.request_frame()  # what a worker thread of the calculator does when its result is in
    assert app.wants_frame is True and app.animating()


# ── 3. Guide, Help, drop, persistence ---------------------------------------------------------------------- #


def test_guide_button_starts_the_tour_whose_awaited_step_waits_for_a_list_click(app):
    draw(app)
    click(app, app.item_rects["guide"])
    assert app.tour.active
    app.tour.next()  # the Next button's callback (its click is test_the_tour_next_button_can_be_clicked)
    draw(app)
    assert app.tour.awaiting
    click_entry(app, "phasor")
    assert not app.tour.awaiting and app.selected == "phasor"
    click(app, text_rect(draw(app), "Close Tour"))
    assert not app.tour.active


def test_the_tour_next_button_can_be_clicked(app):
    draw(app)
    click(app, app.item_rects["guide"])
    click(app, text_rect(draw(app), "Next ►"))
    assert app.tour.step_idx == 1


def test_the_tour_targets_are_drawn_and_the_tour_is_walked_to_the_end_by_the_user(app):
    from chisurf.emtk.help_guide import EmTkGuidedTour

    draw(app)
    steps = json.loads((GUI / "guide.json").read_text(encoding="utf-8"))["steps"]
    for step in steps:
        assert app.item_rects.get(EmTkGuidedTour._target_key(step["target"])), step["title"]
    assert [s["title"] for s in steps if s.get("await")] == ["Pick one"]
    click(app, app.item_rects["guide"])
    for _ in steps:
        draw(app)
        if app.tour.awaiting:
            click_entry(app, "psf_calculator")
        app.tour.next()
    assert not app.tour.active and app.selected == "psf_calculator"


def test_help_button_opens_the_help_window_whose_buttons_work(app):
    draw(app)
    click(app, app.item_rects["help"])
    assert app.help_window.open
    painter = draw(app)
    assert {"Start Guided Tour", "Close", "Close Help"} <= set(painter.strings)
    click(app, text_rect(painter, "Start Guided Tour"))
    assert not app.help_window.open and app.tour.active
    app.tour.stop()
    for closer, last in (("Close Help", True), ("Close", False)):
        click(app, app.item_rects["help"])
        click(app, text_rect(draw(app), closer, last=last))
        assert not app.help_window.open, closer
    click(app, app.item_rects["help"])
    app.key(keys.KEY_ESCAPE, "")
    draw(app)
    assert not app.help_window.open


def test_help_text_is_plain_with_live_links():
    text = (GUI / "help.md").read_text(encoding="utf-8")
    assert "**" not in text and "`" not in text
    links = re.findall(r"\]\((docs/[^)#]+)\)", text)
    assert links and all((REPO / link).is_file() for link in links)


def test_a_file_dropped_on_the_host_goes_to_the_embedded_calculator(app):
    QtWidgets = pytest.importorskip("qtpy.QtWidgets")
    from emtk.qt_host import ControlHost
    from qtpy import QtCore, QtGui

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    draw(app)  # the selected calculator is built by the first frame
    host = ControlHost(app)
    host.resize(*SIZE)
    host.show()
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile("/tmp/run.ptu")])

    def drop():
        enter = QtGui.QDragEnterEvent(QtCore.QPoint(300, 300), QtCore.Qt.CopyAction, mime, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
        host.dragEnterEvent(enter)
        event = QtGui.QDropEvent(QtCore.QPointF(300, 300), QtCore.Qt.CopyAction, mime, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
        host.dropEvent(event)
        qapp.processEvents()
        return enter.isAccepted(), event.isAccepted()

    assert drop() == (True, True)
    assert app.child.model.hetero.status == "The FRET Calculator takes no dropped files."  # the FRET calculator's own answer
    assert app.files_dropped(["/tmp/run.ptu"]) is True and app.on_paths_dropped(["/tmp/run.ptu"]) is True  # taken by the child
    assert "takes no dropped files" in " ".join(draw(app).strings)
    click_entry(app, "kappa2_dist")
    drop()  # the host accepts a drop on any control that has a drop hook ...
    assert app.files_dropped(["/tmp/run.ptu"]) is False  # ... the hub answers False: the kappa2 calculator takes none
    assert app.child.export_settings()["model_type"] == "cone"  # and nothing changed
    host.close()


def test_settings_round_trip_restores_the_selection_and_the_calculators_inputs(app):
    draw(app)
    type_into_child(app, app.child.active.form.rects["R"], "58")
    click_entry(app, "kappa2_dist")
    saved = json.loads(json.dumps(app.export_settings()))
    assert saved["selected"] == "kappa2_dist" and saved["children"]["fret_calculator"]["hetero"]["R"] == 58.0
    assert set(saved["children"]) == {"fret_calculator", "kappa2_dist"}  # only what was opened
    other = make_app()
    other.restore_settings(saved)
    assert other.selected == "kappa2_dist" and other.export_settings()["children"]["kappa2_dist"] == saved["children"]["kappa2_dist"]
    other.select("fret_calculator")  # built later: the saved inputs are applied at that moment
    assert other.children["fret_calculator"].model.hetero.R == 58.0
    other.restore_settings({"selected": "no_such", "children": {"bogus": {}, "fret_calculator": "x", "kappa2_dist": ["x"]}})
    other.restore_settings("garbage")
    assert other.selected == "fret_calculator" and draw(other).strings
    other.close()


def test_close_closes_every_built_calculator(app):
    for id in ("fret_calculator", "kappa2_dist", "psf_calculator"):
        click_entry(app, id)
    closed = []
    for id, child in app.children.items():
        original = getattr(child, "close", None)
        child.close = lambda original=original, id=id: (closed.append(id), original() if original else None)[1]
    app.close()
    assert sorted(closed) == ["fret_calculator", "kappa2_dist", "psf_calculator"] and not app.children


# ── 4. spec, tooltips, no Qt ---------------------------------------------------------------------------------- #


def test_every_control_has_a_tooltip_and_the_port_is_qt_free():
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory, qt_free

    inventory = emtk_inventory(build_emtk_app("calculators"))
    assert inventory["controls_without_tooltip"] == []
    labels = {row["label"] for row in inventory["interactive"]}
    assert {entry.label for entry in default_calculators()} <= labels and {"Guide", "Help"} <= labels
    result = qt_free("calculators")
    assert result["ok"], result["output"]


def test_the_manifest_opens_the_native_app_and_the_qt_hub_is_untouched():
    manifest = json.loads((HERE.parent / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["entrypoints"]["emtk"] == "chisurf.plugins.calculator.hub.gui.app:make_app"
    assert manifest["entrypoints"]["gui"].endswith("CalculatorHub")
    assert isinstance(make_app(), CalculatorHubApp) and hub_module.CalculatorHubApp is CalculatorHubApp
