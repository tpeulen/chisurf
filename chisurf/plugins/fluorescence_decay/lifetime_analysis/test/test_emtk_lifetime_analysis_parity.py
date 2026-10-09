"""The native lifetime hub against the Qt shell it replaces, with real input events routed through the hub to the hosted tools.

Hermetic through ``conftest.py``; the last test proves the user's real ``~/.chisurf`` is untouched. The five hosted tools
have their own test folders: here only what the hub owns is checked (list, search, Back/Next, banner, help, guide,
settings, and that pointer, wheel, keys and file drops reach the selected tool through the hub's coordinates).
"""

from __future__ import annotations

import json
import os
import pwd
from pathlib import Path

import numpy as np
import pytest
from emtk import keys

from chisurf.plugins.emtk_test_input import CTRL, SIZE, SMALL, Driver
from chisurf.plugins.fluorescence_decay.lifetime_analysis.gui.app import PANELS, make_app

PLUGIN = Path(__file__).parent.parent
REAL_CHISURF = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".chisurf"


def snapshot_real():
    if not REAL_CHISURF.is_dir():
        return {}
    return {
        str(p): p.stat().st_mtime_ns
        for p in REAL_CHISURF.rglob("*")
        if p.is_file() and not {"cache", "logs"} & set(p.parts)
    }


REAL_BEFORE = snapshot_real()
IDS = [p[0] for p in PANELS]


@pytest.fixture
def ui():
    app = make_app()
    driver = Driver(app)
    driver.draw(3)
    yield driver
    app.close()


def child_rect(ui, rect):
    """A child-local rectangle in hub coordinates."""
    bx, by = ui.app.child_box[:2]
    return (rect[0] + bx, rect[1] + by, rect[2], rect[3])


def child_texts(ui):
    left = ui.app.child_box[0]
    return [t for t in ui.draw(3).texts if t[0] >= left]


# ───────────────────────────── the Qt shell's list is the native list ───────────────────────────── #


def test_names_descriptions_order_and_maturity_equal_the_qt_shell():
    pytest.importorskip("qtpy")
    from chisurf.plugins.fluorescence_decay.lifetime_analysis.gui.tool import LIFETIME_PANELS

    assert [p[1] for p in PANELS] == [p["name"] for p in LIFETIME_PANELS]
    assert [p[3] for p in PANELS] == [p["description"] for p in LIFETIME_PANELS]
    app = make_app()
    try:
        for (ident, _label, _icon, _desc, _alias), qt in zip(PANELS, LIFETIME_PANELS):
            assert bool(app.experimental_message(ident)) == bool(qt.get("experimental")), ident
            if qt.get("experimental"):
                assert app.experimental_message(ident) == qt["experimental_message"]
    finally:
        app.close()


# ───────────────────────────────────── list, banner, stepping ───────────────────────────────────── #


def test_each_entry_is_clicked_builds_its_tool_and_shows_its_description(ui):
    for ident, label, _icon, description, alias in PANELS:
        ui.click_name(alias)
        assert ui.app.selected == ident and ui.app.child is ui.app.children[ident]
        strings = [t[5] for t in ui.draw().texts]
        assert label in strings and description in strings
    assert len(ui.app.children) == len(PANELS)


def test_a_selected_tool_is_kept_alive_and_not_rebuilt(ui):
    ui.click_name("MaxEnt MEM")
    first = ui.app.child
    ui.click_name("Lazy Lifetime")
    ui.click_name("MaxEnt MEM")
    assert ui.app.child is first


def test_only_the_experimental_tool_carries_the_banner_and_the_list_mark(ui):
    ui.click_name("Lazy Lifetime")
    strings = [t[5] for t in ui.draw().texts]
    assert any("experimental and not yet validated" in s for s in strings)
    assert any(s.endswith(" *") for s in strings)
    ui.click_name("MaxEnt MEM")
    assert not any("experimental and not yet validated" in t[5] for t in ui.draw().texts)


def test_back_and_next_walk_the_tools_and_grey_out_at_the_ends(ui):
    ui.click_name("back")
    assert ui.app.selected == IDS[0]
    for ident in IDS[1:]:
        ui.click_name("next")
        assert ui.app.selected == ident
    ui.click_name("next")
    assert ui.app.selected == IDS[-1]
    for ident in reversed(IDS[:-1]):
        ui.click_name("back")
        assert ui.app.selected == ident


