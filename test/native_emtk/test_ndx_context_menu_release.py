"""ndX's map context menu in the emtk shell: after it closes, by any path, the next click lands.

The report (2026-10-12): right-click ndX's 2-D map in the shell, choose an item, and no click landed
anywhere after; the menu stayed drawn. Two causes, both fixed in emtk:

* the menu's "Send selection to ▸" row is a submenu (``emtk.widgets.menus.Menu``), which had no
  ``tooltip``: the moment the pointer crossed it the popup raised in every frame -- drawn, never
  closed, holding every click of the ndX frame;
* a press outside the hosted ndX (on the ribbon, another dock) never reached ndX, so its menu stayed
  up and the first click back into ndX only closed it. The shell now tells every other hosted child
  (``emtk.overlays.dismiss``).

Each case drives the shell with :class:`emtk.testing_realistic.RealisticDriver` -- pointer travel,
press and release in different frames -- opens the menu with a right-click on the map, closes it one
way, then clicks a control elsewhere and checks it registered (``assert_input_released``).
"""

from __future__ import annotations

import time

import pytest
from emtk.events import RIGHT_BUTTON
from emtk.keys import KEY_ESCAPE
from emtk.overlays import open_panels
from emtk.testing_realistic import RealisticDriver, assert_input_released

from chisurf.emtk.main_app import EmtkShellApp

SIZE = (1440, 900)


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    """Preferences and the example table go to a scratch folder, and copies stay off the user's clipboard."""
    from emtk import clipboard

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    copied = []
    monkeypatch.setattr(clipboard, "_hook", copied.append)


@pytest.fixture(scope="module")
def session():
    """The shell with ndX docked and its example table open, as after *Load example*."""
    import os
    import tempfile

    os.environ.setdefault("CHISURF_SETTINGS_DIR", tempfile.mkdtemp(prefix="ndx-menu-"))
    shell = EmtkShellApp(console_history=False, console_session_file=False)
    driver = RealisticDriver(shell, SIZE, real_painter=False)
    driver.frame(3)
    hosted = shell.open_plugin("ndxplorer")
    _wait(driver, lambda: hosted.build is None and hosted.box is not None, "ndX")
    app = hosted.app
    guide = next(f for f in app.features if getattr(f, "name", "") == "chisurf_guide")
    guide.load_example()
    _wait(driver, lambda: app.model.histograms is not None, "the example's map")
    used = []
    for form in app.forms.values():
        previous = form.on_used

        def record(key, _previous=previous):
            used.append(key)
            if _previous is not None:
                _previous(key)

        form.on_used = record
    yield shell, driver, hosted, used
    shell.close()


def _wait(driver, predicate, what, timeout=120.0):
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end, f"timed out waiting for {what}"
        driver.frame(1)
        time.sleep(0.02)
    driver.frame(2)


def _child(hosted, rect):
    bx, by, _w, _h = hosted.box
    x, y, w, h = rect
    return bx + x + w / 2.0, by + y + h / 2.0


def _map_point(hosted):
    bx, by, _w, _h = hosted.box
    x, y, w, h = hosted.app.plots.rects["map"]
    return bx + x + w * 0.45, by + y + h * 0.6


def _row(hosted, panel, part):
    index = next(i for i, e in enumerate(panel.entries) if e is not None and part in e.label)
    return _child(hosted, panel.row_rect(index))


def _open(driver, hosted):
    driver.click(_map_point(hosted), button=RIGHT_BUTTON)
    driver.frame(2)
    panels = open_panels(hosted.app.storage)
    assert panels, "the right-click on the map opened no menu"
    return panels[0]


def _escape(driver):
    driver.press(KEY_ESCAPE)
    driver.frame(2)


CLOSE = {
    "escape": lambda d, h, p: _escape(d),
    "click_outside_in_ndx": lambda d, h, p: d.click(
        _child(h, h.app.forms["plot_corner"].rects["count_total"])
    ),
    "click_on_another_dock": lambda d, h, p: d.click("tools.filter"),
    "click_on_the_ribbon": lambda d, h, p: d.click("ribbon.tab.Main"),
    "right_click_again": lambda d, h, p: (
        d.click(_map_point(h), button=RIGHT_BUTTON),
        d.frame(2),
        _escape(d),
    ),
    "wheel_over_the_map": lambda d, h, p: (d.wheel(-1, at=_map_point(h)), d.frame(2), _escape(d)),
    "wheel_over_the_menu": lambda d, h, p: (
        d.wheel(-1, at=_row(h, p, "Copy 2D")),
        d.frame(2),
        _escape(d),
    ),
    "pick_copy_2d": lambda d, h, p: d.click(_row(h, p, "Copy 2D")),
    "pick_copy_1d": lambda d, h, p: d.click(_row(h, p, "Copy 1D")),
    "pick_fit_gate": lambda d, h, p: d.click(_row(h, p, "Fit gate")),
    # The rows that say why they are disabled: inert to a click, and the submenu row is where the
    # menu fell over (it had no tooltip). Hover them, click them, then Escape.
    "disabled_napari_then_escape": lambda d, h, p: (d.click(_row(h, p, "Napari")), _escape(d)),
    "hover_send_then_escape": lambda d, h, p: (
        d.hover(_row(h, p, "Send selection")),
        d.frame(3),
        _escape(d),
    ),
    "hover_send_then_pick_fit_gate": lambda d, h, p: (
        d.hover(_row(h, p, "Send selection")),
        d.frame(3),
        d.click(_row(h, p, "Fit gate")),
    ),
}


@pytest.mark.parametrize("path", sorted(CLOSE))
def test_after_the_map_menu_closes_the_next_click_lands(session, path):
    shell, driver, hosted, used = session
    panel = _open(driver, hosted)
    CLOSE[path](driver, hosted, panel)
    driver.frame(2)
    assert not open_panels(hosted.app.storage), f"{path}: the menu is still up"
    # A control inside ndX: the header's log-scale toggle (clicked twice, so the state is kept).
    log_counts = _child(hosted, hosted.app.forms["plot_header"].rects["log_counts"])
    used.clear()
    assert_input_released(
        driver,
        log_counts,
        lambda: "log_counts" in used,
        apps=(shell, hosted.app),
        label=f"{path}, ndX control",
    )
    driver.click(log_counts)
    # And the shell's own chrome.
    target = "Structure" if shell.ribbon.ribbon.current != "Structure" else "Spectroscopy"
    assert_input_released(
        driver,
        f"ribbon.tab.{target}",
        lambda: shell.ribbon.ribbon.current == target,
        apps=(shell, hosted.app),
        label=f"{path}, ribbon",
    )


def test_the_long_disabled_row_stays_inside_the_window_and_says_why_on_hover(session):
    shell, driver, hosted, _used = session
    panel = _open(driver, hosted)
    try:
        bx, by, bw, bh = hosted.box
        x, y, w, h = panel.panel_rect
        assert bx + x >= bx - 0.5 and bx + x + w <= bx + bw + 0.5, "the menu runs out of ndX"
        assert w < 0.6 * SIZE[0], f"one long row made the menu {w:.0f} px wide"
        driver.hover(_row(hosted, panel, "Send selection"))
        driver.frame(2)
        assert panel.tooltip and "burst provenance" in panel.tooltip
    finally:
        _escape(driver)
