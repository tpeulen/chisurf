"""The two ported chimol controls, hosted as AutoForm sections.

What these protect is the seam rather than the controls: the controls have
their own painter-level tests under ``chisurf/plugins/chimol/test``. Here the
question is whether a toolkit-free control really does reach a Qt form -- that
``ControlHost`` paints it, that a key typed into the host lands in the model
attribute the section is bound to, and that a form built from a ``view.json``
resolves both keys.
"""

from __future__ import annotations

import struct

import pytest
from qtpy import QtCore, QtGui, QtWidgets


class _Model:
    """A model with a script to edit and a block of bytes to look at."""

    def __init__(self) -> None:
        self.script = "fetch 148L\nshow cartoon\n"
        self.raw_block = bytes(range(256))
        self.blocks = [bytes(64), bytearray(struct.pack("<4d", 1.0, 2.0, 3.0, 4.0))]


def test_both_sections_are_registered():
    """A key nothing registers is a section that silently renders nothing."""
    from chisurf.gui.autoform.sections import get_section_factory

    assert get_section_factory("code_editor") is not None
    assert get_section_factory("memory_editor") is not None


def test_the_code_editor_section_shows_the_bound_attribute(qapp, qtbot):
    """Built from the model, not from an empty buffer."""
    from chisurf.gui.autoform.sections.code_editor_section import CodeEditorWidget

    model = _Model()
    widget = CodeEditorWidget(model, "script", language="lua")
    qtbot.addWidget(widget)
    assert widget.text == model.script
    assert widget.editor is not None
    assert widget.editor.language_name == "Lua"


def test_typing_into_the_hosted_editor_writes_back_to_the_model(qapp, qtbot):
    """The whole point of a bound section: the model is the storage."""
    from chisurf.gui.autoform.sections.code_editor_section import CodeEditorWidget

    model = _Model()
    widget = CodeEditorWidget(model, "script")
    qtbot.addWidget(widget)
    widget.editor.set_cursor(widget.editor.document.top())
    QtWidgets.QApplication.sendEvent(
        widget._host,
        QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_X, QtCore.Qt.NoModifier, "X"),
    )
    assert model.script.startswith("X")


def test_the_host_paints_the_control_without_the_control_knowing_about_qt(qapp, qtbot):
    """``ControlHost`` renders straight into a ``QImage``, offscreen."""
    from chisurf.gui.autoform.sections.code_editor_section import CodeEditorWidget

    widget = CodeEditorWidget(_Model(), "script")
    qtbot.addWidget(widget)
    widget.resize(420, 200)
    image = widget._host.grab().toImage()
    assert image.width() > 0
    colours = {
        image.pixel(x, y) for x in range(0, image.width(), 7) for y in range(0, image.height(), 7)
    }
    # More than the background alone: the text actually drew.
    assert len(colours) > 3


def test_a_refresh_does_not_overwrite_what_somebody_is_typing(qapp, qtbot):
    """A bound editor that fights the user is a bound editor nobody uses."""
    from chisurf.gui.autoform.sections.code_editor_section import CodeEditorWidget

    model = _Model()
    widget = CodeEditorWidget(model, "script")
    qtbot.addWidget(widget)
    widget.editor.set_cursor(widget.editor.document.top())
    widget.editor.insert("edited ")
    model.script = "something else entirely"
    widget.refresh()
    assert widget.text.startswith("edited ")


def test_the_status_strip_says_where_the_caret_is(qapp, qtbot):
    """With multiple carets and a switchable language, this stops being obvious."""
    from chisurf.gui.autoform.sections.code_editor_section import CodeEditorWidget

    widget = CodeEditorWidget(_Model(), "script", language="python")
    qtbot.addWidget(widget)
    assert "Python" in widget.status.text()
    assert "line 1" in widget.status.text()


def test_marking_a_line_recolours_it(qapp, qtbot):
    """What a failing script step uses to point at the line that failed."""
    from chisurf.gui.autoform.sections.code_editor_section import CodeEditorWidget

    widget = CodeEditorWidget(_Model(), "script")
    qtbot.addWidget(widget)
    widget.mark_line(1, "unknown command")
    assert widget.editor.document.lines[1].marker is not None
    widget.clear_marks()
    assert widget.editor.document.lines[1].marker is None


def test_the_memory_section_shows_a_bound_buffer(qapp, qtbot):
    """bytes, bytearray, memoryview and NumPy all go straight in."""
    from chisurf.gui.autoform.sections.memory_editor_section import MemoryEditorWidget

    widget = MemoryEditorWidget(_Model(), "raw_block")
    qtbot.addWidget(widget)
    assert widget.editor is not None
    assert widget.editor.size == 256
    assert not widget.picker.isVisible()  # one block needs no picker


def test_a_list_of_buffers_grows_a_picker(qapp, qtbot):
    """One section, a whole set of buffers, chosen by name."""
    from chisurf.gui.autoform.sections.memory_editor_section import MemoryEditorWidget

    widget = MemoryEditorWidget(_Model(), "blocks")
    qtbot.addWidget(widget)
    assert widget.picker.count() == 2
    widget.picker.setCurrentIndex(1)
    assert widget.editor.size == 32
    assert "2 block(s)" in widget.caption.text()


def test_with_no_target_it_probes_and_reports_both_totals(qapp, qtbot):
    """The "where did the memory go" view, which is why the section exists."""
    numpy = pytest.importorskip("numpy")
    from chisurf.gui.autoform.sections.memory_editor_section import MemoryEditorWidget

    class _Viewer:
        def __init__(self) -> None:
            self.vertices = numpy.zeros(4096, dtype=numpy.float32)

    class _WithViewer:
        def __init__(self) -> None:
            self.viewer = _Viewer()

    widget = MemoryEditorWidget(_WithViewer(), "")
    qtbot.addWidget(widget)
    assert "RAM" in widget.caption.text()
    assert widget.editor.size == 4096 * 4
