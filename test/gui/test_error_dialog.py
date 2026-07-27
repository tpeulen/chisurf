"""A startup failure is reported through the simple error dialog.

This replaces a manual script that, at *import* time, replaced
``sys.modules["chisurf.gui"]`` with a stub module and monkeypatched
``sys.exit`` — permanently, for the whole pytest process. Every GUI test module
collected after it then failed with
``ImportError: cannot import name 'chiplot' from 'mock_module'``, which is also
what took the ``test/gui`` collection down. The behaviour it meant to check is
kept here, with the patching scoped to the test.
"""

from __future__ import annotations

import os
import sys
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

qtpy = pytest.importorskip("qtpy")

from qtpy import QtWidgets  # noqa: E402

import chisurf.__main__ as chisurf_main  # noqa: E402


@pytest.fixture
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_startup_failure_shows_the_error_dialog(qapp, monkeypatch):
    """``main`` catches a failing ``get_app`` and shows the dialog, exit code 1."""
    stub = types.ModuleType("chisurf.gui")
    stub.__file__ = "stub_chisurf_gui.py"

    def _boom():
        raise RuntimeError("startup exploded")

    stub.get_app = _boom
    monkeypatch.setitem(sys.modules, "chisurf.gui", stub)

    shown: list[str] = []

    class _Dialog:
        def __init__(self, exception_text, parent=None):
            shown.append(exception_text)

        def exec(self):
            return 0

    monkeypatch.setattr(chisurf_main, "SimpleErrorDialog", _Dialog)

    with pytest.raises(SystemExit) as excinfo:
        chisurf_main.main()

    assert excinfo.value.code == 1
    assert shown and "startup exploded" in shown[0]


def test_error_dialog_module_does_not_leak_a_stubbed_gui():
    """The real ``chisurf.gui`` is intact after the test above."""
    import chisurf.gui

    assert getattr(chisurf.gui, "__file__", "").endswith("chisurf/gui/__init__.py")
