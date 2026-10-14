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
