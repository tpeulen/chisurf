"""The Settings hub with real input: sidebar, search, Back / Next / fast-forward, Guide, Help, hosted panels.

Hermetic: temporary settings folder, temporary MMFDB with users, temporary HOME (``seeded.prepare``); the updater's fakes
stand in for the network and conda. Only what a host delivers reaches the app: pointer press / release / move, the wheel,
typed characters and keys, focus loss and file drops.
"""

from __future__ import annotations

import pytest
from emtk import keys

from chisurf.plugins.core.setup.gui.model import PANELS
from chisurf.plugins.core.setup.test import seeded
from chisurf.plugins.emtk_test_input import Driver

SIZES = [(1200, 800), (800, 600)]
LABELS = [p.label for p in PANELS]
#: The dedicated panel (class name) each destination must host: never the generic file editor.
EXPECTED = {
    "boarding": "BoardingApp",
    "chisurf": "ConfigurationApp",
    "acq": "AcquisitionSettingsApp",
    "style": "StyleManagerApp",
    "plots": "PlotSettingsApp",
    "models": "ModelManagerApp",
    "users": "UserEditorApp",
    "ai": "AISettingsApp",
    "plugins": "PluginManagerApp",
    "updates": "UpdaterApp",
    "packages": "PackageApp",
    "channels": "SetupChannelDefinitionApp",
    "fcs": "PresetApp",
    "lut": "LutToolsApp",
    "check": "PluginCheckApp",
}


@pytest.fixture
def world(tmp_path, monkeypatch):
    return seeded.prepare(tmp_path, monkeypatch)


@pytest.fixture
def hub(world):
    from chisurf.plugins.core.setup.gui.app import make_app

    app = make_app(settings_dir=world)
    drv = Driver(app)
    drv.draw(3)
    yield drv
    app.close()


def dest(hub_driver, key):
    return hub_driver.rect("dest_" + key)


def shown_labels(drv):
    """Labels of the destinations drawn in the sidebar (their selectable rows)."""
    drv.draw(2)
    return [p.label for p in PANELS if "dest_" + p.key in drv.app.item_rects and drv.drawn_sidebar(p)]


def in_sidebar(drv, painter=None):
    painter = painter or drv.draw(2)
    box = drv.app.item_rects["destinations"]
    found = []
    for x, y, w, h, *_rest, text in [t[:4] + (None, t[5]) for t in painter.texts]:
        if text in LABELS and x >= box[0] and x + w <= box[0] + box[2] + 1 and y >= box[1] and y + h <= box[1] + box[3]:
            found.append(text)
    return found


# ----------------------------------------------------------------------------------------------- structure
def test_the_hub_opens_on_getting_started_and_lists_the_fifteen_qt_destinations(hub):
    assert hub.app.selected == "boarding"
    assert type(hub.app.child).__name__ == "BoardingApp"
    assert in_sidebar(hub) == LABELS
    assert len(LABELS) == 15


def test_the_destinations_equal_the_qt_hub_in_name_and_order():
    from chisurf.plugins.core.setup.gui.tool import SETTINGS_PANELS

    assert LABELS == [p["name"] for p in SETTINGS_PANELS]


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_every_sidebar_entry_opens_its_dedicated_panel_by_a_real_click(hub, size):
    hub.resize(size)
    for panel in PANELS:
        hub.click(dest(hub, panel.key))
        assert hub.app.selected == panel.key
        assert type(hub.app.child).__name__ == EXPECTED[panel.key], panel.key
        assert hub.app.error == "" and hub.app.status == "Ready", (panel.key, hub.app.error)
        assert hub.app.routes[panel.key] != "unavailable"


