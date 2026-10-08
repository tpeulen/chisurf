"""Shared family constructors must retain geometry before preparing form sections."""

import importlib

import pytest


@pytest.mark.parametrize(
    "factory",
    [
        "chisurf.plugins.microscopy.img_drift.gui.app:make_app",
        "chisurf.plugins.traj.traj_rotate_translate.app:make_app",
    ],
)
def test_shared_family_default_reaches_real_app(factory, tmp_path, monkeypatch):
    """A real subclass adopts the shared family default before host creation."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    module, name = factory.split(":")
    app = getattr(importlib.import_module(module), name)()
    try:
        assert app.window_size == (1100, 720)
    finally:
        close = getattr(app, "close", None)
        if callable(close):
            close()


def test_closed_trajectory_dialog_does_not_open_a_window_stack(tmp_path, monkeypatch):
    """Closing a chooser before its draw must leave the frame's begin/end stack alone."""
    from types import SimpleNamespace

    from chisurf.plugins.traj.traj_rotate_translate.app import make_app

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    app = make_app()
    events = []
    app.dialog_window = SimpleNamespace(
        begin=lambda box: events.append("begin"), end=lambda: events.append("end")
    )
    app.dialog = None
    try:
        app._draw_dialog((0, 0, 640, 480))
        assert events == []
    finally:
        app.close()
