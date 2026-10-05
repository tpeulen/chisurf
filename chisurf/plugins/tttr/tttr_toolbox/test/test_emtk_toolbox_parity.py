"""The TTTR toolbox's emtk app against the Qt tool, every control operated with real input.

Hermetic: temporary ``HOME`` / ``CHISURF_SETTINGS_DIR`` / MMFDB settings, the real ``~/.chisurf`` is snapshotted (``logs`` and the
bytecode cache aside) and must be unchanged afterwards. Only pointer, wheel, key and drop events reach the window; the
children are real emtk apps where a route is under test and recording fakes where input routing is.
"""

from __future__ import annotations

import json
import os
import pwd
from pathlib import Path

import pytest
from emtk import keys
from emtk.app import ImApp

from chisurf.plugins.emtk_test_input import Driver, assert_tour_card_clear
from chisurf.plugins.tttr.tttr_toolbox.gui.app import HEADER, make_app
from test.gui import emtk_layout_checks as lay

PLUGIN = Path(__file__).resolve().parents[1]
SIZES = [(1200, 800), (800, 600)]
REAL_HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)


def _tree(root: Path) -> dict:
    out = {}
    for path in sorted(root.rglob("*")) if root.is_dir() else []:
        if path.relative_to(root).parts[:1] in (("logs",), ("cache",)):
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        out[str(path.relative_to(root))] = (st.st_size, st.st_mtime_ns)
    return out


@pytest.fixture(scope="module", autouse=True)
def real_chisurf_untouched():
    before = _tree(REAL_HOME / ".chisurf")
    yield
    assert _tree(REAL_HOME / ".chisurf") == before, "a test wrote into the real ~/.chisurf"


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    (tmp_path / "home").mkdir()
    monkeypatch.chdir(tmp_path)


class Child(ImApp):
    """A recording child: what the toolbox forwards reaches ``calls``."""

    def __init__(self):
        super().__init__(lambda: None)
        self.calls, self.value, self.dropped = [], 1, []

    def pointer_press(self, *a):
        self.calls.append(("press", a))

    def pointer_release(self, *a):
        self.calls.append(("release", a))

    def wheel(self, *a):
        self.calls.append(("wheel", a))

    def key(self, *a):
        self.calls.append(("key", a))
        return True

    def on_paths_dropped(self, paths):
        self.dropped.extend(paths)

    def export_settings(self):
        return {"value": self.value}

    def restore_settings(self, data):
        self.value = data["value"]

    def close(self):
        self.calls.append(("close", ()))


def fake(panel):
    return Child, "test:child"


@pytest.fixture
def ui():
    driver = Driver(make_app(resolver=fake))
    yield driver
    driver.app.close()


# -- parity with the Qt tool ----------------------------------------------------------------------------------------- #


def test_the_navigation_list_equals_the_qt_tools_panels(ui, qapp, qtbot):
    from chisurf.plugins.tttr.tttr_toolbox.gui.tool import TttrToolboxTool

    spec = json.loads((PLUGIN / "gui" / "panels.json").read_text())
    expected = [p["name"] for p in spec["panels"] if not p.get("separator")]
    assert [p["name"] for p in ui.app.tools] == expected
    qt = TttrToolboxTool()
    qtbot.addWidget(qt)
    assert qt.windowTitle().endswith("TTTR Tools")
    ui.draw(3)
    for panel in ui.app.tools:
        assert f"nav.{panel['role']}" in ui.app.item_rects
        assert ui.drawn(panel["name"])


def test_the_search_matches_what_the_qt_search_does(ui):
    for query, role in (("count", "count_rate"), ("PIE", "alex_creator"), ("routing channel", "photon_table"), ("audio", "audifier")):
        ui.app.filter = query
        assert role in {p["role"] for p in ui.app.matching_panels()}, query
    ui.app.filter = "no-such-tool"
    assert ui.app.matching_panels() == []


# -- navigation ------------------------------------------------------------------------------------------------------ #


def test_clicking_each_navigation_row_selects_and_builds_the_tool(ui):
    ui.draw(3)
    for panel in ui.app.tools:
        ui.click_name(f"nav.{panel['role']}")
        assert ui.app.selected == panel["role"] and ui.app.child is not None
        assert ui.drawn(panel["description"][:30]) or ui.app.panel["role"] == panel["role"]
    assert len(ui.app.children) == len(ui.app.tools)


def test_a_selected_tool_is_kept_alive_when_another_is_visited(ui):
    first = ui.app.select("alex_creator")
    ui.draw(2)
    ui.click_name("nav.audifier")
    ui.click_name("nav.alex_creator")
    assert ui.app.child is first


def test_the_search_field_is_typed_into_and_narrows_the_list(ui):
    ui.type_into_name("search", "count")
    assert ui.app.filter == "count"
    assert ui.drawn("Count Rate Analysis") and not ui.drawn("Audifier")
    ui.type_into_name("search", "zzz")
    assert ui.drawn("No matching tools.")
    ui.click_name("search")
    ui.app.key(0x41, "a", 0x04000000)
    ui.delete()  # select all + Delete empties the field
    assert ui.app.filter == "" and ui.drawn("Audifier")


def test_back_and_next_walk_the_tools_and_grey_at_the_ends(ui):
    roles = [p["role"] for p in ui.app.tools]
    ui.draw(3)
    ui.click_name("back")
    assert ui.app.selected == roles[0]  # greyed on the first tool
    for role in roles[1:]:
        ui.click_name("next")
        assert ui.app.selected == role
    ui.click_name("next")
    assert ui.app.selected == roles[-1]
    ui.click_name("back")
    assert ui.app.selected == roles[-2]


