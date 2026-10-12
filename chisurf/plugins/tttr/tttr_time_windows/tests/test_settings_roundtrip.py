"""Time-window options survive a session (the tool owns its preferences, not a hub)."""

import json

from chisurf.plugins.tttr.tttr_time_windows.gui.controller import create_app


def test_window_length_and_output_folder_roundtrip():
    """Window length and output folder survive an export/restore cycle."""
    app = create_app()
    restored = create_app()
    try:
        app.tool.time_window_ms = 37.5
        app.tool.output_dir_text = "/private/tmp/windows"
        restored.restore_settings(json.loads(json.dumps(app.export_settings())))
        assert restored.tool.time_window_ms == 37.5
        assert restored.tool.output_dir_text == "/private/tmp/windows"
    finally:
        app.close()
        restored.close()
