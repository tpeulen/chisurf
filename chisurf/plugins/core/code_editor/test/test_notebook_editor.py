"""Tests for the notebook editor widget and its code_editor host integration.

The notebook editor runs cells in an in-process :class:`Shell` (no Jupyter
kernel, no web view); these tests cover loading, cell execution, embedded
inline figures, save round-trips and the host's ``.ipynb`` routing.
"""

from __future__ import annotations

import pathlib

import nbformat
import pytest
from qtpy import QtCore, QtWidgets

from chisurf.plugins.core.code_editor.editor import CodeEditor
from chisurf.plugins.core.code_editor.notebook_editor import (
    NotebookEditor,
    shipped_notebooks,
)
from chisurf.plugins.core.code_editor.text_editor import TextEditor

pytestmark = [pytest.mark.gui, pytest.mark.widget]


@pytest.fixture
def app() -> QtWidgets.QApplication:
    instance = QtWidgets.QApplication.instance()
    if instance is not None:
        return instance
    return QtWidgets.QApplication([])


@pytest.fixture
def notebook_path(tmp_path: pathlib.Path) -> pathlib.Path:
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_code_cell(source="x = 21"),
        nbformat.v4.new_code_cell(source="x + 1"),
        nbformat.v4.new_markdown_cell(source="# A heading"),
        nbformat.v4.new_code_cell(
            source=(
                "import matplotlib\nmatplotlib.use('Agg')\n"
                "import matplotlib.pyplot as plt\n"
                "fig, ax = plt.subplots()\nax.plot([1, 2, 3])\nfig"
            )
        ),
    ]
    path = tmp_path / "sample.ipynb"
    nbformat.write(nb, path)
    return path


def _open_notebook(app, path: str) -> tuple[CodeEditor, NotebookEditor]:
    editor_widget = CodeEditor(can_load=False, enable_lsp=None)
    editor_widget.open_file(str(path))
    notebooks = [
        editor_widget.tab_widget.widget(i)
        for i in range(editor_widget.tab_widget.count())
        if isinstance(editor_widget.tab_widget.widget(i), NotebookEditor)
    ]
    assert len(notebooks) == 1, f"expected one notebook tab, got {len(notebooks)}"
    return editor_widget, notebooks[0]


def test_open_ipynb_creates_notebook_tab(app, notebook_path):
    """A ``.ipynb`` path opens as a NotebookEditor tab with its cells loaded."""
    editor_widget, nb_ed = _open_notebook(app, notebook_path)
    assert nb_ed.current_file is not None
    assert pathlib.Path(nb_ed.current_file).resolve() == pathlib.Path(notebook_path).resolve()
    assert [cell.cell_type for cell in nb_ed.cells()] == ["code", "code", "markdown", "code"]
    assert nb_ed.cells()[0].editor.toPlainText() == "x = 21"
    assert nb_ed.cells()[2].editor.toPlainText() == "# A heading"


def test_language_from_path_is_notebook(app):
    """The host maps ``.ipynb`` to the Notebook language."""
    assert CodeEditor._language_from_path("foo.ipynb") == "Notebook"
    assert CodeEditor._language_from_path("foo.py") == "Python"


def test_cells_share_shell_state(app, notebook_path):
    """Running cells mutates a single in-process shell, top to bottom."""
    _, nb_ed = _open_notebook(app, notebook_path)
    for cell in nb_ed.code_cells():
        nb_ed.run_cell(cell)
    assert nb_ed._shell is not None
    assert nb_ed._shell.user_ns.get("x") == 21


def test_plot_embeds_image_output(app, notebook_path):
    """A cell that produces a figure records an embedded ``image/png`` output."""
    _, nb_ed = _open_notebook(app, notebook_path)
    for cell in nb_ed.code_cells():
        nb_ed.run_cell(cell)
    image_records = 0
    for cell in nb_ed.cells():
        for rec in cell.collect_outputs():
            data = rec.get("data") or {}
            if rec.get("output_type") == "display_data" and "image/png" in data:
                image_records += 1
    assert image_records >= 1


def test_save_round_trip_preserves_cells_and_outputs(app, notebook_path, tmp_path):
    """Saving writes a valid ipynb with sources, markdown and recorded outputs."""
    _, nb_ed = _open_notebook(app, notebook_path)
    for cell in nb_ed.code_cells():
        nb_ed.run_cell(cell)
    out = tmp_path / "out.ipynb"
    nb_ed.save_to(str(out))
    roundtrip = nbformat.read(str(out), as_version=4)
    assert [c.cell_type for c in roundtrip.cells] == ["code", "code", "markdown", "code"]
    assert roundtrip.cells[0].source == "x = 21"
    assert roundtrip.cells[2].source == "# A heading"
    assert len(roundtrip.cells[3].outputs) >= 1