def test_up_and_down_keys_step_the_selection_when_the_tool_takes_no_keys(ui):
    ui.click_name("Lazy Lifetime")
    ui.app.pointer_move(5, 700)  # off every field
    ui.app.key(keys.KEY_DOWN, "")
    ui.draw(2)
    assert ui.app.selected == "microtime_histogram"
    ui.app.key(keys.KEY_UP, "")
    ui.app.key(keys.KEY_UP, "")
    ui.draw(2)
    assert ui.app.selected == "maxent_decay"


# ──────────────────────────────────────────── search ──────────────────────────────────────────── #


def test_typing_in_the_search_box_filters_the_list_and_clearing_restores_it(ui):
    ui.click(ui.rect("search"))
    assert ui.app.io.want_capture_keyboard
    ui.type("lazy")
    assert ui.app.search == "lazy"
    strings = [t[5] for t in ui.draw().texts]
    assert any(s.startswith("3. Lazy") for s in strings) and "2. MaxEnt MEM" not in strings
    ui.app.key(0x41, "a", CTRL)
    for _ in range(4):
        ui.app.key(keys.KEY_BACKSPACE, "")
        ui.draw(1)
    assert ui.app.search == ""
    assert "2. MaxEnt MEM" in [t[5] for t in ui.draw().texts]


def test_a_search_without_match_says_so_and_keeps_the_selected_tool(ui):
    before = ui.app.selected
    ui.click(ui.rect("search"))
    ui.type("zzzz")
    assert "No tool matches the search." in [t[5] for t in ui.draw().texts]
    assert ui.app.selected == before and ui.app.child is not None


def test_the_search_matches_descriptions_too(ui):
    ui.click(ui.rect("search"))
    ui.type("g-factor")
    labels = [
        t[5]
        for t in ui.draw().texts
        if t[5][:2] in ("1.", "2.", "3.", "4.", "5.")
        and t[0] < ui.app.child_box[0]
        and ": ready" not in t[5]
    ]
    assert labels == ["5. VV/VH G-Factor"]


# ─────────────────────────── input reaches the hosted tool through the hub ─────────────────────────── #


def test_a_click_in_the_hosted_tool_is_translated_into_its_own_coordinates(ui):
    ui.click_name("G-Factor")
    child = ui.app.child
    x, y, w, h = [t[:4] for t in ui.draw().texts if t[5] == "Slow protein..."][-1]
    assert x >= ui.app.child_box[0]
    ui.click((x, y, w, h))
    assert child.dialog is not None
    assert child.dialog_window is not None
    ui.click_text("Cancel")
    assert child.dialog is None


def test_typing_into_a_hosted_field_reaches_its_model(ui):
    ui.click_name("MaxEnt MEM")
    child = ui.app.child
    ui.draw(3)
    rect = child_rect(ui, child.forms["mode"].rects["nu"])
    ui.click(rect, fx=0.3)
    assert child.io.want_capture_keyboard, "the hosted field did not take the keyboard"
    ui.app.key(0x41, "a", CTRL)
    ui.draw(1)
    ui.type("0.02")
    ui.enter()
    assert child.model.settings.nu == pytest.approx(0.02)


def test_the_wheel_over_a_hosted_plot_zooms_it_and_over_the_list_does_nothing(ui):
    ui.click_name("MaxEnt MEM")
    child = ui.app.child
    child.model.set_data(np.arange(64) * 0.05, np.arange(64) + 5.0, "d")
    ui.draw(4)
    info = child.plot_info.get("decay")
    before = [t[5] for t in ui.draw().texts]
    bx, by = ui.app.child_box[:2]
    # a plot area: the decay window sits at the top of the hosted tool's right area
    ui.wheel(bx + 600, by + 200, -3.0)
    assert [t[5] for t in ui.draw().texts] != before or info is None
    selected = ui.app.selected
    ui.wheel(50, 300, -3.0)
    assert ui.app.selected == selected


def test_a_dropped_file_goes_to_the_selected_tool(ui, tmp_path):
    ui.click_name("MaxEnt MEM")
    path = tmp_path / "decay.dat"
    np.savetxt(path, np.column_stack((np.arange(64) * 0.05, np.arange(64) + 5.0)))
    assert ui.drop(path) is True
    assert ui.app.child.model.source == "decay.dat"
    ui.click_name("Lazy Lifetime")
    assert ui.drop(path) in (True, False)


