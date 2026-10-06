"""The LLTF window's output pane, entry point and configuration editor.

These assertions were written against the Qt ``LLTFGUIWizard`` (its
``ProcessOutputWidget`` and ``LLTFSettingsEditor``); the wizard is retired and
they hold on the emtk app that replaced it.
"""

import json
from pathlib import Path

from emtk.testing import RecordingPainter

from chisurf.plugins.fluorescence_decay.lltf.gui.app import LLTFApp

HERE = Path(__file__).parent
CONFIG = str((HERE.parent / "example" / "config.yml").resolve())


def _strings(app, size=(1200, 800)):
    painter = None
    for _ in range(2):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return set(painter.strings)


def test_process_output_pane():
    """No process before a fit; the output tab carries Clear, the controls Stop."""
    app = LLTFApp()
    try:
        assert app.model.process is None
        assert app.model.running is False
        assert app.model.output == []
        app.pending_tab = "Analysis Output"
        drawn = " ".join(_strings(app))
        assert "Clear output" in drawn
        assert "Stop" in drawn
    finally:
        app.close()


def test_the_plugin_opens_the_emtk_window():
    """The manifest launches the emtk app; no Qt wizard is declared any more."""
    manifest = json.loads((HERE.parent / "manifest.json").read_text())
    entry = manifest["entrypoints"]
    assert "gui" not in entry
    module, attr = entry["emtk"].split(":")
    assert (module, attr) == ("chisurf.plugins.fluorescence_decay.lltf.gui.app", "make_app")


def test_edit_config_opens_the_editor_on_the_file():
    """*Edit…* is the GUI route to the analysis settings (RF-877).

    It used to call a name that did not exist and abort the process; the editor
    must open on the configuration file's text.
    """
    app = LLTFApp()
    try:
        app.model.config_file = CONFIG
        app.edit_config()
        assert app.config_open
        assert app.model.config_text == Path(CONFIG).read_text()
    finally:
        app.close()