def test_only_the_settings_file_editor_is_a_file_editor_and_it_is_the_chisurf_settings_destination(hub):
    for panel in PANELS:
        hub.app.select(panel.key)
    generic = [k for k, c in hub.app.children.items() if type(c).__name__ == "ConfigurationApp"]
    assert generic == ["chisurf"]


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_layout_sidebar_width_no_clipping_and_the_panel_gets_the_space(hub, size):
    hub.resize(size)
    painter = hub.draw(3)
    box = hub.app.item_rects["destinations"]
    assert 120 <= box[2] <= 260 and box[2] <= size[0] * 0.3 + 1
    # every label is drawn whole inside the sidebar (a clipped label would be cut by the width)
    assert in_sidebar(hub, painter) == LABELS
    panel = hub.app.item_rects["panel"]
    assert panel[0] == pytest.approx(box[2]) and panel[0] + panel[2] == pytest.approx(size[0])
    status = hub.app.item_rects["status"]
    assert panel[1] + panel[3] <= status[1] + 1          # the panel ends above the status line
    for name in ("guide", "help", "back", "ff", "next"):
        x, y, w, h = hub.app.item_rects[name]
        assert 0 <= x and x + w <= size[0] and 0 <= y and y + h <= size[1], name
    # nothing overlaps: the three stepper buttons sit in one row, left to right
    back, ff, nxt = (hub.app.item_rects[n] for n in ("back", "ff", "next"))
    assert back[0] + back[2] <= ff[0] and ff[0] + ff[2] <= nxt[0]


# ----------------------------------------------------------------------------------------------- search
def type_search(drv, text, replace=True):
    rect = drv.app.item_rects["search"]
    drv.click(rect)
    assert drv.app.io.want_capture_keyboard
    if replace:
        drv.app.key(0x41, "a", 0x04000000)
        drv.draw(1)
    drv.type(text)


def test_typing_in_the_search_box_filters_by_name_like_qt(hub):
    type_search(hub, "plug")
    assert hub.app.filter == "plug"
    assert in_sidebar(hub) == ["Plugins", "Plugin Check"]
    type_search(hub, "zzz")
    assert in_sidebar(hub) == []
    assert any(t[5] == "No matching settings." for t in hub.draw(1).texts)
    type_search(hub, "")
    hub.app.key(keys.KEY_BACKSPACE, "")
    hub.draw(2)
    assert in_sidebar(hub) == LABELS


def test_the_search_filter_equals_the_qt_navigation_filter():
    """Qt: a case-insensitive substring of the panel name (descriptions do not match)."""
    from chisurf.plugins.core.setup.gui.model import visible_panels

    for query in ("", "plug", "PLUG", "s", "fcs", "definition", "check", "x"):
        expected = [p.label for p in PANELS if query.lower() in p.label.lower()]
        assert [p.label for p in visible_panels(PANELS, query)] == expected


def test_enter_in_the_search_box_opens_the_first_match(hub):
    type_search(hub, "chan")
    hub.enter()
    assert hub.app.selected == "channels"
    assert type(hub.app.child).__name__ == "SetupChannelDefinitionApp"


def test_a_filtered_out_destination_stays_open(hub):
    hub.click(dest(hub, "plots"))
    type_search(hub, "user")
    assert in_sidebar(hub) == ["User Editor"]
    assert hub.app.selected == "plots" and type(hub.app.child).__name__ == "PlotSettingsApp"


def test_clicking_a_filtered_result_opens_it(hub):
    type_search(hub, "fcs")
    hub.click(dest(hub, "fcs"))
    assert type(hub.app.child).__name__ == "PresetApp"


def test_the_wheel_over_the_sidebar_scrolls_a_list_that_does_not_fit(hub):
    hub.resize((800, 300))
    y_before = hub.app.item_rects["dest_check"][1]
    box = hub.app.item_rects["destinations"]
    for _ in range(6):
        hub.wheel(box[0] + 60, box[1] + 120, -3)
    assert hub.app.item_rects["dest_check"][1] < y_before - 20
    # and back: the other direction brings the first entry back
    for _ in range(12):
        hub.wheel(box[0] + 60, box[1] + 120, 3)
    assert hub.app.item_rects["dest_boarding"][1] >= 0