def test_a_tool_that_cannot_be_built_is_reported_in_the_header(ui, monkeypatch):
    import chisurf.plugins.fluorescence_decay.lifetime_analysis.gui.app as hub

    def broken(*args, **kwargs):
        raise RuntimeError("no module")

    monkeypatch.setattr(hub, "load_plugin", broken)
    ui.click_name("Histogram-Microtime")
    assert ui.app.child is None and "could not open: no module" in ui.app.error
    assert any("could not open: no module" in t[5] for t in ui.draw().texts)
    assert "could not open" in ui.app.status


# ───────────────────────────────────── help, guide, settings ───────────────────────────────────── #


def test_help_opens_with_live_links_and_closes(ui):
    ui.click_name("help")
    assert ui.app.help_window.open
    ui.click_text("Close")
    assert not ui.app.help_window.open
    import re

    repo = next(p for p in PLUGIN.parents if (p / "pyproject.toml").exists())
    links = re.findall(r"\]\((docs/[^)#]+)", (PLUGIN / "gui" / "help.md").read_text())
    assert links and all((repo / link).is_file() for link in links)


def test_the_tour_waits_for_each_real_selection(ui):
    ui.click_name("guide")
    tour = ui.app.tour
    assert tour.active
    waited = 0
    for _ in range(len(tour.steps) + 2):
        if not tour.active:
            break
        step = tour.steps[tour.step_idx]
        if tour.awaiting:
            waited += 1
            ui.click_text("Next ►")
            assert tour.awaiting  # refused until the real control is used
            key = tour._target_key(step.get("target"))
            assert key in ui.app.item_rects
            ui.click_name(key)
            assert not tour.awaiting
        ui.click_text("Next ►") if tour.step_idx < len(tour.steps) - 1 else ui.click_text(
            "Close Tour"
        )
    assert waited >= 3 and not tour.active


def test_every_tour_target_is_drawn(ui):
    for index, step in enumerate(ui.app.tour.steps):
        key = ui.app.tour._target_key(step.get("target"))
        if not key:
            continue
        ui.app.tour.start(index)
        ui.draw(3)
        assert ui.app.tour.get_target_rect(key), key
        ui.app.tour.stop()


def test_settings_round_trip_keeps_the_selection_and_the_tools_own_settings(ui):
    ui.click_name("MaxEnt MEM")
    ui.app.child.model.settings.tau_max = 9.0
    saved = json.loads(json.dumps(ui.app.export_settings()))
    assert (
        saved["selected"] == "maxent_decay"
        and saved["children"]["maxent_decay"]["settings"]["tau_max"] == 9.0
    )
    other = make_app()
    other.restore_settings(saved)
    assert other.selected == "maxent_decay"
    child = other.select("maxent_decay")  # built later: the pending settings apply on first use
    assert child.model.settings.tau_max == 9.0
    other.restore_settings({"selected": "nonsense", "children": {"nonsense": {}, "lltf": "junk"}})
    assert other.selected == "maxent_decay"
    other.restore_settings(None)
    other.close()


# ───────────────────────────────────── layout, tooltips, hygiene ───────────────────────────────────── #


@pytest.mark.parametrize("size", [SIZE, SMALL, (500, 500)])
def test_every_tool_draws_at_every_size(ui, size):
    ui.resize(size)
    for alias in [p[4] for p in PANELS]:
        ui.click_name(alias)
        ui.draw(3)


def test_the_hub_controls_do_not_run_past_the_window_edge_in_the_small_window(ui):
    ui.resize(SMALL)
    left = ui.app.child_box[0]
    for x, y, w, h, align, string, *_ in ui.draw(3).texts:
        if x < left:
            assert x + w <= left + 1, (string, x, w)


def test_the_header_grows_for_the_banner_instead_of_overlapping_the_tool(ui):
    ui.click_name("Lazy Lifetime")
    with_banner = ui.app.child_box[1]
    ui.click_name("MaxEnt MEM")
    assert with_banner > ui.app.child_box[1]


def test_every_hub_control_has_a_tooltip(ui):
    from test.gui.emtk_port_parity import emtk_inventory

    inventory = emtk_inventory(ui.app, SIZE)
    hub = [
        r
        for r in inventory["interactive"]
        if r["id"] in ("##search_tools", "Back", "Next", "Help", "Guide")
        or r["label"].startswith(("1.", "2.", "3.", "4.", "5."))
    ]
    assert hub and all(r.get("tooltip") for r in hub), [r for r in hub if not r.get("tooltip")]


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("lifetime_analysis")
    assert result["ok"], result["output"]


def test_zzz_the_real_chisurf_folder_was_not_touched():
    assert snapshot_real() == REAL_BEFORE