def test_reload_replays_saved_output(app, notebook_path):
    """Reloading replays stored outputs onto the cell widgets."""
    _, nb_ed = _open_notebook(app, notebook_path)
    for cell in nb_ed.code_cells():
        nb_ed.run_cell(cell)
    nb_ed.save_to(str(notebook_path))
    nb_ed.reload()
    assert nb_ed.cells()[0].editor.toPlainText() == "x = 21"
    records = nb_ed.cells()[3].collect_outputs()
    assert len(records) >= 1
    assert any("image/png" in (rec.get("data") or {}) for rec in records)


def test_corrupt_ipynb_falls_back_to_text(app, tmp_path):
    """An unparseable ``.ipynb`` opens as a plain text tab, not a notebook."""
    bad = tmp_path / "broken.ipynb"
    bad.write_text("this is { not json", encoding="utf-8")
    editor_widget = CodeEditor(can_load=False, enable_lsp=None)
    editor_widget.open_file(str(bad))
    text_tabs = [
        editor_widget.tab_widget.widget(i)
        for i in range(editor_widget.tab_widget.count())
        if isinstance(editor_widget.tab_widget.widget(i), TextEditor)
    ]
    assert text_tabs
    assert text_tabs[0].toPlainText() == "this is { not json"


def test_shipped_notebooks_finds_examples(app):
    """The shipped-notebooks helper lists the curated examples/notebooks."""
    notebooks = shipped_notebooks()
    assert len(notebooks) > 10
    assert all(path.suffix == ".ipynb" for path in notebooks)


def test_host_save_writes_nbformat(app, notebook_path, tmp_path):
    """The host's save path writes a notebook through nbformat, not raw text."""
    editor_widget, nb_ed = _open_notebook(app, notebook_path)
    out = tmp_path / "host_save.ipynb"
    nb_ed.save_to(str(out))
    editor_widget.open_file(str(out))
    notebooks = [
        editor_widget.tab_widget.widget(i)
        for i in range(editor_widget.tab_widget.count())
        if isinstance(editor_widget.tab_widget.widget(i), NotebookEditor)
    ]
    assert len(notebooks) == 2
    assert notebooks[1].current_file is not None
    assert [c.cell_type for c in notebooks[1].cells()] == ["code", "code", "markdown", "code"]


def test_markdown_cell_run_renders_without_dirty(app):
    """Running a markdown cell renders it and does not mark the notebook dirty."""
    nb_ed = NotebookEditor()
    cell = nb_ed.add_cell(cell_type="markdown", source="# Hello\n\n**world**")
    nb_ed._beacon.setModified(False)
    nb_ed.run_cell(cell)
    assert not cell._edit_mode
    html = cell.render_view.toHtml()
    assert "Hello" in html
    assert not nb_ed._beacon.isModified()


def test_insert_between_reorders_cells(app):
    """``after_index`` inserts a cell between existing ones and rebuilds gaps."""
    nb_ed = NotebookEditor()
    first = nb_ed.add_cell(cell_type="code", source="a = 1")
    last = nb_ed.add_cell(cell_type="code", source="b = 2")
    inserted = nb_ed.add_cell(cell_type="code", source="mid", after_index=0)
    initial = nb_ed.cells()[0]
    assert [c for c in nb_ed.cells()] == [initial, inserted, first, last]
    QtWidgets.QApplication.processEvents()
    inserts = [
        b for b in nb_ed.container.findChildren(QtWidgets.QToolButton, "notebook_insert_button")
    ]
    assert len(inserts) == 3
    nb_ed.remove_cell(inserted)
    assert [c for c in nb_ed.cells()] == [initial, first, last]
    QtWidgets.QApplication.processEvents()
    inserts = [
        b for b in nb_ed.container.findChildren(QtWidgets.QToolButton, "notebook_insert_button")
    ]
    assert len(inserts) == 2


def test_run_cell_mirrors_to_terminal(app):
    """Executed source and its output are echoed into the attached terminal."""
    nb_ed = NotebookEditor()
    nb_ed.add_cell(cell_type="code", source="x = 21")
    nb_ed.add_cell(cell_type="code", source="print('sum', x + 21)")
    for c in nb_ed.code_cells():
        if c.editor.toPlainText().strip():
            nb_ed.run_cell(c)
    text = nb_ed.terminal.view.toPlainText()
    assert "print('sum', x + 21)" in text
    assert "sum 42" in text


