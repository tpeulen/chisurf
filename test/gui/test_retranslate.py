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

_CATALOGUE = pathlib.Path(__file__).parents[2] / "chisurf" / "gui" / "i18n" / "chisurf_fr.ts"


def _french_pair() -> tuple[str, str, str, str, str]:
    """Two translated strings of one context from the shipped French catalogue.

    Taken from the catalogue rather than written here: the strings this test
    once named went when the Designer forms holding them were deleted, and the
    test then failed for a reason that had nothing to do with retranslation.
    """
    import xml.etree.ElementTree as ET

    for context in ET.parse(_CATALOGUE).getroot().iter("context"):
        pairs = [
            (m.findtext("source"), m.findtext("translation"))
            for m in context.iter("message")
            if m.find("translation") is not None
            and m.find("translation").get("type") is None
            and (m.findtext("translation") or "") not in ("", m.findtext("source"))
            and "&" not in (m.findtext("source") or "") and "<" not in (m.findtext("source") or "")
        ]
        if len(pairs) >= 2:
            (a, a_fr), (b, b_fr) = pairs[:2]
            return context.findtext("name"), a, a_fr, b, b_fr
    raise AssertionError("the French catalogue holds no context with two translations")


def _ui(context: str, button: str, label: str) -> str:
    from xml.sax.saxutils import escape

    return f"""<?xml version="1.0"?>
<ui version="4.0"><class>{context}</class>
<widget class="QWidget" name="{context}">
 <layout class="QVBoxLayout" name="v">
  <item><widget class="QPushButton" name="btn"><property name="text"><string>{escape(button)}</string></property></widget></item>
  <item><widget class="QLabel" name="lbl"><property name="text"><string>{escape(label)}</string></property></widget></item>
 </layout>
</widget></ui>"""


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _write_ui(text: str) -> pathlib.Path:
    p = pathlib.Path(tempfile.mkdtemp()) / "form.ui"
    p.write_text(text, encoding="utf-8")
    return p


def test_retranslate_updates_live_widget_text(qapp):
    """Switching language then retranslating refreshes existing widget text."""
    from chisurf.gui import i18n as gi18n
    from chisurf.gui import uic
    from chisurf.gui.retranslate import retranslate_from_ui

    context, button, button_fr, label, label_fr = _french_pair()
    ui_path = _write_ui(_ui(context, button, label))
    w = QtWidgets.QWidget()
    uic.loadUi(str(ui_path), w)
    assert w.btn.text() == button  # English at load time

    try:
        assert gi18n.apply_language("fr") == "fr"
        # Qt does NOT retranslate the already-built widget on its own …
        assert w.btn.text() == button
        # … until we re-apply from the .ui:
        retranslate_from_ui(w, ui_path)
        assert w.btn.text() == button_fr
        assert w.lbl.text() == label_fr

        # Switching back to English restores the source text.
        gi18n.apply_language("en")
        retranslate_from_ui(w, ui_path)
        assert w.btn.text() == button
    finally:
        gi18n.apply_language("en")


def test_retranslate_is_silent_on_missing_file(qapp):
    """A bad path is a no-op, never an exception (best-effort chrome polish)."""
    from chisurf.gui.retranslate import retranslate_from_ui

    w = QtWidgets.QWidget()
    retranslate_from_ui(w, "/no/such/file.ui")  # must not raise
