"""Real help categories, links and close actions remain reachable in a small host."""

from chisurf.plugins.emtk_layout import action_caption
import sys
from pathlib import Path
from types import ModuleType

import pytest
from emtk.app import ImApp
from emtk.events import LEFT_BUTTON
from emtk.testing import Driver

from chisurf.emtk.help_guide import EmTkHelpWindow, resolve_resource_file

RESOURCE = Path(__file__).resolve().parents[2] / "chisurf/plugins/tttr/microtime_histogram/gui/help.md"


@pytest.mark.parametrize("module_file", [None, "", "owner.py"])
def test_resource_module_file_preserves_none_empty_and_truthy_lookup(tmp_path, monkeypatch, module_file):
    """A missing/empty module origin is ignored; a real origin resolves its sibling help."""
    monkeypatch.chdir(tmp_path)
    package = tmp_path / "package"
    package.mkdir()
    help_file = package / "help.md"
    help_file.write_text("Owner help")
    module = ModuleType("native_help_origin_fixture")
    module.__file__ = str(package / module_file) if module_file else module_file
    monkeypatch.setitem(sys.modules, module.__name__, module)
    owner = type("Owner", (), {"__module__": module.__name__})()
    assert resolve_resource_file("help.md", owner) == (help_file if module_file else None)


def _help_driver(size=(600, 400), guide=None):
    """Open the actual shipped Microtime documentation through the native host contract."""
    window = EmTkHelpWindow(title="Micro-time histogram — Help", resource=RESOURCE,
                            size=(700, 520), on_start_guide=guide)
    app = ImApp(lambda: window.draw((0, 0, *size)))
    window.show()
    driver = Driver(app, size)
    driver.frame(3)
    return window, driver


@pytest.mark.parametrize("size", [(600, 400), (480, 320)])
def test_last_category_is_drawn_inside_the_modal_and_can_be_clicked(size):
    """The Outputs filter cannot sit beyond the modal's right scissor."""
    window, driver = _help_driver(size)
    target = driver.rect(" Outputs ")
    x, y, w, h = target
    dx, dy, dw, dh = window.dlg.box
    assert dx <= x and x + w <= dx + dw and dy <= y and y + h <= dy + dh
    driver.click(target)
    assert window.active_category == "Outputs"
    assert any("maximum" in text for text in driver.painter.strings)
    driver.click(" All ")
    assert window.active_category == "All"
    driver.click("Close Help")
    assert not window.open


def test_all_help_can_scroll_to_real_document_links_without_moving_footer(monkeypatch):
    """Full text is retained; the last live link can be used after a real wheel scroll."""
    window, driver = _help_driver()
    opened = []
    monkeypatch.setattr(window, "_open_link", opened.append)
    footer = driver.rect("Close Help")
    dx, dy, dw, dh = window.dlg.box
    driver.wheel(-100, at=(dx + dw / 2, dy + dh / 2))
    driver.frame(3)
    assert driver.rect("Close Help") == footer
    link = next(t[:4] for t in driver.painter.texts if "TCSPC lifetime fitting" in t[5] and t[5].startswith("↗"))
    x, y, w, h = link
    assert dy <= y and y + h <= footer[1]
    driver.click(link)
    assert opened == ["docs/concepts/tcspc_lifetime.md"]
    driver.click("Close Help")
    assert not window.open


def test_moving_the_modal_preserves_the_current_reading_position():
    """Dragging the header must not send a scrolled document back to its beginning."""
    window, driver = _help_driver((1200, 800))
    dx, dy, dw, dh = window.dlg.box
    driver.wheel(-100, at=(dx + dw / 2, dy + dh / 2))
    driver.frame(3)
    first = next(t[:4] for t in driver.painter.texts if t[5].startswith("↗ TCSPC lifetime fitting"))
    driver.hover((dx + 180, dy + 10))
    driver.surface.on_pointer_press(dx + 180, dy + 10, LEFT_BUTTON, 0)
    driver.frame()
    driver.surface.on_pointer_move(dx + 220, dy + 30, LEFT_BUTTON, 0)
    driver.frame(2)
    driver.surface.on_pointer_release(dx + 220, dy + 30, LEFT_BUTTON, 0)
    driver.frame(3)
    second = next(t[:4] for t in driver.painter.texts if t[5].startswith("↗ TCSPC lifetime fitting"))
    assert second[0] == first[0] + 40 and second[1] == first[1] + 20
    assert second[1] + second[3] <= driver.rect("Close Help")[1]


@pytest.mark.parametrize("size", [(400, 300), (480, 320), (600, 400)])
def test_header_close_and_start_guide_remain_real_actions(size):
    """Packing controls cannot hide Close or the existing guide callback."""
    starts = []
    window, driver = _help_driver(size, guide=lambda: starts.append(True))
    driver.click("Start Guided Tour")
    assert starts == [True] and not window.open
    window.show()
    driver.frame(3)
    driver.click(action_caption("close"))
    assert not window.open