def test_run_cell_busy_writes_into_cell(app):
    """A cell requested while the shell is busy gets a busy marker, not a deadlock."""
    nb_ed = NotebookEditor()
    cell = nb_ed.add_cell(cell_type="code", source="1 + 1")
    nb_ed._shell._busy = True
    nb_ed.run_cell(cell)
    assert "wait for it to finish" in cell.output.toPlainText()
    nb_ed._shell._busy = False


# ----------------------------------------------------------------------
# layout: every surface is sized to what it holds
# ----------------------------------------------------------------------


def _laid_out(widget: QtWidgets.QWidget, width: int = 900, height: int = 700) -> None:
    """Show *widget* offscreen at a realistic size and let Qt lay it out."""
    widget.resize(width, height)
    widget.show()
    for _ in range(3):
        QtWidgets.QApplication.processEvents()


def test_empty_output_takes_no_height(app):
    """A cell that has not run yet contributes no output height at all."""
    nb_ed = NotebookEditor()
    _laid_out(nb_ed)
    cell = nb_ed.cells()[0]
    assert not cell.output.isVisible()
    assert cell.output.height() == 0


def test_output_height_tracks_line_count(app):
    """Three lines of output are taller than one, and neither is a fixed block."""
    nb_ed = NotebookEditor()
    _laid_out(nb_ed)
    one = nb_ed.add_cell(cell_type="code", source="print('a')")
    many = nb_ed.add_cell(cell_type="code", source="print('a')\nprint('b')\nprint('c')")
    QtWidgets.QApplication.processEvents()
    nb_ed.run_cell(one)
    nb_ed.run_cell(many)
    QtWidgets.QApplication.processEvents()
    line = one.output.fontMetrics().lineSpacing()
    assert one.output.height() < many.output.height()
    assert many.output.height() - one.output.height() >= 2 * line - 4
    assert one.output.height() < 3 * line


def test_long_output_is_clamped_and_scrolls(app):
    """Runaway output stops growing at MAX_HEIGHT instead of pushing cells away."""
    nb_ed = NotebookEditor()
    _laid_out(nb_ed)
    cell = nb_ed.add_cell(cell_type="code", source="for i in range(200):\n    print(i)")
    QtWidgets.QApplication.processEvents()
    nb_ed.run_cell(cell)
    QtWidgets.QApplication.processEvents()
    assert cell.output.height() == cell.output.MAX_HEIGHT
    assert cell.output.verticalScrollBarPolicy() == QtCore.Qt.ScrollBarAsNeeded


def test_source_editor_does_not_scroll_while_it_fits(app):
    """A five-line cell shows five lines, not four and a scrollbar."""
    nb_ed = NotebookEditor()
    _laid_out(nb_ed)
    cell = nb_ed.add_cell(cell_type="code", source="\n".join(f"a{i} = {i}" for i in range(5)))
    QtWidgets.QApplication.processEvents()
    line = cell.editor.fontMetrics().lineSpacing()
    assert cell.editor.verticalScrollBarPolicy() == QtCore.Qt.ScrollBarAlwaysOff
    assert cell.editor.height() >= 5 * line
    assert cell.editor.height() < 6 * line + 12


def test_figure_is_scaled_into_the_output_width(app):
    """A figure wider than the cell is shrunk, not clipped or scrolled sideways."""
    nb_ed = NotebookEditor()
    _laid_out(nb_ed, width=420)
    cell = nb_ed.add_cell(
        cell_type="code",
        source=(
            "import matplotlib\nmatplotlib.use('Agg')\n"
            "import matplotlib.pyplot as plt\n"
            "fig, ax = plt.subplots(figsize=(9, 3))\nax.plot([1, 2, 3])\nfig"
        ),
    )
    QtWidgets.QApplication.processEvents()
    nb_ed.run_cell(cell)
    QtWidgets.QApplication.processEvents()
    assert any(record[0] == "display" for record in cell.output._records)
    assert cell.output.horizontalScrollBarPolicy() == QtCore.Qt.ScrollBarAlwaysOff
    assert cell.output.document().size().width() <= cell.output.viewport().width() + 1