# ----------------------------------------------------------------------------------------------- Back / Next / fast-forward
def test_back_is_greyed_on_the_first_destination_and_next_on_the_last(hub):
    hub.click_name("back")
    assert hub.app.selected == "boarding"
    hub.click(dest(hub, "check"))
    hub.click_name("next")
    assert hub.app.selected == "check"


def test_next_and_back_walk_the_list_in_order_by_clicks(hub):
    order = [p.key for p in PANELS]
    for key in order[1:]:
        hub.click_name("next")
        assert hub.app.selected == key
        assert type(hub.app.child).__name__ == EXPECTED[key]
    for key in reversed(order[:-1]):
        hub.click_name("back")
        assert hub.app.selected == key


def test_next_and_back_equal_the_qt_stepper(world):
    """The Qt stepper walks every non-separator row of the list in order."""
    from chisurf.plugins.core.setup.gui.model import step_target
    from chisurf.plugins.core.setup.gui.tool import SETTINGS_PANELS

    qt_names = [p["name"] for p in SETTINGS_PANELS if not p.get("separator")]
    walked = [PANELS[0].key]
    while (nxt := step_target(PANELS, walked[-1], 1)) is not None:
        walked.append(nxt)
    assert [next(p.label for p in PANELS if p.key == k) for k in walked] == qt_names
    assert step_target(PANELS, PANELS[0].key, -1) is None


def test_fast_forward_visits_every_remaining_destination_and_says_so(hub):
    statuses = []
    original = hub.app._ff_step

    def spy():
        original()
        statuses.append(hub.app.status)

    hub.app._ff_step = spy
    hub.click_name("ff")
    for _ in range(40):
        hub.draw(1)
        if not hub.app.fast_forward:
            break
    assert hub.app.selected == "check"
    assert hub.app.status == "Fast-forward finished - the pipeline is done"
    assert any(s.startswith("Fast-forward 1/15: Getting Started") for s in statuses)
    assert any(s == "Fast-forward 15/15: Plugin Check" for s in statuses)
    assert len(hub.app.children) == 15            # every destination was built on the way
    assert not hub.app.fast_forward


def test_a_second_press_of_fast_forward_stops_it(hub):
    hub.click_name("ff")
    assert hub.app.fast_forward
    hub.click_name("ff")
    assert not hub.app.fast_forward
    assert hub.app.status.startswith("Fast-forward stopped")
    assert hub.app.selected != "check"


def test_back_and_a_hand_pick_stop_a_fast_forward(hub):
    hub.click_name("ff")
    hub.click_name("back")
    assert not hub.app.fast_forward
    hub.click(dest(hub, "models"))
    hub.click_name("ff")
    hub.click(dest(hub, "plots"))
    assert not hub.app.fast_forward and hub.app.status == "Ready" and hub.app.selected == "plots"


def test_the_status_line_reads_ready(hub):
    assert any(t[5] == "Ready" for t in hub.draw(1).texts)


# ----------------------------------------------------------------------------------------------- Guide / Help
def test_the_help_button_opens_the_help_window_and_it_closes(hub):
    hub.click_name("help")
    assert hub.app.help.open
    painter = hub.draw(2)
    assert any("Back, Next and fast-forward" in t[5] for t in painter.texts)
    hub.escape()
    hub.app.help.hide()
    hub.draw(2)
    assert not hub.app.help.open


def test_the_guide_walks_the_hub_and_waits_for_the_real_controls(hub):
    hub.click_name("guide")
    tour = hub.app.tour
    assert tour.active and tour.step_idx == 0 and tour.awaiting
    tour.next()
    assert tour.step_idx == 0                     # Next does nothing until the search box was used
    type_search(hub, "p")
    assert not tour.awaiting
    tour.next()                                   # step 2: informational
    assert tour.step_idx == 1 and not tour.awaiting
    tour.next()                                   # step 3: wait for a click on a destination
    assert tour.step_idx == 2 and tour.awaiting
    hub.click(dest(hub, "plots"))
    assert not tour.awaiting
    tour.next()                                   # step 4: wait for Next
    assert tour.step_idx == 3 and tour.awaiting
    hub.click_name("next")
    assert not tour.awaiting
    tour.next()
    tour.next()
    assert tour.step_idx == 5
    tour.next()
    assert not tour.active


