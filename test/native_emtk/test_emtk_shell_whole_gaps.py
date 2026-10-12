"""The emtk shell's last Qt main-window controls, used the way a person uses them.

Each test drives the shell with :class:`emtk.testing_realistic.RealisticDriver` (pointer travel, press and
release in different frames, OS drops that deliver no pointer moves) and checks what the shell then shows or
wrote, not what was called: a file dropped on the tool under the pointer, the ribbon's pin kept between
sessions, *Menu Switch*, the Log dock's filter / level / hide / RPC pause / history, *Screenshot*, the fit
export (*Current Fit*, *All Fits*) and import (*Load Fit*), and the console's help. The PNGs written to
``CHISURF_NATIVE_SCREENSHOTS`` are for review.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import pytest
from emtk.keys import KEY_RETURN
from emtk.testing_realistic import RealisticDriver

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from chisurf.emtk.main_app import EmtkShellApp  # noqa: E402

SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))
SIZE = (1440, 900)


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    """Preferences (the ribbon switch) go to a scratch folder, never the user's."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))


def _driver(shell) -> RealisticDriver:
    driver = RealisticDriver(shell, SIZE, real_painter=False)
    driver.frame(3)
    return driver


def _shot(driver, name: str) -> Path:
    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / f"emtk_shell_gaps_{name}.png"
    driver.screenshot(path)
    return path


def _wait(driver, predicate, what: str, timeout: float = 120.0) -> None:
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end, f"timed out waiting for {what}"
        driver.frame(1)
        time.sleep(0.02)
    driver.frame(2)


def _child_point(shell, plugin_id: str, key: str) -> tuple[float, float]:
    """The canvas point at the centre of a hosted plugin's control *key*."""
    hosted = shell.hosted[plugin_id]
    bx, by, _w, _h = hosted.box
    x, y, w, h = hosted.app.item_rects[key]
    return bx + x + w / 2.0, by + y + h / 2.0


def _form_point(rects: dict, key: str) -> tuple[float, float]:
    x, y, w, h = rects[key]
    return x + w / 2.0, y + h / 2.0


# ── a drop goes to the dock under the pointer ─────────────────────────────────


def test_a_file_dropped_on_a_plugin_dock_goes_to_the_dock_under_the_pointer(tmp_path):
    """Imaging QA: open Image Tools, pick *1. Intensity*, click elsewhere, drop a .ptu on it unclicked."""
    from chisurf.plugins.microscopy.imaging_emtk import pixel_testing as data

    source = Path(data.flim_ptu(tmp_path / "flim.ptu"))
    shell = EmtkShellApp(console_history=False, console_session_file=False)
    driver = _driver(shell)
    try:
        hosted = shell.open_plugin("imaging_tools")
        _wait(driver, lambda: hosted.build is None and hosted.box is not None, "Image Tools")
        driver.click(_child_point(shell, "imaging_tools", "entry:pixel_intensity"))
        driver.frame(3)
        # The keys go elsewhere now: the Tools filter has them, not the imaging dock.
        driver.click("tools.filter")
        assert shell._focus is None
        driver.drop_files([str(source)], _child_point(shell, "imaging_tools", "source"))
        step = hosted.app.children["pixel_intensity"]
        _wait(driver, lambda: step.model.filename == str(source), "the step to take the file")
        _shot(driver, "drop_on_imaging")
    finally:
        shell.close()


# ── the ribbon's pin ──────────────────────────────────────────────────────────


