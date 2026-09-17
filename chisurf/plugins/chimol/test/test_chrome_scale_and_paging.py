"""Two things the chrome owes a small window: a size knob, and pages.

The chrome is drawn over the molecule, so its size is a setting rather than a
constant. Scaling the font alone would not do: seventeen-pixel rows around
eleven-pixel text is not smaller chrome, only emptier chrome, so one knob moves
both.

It draws at **1.0 by default** — the size the glyph atlas was baked at. It was
0.85, to leave more room for the molecule, and that cost sharpness everywhere:
the atlas is baked once, so any other scale resamples every glyph. Shrinking it
is still one drag of the status-bar slider, which snaps to the scales that stay
crisp.

Paging is the other half. A menu taller than the viewport already scrolled, and
scrolling is a wheel — a menu whose remainder can only be reached by a wheel is
a menu whose remainder most people never find. Its title now says which page it
is on, and the arrows beside the title turn it.
"""

from __future__ import annotations

import pytest
from chimol.ui.gui import BASE_FONT_PT, GuiRow, InternalGui, char_width
from chimol.ui.menus.objects import MenuEntry

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
def test_the_chrome_draws_at_the_baked_size_by_default(gui):
    """The default is 1.0, which is the size the glyph atlas was baked at.

    It was 0.85, chosen to give the molecule more room, and it cost sharpness
    everywhere to do it: the atlas is baked once, so any other scale resamples
    every glyph. "The native window looks pixelated" was that, and nothing
    else -- the sampler is already linear and the atlas is 4x supersampled.

    Making a *smaller* chrome is still one drag of the status-bar slider, and
    the ladder it snaps to keeps those sizes crisp too.
    """
    assert InternalGui.DEFAULT_UI_SCALE == 1.0
    assert gui.ui_scale == 1.0
    assert gui.ROW_H == InternalGui.ROW_H
    assert gui.FONT_PT == InternalGui.FONT_PT


def test_the_slider_only_stops_where_glyphs_stay_crisp():
    """Every snap target puts a character's advance on a whole pixel.

    The baked advance is 7 px, so a whole-pixel advance means the scale is a
    multiple of 1/7. Between those the text goes soft, which is the whole
    reason the slider snaps rather than moving freely.
    """
    steps = InternalGui.UI_SCALE_STEPS
    assert steps == tuple(sorted(steps)), "the ladder must be ordered"
    assert 1.0 in steps and 2.0 in steps
    for step in steps:
        assert InternalGui.UI_SCALE_MIN <= step <= InternalGui.UI_SCALE_MAX
        assert abs(round(7.0 * step) - 7.0 * step) < 0.02, (
            f"scale {step} draws the advance on a fractional pixel"
        )
    # Anything dropped between two rungs lands on the nearer one.
    assert InternalGui.snap_ui_scale(0.85) in steps
    assert InternalGui.snap_ui_scale(3.0) == 2.0
    assert InternalGui.snap_ui_scale(0.0) == steps[0]


def test_the_startup_guess_keeps_the_effective_scale_whole():
    """On a HiDPI display the chrome is already drawn at the pixel ratio.

    So what has to be a whole number is ``ratio * ui_scale``, not the scale --
    which is why a clean 2x display wants 1.0, the same as an ordinary one, and
    only a fractional ratio needs correcting.
    """
    assert InternalGui.suggest_ui_scale(1.0) == 1.0
    assert InternalGui.suggest_ui_scale(2.0) == 1.0
    fractional = InternalGui.suggest_ui_scale(1.5)
    assert fractional in InternalGui.UI_SCALE_STEPS
    assert abs(round(1.5 * fractional) - 1.5 * fractional) < 0.12


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
