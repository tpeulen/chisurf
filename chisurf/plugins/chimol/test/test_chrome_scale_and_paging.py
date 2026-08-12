"""Two things the chrome owes a small window: a size knob, and pages.

The chrome is drawn over the molecule, so its size is a setting rather than a
constant, and it is **smaller than the baked font by default** — every pixel it
takes is a pixel of the picture it covers. Scaling the font alone would not do:
seventeen-pixel rows around eleven-pixel text is not smaller chrome, only
emptier chrome, so one knob moves both.

Paging is the other half. A menu taller than the viewport already scrolled, and
scrolling is a wheel — a menu whose remainder can only be reached by a wheel is
a menu whose remainder most people never find. Its title now says which page it
is on, and the arrows beside the title turn it.
"""
from __future__ import annotations

import pytest

from chisurf.plugins.chimol.chimol.object_menus import MenuEntry
from chisurf.plugins.chimol.chimol.renderer.internal_gui import (
    BASE_FONT_PT,
    GuiRow,
    InternalGui,
    char_width,
)

WIDTH, HEIGHT = 900, 600


@pytest.fixture
def gui():
    panel = InternalGui(run_command=lambda line: None)
    panel.set_rows([GuiRow(name="all", is_header=True), GuiRow(name="148l", enabled=True)])
    panel.layout(WIDTH, HEIGHT)
    return panel


# --------------------------------------------------------------------------- #
# The size knob
# --------------------------------------------------------------------------- #
def test_the_chrome_is_smaller_than_the_baked_font_by_default(gui):
    assert gui.ui_scale == InternalGui.DEFAULT_UI_SCALE < 1.0
    assert gui.ROW_H < InternalGui.ROW_H
    assert gui.FONT_PT < InternalGui.FONT_PT


def test_the_knob_moves_text_and_rows_together(gui):
    small_row, small_font = gui.ROW_H, gui.FONT_PT
    gui.set_ui_scale(1.5)
    assert gui.ROW_H > small_row and gui.FONT_PT > small_font
    # Every length, not a chosen few: a menu row that did not follow leaves the
    # text of one entry sitting in the box of the next.
    assert gui.MENU_ITEM_H > InternalGui.MENU_ITEM_H
    assert gui.WINDOW_TITLE_H > InternalGui.WINDOW_TITLE_H


def test_the_layout_budget_follows_the_font():
    """`char_width` is what every box is sized in multiples of."""
    assert char_width(BASE_FONT_PT * 0.5) == pytest.approx(char_width(BASE_FONT_PT) * 0.5)


def test_the_scale_is_clamped_to_something_legible(gui):
    assert gui.set_ui_scale(0.01) == 0.5
    assert gui.set_ui_scale(99.0) == 2.0


def test_a_smaller_scale_gives_the_scene_more_room(gui):
    """The point of the knob: less chrome, more molecule."""
    gui.menubar = [("File", (MenuEntry("Quit", "quit"),))]
    gui.toolbar = [("Open", "open", "")]
    gui.set_ui_scale(1.0)
    gui.layout(WIDTH, HEIGHT)
    tall = gui.top_band_height()
    gui.set_ui_scale(0.7)
    gui.layout(WIDTH, HEIGHT)
    assert 0.0 < gui.top_band_height() < tall


# --------------------------------------------------------------------------- #
# Paging
# --------------------------------------------------------------------------- #
def _long_menu(gui, count=60):
    """Open a menu with more entries than the viewport can hold."""
    entries = tuple(MenuEntry(f"entry {i}", f"cmd {i}") for i in range(count))
    gui.layout(WIDTH, HEIGHT)
    gui._open_menu("Long:", "all", entries, 20.0, 20.0)
    return gui._menus[-1]


def test_a_menu_that_fits_has_one_page(gui):
    menu = _long_menu(gui, count=3)
    assert gui.menu_pages(menu) == (1, 1)
    assert menu.max_scroll == 0.0


def test_a_menu_too_tall_for_the_window_is_paged(gui):
    menu = _long_menu(gui)
    page, pages = gui.menu_pages(menu)
    assert pages > 1 and page == 1

    assert gui.page_menu(1) is True
    assert gui.menu_pages(menu)[0] == 2
    # A page is a screenful, not a row -- or the whole remainder when what is
    # left is less than a screenful, which is this menu.
    assert menu.scroll == pytest.approx(min(menu.page_px, menu.max_scroll))

    while gui.page_menu(1):
        pass
    assert gui.menu_pages(menu)[0] == gui.menu_pages(menu)[1]
    assert menu.scroll == menu.max_scroll


def test_the_last_page_does_not_scroll_past_the_end(gui):
    menu = _long_menu(gui)
    for _ in range(20):
        gui.page_menu(1)
    assert menu.scroll == menu.max_scroll
    assert gui.page_menu(1) is False


def test_the_arrows_in_the_title_turn_the_page(gui):
    """The press target, not just the API -- that is what a hand reaches for."""
    menu = _long_menu(gui)
    button = gui._menu_page_button(menu)
    assert button.w > 0 and menu.rect.contains(button.x + 1, button.y + 1)

    gui.mouse_press(button.x + button.w * 0.9, button.y + button.h * 0.5)
    assert gui.menu_pages(menu)[0] == 2, "the right half must go forward"

    gui.mouse_press(button.x + 1.0, button.y + button.h * 0.5)
    assert gui.menu_pages(menu)[0] == 1, "the left half must go back"


def test_paging_does_not_close_the_menu(gui):
    """A press inside a menu's own frame must not dismiss it."""
    menu = _long_menu(gui)
    button = gui._menu_page_button(menu)
    gui.mouse_press(button.x + button.w * 0.9, button.y + button.h * 0.5)
    assert gui._menus and gui._menus[-1] is menu