def test_every_guide_target_is_a_drawn_hub_control(hub):
    import json
    from pathlib import Path

    steps = json.loads((Path(__file__).parents[1] / "gui" / "guide.json").read_text())["steps"]
    hub.draw(2)
    for step in steps:
        name = step["target"]["name"]
        assert name in hub.app.item_rects, name


def test_the_tour_card_does_not_cover_the_control_it_points_at(hub):
    from chisurf.emtk.help_guide import place_tour_card

    hub.click_name("guide")
    for step in hub.app.tour.steps:
        rect = hub.app.item_rects[step["target"]["name"]]
        w, h = hub.size
        x, y = place_tour_card(rect, w, h, min(480.0, w - 40.0), 140.0)
        assert x + 480 <= rect[0] or x >= rect[0] + rect[2] or y + 140 <= rect[1] or y >= rect[1] + rect[3] or rect[2] > w * 0.5, step["title"]


# ----------------------------------------------------------------------------------------------- hosting
def test_pointer_events_reach_the_hosted_panel_in_its_own_coordinates(hub):
    hub.click(dest(hub, "plots"))
    child = hub.app.child
    guide = child.item_rects["guide"]
    x0, y0 = hub.app.child_box[:2]
    # a rect of the child is in the child's coordinates: shift it to the hub canvas
    hub.click((guide[0] + x0, guide[1] + y0, guide[2], guide[3]))
    assert child.tour.active


def test_a_hosted_panel_keeps_its_state_while_another_destination_is_shown(hub):
    hub.click(dest(hub, "chisurf"))
    editor = hub.app.child
    editor.document.text = "gui:\n  language: de\n"
    hub.click(dest(hub, "models"))
    hub.click(dest(hub, "chisurf"))
    assert hub.app.child is editor and editor.document.text.startswith("gui:\n  language: de")


class Recorder:
    """A fake hosted app that records everything the hub forwards."""

    def __init__(self):
        self.log = []
        self.item_rects = {}

    def draw(self, painter, x, y, w, h):
        self.log.append(("draw", x, y, w, h))

    def pointer_press(self, x, y, button, modifiers=0, clicks=1):
        self.log.append(("press", x, y, button))

    def pointer_release(self, x, y, button, modifiers=0):
        self.log.append(("release", x, y, button))

    def pointer_move(self, x, y, buttons=0, modifiers=0):
        self.log.append(("move", x, y))

    def wheel(self, x, y, steps, modifiers=0):
        self.log.append(("wheel", x, y, steps))

    def scroll(self, rows):
        self.log.append(("scroll", rows))

    def key(self, key, text="", modifiers=0):
        self.log.append(("key", key, text))
        return True

    def key_release(self, key, text="", modifiers=0):
        self.log.append(("key_release", key, text))

    def focus_lost(self):
        self.log.append(("focus_lost",))

    def files_dropped(self, paths):
        self.log.append(("drop", tuple(paths)))
        return True

    def animating(self):
        return False

    def next_frame_in(self):
        return None

    def close(self):
        self.log.append(("close",))


@pytest.fixture
def fake_hub(world, monkeypatch):
    from chisurf.plugins.core.setup.gui import app as app_module

    fake = Recorder()
    monkeypatch.setattr(app_module, "resolve_factory", lambda panel: (lambda: fake))
    app = app_module.make_app(settings_dir=world)
    drv = Driver(app)
    drv.draw(3)
    return drv, fake