def test_returned_figure_does_not_also_print_its_repr(app):
    """``fig`` as the last expression yields the image only, not ``<Figure ...>``."""
    nb_ed = NotebookEditor()
    _laid_out(nb_ed)
    cell = nb_ed.add_cell(
        cell_type="code",
        source=(
            "import matplotlib\nmatplotlib.use('Agg')\n"
            "import matplotlib.pyplot as plt\n"
            "fig, ax = plt.subplots()\nax.plot([1, 2, 3])\nfig"
        ),
    )
    QtWidgets.QApplication.processEvents()
    nb_ed.run_cell(cell)
    QtWidgets.QApplication.processEvents()
    assert "<Figure" not in cell.output.toPlainText()


def test_figure_is_not_mirrored_into_the_terminal(app):
    """The plot belongs to the cell that drew it; the terminal keeps its height."""
    nb_ed = NotebookEditor()
    _laid_out(nb_ed)
    cell = nb_ed.add_cell(
        cell_type="code",
        source=(
            "import matplotlib\nmatplotlib.use('Agg')\n"
            "import matplotlib.pyplot as plt\n"
            "fig, ax = plt.subplots()\nax.plot([1, 2, 3])\nfig"
        ),
    )
    QtWidgets.QApplication.processEvents()
    nb_ed.run_cell(cell)
    QtWidgets.QApplication.processEvents()
    assert any(record[0] == "display" for record in cell.output._records)
    assert _image_fragments(cell.output.document()) != []
    assert _image_fragments(nb_ed.terminal.view.document()) == [], (
        "the terminal was handed the figure as well"
    )


def _image_fragments(document) -> list:
    """Return the names of every image embedded in *document*."""
    names = []
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fmt = iterator.fragment().charFormat()
            if fmt.isImageFormat():
                names.append(fmt.toImageFormat().name())
            iterator += 1
        block = block.next()
    return names


def test_traceback_ansi_is_rendered_not_printed(app):
    """A coloured traceback reaches the cell as colour, not as escape bytes."""
    nb_ed = NotebookEditor()
    _laid_out(nb_ed)
    cell = nb_ed.add_cell(cell_type="code", source="raise ValueError('boom')")
    QtWidgets.QApplication.processEvents()
    nb_ed.run_cell(cell)
    QtWidgets.QApplication.processEvents()
    text = cell.output.toPlainText()
    assert "ValueError" in text and "boom" in text
    assert "\x1b" not in text
    assert "[91m" not in text and "[0m" not in text


def test_rendered_markdown_cell_keeps_its_gutter(app):
    """A rendered markdown cell can still be deleted and re-rendered."""
    nb_ed = NotebookEditor()
    _laid_out(nb_ed)
    cell = nb_ed.add_cell(cell_type="markdown", source="# Title")
    cell.render_markdown()
    QtWidgets.QApplication.processEvents()
    assert not cell.editor.isVisible()
    assert cell.render_view.isVisible()
    assert cell._header.isVisible()
    assert cell.close_button.isVisible()


def test_clearing_cells_leaves_no_ghost_widgets(app, notebook_path):
    """Reloading a notebook unparents the old cells instead of leaving them painting."""
    nb_ed = NotebookEditor()
    _laid_out(nb_ed)
    first = nb_ed.cells()[0]
    nb_ed.open_file(str(notebook_path))
    assert first.parent() is None


def test_toolbar_actions(app):
    """Run all, clear and restart act on every cell without touching the source."""
    nb_ed = NotebookEditor()
    _laid_out(nb_ed)
    nb_ed._clear_cells()
    nb_ed.add_cell(cell_type="code", source="a = 1")
    nb_ed.add_cell(cell_type="code", source="print(a + 1)")
    nb_ed.run_all()
    QtWidgets.QApplication.processEvents()
    assert "2" in nb_ed.cells()[1].output.toPlainText()

    nb_ed.clear_all_outputs()
    assert nb_ed.cells()[1].output.toPlainText() == ""
    assert nb_ed.cells()[1].output.height() == 0

    nb_ed.restart_kernel()
    assert "a" not in nb_ed._shell.user_ns
    assert [c.execution_count for c in nb_ed.cells()] == [None, None]
    assert nb_ed.cells()[0].editor.toPlainText() == "a = 1"


def test_terminal_toggle_gives_its_height_to_the_cells(app):
    """Hiding the terminal is what reclaims its space, not just blanking it."""
    nb_ed = NotebookEditor()
    _laid_out(nb_ed)
    assert nb_ed.terminal.isVisible()
    nb_ed.terminal_button.setChecked(False)
    QtWidgets.QApplication.processEvents()
    assert not nb_ed.terminal.isVisible()
    nb_ed.terminal_button.setChecked(True)
    QtWidgets.QApplication.processEvents()
    assert nb_ed.terminal.isVisible()


