"""Real intensity-trace factories honor declared defaults and saved user geometry."""

import json

import pytest

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.tttr.intensity_trace.gui import app as module


def test_native_factory_uses_primary_view_window(tmp_path, monkeypatch):
    """The actual tool advertises its family dimensions before either host starts."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    spec = json.loads((module.HERE / "intensity_trace.view.json").read_text())
    app = module.make_app()
    try:
        assert spec["window"] == {"width": 1100, "height": 720}
        assert app.window_size == (1100, 720)
    finally:
        app.close()


def test_factory_reads_geometry_from_spec_instead_of_hardcoding(tmp_path, monkeypatch):
    """A valid authored declaration reaches the factory without altering its panels."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    spec = json.loads((module.HERE / "intensity_trace.view.json").read_text())
    spec["window"] = {"width": 1280, "height": 760}
    (tmp_path / "intensity_trace.view.json").write_text(json.dumps(spec))
    monkeypatch.setattr(module, "HERE", tmp_path)
    app = module.make_app()
    try:
        assert app.window_size == (1280, 760)
        assert app.spec == spec["panels"]
    finally:
        app.close()


def test_saved_resize_wins_when_reopening_the_actual_tool(tmp_path, monkeypatch):
    """State binding restores user dimensions over the new family default."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    first = attach_native_state("intensity_trace", module.make_app())
    assert first.window_size == (1100, 720)
    first.window_resized(940, 640)
    first.close()
    reopened = attach_native_state("intensity_trace", module.make_app())
    try:
        assert reopened.window_size == (940, 640)
    finally:
        reopened.close()


def test_qt_host_resolves_declared_tool_size_on_an_adequate_screen(qapp, tmp_path, monkeypatch):
    """The host reads the real factory declaration before applying screen bounds."""
    from types import SimpleNamespace

    from emtk.qt_host import ControlHost
    from qtpy import QtCore, QtGui

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    app = module.make_app()
    host = ControlHost(app)
    try:
        monkeypatch.setattr(
            QtGui.QGuiApplication,
            "primaryScreen",
            lambda: SimpleNamespace(availableGeometry=lambda: QtCore.QRect(0, 0, 1920, 1080)),
        )
        assert host.window_size_hint() == (1100, 720)
    finally:
        host.close()


@pytest.mark.parametrize("size", [(1100, 720), (800, 600)])
def test_result_selector_wraps_with_complete_labels_and_pointer_reachability(
    tmp_path, monkeypatch, size
):
    """Every real selector retains its hidden ID and reaches its result inside the dock."""
    from emtk import im
    from emtk.testing import Driver

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    app = module.make_app()
    driver = Driver(app, size)
    submitted = []
    original_button = im.button

    def record(label, *args, **kwargs):
        """Observe submitted widget identity without changing pointer behavior."""
        submitted.append(label)
        return original_button(label, *args, **kwargs)

    monkeypatch.setattr(im, "button", record)
    try:
        driver.frame(3)
        seen = set()
        for label, metadata in zip(driver.painter.strings, driver.painter.text_metadata):
            if label in module.RESULTS:
                assert metadata["measured_bounds"] == metadata["visible_bounds"], (label, metadata)
                seen.add(label)
        assert seen == set(module.RESULTS)
        # button_row ids a caption with "###": the id survives a translated caption
        assert {f"{name}###result_{i}" for i, name in enumerate(module.RESULTS)} <= set(submitted)
        original_config = app.model.window_ms, app.model.n_states
        bx, by, bw, bh = app.docks.windows["results"].content
        for name in module.RESULTS:
            x, y, w, h = driver.rect(f"result.{name}")
            assert bx <= x and x + w <= bx + bw
            assert by <= y and y + h <= by + bh
            driver.click(f"result.{name}")
            assert app.result == name
        assert (app.model.window_ms, app.model.n_states) == original_config
        assert not app.model.loaded
    finally:
        app.close()


def test_short_fret_caption_preserves_the_plot_identity():
    """The unchanged hidden plot suffix retains its stored axes when the caption changes."""
    import emtk
    from emtk.testing import RecordingPainter

    with emtk.frame(RecordingPainter(), (0, 0, 800, 600)) as context:
        assert context.get_id("FRET Efficiency Distributions by State##fretdist") == context.get_id(
            "FRET efficiency by state##fretdist"
        )