def test_the_ribbon_pin_keeps_the_fold_and_tab_and_unpinned_it_folds_after_a_pick():
    shell = EmtkShellApp(console_history=False, console_session_file=False)
    driver = _driver(shell)
    ribbon = shell.ribbon.ribbon
    try:
        assert "ribbon.pin" in shell.item_rects and ribbon.pinned
        driver.click("ribbon.tab.Structure")
        driver.click("ribbon.fold")
        saved = shell.export_settings()
        assert saved["ribbon"] == {"pinned": True, "folded": True, "current": "Structure"}
        driver.click("ribbon.pin")  # unpin: auto-fold
        assert not ribbon.pinned and ribbon.folded
        _shot(driver, "ribbon_unpinned")
        unpinned = shell.export_settings()
        assert unpinned["ribbon"] == {"pinned": False}
    finally:
        shell.close()
    # The next session: a pinned ribbon comes back as it was left.
    again = EmtkShellApp(console_history=False, console_session_file=False)
    try:
        again.restore_settings(saved)
        driver = _driver(again)
        assert again.ribbon.ribbon.folded and again.ribbon.ribbon.current == "Structure"
        again.restore_settings(unpinned)
        driver.frame(2)
        assert again.ribbon.ribbon.folded and not again.ribbon.ribbon.pinned
        driver.click("ribbon.tab.Spectroscopy")  # the band shows for one pick ...
        driver.frame(2)
        assert again.ribbon.ribbon.height() > again.ribbon.ribbon.tab_row_height()
        driver.click("ribbon.button.plugin.pch")  # ... and folds away after it
        driver.frame(2)
        assert "pch" in again.hosted
        assert again.ribbon.ribbon.height() == again.ribbon.ribbon.tab_row_height()
    finally:
        again.close()


# ── Menu Switch ───────────────────────────────────────────────────────────────


def test_menu_switch_hides_and_shows_the_ribbon_and_keeps_the_choice(tmp_path):
    import yaml

    shell = EmtkShellApp(console_history=False, console_session_file=False)
    driver = _driver(shell)
    try:
        assert shell.ribbon_enabled and "ribbon.tab.File" in shell.item_rects
        driver.click("ribbon.tab.File")
        driver.click("ribbon.button.plugin.menu_switch")
        driver.frame(2)
        assert not shell.ribbon_enabled
        assert not any(key.startswith("ribbon.tab.") for key in shell.item_rects), (
            "ribbon still drawn"
        )
        settings = yaml.safe_load((tmp_path / "settings" / "settings_chisurf.yaml").read_text())
        assert settings["gui"]["use_ribbon_interface"] is False
        _shot(driver, "menu_switch_menu_bar")
        # Without the ribbon, Menu Switch is in the menu bar's File menu.
        driver.click("menu.File")
        driver.frame(2)
        driver.click("Menu Switch")
        driver.frame(2)
        assert shell.ribbon_enabled and "ribbon.tab.File" in shell.item_rects
    finally:
        shell.close()


# ── the Log dock ──────────────────────────────────────────────────────────────