def test_the_hub_forwards_pointer_wheel_keys_focus_loss_and_drops_to_the_hosted_app(fake_hub):
    drv, fake = fake_hub
    drv.app.select("style")                                  # a non-file destination: the fake is hosted
    assert drv.app.child is fake
    bx, by, bw, bh = drv.app.child_box
    inside = (bx + 50, by + 40)
    drv.app.pointer_move(*inside)
    drv.app.pointer_press(*inside, 1)
    drv.app.pointer_release(*inside, 1)
    drv.app.wheel(*inside, -2)
    drv.app.key(keys.KEY_DOWN, "")
    drv.app.key_release(keys.KEY_DOWN, "")
    assert drv.app.files_dropped(["/tmp/x.dat"])
    drv.app.focus_lost()
    names = [e[0] for e in fake.log]
    for expected in ("draw", "move", "press", "release", "wheel", "key", "key_release", "drop", "focus_lost"):
        assert expected in names, (expected, names)
    local = (inside[0] - bx, inside[1] - by)
    assert ("press", *local, 1) in fake.log and ("wheel", *local, -2) in fake.log
    # the child is drawn in local coordinates of the region it is given
    assert ("draw", 0.0, 0.0, bw, bh) in fake.log


def test_a_press_outside_the_hosted_panel_does_not_reach_it_and_keys_stay_with_the_hub(fake_hub):
    drv, fake = fake_hub
    drv.app.select("style")
    fake.log.clear()
    sidebar = (60, 300)
    drv.app.pointer_move(*sidebar)
    drv.app.pointer_press(*sidebar, 1)
    drv.app.pointer_release(*sidebar, 1)
    drv.app.key(keys.KEY_DOWN, "")
    drv.app.wheel(*sidebar, -1)
    names = [e[0] for e in fake.log]
    assert "press" not in names and "release" not in names and "key" not in names and "wheel" not in names


def test_the_wheel_after_a_hosted_panel_was_left_never_reaches_a_stale_child(fake_hub):
    drv, fake = fake_hub
    drv.app.select("style")
    drv.app.select("chisurf")
    fake.log.clear()
    bx, by, bw, bh = drv.app.child_box
    drv.app.wheel(bx + 30, by + 30, -1)
    assert not any(e[0] == "wheel" for e in fake.log)


def test_a_panel_that_cannot_be_built_says_why_and_retries_never_a_file_editor(world, monkeypatch):
    from chisurf.plugins.core.setup.gui import app as app_module

    calls = []

    def broken(panel):
        def factory():
            if panel.key == "plots":
                calls.append(1)
            if panel.key == "plots" and len(calls) == 1:
                raise RuntimeError("boom: the plugin is missing")
            return Recorder()

        return factory

    monkeypatch.setattr(app_module, "resolve_factory", broken)
    app = app_module.make_app(settings_dir=world)
    drv = Driver(app)
    drv.draw(2)
    app.select("plots")
    painter = drv.draw(3)
    assert app.routes["plots"] == "unavailable"
    assert any("boom: the plugin is missing" in t[5] for t in painter.texts)
    assert "Cannot load Plots" in app.status
    assert type(app.child).__name__ == "UnavailablePanel"
    bx, by = app.child_box[:2]
    r = app.child.item_rects["retry"]
    drv.click((r[0] + bx, r[1] + by, r[2], r[3]))
    assert type(app.child).__name__ == "Recorder" and app.routes["plots"] == "native"


# ----------------------------------------------------------------------------------------------- remembered selection
def test_the_selected_destination_and_each_panels_state_are_remembered(world):
    from chisurf.plugins.core.setup.gui.app import make_app

    first = make_app(settings_dir=world)
    drv = Driver(first)
    drv.draw(2)
    drv.click(dest(drv, "plots"))
    saved = first.export_settings()
    assert saved["selected"] == "plots" and "plots" in saved["children"]
    first.close()
    second = make_app(settings_dir=world)
    second.restore_settings(saved)
    assert second.selected == "plots" and type(second.child).__name__ == "PlotSettingsApp"
    assert second.export_settings()["selected"] == "plots"
    second.close()


