"""Headless tests for live ``.ui`` retranslation (offscreen Qt).

Verifies that :func:`chisurf.gui.retranslate.retranslate_from_ui` refreshes an
already-built widget's text in place when the UI language changes — the gap Qt
leaves for runtime ``uic.loadUi`` forms (it only translates at build time).
"""

from __future__ import annotations

import os
import pathlib
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("qtpy")
from qtpy import QtWidgets  # noqa: E402

_UI = """<?xml version="1.0"?>
<ui version="4.0"><class>Form</class>
<widget class="QWidget" name="Form">
 <property name="windowTitle"><string>Form</string></property>
 <layout class="QVBoxLayout" name="v">
  <item><widget class="QPushButton" name="btn"><property name="text"><string>Update widgets</string></property></widget></item>
  <item><widget class="QLabel" name="lbl"><property name="text"><string>Display equation</string></property></widget></item>
 </layout>
</widget></ui>"""


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _write_ui() -> pathlib.Path:
    p = pathlib.Path(tempfile.mkdtemp()) / "form.ui"
    p.write_text(_UI, encoding="utf-8")
    return p


def test_retranslate_updates_live_widget_text(qapp):
    """Switching language then retranslating refreshes existing widget text."""
    from chisurf.gui import i18n as gi18n
    from chisurf.gui import uic
    from chisurf.gui.retranslate import retranslate_from_ui

    ui_path = _write_ui()
    w = QtWidgets.QWidget()
    uic.loadUi(str(ui_path), w)
    assert w.btn.text() == "Update widgets"  # English at load time

    try:
        gi18n.apply_language("fr")
        # Qt does NOT retranslate the already-built widget on its own …
        assert w.btn.text() == "Update widgets"
        # … until we re-apply from the .ui:
        retranslate_from_ui(w, ui_path)
        assert w.btn.text() == "Actualiser les widgets"
        assert w.lbl.text() == "Afficher l'équation"

        # Switching back to English restores the source text.
        gi18n.apply_language("en")
        retranslate_from_ui(w, ui_path)
        assert w.btn.text() == "Update widgets"
    finally:
        gi18n.apply_language("en")


def test_retranslate_is_silent_on_missing_file(qapp):
    """A bad path is a no-op, never an exception (best-effort chrome polish)."""
    from chisurf.gui.retranslate import retranslate_from_ui

    w = QtWidgets.QWidget()
    retranslate_from_ui(w, "/no/such/file.ui")  # must not raise
