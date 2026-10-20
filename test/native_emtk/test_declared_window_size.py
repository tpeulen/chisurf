"""Declared defaults remain bounded while saved user geometry takes precedence."""

import pytest
from emtk.app import ImApp

from chisurf.core.dataspec.schema import validate_view_spec
from chisurf.emtk.state import attach_native_state
from chisurf.plugins.emtk_layout import window_size


@pytest.mark.parametrize("size", [(120, 120), (640, 480), (1100, 720), (8192, 8192)])
def test_window_declaration_and_schema_agree(size):
    """Both readers accept exactly the declared logical pixel dimensions."""
    spec = {"sections": [], "window": dict(zip(("width", "height"), size))}
    assert window_size(spec, (1200, 800)) == size
    assert not validate_view_spec(spec)


def test_missing_window_uses_family_default():
    """An older spec can adopt its app family's default without mutation."""
    spec = {"sections": []}
    assert window_size(spec, (640, 480)) == (640, 480)
    assert spec == {"sections": []}


@pytest.mark.parametrize(
    "window",
    [
        None,
        [],
        {},
        {"width": 640},
        {"width": True, "height": 480},
        {"width": 640.5, "height": 480},
        {"width": "640", "height": 480},
        {"width": 119, "height": 480},
        {"width": 640, "height": 8193},
        {"width": 640, "height": 480, "widht": 640},
    ],
)
def test_invalid_declared_window_fails_at_source(window):
    """Typos and coercions cannot silently select a different host size."""
    spec = {"sections": [], "window": window}
    with pytest.raises(ValueError, match="window"):
        window_size(spec, (1200, 800))
    assert validate_view_spec(spec)


def test_saved_geometry_wins_over_declared_default(tmp_path, monkeypatch):
    """Reopening a resized app retains the user's dimensions."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))

    def make():
        app = ImApp(lambda: None)
        app.window_size = window_size({"window": {"width": 640, "height": 480}}, (1200, 800))
        return attach_native_state("declared_window_example", app)

    first = make()
    assert first.window_size == (640, 480)
    first.window_resized(950, 700)
    first.close()
    reopened = make()
    assert reopened.window_size == (950, 700)
    reopened.close()


def test_python_reader_rejects_integral_float_without_coercion():
    """JSON Schema accepts 640.0 as an integer; the Python declaration stays strict."""
    with pytest.raises(ValueError, match="window"):
        window_size({"window": {"width": 640.0, "height": 480}}, (1200, 800))


@pytest.mark.parametrize(
    "factory, expected",
    [
        ("chisurf.plugins.calculator.fret_calculator.gui.app:make_app", (640, 480)),
        ("chisurf.plugins.microscopy.imaging_tools.gui.app:make_app", (1100, 720)),
        ("chisurf.plugins.tttr.tttr_image_browser.gui.app:make_app", (1200, 800)),
    ],
)
def test_real_factories_adopt_family_declarations(factory, expected, tmp_path, monkeypatch):
    """The declarations reach constructed apps before either host creates its window."""
    import importlib

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    module, name = factory.split(":")
    app = getattr(importlib.import_module(module), name)()
    try:
        assert app.window_size == expected
    finally:
        close = getattr(app, "close", None)
        if callable(close):
            close()