def test_the_log_dock_filters_hides_pauses_clears_and_goes_back_in_history():
    from chisurf.emtk.session import start_session
    from chisurf.server.session import SessionState

    session = start_session(state=SessionState())
    shell = EmtkShellApp(
        loader=lambda plugin_id: None, console_history=False, console_session_file=False
    )
    shell.data.adopt(session)
    driver = _driver(shell)
    log = shell.log
    try:
        shell.docks.undock("log", (300.0, 160.0, 1000.0, 560.0))
        shell.docks.focus("log")
        driver.frame(3)
        writer = logging.getLogger("chisurf.qa")
        writer.setLevel(logging.DEBUG)
        writer.info("Loaded 3 datasets")
        writer.warning("TAC range clipped")
        writer.debug("a debug detail")
        driver.frame(3)
        messages = [row["message"] for row in log.log_rows()]
        assert "TAC range clipped" in messages and "a debug detail" not in messages
        # Level: DEBUG shows the detail too.
        log.log_level = "DEBUG"
        driver.frame(2)
        assert "a debug detail" in [row["message"] for row in log.log_rows()]
        # Filter: typed into the field, the others are dimmed; with Hide they go.
        driver.click(_form_point(log.form.rects, "log_filter"))
        driver.type("TAC")
        driver.key(KEY_RETURN)  # Enter commits the field
        driver.frame(2)
        rows = log.log_rows()
        assert log.log_filter == "TAC"
        assert {row["message"] for row in rows if not row["muted"]} == {"TAC range clipped"}
        _shot(driver, "log_filter")
        driver.click(_form_point(log.form.rects, "log_hide"))
        driver.frame(2)
        assert [row["message"] for row in log.log_rows()] == ["TAC range clipped"]
        driver.click(_form_point(log.form.rects, "clear_log"))
        driver.frame(2)
        assert not log.log_rows()
        # RPC Monitor: calls are listed; Pause stops the recording, Clear empties it.
        driver.click(_form_point(log.form.rects, "log_tabs.rpc"))
        driver.frame(3)
        shell.project.channel.api.list_fits()
        driver.frame(2)
        assert any(row["target"] == "fit.list" for row in log.rpc_rows())
        _shot(driver, "log_rpc")
        driver.click(_form_point(log.form.rects, "rpc_paused"))
        driver.click(_form_point(log.form.rects, "clear_rpc"))
        shell.project.channel.api.list_fits()
        driver.frame(2)
        assert log.rpc_paused and not log.rpc_rows()
        # History: an edit is a step; a click on the step before goes back to it.
        driver.click(_form_point(log.form.rects, "log_tabs.history"))
        driver.frame(3)
        _wait(driver, lambda: shell.project.history_ready, "the history baseline")
        from chisurf.core.experiments.fcs.demo import DEMO, make_demo

        data = shell.data
        data.read.experiment, data.read.setup = DEMO["experiment"], DEMO["reader"]
        data.read.experiment_changed(DEMO["experiment"])
        data.read.setup = DEMO["reader"]
        data.read.path = str(make_demo())
        data.read.load()
        _wait(driver, lambda: len(log.history_rows()) >= 1 and not shell.project.busy, "a step")
        assert log.history_rows()[-1]["current"] == "▶"
        _shot(driver, "log_history")
    finally:
        shell.close()
        session.close()


# ── Screenshot ────────────────────────────────────────────────────────────────


def test_screenshot_copies_the_window_to_the_clipboard():
    from emtk.clipboard import last_copied_image

    shell = EmtkShellApp(console_history=False, console_session_file=False)
    driver = _driver(shell)
    try:
        before = last_copied_image()[0]
        driver.click("ribbon.tab.Main")
        driver.click("ribbon.button.action.screenshot")
        driver.frame(2)
        count, png = last_copied_image()
        assert count == before + 1 and png[:8] == b"\x89PNG\r\n\x1a\n"
        assert shell.status in (
            "Screenshot copied to clipboard.",
            "Screenshot failed: the window could not be grabbed.",
        )
        _shot(driver, "main_tab")
    finally:
        shell.close()


# ── fit export and import ─────────────────────────────────────────────────────


@pytest.fixture
def fitted():
    """A shell with its own session, the FCS demo read and one fit made, by its controls."""
    import test_emtk_shell_fits as fits_test

    from chisurf.emtk.fit_docks import READ_KEY
    from chisurf.emtk.session import start_session
    from chisurf.server.session import SessionState

    session = start_session(state=SessionState())
    shell = EmtkShellApp(
        {}, loader=lambda plugin_id: None, console_history=False, console_session_file=False
    )
    shell.data.adopt(session)
    driver = _driver(shell)
    shell.docks.focus(READ_KEY)
    driver.frame(2)
    driver.click("read.use_demo")
    driver.click("read.load")
    _wait(
        driver,
        lambda: (
            fits_test._idle(shell)
            and any(r["name"] == "fcs_demo" for r in shell.data.datasets.datasets)
        ),
        "the demo",
    )
    fits_test._add_fit(driver, shell, shell.data.datasets.model)
    yield shell, driver, session
    shell.close()
    session.close()


def _menu(driver, shell, caption: str) -> None:
    driver.click("menu.File")
    driver.frame(2)
    driver.click(caption)
    driver.frame(2)