# ----------------------------------------------------------------------
# the kernel terminal is a window dock, beside Diagnostics and Output
# ----------------------------------------------------------------------


def _window(app, path=None):
    """Return a shown CodeEditorWindow, optionally with *path* open."""
    from chisurf.plugins.core.code_editor.window import CodeEditorWindow

    window = CodeEditorWindow(can_load=False, enable_lsp=None)
    window.resize(1100, 800)
    window.show()
    if path is not None:
        window.editor.open_file(str(path))
    for _ in range(3):
        QtWidgets.QApplication.processEvents()
    return window


def test_window_forwards_editor_options_without_choking_qmainwindow(app):
    """Editor-only kwargs must not reach QMainWindow, which rejects them."""
    window = _window(app)
    assert window.editor is not None


def test_every_panel_is_a_chisurf_dock(app):
    """All of the editor's panels share the one dock class."""
    from chisurf.gui.widgets.tools.chisurf_dock import ChisurfDock

    window = _window(app)
    docks = [
        window.file_dock,
        window.symbol_dock,
        window.diagnostics_dock,
        window.output_dock,
        window.kernel_dock,
        window.agent_dock,
    ]
    assert all(isinstance(dock, ChisurfDock) for dock in docks)
    assert len({dock.objectName() for dock in docks}) == len(docks)


def test_kernel_dock_sits_with_diagnostics_and_output(app, notebook_path):
    """The kernel terminal is a bottom panel tabbed with the other two."""
    window = _window(app, notebook_path)
    assert window.dockWidgetArea(window.kernel_dock) == QtCore.Qt.BottomDockWidgetArea
    siblings = window.tabifiedDockWidgets(window.kernel_dock)
    assert window.output_dock in siblings
    assert window.diagnostics_dock in siblings


def test_kernel_dock_holds_the_open_notebooks_terminal(app, notebook_path):
    """The notebook keeps its shell; the dock shows that notebook's console."""
    window = _window(app, notebook_path)
    notebooks = [
        window.editor.tab_widget.widget(i)
        for i in range(window.editor.tab_widget.count())
        if isinstance(window.editor.tab_widget.widget(i), NotebookEditor)
    ]
    assert notebooks
    notebook = notebooks[0]
    assert window._kernel_stack.currentWidget() is notebook.terminal
    assert notebook.terminal.shell is notebook._shell
    # The notebook no longer paints the terminal itself.
    assert notebook.terminal.parent() is not notebook


def test_kernel_dock_follows_the_active_tab(app, notebook_path, tmp_path):
    """Two notebooks means two kernels; the dock shows the one in front."""
    second = tmp_path / "second.ipynb"
    nbformat.write(
        nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(source="y = 1")]), second
    )
    window = _window(app, notebook_path)
    window.editor.open_file(str(second))
    for _ in range(3):
        QtWidgets.QApplication.processEvents()
    notebooks = [
        window.editor.tab_widget.widget(i)
        for i in range(window.editor.tab_widget.count())
        if isinstance(window.editor.tab_widget.widget(i), NotebookEditor)
    ]
    assert len(notebooks) == 2
    for index in range(window.editor.tab_widget.count()):
        widget = window.editor.tab_widget.widget(index)
        window.editor.tab_widget.setCurrentIndex(index)
        QtWidgets.QApplication.processEvents()
        if isinstance(widget, NotebookEditor):
            assert window._kernel_stack.currentWidget() is widget.terminal


def test_terminal_button_toggles_the_dock_when_hosted(app, notebook_path):
    """A hosted notebook forwards the toggle instead of resizing its splitter."""
    window = _window(app, notebook_path)
    notebooks = [
        window.editor.tab_widget.widget(i)
        for i in range(window.editor.tab_widget.count())
        if isinstance(window.editor.tab_widget.widget(i), NotebookEditor)
    ]
    notebook = notebooks[0]
    window.kernel_dock.show_raised()
    QtWidgets.QApplication.processEvents()
    notebook.terminal_button.setChecked(False)
    QtWidgets.QApplication.processEvents()
    assert not window.kernel_dock.isVisible()
    notebook.terminal_button.setChecked(True)
    QtWidgets.QApplication.processEvents()
    assert window.kernel_dock.isVisible()


def test_kernel_dock_is_disabled_without_a_notebook(app):
    """A plain text tab has no kernel, and the dock says so instead of lying."""
    window = _window(app)
    assert not window.kernel_dock.isEnabled()
    assert window._kernel_stack.currentWidget() is window._kernel_placeholder
