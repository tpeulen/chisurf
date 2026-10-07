"""Startup failure tests keep GUI stubs scoped to their own invocation.

This replaces a manual script that, at *import* time, replaced
``sys.modules["chisurf.gui"]`` with a stub module and monkeypatched
``sys.exit`` — permanently, for the whole pytest process. Every GUI test module
collected after it then failed with
``ImportError: cannot import name 'chiplot' from 'mock_module'``, which is also
what took the ``test/gui`` collection down. The behaviour it meant to check is
kept here, with the patching scoped to the test.
"""

from __future__ import annotations

import faulthandler
import pathlib
import sys
import types

import pytest

import chisurf.__main__ as chisurf_main


def test_startup_failure_keeps_the_gui_stub_scoped(monkeypatch, tmp_path):
    """A failed startup re-raises while restoring the real GUI module."""
    import chisurf.gui

    real_gui = sys.modules["chisurf.gui"]
    stub = types.ModuleType("chisurf.gui")
    stub.__file__ = "stub_chisurf_gui.py"

    failure = RuntimeError("startup exploded")

    def _boom():
        """Fail before constructing any application window."""
        raise failure

    stub.get_app = _boom
    with monkeypatch.context() as scoped:
        scoped.setitem(sys.modules, "chisurf.gui", stub)
        scoped.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
        scoped.setattr(pathlib.Path, "home", lambda: tmp_path / "unused-home")
        scoped.setattr(faulthandler, "enable", lambda **kwargs: None)
        scoped.setattr(faulthandler, "disable", lambda: None)
        scoped.setattr(chisurf_main, "QtWidgets", None, raising=False)
        with pytest.raises(RuntimeError) as captured:
            chisurf_main.main()
        assert captured.value is failure

    assert sys.modules["chisurf.gui"] is real_gui


def test_error_dialog_module_does_not_leak_a_stubbed_gui():
    """The real ``chisurf.gui`` is intact after the test above."""
    import chisurf.gui

    assert getattr(chisurf.gui, "__file__", "").endswith("chisurf/gui/__init__.py")