def test_a_saved_selection_that_no_longer_exists_opens_getting_started(world):
    from chisurf.plugins.core.setup.gui.app import make_app

    app = make_app(settings_dir=world)
    app.restore_settings({"selected": "gone", "children": {"gone": {}}})
    assert app.selected == "boarding"
    app.close()


# ----------------------------------------------------------------------------------------------- tooltips
@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_every_hub_control_has_a_tooltip(hub, size):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "emtk_port_parity", str(__import__("pathlib").Path(__file__).parents[5] / "test" / "gui" / "emtk_port_parity.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    inventory = module.emtk_inventory(hub.app, size)
    assert inventory["controls_without_tooltip"] == []


# ----------------------------------------------------------------------------------------------- no Qt
def test_the_hub_and_every_hosted_destination_draw_with_qt_forbidden(world):
    import os
    import subprocess
    import sys

    code = r"""
import sys
class BlockQt:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'}:
            raise ImportError('Qt forbidden ' + fullname)
sys.meta_path.insert(0, BlockQt())
import pytest
from chisurf.plugins.core.updater.test.fakes import Fakes
Fakes().install(pytest.MonkeyPatch())
from emtk.testing import RecordingPainter
from chisurf.plugins.core.setup.gui.app import make_app
app = make_app(settings_dir=sys.argv[1])
for size in ((1200, 800), (800, 600)):
    for panel in app.panels:
        app.select(panel.key)
        assert app.routes[panel.key] in ('native', 'configuration'), (panel.key, app.error)
        for _ in range(3):
            app.draw(RecordingPainter(), 0, 0, *size)
app.help.show(); app.tour.start(); app.draw(RecordingPainter(), 0, 0, 1200, 800)
assert 'qtpy' not in sys.modules
app.close()
print('QT-FREE OK')
"""
    import subprocess as sp

    from chisurf.plugins.core.updater.test.fakes import REAL_POPEN

    proc = REAL_POPEN([sys.executable, "-c", code, str(world)], env=os.environ.copy(), text=True, stdout=sp.PIPE, stderr=sp.PIPE)
    out, err = proc.communicate(timeout=300)
    assert proc.returncode == 0 and "QT-FREE OK" in out, out + err[-3000:]


def test_the_saved_window_state_is_plain_json_and_restores_in_a_new_hub(world):
    import json

    from chisurf.plugins.core.setup.gui.app import make_app

    app = make_app(settings_dir=world)
    for key in ("acq", "plots", "models", "check"):
        app.select(key)
    state = json.loads(json.dumps(app.export_settings()))
    app.close()
    again = make_app(settings_dir=world)
    again.restore_settings(state)
    assert again.selected == "check" and set(again.export_settings()["children"]) >= {"acq", "plots", "models", "check"}
    again.close()


def test_no_provider_key_of_the_developers_shell_reaches_the_ai_settings_panel(world):
    import os

    assert not [n for n in os.environ if n.endswith(("_API_KEY", "_KEY", "_TOKEN"))]
    from chisurf.plugins.core.setup.gui.app import make_app

    app = make_app(settings_dir=world)
    app.select("ai")
    assert app.child.model.api_key == ""
    app.close()


def test_the_hosted_updater_checks_quietly_like_the_qt_hub(world):
    import time

    from chisurf.plugins.core.setup.gui.app import make_app

    app = make_app(settings_dir=world)
    app.select("updates")
    child = app.child
    child.auto_check_delay = 0.0
    drv = Driver(app)
    end = time.monotonic() + 20
    while time.monotonic() < end and (child.model.auto_check_pending or child.job.busy):
        drv.draw(1)
        time.sleep(0.05)
    drv.draw(3)
    assert not child.model.auto_check_pending
    assert child.model.suppress_initial_notification and not child.model.dialog
    assert not any(t[5] == "Update Available" for t in drv.draw(1).texts)
    app.close()
