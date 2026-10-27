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


def test_the_input_comes_from_the_workspace_not_a_drop(monkeypatch, tmp_path):
    """The split input is handed over from the Datasets workspace (``receive_split``); the window
    takes no file drops of its own -- the shell's drop adds files to the workspace."""
    from chisurf.plugins.tttr.tttr_splitter.gui.controller import receive_split

    app = create_app()
    try:
        target = tmp_path / "x.ptu"
        target.write_bytes(b"")
        seen = []
        monkeypatch.setattr(
            app.tool, "load_input", lambda address, source="": seen.append((address, source))
        )
        receive_split(app, {"file": str(target), "datasets": ["uid-1"]})
        assert seen == [(str(target), "uid-1")]
        assert not hasattr(app, "files_dropped")
    finally:
        app.close()
