from pathlib import Path

from chisurf.plugins.core.style_manager.gui.app import StyleManagerModel


def model(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    (package / "dark.css").write_text("window { background-color: #112233; color: #eeeeee; }")
    return StyleManagerModel(tmp_path / "user", package)


def test_edit_save_apply_and_reset(tmp_path):
    m = model(tmp_path)
    assert m.current_file.name == "dark.css"
    m.editor.set_text("button { background-color: #abcdef; }")
    applied = []
    m.apply_callback = lambda style: applied.append(style)
    assert m.apply()
    assert applied
    from emtk import im

    assert applied[-1].color(im.Col.BUTTON) == (171, 205, 239, 255)
    assert m.current_file.read_text() == m.editor.text
    (m.styles_dir / "keep.txt").write_text("keep")
    assert m.reset(discard=True)
    assert "#112233" in m.editor.text
    assert (m.styles_dir / "keep.txt").read_text() == "keep"


def test_canceled_or_failed_operations_preserve_buffer(tmp_path, monkeypatch):
    m = model(tmp_path)
    original = m.current_file
    m.editor.set_text("unsaved")
    assert not m.load(original)
    assert not m.reset()
    destination = tmp_path / "existing.css"
    destination.write_text("external")
    assert not m.save(destination)
    assert destination.read_text() == "external"
    assert m.current_file == original

    def fail(*args, **kwargs):
        raise PermissionError("read-only")

    monkeypatch.setattr(Path, "write_text", fail)
    assert not m.save()
    assert "read-only" in m.status
    assert m.modified


def test_new_never_overwrites_and_conversion_reports_unsupported(tmp_path):
    m = model(tmp_path)
    original = m.current_file.read_text()
    assert not m.new("../outside")
    assert not m.new("dark")
    assert m.current_file.read_text() == original
    assert m.new("custom")
    assert m.current_file.name == "custom.css"


def test_native_controls_cancel_and_apply_callback(tmp_path, monkeypatch):
    import types

    from emtk import im
    from emtk.testing import RecordingPainter

    from chisurf.plugins.core.style_manager.gui.app import StyleManagerApp

    m = model(tmp_path)
    app = StyleManagerApp(m)
    tips = []
    monkeypatch.setattr(im, "set_item_tooltip", lambda tip: tips.append(tip))
    monkeypatch.setattr(im, "button", lambda label, *args, **kwargs: label == "Apply")
    with im.frame(RecordingPainter(), (0, 0, 800, 600)):
        app._render()
    assert app.style is m.applied_style
    assert any("replacement" in tip for tip in tips)
    assert any("clipboard" in tip for tip in tips)
    m.editor.set_text("unsaved")
    app.file_dialog = types.SimpleNamespace(overwrite_confirmed=False)
    app.accept_dialog(False)
    assert app.file_dialog is None
    assert m.modified
    app.request_load(m.current_file)
    assert app.pending[0] == "load"
    monkeypatch.setattr(im, "button", lambda label, *args, **kwargs: label == "Cancel change")
    with im.frame(RecordingPainter(), (0, 0, 800, 600)):
        app._draw_dialogs()
    assert app.pending is None
    assert m.editor.text == "unsaved"
    app.close()
    assert m.apply_callback is None


def test_native_factory_has_no_qt_imports(tmp_path):
    import os
    import subprocess
    import sys

    script = """import sys
class BlockQt:
 def find_spec(self, fullname, *args):
  if fullname.split('.')[0] in ('qtpy','PyQt5','PyQt6','PySide2','PySide6'):
   raise AssertionError('Qt imported: '+fullname)
sys.meta_path.insert(0,BlockQt())
from chisurf.plugins.core.style_manager.gui.app import make_style_manager_app
from emtk import im
from emtk.testing import RecordingPainter
app=make_style_manager_app()
with im.frame(RecordingPainter(),(0,0,800,600)): app._render()
app.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ, "CHISURF_SETTINGS_DIR": str(tmp_path / "settings")},
        timeout=20,
    )
    assert result.returncode == 0, result.stderr


def test_apply_restyles_the_running_application_with_the_shared_widget_fragments(tmp_path):
    m = model(tmp_path)
    (m.package_dir / "widgets").mkdir()
    (m.package_dir / "widgets" / "buttons.css").write_text(
        "/* shared */ button { padding: 3px; }"
    )
    m.editor.set_text("window { background-color: #abcdef; }")
    seen = []
    m.application_callback = lambda text: seen.append(text) or True
    assert m.apply()
    assert seen and seen[-1].startswith("/* shared */") and seen[-1].endswith("#abcdef; }")
    assert m.status.endswith("The running application was restyled.")
    m.application_callback = lambda text: False
    assert m.apply() and m.status.endswith("at the next launch.")



def test_apply_restyles_emtk_live_and_supports_css(tmp_path):
    from emtk import im, theme
    from emtk import style as emtk_style
    from emtk.testing import RecordingPainter

    from chisurf.plugins.core.style_manager.gui.app import StyleManagerApp

    m = model(tmp_path)
    # Test creating a .css file
    assert m.new("modern.css")
    assert m.current_file.name == "modern.css"
    m.editor.set_text("window { background-color: #112233; color: #ffffff; } button { background-color: #445566; }")
    app = StyleManagerApp(m)
    try:
        pressed = []
        original = im.button
        im.button = lambda label, *a, **k: pressed.append(label) or label == "Apply"
        try:
            with im.frame(RecordingPainter(), (0, 0, 800, 600)):
                app._render()
        finally:
            im.button = original
        assert emtk_style.WINDOW_BG == (17, 34, 51, 255)
        assert emtk_style.BUTTON == (68, 85, 102, 255)
        assert "Applied modern.css to EMTK" in m.status
    finally:
        theme.apply_theme("dark")
        app.close()


def test_editor_uses_default_code_editor_and_no_yellow_popup(tmp_path):
    from emtk.im_core import Col
    from emtk.stylesheet import parse_stylesheet

    m = model(tmp_path)
    assert m.editor.config.show_line_numbers is True
    assert m.editor.config.tab_size == 4
    assert m.editor.config.font_role == "code"

    # Verify that tooltip does not turn POPUP_BG yellow
    css_with_tooltip = """
    menu {
        background-color: #2c2c2c;
    }
    tooltip {
        background-color: rgba(255, 200, 80, 0.9);
        color: #000000;
    }
    """
    _, _, style = parse_stylesheet(css_with_tooltip)
    assert style.color(Col.POPUP_BG) == (44, 44, 44, 255)
