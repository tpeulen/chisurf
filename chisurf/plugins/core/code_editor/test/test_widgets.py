"""The code editor window (the emtk app), ported from the retired Qt ``CodeEditor`` widget tests.

The same behaviours, on ``gui/editor_app.py`` through its model and the emtk ``Driver`` (only
drawn text, clicks and keys reach the window).
"""

from __future__ import annotations

import pathlib

from emtk.testing import Driver

import chisurf as cs
from chisurf.plugins.core.code_editor.gui.editor_app import CodeEditorApp, make_editor_app

SOURCE = "class Alpha:\n    def beta(self):\n        pass\n\ndef gamma():\n    pass\n"


class TestCodeEditor:
    """The shared multi-document editor."""

    def test_creation(self):
        """The editor window can be created and draws its menu bar and an editor tab."""
        app = make_editor_app()
        try:
            assert isinstance(app, CodeEditorApp)
            drawn = [t[5] for t in Driver(app, (1200, 800)).frame(3).texts]
            assert "File" in drawn and "Settings" in drawn
        finally:
            app.close()

    def test_creation_with_filename(self, tmp_path):
        """A file given at start is opened in its own tab, with its language."""
        path = tmp_path / "test.py"
        path.write_text("x = 1\n", encoding="utf-8")
        app = make_editor_app(str(tmp_path))
        try:
            doc = app.model.open_file(path)
            assert doc is not None and doc.name == "test.py"
            assert doc.editor.language_name.lower() == "python"
        finally:
            app.close()

    def test_creation_uses_global_lsp_setting(self, monkeypatch):
        """Without preferences of its own the editor follows ``gui.editor.enable_lsp``."""
        from chisurf.plugins.core.code_editor.gui import editor_app

        started = []
        monkeypatch.setattr(editor_app.EditorModel, "start_lsp", lambda self, *a: started.append(1))
        monkeypatch.setattr(cs.core.settings, "gui", {"editor": {"enable_lsp": False}})
        app = make_editor_app()
        try:
            assert app.model.enable_lsp is False and not started
        finally:
            app.close()
        monkeypatch.setattr(cs.core.settings, "gui", {"editor": {"enable_lsp": True}})
        app = make_editor_app()
        try:
            assert started == [1]
        finally:
            app.close()

    def test_the_window_has_a_menu_bar_status_line_toolbar_and_settings_toggles(self):
        """The window is the full editor: menu bar, toolbar, status line, Settings toggles."""
        app = make_editor_app()
        try:
            driver = Driver(app, (1200, 800))
            drawn = [t[5] for t in driver.frame(3).texts]
            assert any("Ln " in text and "Col " in text for text in drawn)  # the status line
            assert "📁 Folder" in drawn and "🧹 Lint" in drawn  # the toolbar
            driver.click("Settings")
            menu = [t[5] for t in driver.frame(2).texts]
            assert "Show Line Numbers" in menu and "Enable Python LSP" in menu
        finally:
            app.close()

    def test_the_editor_extracts_symbols_and_jumps(self, tmp_path):
        """The active Python document's symbols are listed and a jump lands on the line."""
        app = make_editor_app(str(tmp_path))
        try:
            app.model.new_document("sample.py", SOURCE)
            symbols = app.model.document_symbols()
            assert [s.display_name for s in symbols] == ["Alpha", "Alpha.beta", "gamma"]
            app.model.goto_line(symbols[-1].line, symbols[-1].column)
            assert app.model.active_doc.editor.cursors.main.end.line + 1 == 5
        finally:
            app.close()

    def test_the_status_tracks_dirty_line_column_and_file(self, tmp_path):
        """The status line names the file, the caret's line and column, and the modified state."""
        path = tmp_path / "sample.py"
        path.write_text("a = 1\nb = 2\n", encoding="utf-8")
        app = make_editor_app(str(tmp_path))
        try:
            driver = Driver(app, (1400, 800))
            app.model.open_file(path)
            driver.frame(2)
            doc = app.model.active_doc
            doc.editor.text = "a = 1\nb = 2\nc"
            app.model.goto_line(2, 1)
            status = next(t[5] for t in driver.frame(2).texts if "Ln " in t[5])
            assert str(path)[-20:] in status and "Ln 2, Col 2" in status and "Modified" in status
            assert doc.is_modified
        finally:
            app.close()

    def test_the_editor_opens_files_and_a_symbol_click_jumps(self, tmp_path):
        """Open a file, then click its function in the Symbols dock: the caret is on its line."""
        path = tmp_path / "sample.py"
        path.write_text(SOURCE, encoding="utf-8")
        app = make_editor_app(str(tmp_path))
        try:
            driver = Driver(app, (1400, 860))
            app.model.open_file(path, line=1)
            assert app.model.active_doc.path == str(path.resolve())
            driver.frame(2)
            driver.click("Symbols")
            driver.click("gamma")
            assert app.model.active_doc.editor.cursors.main.end.line + 1 == 5
        finally:
            app.close()

    def test_a_click_in_the_project_tree_opens_the_file(self, tmp_path):
        """The Project dock opens a clicked file."""
        (tmp_path / "clicked.py").write_text("x = 1\n", encoding="utf-8")
        app = make_editor_app(str(tmp_path))
        try:
            driver = Driver(app, (1400, 860))
            driver.frame(3)
            driver.click("clicked.py")
            assert app.model.active_doc.name == "clicked.py"
            assert pathlib.Path(app.model.active_doc.path) == (tmp_path / "clicked.py").resolve()
        finally:
            app.close()

    def test_the_lsp_client_dispatches_a_response_to_its_callback(self, tmp_path):
        """The language-server client hands a JSON-RPC response to the request's callback."""
        from chisurf.plugins.core.code_editor.gui.native_lsp import NativeLspClient

        client = NativeLspClient(tmp_path, ["pylsp"])
        client._send = lambda payload: None  # no process: the request is only recorded
        results = []
        request_id = client.request("fake/method", {}, results.append)
        client._handle_message({"jsonrpc": "2.0", "id": request_id, "result": {"ok": True}})
        assert results == [{"ok": True}]
