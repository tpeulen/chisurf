"""Gaps the final shell parity pass found (okf/plugins/emtk-ports/final-parity/shell).

The Start document shows the machine, the versions and the process's use, as the Qt workspace
did: the Qt main window painted a watermark over its empty workspace (OS, RAM, Python, ChiSurf,
numpy, tttrlib, the thread environment, the log level, CPU and memory).
"""

from __future__ import annotations

import platform

from emtk.testing import Driver

from chisurf.core.system_info import system_info_lines
from chisurf.emtk.main_app import EmtkShellApp


def test_system_info_lines_name_the_machine_and_the_versions():
    lines = system_info_lines()
    assert lines[0].startswith("OS: ")
    assert f"Python: {platform.python_version()}" in lines
    assert any(line.startswith("ChiSurf: ") for line in lines)
    assert lines[-1].startswith("Log level: ")


def test_the_start_document_draws_them():
    shell = EmtkShellApp({}, loader=lambda plugin_id: None, console_history=False,
                         console_session_file=False)
    try:
        driver = Driver(shell, (1440, 900))
        driver.frame(3)
        strings = set(driver.painter.strings)
        assert "System" in strings
        assert f"Python: {platform.python_version()}" in strings
        assert "system_info" in shell.item_rects
    finally:
        shell.close()



def test_the_pda_editor_draws_its_binning_labels_and_light_path_note_readably():
    """The PDA editor drew ``x<sub>min</sub>`` with its tags, and typeset the light-path note
    (a sentence with ``&gamma;``) as one formula squeezed into the dock width, unreadable."""
    import types

    from emtk import im
    from emtk.app import ImApp

    from chisurf.emtk.model_editor import ModelEditor

    note = (
        "Not applied. Fills leakage, direct excitation and &gamma; from a simulated optical "
        "setup instead of leaving them as guesses."
    )
    editor = ModelEditor(types.SimpleNamespace(busy=False))
    editor.set_editor(
        "fit",
        {
            "sections": [
                {
                    "type": "custom",
                    "key": "scalar_table",
                    "id": "binning",
                    "options": {"title": "Binning"},
                    "data": {"rows": [{"attr": "x_min", "label": "x<sub>min</sub>", "value": 0}]},
                },
                {"type": "info", "text": note},
            ]
        },
    )

    def gui():
        im.begin("editor", (0, 0, 420, 400))
        editor.draw()
        im.end()

    driver = Driver(ImApp(gui), size=(420, 400))
    driver.frame(3)
    strings = [str(s) for s in driver.painter.strings]
    assert not any("<sub>" in s for s in strings), strings
    assert "min" in strings, "the binning row's label is drawn (as x with a subscript min)"
    assert any("γ" in s for s in strings), "the note is drawn as wrapped text with its γ"


def _wide_tool_shell(state=None, size=(1440, 900)):
    from emtk import im
    from emtk.app import ImApp

    from chisurf.emtk.plugins import manifests

    def make(plugin_id):
        app = ImApp(lambda: im.text_unformatted(plugin_id))
        app.window_size = (1200, 800) if plugin_id == "setup" else (300, 400)
        return app

    catalog = {k: manifests()[k] for k in ("setup", "about")}
    shell = EmtkShellApp(catalog, loader=make, console_history=False, console_session_file=False)
    if state is not None:
        shell.docks.restore(state)
    return shell, Driver(shell, size)


def _open(shell, driver, plugin_id):
    import time

    hosted = shell.open_plugin(plugin_id)
    end = time.monotonic() + 30
    while (hosted.app is None or not hosted.extra.get("placed")) and time.monotonic() < end:
        driver.frame(1)
        time.sleep(0.02)
    driver.frame(3)
    return hosted


def test_a_tool_wider_than_its_dock_floats_at_its_declared_size():
    """Settings declares 1200 x 800; docked right of the workspace (~390 px) it clipped its own
    Save button (final shell parity pass). It opens floating at its declared size; a narrow tool
    (About, 300 px) still docks; tile / cascade of the workspace are untouched."""
    shell, driver = _wide_tool_shell()
    try:
        driver.frame(2)
        wide = _open(shell, driver, "setup")
        assert shell.docks.region_of(wide.key) is None, "the wide tool floats"
        frame = shell.docks.window(wide.key).frame or shell.docks.window(wide.key).box
        room = shell.docks.box[3] - 40.0  # the declared 800 px, as far as the window has room
        assert abs(frame[2] - 1200.0) < 2.0 and abs(frame[3] - min(800.0, room)) < 2.0, frame
        narrow = _open(shell, driver, "about")
        assert shell.docks.region_of(narrow.key) == "right", "a narrow tool docks"
    finally:
        shell.close()


def test_a_wide_tool_the_user_docked_stays_docked():
    """The choice is remembered: docked by hand, closed and reopened (this run or the next,
    through the saved layout), the wide tool goes back to its dock."""
    shell, driver = _wide_tool_shell()
    try:
        driver.frame(2)
        hosted = _open(shell, driver, "setup")
        shell.docks.dock(hosted.key, "right")
        driver.frame(2)
        shell.close_plugin("setup")
        again = _open(shell, driver, "setup")
        assert shell.docks.region_of(again.key) == "right"
        state = shell.docks.state()
    finally:
        shell.close()
    shell, driver = _wide_tool_shell(state)
    try:
        driver.frame(2)
        hosted = _open(shell, driver, "setup")
        assert shell.docks.region_of(hosted.key) == "right", "the saved layout keeps it docked"
    finally:
        shell.close()