def test_current_fit_all_fits_and_load_fit_round_trip(fitted, tmp_path):
    shell, driver, session = fitted
    project = shell.project
    state = session.server.state
    # Current Fit: a folder dialog; the fit's curves, its fit document and the report land there.
    _menu(driver, shell, "Current Fit")
    assert project.file_dialog is not None and project.file_dialog.mode == "folder"
    _shot(driver, "save_fit_dialog")
    out = tmp_path / "one"
    out.mkdir()
    project.choose_file(out)
    _wait(driver, lambda: not project.busy and (out / "fcs_demo.docx").is_file(), "the export")
    written = {path.name for path in out.iterdir()}
    assert {"fcs_demo.docx", "fcs_demo.fit.cs.pto"} <= written
    assert any(name.endswith("_model.csv") for name in written)
    import docx

    report = docx.Document(str(out / "fcs_demo.docx"))
    assert len(report.inline_shapes) == 2, "the fit window and the model editor, drawn by emtk"
    assert report.tables[0].rows[-1].cells[0].text == "Chi2r"
    # All Fits: a folder per fit and the stacked report; a second time, existing folders are asked about.
    _menu(driver, shell, "All Fits")
    every = tmp_path / "all"
    every.mkdir()
    project.choose_file(every)
    _wait(driver, lambda: not project.busy and (every / "all_fits.docx").is_file(), "all fits")
    assert (every / "fcs_demo" / "fcs_demo.fit.cs.pto").is_file()
    _menu(driver, shell, "All Fits")
    project.choose_file(every)
    _wait(driver, lambda: not project.busy and project.dialogs.modal, "the overwrite question")
    _shot(driver, "all_fits_exists")
    driver.click("Skip")
    _wait(driver, lambda: not project.busy, "the skip")
    assert "skipped" in project.status
    # Load Fit: the fit, closed meanwhile, comes back from its document with its data.
    _menu(driver, shell, "Close all fits")
    _wait(driver, lambda: not state.fits and not shell.data.datasets.fits, "the fits to close")
    fits_before = len(state.fits)
    _menu(driver, shell, "Load Fit")
    project.choose_file(out / "fcs_demo.fit.cs.pto")
    _wait(
        driver,
        lambda: not project.busy and len(shell.data.datasets.fits) == fits_before + 1,
        "the loaded fit",
    )
    assert len(state.fits) == fits_before + 1
    _shot(driver, "load_fit")
    # Loading the same document again is refused with its reason, not a second copy.
    _menu(driver, shell, "Load Fit")
    project.choose_file(out / "fcs_demo.fit.cs.pto")
    _wait(driver, lambda: not project.busy and project.dialogs.modal, "the refusal")
    assert len(state.fits) == fits_before + 1


def test_the_qt_windows_save_fit_macro_writes_the_same_files_without_qt(fitted, tmp_path):
    """``chisurf.macros.core_fit.save_fit`` (the Qt window's *Current Fit*) draws its report with emtk."""
    from types import SimpleNamespace

    import docx

    from chisurf.macros import core_fit

    from qtpy import QtWidgets

    _shell, _driver_, session = fitted
    fit = session.server.state.fits[-1]
    # Any earlier test in the process may have made the application; the export must not make one.
    app_before = QtWidgets.QApplication.instance()
    core_fit.save_fit(str(tmp_path), fit_window=SimpleNamespace(fit=fit))
    report = docx.Document(str(tmp_path / "fcs_demo.docx"))
    assert len(report.inline_shapes) == 2
    assert (tmp_path / "fcs_demo.fit.cs.pto").is_file()
    assert QtWidgets.QApplication.instance() is app_before, "the export made a Qt application"


def test_current_fit_has_the_qt_shortcut(fitted):
    from chisurf.emtk.main_app import parse_shortcut

    shell, _driver_, _session = fitted
    assert shell.shortcuts()[parse_shortcut("Ctrl+Alt+S")].key == "save_fit"


# ── the console's help ────────────────────────────────────────────────────────


def test_the_console_help_button_opens_its_help():
    shell = EmtkShellApp(console_history=False, console_session_file=False)
    driver = _driver(shell)
    try:
        shell.docks.focus("console")
        driver.frame(2)
        driver.click(_form_point(shell.console.item_rects, "help"))
        driver.frame(3)
        assert shell.console._help.open
        _shot(driver, "console_help")
    finally:
        shell.close()
