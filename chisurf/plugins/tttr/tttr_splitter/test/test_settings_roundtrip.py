"""Split/Convert keeps its options between sessions (it is a tool of its own, not a hub panel)."""

import json

from chisurf.plugins.tttr.tttr_splitter.gui.controller import create_app


def test_options_roundtrip():
    """Photon count and macro-time reset survive an export/restore cycle."""
    app = create_app()
    restored = create_app()
    try:
        app.tool._model.photons_per_file_k = 123
        app.tool._model.reset_macro_times = False
        restored.restore_settings(json.loads(json.dumps(app.export_settings())))
        assert restored.tool._model.photons_per_file_k == 123
        assert restored.tool._model.reset_macro_times is False
    finally:
        app.close()
        restored.close()


def test_dropped_file_goes_to_the_input(monkeypatch, tmp_path):
    """A file dropped on the window is loaded as the input."""
    app = create_app()
    try:
        seen = []
        monkeypatch.setattr(app.tool, "load_input", seen.append)
        assert app.files_dropped([tmp_path / "x.ptu"]) is True
        assert seen == [str(tmp_path / "x.ptu")]
        assert app.files_dropped([]) is False
    finally:
        app.close()
