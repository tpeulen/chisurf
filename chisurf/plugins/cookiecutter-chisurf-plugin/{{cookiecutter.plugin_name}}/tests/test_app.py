"""The {{ cookiecutter.plugin_display_name }} window, headless: it draws, its controls work, it imports no Qt."""

from __future__ import annotations

import subprocess
import sys

from emtk.testing import RecordingPainter

from chisurf.plugins.{{ cookiecutter.plugin_name }}.gui.app import {{ cookiecutter.class_prefix }}App
from chisurf.plugins.{{ cookiecutter.plugin_name }}.gui.view_model import (
    {{ cookiecutter.class_prefix }}ViewModel,
)


class FakeClient:
    """The backend without a server: doubles the number, as the example core does."""

    def compute(self, settings):
        return settings["example_number"] * 2


def draw(app, size=(900, 600), frames=3):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def test_the_window_draws_every_declared_control():
    shown = " ".join(draw({{ cookiecutter.class_prefix }}App({{ cookiecutter.class_prefix }}ViewModel(FakeClient()))).strings)
    for text in ("Help", "Guide", "Settings", "Example number", "Run", "Result"):
        assert text in shown, text


def test_run_computes_through_the_client_and_shows_the_result():
    model = {{ cookiecutter.class_prefix }}ViewModel(FakeClient())
    app = {{ cookiecutter.class_prefix }}App(model)
    model.example_number = 2.5
    model.run()
    assert model.result == 5.0 and model.status == "Done: 5"
    assert "Result: 5" in " ".join(draw(app).strings)


def test_a_failing_backend_is_a_status_line_not_an_exception():
    class Broken:
        def compute(self, settings):
            raise RuntimeError("backend is gone")

    model = {{ cookiecutter.class_prefix }}ViewModel(Broken())
    model.run()
    assert model.result is None and model.status == "Failed: backend is gone"


def test_help_and_guide_buttons_open_the_help_and_the_tour():
    app = {{ cookiecutter.class_prefix }}App({{ cookiecutter.class_prefix }}ViewModel(FakeClient()))
    app.model.open_help()
    app.model.start_guide()
    assert app.tour.active


def test_settings_round_trip_and_ignore_bad_values():
    app = {{ cookiecutter.class_prefix }}App({{ cookiecutter.class_prefix }}ViewModel(FakeClient()))
    app.model.example_number = 7.0
    state = app.export_settings()
    other = {{ cookiecutter.class_prefix }}App({{ cookiecutter.class_prefix }}ViewModel(FakeClient()))
    other.restore_settings(state)
    assert other.model.example_number == 7.0
    other.restore_settings({"example_number": "x"})
    assert other.model.example_number == 7.0


def test_the_window_imports_no_qt():
    code = (
        "import sys; import chisurf.plugins.{{ cookiecutter.plugin_name }}.gui.app as a; a.make_app();"
        "bad = [m for m in sys.modules if m.split('.')[0] in ('PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'qtpy')];"
        "print(bad); raise SystemExit(1 if bad else 0)"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout + done.stderr
