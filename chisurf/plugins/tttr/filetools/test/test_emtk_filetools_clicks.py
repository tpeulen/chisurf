"""Every control of the native File tools hub operated with simulated pointer and keyboard events.

Only ``press`` / ``release`` / ``pointer_move`` / ``wheel`` / ``key`` at the rectangles the controls were drawn in (or at the
text a list entry or a button drew) and host file drops reach the window; the assertions read the visible outcome (the
selection, the description strip, the embedded tool's event log, the pending panel). The embedded tools are recording fakes
here (the real native children are opened in ``test_emtk_filetools_parity.py``). The control -> test list is in
``okf/plugins/emtk-ports/filetools/REPORT.md``. A module guard fails the run if anything appears in the real
``~/.chisurf`` other than its ``logs`` folder.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from emtk import keys
from emtk.app import ImApp

from chisurf.emtk.plugin_icons import entry_icon
from chisurf.plugins.core.project_browser.test.driving import (
    clipped_texts,
    draw_clip,
    layout_problems,
)
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
from chisurf.plugins.tttr.filetools.gui.app import FileToolsApp, caption

PANELS = None
BIG, SMALL = (1200, 800), (800, 600)
REAL_CHISURF = Path(os.path.expanduser("~")) / ".chisurf"
SPEC = "chisurf.plugins.tttr.filetools.test.test_emtk_filetools_clicks:Recorder"


def _snapshot(root: Path) -> dict:
    out = {}
    if root.exists():
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root)
            if (rel.parts and rel.parts[0] == "logs") or "__pycache__" in rel.parts:
                continue
            stat = path.stat()
            out[str(rel)] = (stat.st_size, stat.st_mtime_ns)
    return out


@pytest.fixture(scope="module", autouse=True)
def real_chisurf_untouched():
    before = _snapshot(REAL_CHISURF)
    yield
    assert _snapshot(REAL_CHISURF) == before


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    for name in ("settings", "mmfdb", "home"):
        (tmp_path / name).mkdir()
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


class Recorder(ImApp):
    """A tool that records what the hub hands it."""

    def __init__(self):
        self.events = []
        self.dropped = []
        super().__init__(lambda: None)

    def pointer_press(self, x, y, button, modifiers=0, clicks=1):
        self.events.append(("press", round(x), round(y), button))

    def pointer_release(self, x, y, button, modifiers=0):
        self.events.append(("release", round(x), round(y), button))

    def wheel(self, x, y, steps, modifiers=0):
        self.events.append(("wheel", round(x), round(y), steps))

    def key(self, key, text="", modifiers=0):
        self.events.append(("key", key, text))
        return True

    def files_dropped(self, paths):
        self.dropped.append(list(paths))

    def close(self):
        pass


class HubDriver(Driver):
    def rect(self, name):
        self.draw(1)
        found = self.app.item_rects.get(name)
        assert found, f"{name!r} was not drawn: {sorted(self.app.item_rects)}"
        return tuple(found)


def fake_hub(broken=()):
    def resolver(panel):
        if panel["role"] in broken:
            raise RuntimeError("missing dependency for " + panel["role"])
        return SPEC

    return FileToolsApp(resolver=resolver)


@pytest.fixture
def drv():
    app = fake_hub()
    d = HubDriver(app, BIG)
    d.draw(3)
    yield d
    app.close()


def roles(drv):
    return [p["role"] for p in drv.app.panels]


def test_every_tool_is_listed_and_a_click_on_its_entry_selects_it_builds_its_tool_and_shows_its_description(drv):
    app = drv.app
    assert app.selected == roles(drv)[0] and app.child is not None
    for panel in app.panels:
        drv.click(drv.rect("nav_" + panel["role"]))
        drv.draw(3)
        assert app.selected == panel["role"] and panel["role"] in app.children
        assert drv.draw(2).strings.count(caption(panel)) == 2  # the entry and the description strip
        assert panel["description"][:40] in " ".join(drv.draw(2).strings)
    count = len(app.children)
    drv.click(drv.rect("nav_" + roles(drv)[0]))
    assert len(app.children) == count and app.child is app.children[roles(drv)[0]]  # kept, not rebuilt


def test_the_search_field_keeps_the_tools_matching_name_or_description(drv):
    app = drv.app
    names = [caption(p) for p in app.panels]
    drv.click(drv.rect("nav_" + app.panels[1]["role"]))  # select another tool: the description strip names it, not the list
    drv.type_into("search", "header", enter=False)
    strings = drv.draw(2).strings
    assert strings.count(names[3]) == 1 and strings.count(names[2]) == 0  # only the matching tool stays in the list
    drv.select_all()
    drv.type_text("zzzz")
    assert [n for n in names if drv.draw(2).strings.count(n) == 1 and n != caption(app.panels[1])] == []
    drv.select_all()
    drv.key(keys.KEY_BACKSPACE)
    strings = drv.draw(2).strings
    assert all(n in strings for n in names) and app.filter == ""


def test_the_embedded_tool_gets_pointer_events_in_its_own_coordinates_inside_its_box_only(drv):
    app = drv.app
    bx, by, bw, bh = app.child_box
    drv.click_at(bx + 100, by + 60)
    assert ("press", 100, 60, 1) in app.child.events and ("release", 100, 60, 1) in app.child.events
    n = len(app.child.events)
    drv.click_at(bx - 50, by + 60)  # on the list
    assert not [e for e in app.child.events[n:] if e[0] == "press"]


def test_the_wheel_over_the_tool_reaches_it_and_over_the_list_does_not(drv):
    app = drv.app
    bx, by, bw, bh = app.child_box
    drv.wheel(bx + 200, by + 200, 2)
    assert ("wheel", 200, 200, 2) in app.child.events
    n = len(app.child.events)
    drv.wheel(bx - 100, 300, 2)
    assert not [e for e in app.child.events[n:] if e[0] == "wheel"]


def test_keys_go_to_the_open_tool_after_a_press_inside_it_and_a_file_dropped_on_the_window_goes_to_it(drv, tmp_path):
    bx, by, bw, bh = drv.app.child_box
    drv.click_at(bx + 100, by + 60)
    drv.key(0x41, "a")
    assert ("key", 0x41, "a") in drv.app.child.events
    path = tmp_path / "x.ptu"
    path.write_bytes(b"x")
    assert drv.drop(str(path)) is True and drv.app.child.dropped == [[str(path)]]


def test_a_tool_that_cannot_open_breaks_only_its_panel_and_retry_tries_again():
    app = fake_hub(broken={"tttr_to_pto"})
    d = HubDriver(app, BIG)
    d.draw(3)
    d.click(d.rect("nav_tttr_to_pto"))
    d.draw(3)
    shown = " ".join(d.draw(2).strings)
    assert "Cannot open native panel: missing dependency for tttr_to_pto" in shown and "Retry" in d.draw(2).strings
    d.click(d.rect("nav_pto_inspector"))
    assert app.child is not None and "pto_inspector" in app.children  # the rest of the hub works
    d.click(d.rect("nav_tttr_to_pto"))
    calls = []
    app.resolver = lambda panel: calls.append(panel["role"]) or SPEC
    d.click_text("Retry")
    d.draw(3)
    assert calls == ["tttr_to_pto"] and "tttr_to_pto" in app.children and "Retry" not in d.draw(2).strings
    app.close()


def test_a_tool_without_a_native_declaration_says_pending_and_the_rest_works():
    app = FileToolsApp(resolver=lambda panel: None if panel["role"] == "tttr_header_edit" else SPEC)
    d = HubDriver(app, BIG)
    d.draw(3)
    d.click(d.rect("nav_tttr_header_edit"))
    d.draw(3)
    assert "Native panel pending." in " ".join(d.draw(2).strings)
    app.close()


def test_help_button_opens_the_help_window_whose_buttons_work(drv):
    window = drv.app.help
    drv.click_text("Help")
    assert window.open and {"Start Guided Tour", "Close", "Close Help"} <= set(drv.draw(2).strings)
    drv.click_text("Start Guided Tour")
    assert not window.open and drv.app.tour.active
    drv.app.tour.stop()
    drv.draw(2)
    for closer in ("Close Help", "Close"):
        drv.click_text("Help")
        drv.click_text(closer, last=closer == "Close Help")
        assert not window.open, closer
    drv.click_text("Help")
    drv.escape()
    assert not window.open


def test_the_tour_is_walked_with_the_user_operating_each_awaited_control(drv):
    tour = drv.app.tour
    drv.click_text("Guide")
    seen = []
    for _ in range(30):
        if not tour.active:
            break
        drv.draw(2)
        step = tour.steps[tour.step_idx]
        if tour.awaiting:
            seen.append(step["title"])
            key = step["target"]["name"]
            drv.click(drv.rect(key))
            assert not tour.awaiting, f"{step['title']}: operating {key} did not release the step"
        tour.next()
    assert not tour.active and seen == ["The converters move, they do not change"]


def test_every_guide_target_is_a_drawn_control_and_the_card_does_not_cover_it(drv):
    from chisurf.emtk.help_guide import place_tour_card

    for step in drv.app.tour.steps:
        key = (step.get("target") or {}).get("name")
        if not key:
            continue
        rect = drv.app.item_rects.get(key)
        assert rect and rect[2] > 0, f"{step['title']}: {key} is not drawn"
        card_w, card_h = min(480.0, BIG[0] - 40.0), 150.0
        x, y = place_tour_card(rect, float(BIG[0]), float(BIG[1]), card_w, card_h)
        clear = x + card_w <= rect[0] or x >= rect[0] + rect[2] or y + card_h <= rect[1] or y >= rect[1] + rect[3]
        free = (rect[0] + rect[2] + card_w + 16 <= BIG[0] or rect[0] - card_w - 16 >= 0
                or rect[1] + rect[3] + card_h + 16 <= BIG[1] or rect[1] - card_h - 16 >= 0)
        assert clear or not free, step["title"]


@pytest.mark.parametrize("size", [BIG, SMALL])
def test_the_hub_draws_without_clipped_or_overlapping_text_around_a_child(size):
    app = fake_hub()
    painter = draw_clip(app, size, frames=3)
    left, top = app.child_box[0], app.child_box[1]
    hub = [t for t in painter.shown if t[0][0] < left or t[0][1] < top]
    holder = type("P", (), {"shown": hub})()
    assert layout_problems(holder, size) == [] and clipped_texts(holder) == []
    assert {"Guide", "Help"} <= set(painter.strings)
    app.close()


@pytest.mark.parametrize("size", [BIG, SMALL])
def test_every_description_fits_above_the_tool_whatever_the_window_width(size):
    app = fake_hub()
    d = HubDriver(app, size)
    d.draw(3)
    for panel in app.panels:
        d.click(d.rect("nav_" + panel["role"]))
        painter = d.draw(3)
        top = app.child_box[1]
        words = panel["description"].split()[:3]
        lines = [t for t in painter.texts if t[0] >= app.child_box[0] - 1 and t[1] < top + 2 and t[5] and t[5] != caption(panel)]
        assert lines and max(t[1] + t[3] for t in lines) <= top + 0.5, f"{panel['role']}: the description runs into the tool"
    app.close()


def test_emoji_are_only_the_list_rows_icons(drv):
    """Each row carries its tool's pictogram in the icon slot; buttons and captions carry none."""
    from emtk.im_widgets import icon_text

    icons = {icon_text(entry_icon(p, p["entrypoint"])) for p in drv.app.panels}
    strings = drv.draw(2).strings
    assert icons <= set(strings)
    for text in strings:
        if text in icons:
            continue
        assert all(ord(ch) < 0x2190 or 0x2190 <= ord(ch) <= 0x21FF for ch in text), (
            text
        )  # arrows (the .pto caption) only


def test_the_whole_flow_works_in_the_small_window_too():
    app = fake_hub()
    d = HubDriver(app, SMALL)
    d.draw(3)
    d.click(d.rect("nav_tttr_header_edit"))
    assert app.selected == "tttr_header_edit"
    d.click_text("Guide")
    assert app.tour.active
    app.close()