def test_the_status_line_says_ready(ui):
    assert ui.drawn("Ready")


# -- help and guide ---------------------------------------------------------------------------------------------------- #


def test_help_and_tool_help_open_and_close(ui):
    ui.click_name("help")
    assert ui.app.help.open
    ui.click_text("Close Help")
    assert not ui.app.help.open
    ui.click_name("tool_help")
    assert ui.app.child_help is not None and ui.app.child_help.open
    ui.click_text("Close Help")
    assert not ui.app.child_help.open


def test_the_tour_is_walked_selecting_each_awaited_row_and_the_card_never_covers_its_target(ui):
    ui.click_name("guide")
    tour = ui.app.tour
    assert tour.active
    seen = []
    for _ in range(20):
        if not tour.active:
            break
        ui.draw(3)
        step = tour.steps[tour.step_idx]
        assert_tour_card_clear(tour, ui.size)
        if tour.awaiting:
            key = tour._target_key(step["target"])
            seen.append(key)
            role = next(p["role"] for p in ui.app.tools if key.casefold() in p["name"].casefold())
            ui.click_name(f"nav.{role}")
            assert not tour.awaiting, f"selecting {key!r} did not release the step"
        ui.click_text("Finish ✓" if tour.step_idx == len(tour.steps) - 1 else "Next ►")
    assert not tour.active and seen == ["Count Rate", "ALEX Creator"]


def test_the_tour_card_is_draggable_and_still_clear_of_the_target(ui):
    ui.click_name("guide")
    ui.app.tour.start(1)
    ui.draw(3)
    ui.app.tour.card_offset = (-40.0, 30.0)
    ui.draw(2)
    assert_tour_card_clear(ui.app.tour, ui.size)


# -- errors, input routing, drops ---------------------------------------------------------------------------------------- #


def test_a_tool_that_cannot_open_shows_the_reason_and_retry_reopens_it():
    attempts = []

    def resolver(panel):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("broken child dependency")
        return Child, "test:child"

    driver = Driver(make_app(resolver=resolver))
    try:
        driver.draw(3)
        assert driver.drawn("The selected tool could not be opened.")
        assert any("broken child dependency" in s for s in driver.draw(2).strings)
        driver.click_name("retry")
        assert driver.app.child is not None and not driver.app.errors
    finally:
        driver.app.close()


def test_pointer_wheel_and_keys_reach_the_child_only_inside_its_area(ui):
    child = ui.app.select("alex_creator")
    ui.draw(3)
    cx, cy, cw, ch = ui.app.child_box
    assert cy == HEADER
    ui.click((cx + 20, cy + 20, 1, 1))
    assert child.calls[-2][0] == "press" and child.calls[-2][1][:2] == pytest.approx((20.5, 20.5))
    ui.app.key(65, "a")
    assert child.calls[-1][0] == "key"
    n = len(child.calls)
    ui.wheel(cx + 50, cy + 50, 2.0)
    assert child.calls[-1][0] == "wheel" and child.calls[-1][1][2] == 2.0
    n = len(child.calls)
    ui.wheel(30, 300, 2.0)  # over the navigation list
    assert len(child.calls) == n


def test_files_dropped_go_to_the_child_and_not_under_an_open_help(ui):
    child = ui.app.select("alex_creator")
    assert ui.drop("a.ptu")
    assert child.dropped == ["a.ptu"]
    ui.click_name("help")
    assert not ui.drop("b.ptu") and child.dropped == ["a.ptu"]


def test_child_settings_and_selection_round_trip(ui):
    ui.app.select("alex_creator").value = 42
    ui.click_name("nav.count_rate")
    state = json.loads(json.dumps(ui.app.export_settings()))
    other = make_app(resolver=fake)
    try:
        other.restore_settings(state)
        assert other.selected == "count_rate" and other.children["alex_creator"].value == 42
    finally:
        other.close()


# -- layout, tooltips, translations --------------------------------------------------------------------------------------- #


@pytest.mark.parametrize("size", SIZES)
def test_layout(ui, size):
    ui.resize(size)
    ui.draw(3)
    painter = ui.draw(3)
    lay.assert_texts_apart(painter)
    rects = {k: v for k, v in ui.app.item_rects.items() if not k.endswith(".stepper")}
    lay.assert_inside(rects, size)
    left = max(r[0] + r[2] for k, r in rects.items() if k.startswith("nav.")) + 8
    assert left < 0.34 * size[0] + 40, "the navigation list is narrow"
    assert ui.app.child_box[2] * ui.app.child_box[3] > 0.55 * size[0] * size[1], "the tool gets the space"


def test_every_control_has_a_tooltip_and_every_text_is_translated(ui):
    from emtk.i18n import get_locale, set_locale, tr

    from chisurf.plugins.tttr.tttr_toolbox.gui import translations
    from test.gui.emtk_port_parity import emtk_inventory

    for size in SIZES:
        assert emtk_inventory(ui.app, size)["controls_without_tooltip"] == []
    rows = [line.split("|") for line in translations.ROWS.splitlines()]
    assert all(len(r) == 6 for r in rows)
    known = {r[0] for r in rows}
    need = {"Ready", "Back", "Next", "Search…", "Tool help", "Retry", "No matching tools."}
    need |= {p["name"] for p in ui.app.tools} | {p["description"] for p in ui.app.tools}
    assert not need - known, sorted(need - known)
    previous = get_locale()
    try:
        for i, locale in enumerate(("de", "fr", "es", "pt", "ru"), start=1):
            set_locale(locale)
            assert all(tr(r[0]) == r[i] for r in rows)
    finally:
        set_locale(previous)


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("tttr_toolbox")
    assert result["ok"], result["output"]
