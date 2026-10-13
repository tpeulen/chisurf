"""Notebooks in the code editor (emtk ``NativeNotebook`` hosted by the editor app).

Ported from the retired Qt ``NotebookEditor`` tests: opening, running, saving and reloading
``.ipynb`` files, the shared shell and its terminal, figures, layout (every surface sized to what
it holds, measured from what was drawn) and the Kernel dock. Driven through the model and the
emtk ``Driver``; runs are synchronous (``run_cell``) so nothing waits on a thread.
"""

from __future__ import annotations

import pathlib

import pytest
from emtk.testing import Driver

from chisurf.plugins.core.code_editor import ipynb
from chisurf.plugins.core.code_editor.gui.editor_app import make_editor_app
from chisurf.plugins.core.code_editor.gui.notebook_app import MAX_OUTPUT_HEIGHT, NativeNotebook
from chisurf.plugins.core.code_editor.shipped_notebooks import shipped_notebooks

FIGURE = (
    "import matplotlib\nmatplotlib.use('Agg')\n"
    "import matplotlib.pyplot as plt\n"
    "fig, ax = plt.subplots()\nax.plot([1, 2, 3])\nfig"
)
SIZE = (1100, 800)


@pytest.fixture
def notebook_path(tmp_path: pathlib.Path) -> pathlib.Path:
    nb = ipynb.v4.new_notebook()
    nb.cells = [
        ipynb.v4.new_code_cell(source="x = 21"),
        ipynb.v4.new_code_cell(source="x + 1"),
        ipynb.v4.new_markdown_cell(source="# A heading"),
        ipynb.v4.new_code_cell(source=FIGURE),
    ]
    path = tmp_path / "sample.ipynb"
    path.write_text(ipynb.writes(nb), encoding="utf-8")
    return path


@pytest.fixture
def app(tmp_path):
    application = make_editor_app(str(tmp_path))
    yield application
    application.close()


def _open(app, path):
    doc = app.model.open_file(path)
    assert doc is not None and doc.notebook is not None
    return doc, doc.notebook


def _run_all(nb: NativeNotebook) -> None:
    for index, cell in enumerate(nb.cells):
        if cell.cell_type == "code":
            nb.run_cell(index)


def _new(source_cells=()) -> NativeNotebook:
    nb = NativeNotebook.new()
    for cell_type, source in source_cells:
        nb.add_cell(cell_type, source)
    return nb


def _draw(app, frames=3, size=SIZE):
    driver = Driver(app, size)
    return driver, driver.frame(frames)


def test_open_ipynb_creates_notebook_tab(app, notebook_path):
    """A ``.ipynb`` path opens as a notebook tab with its cells loaded."""
    doc, nb = _open(app, notebook_path)
    assert pathlib.Path(doc.path).resolve() == notebook_path.resolve()
    assert [cell.cell_type for cell in nb.cells] == ["code", "code", "markdown", "code"]
    assert nb.cells[0].editor.text == "x = 21"
    assert nb.cells[2].editor.text == "# A heading"


def test_language_from_path_is_notebook(app, tmp_path):
    """``.ipynb`` opens as a notebook, ``.py`` as Python source."""
    (tmp_path / "foo.py").write_text("x = 1\n", encoding="utf-8")
    assert app.model.open_file(tmp_path / "foo.py").notebook is None
    assert app.model.open_file(tmp_path / "foo.py").editor.language_name.lower() == "python"
    assert app.model.new_document("foo.ipynb").notebook is not None


def test_cells_share_shell_state(app, notebook_path):
    """Running cells mutates a single in-process shell, top to bottom."""
    _, nb = _open(app, notebook_path)
    _run_all(nb)
    assert nb.shell is not None
    assert nb.shell.user_ns.get("x") == 21
    assert any("22" in str(o.get("data", {}).get("text/plain", "")) for o in nb.cells[1].outputs)


def test_plot_embeds_image_output(app, notebook_path):
    """A cell that produces a figure records an embedded ``image/png`` output."""
    _, nb = _open(app, notebook_path)
    _run_all(nb)
    images = [
        o for cell in nb.cells for o in cell.outputs
        if o.get("output_type") in ("display_data", "execute_result") and "image/png" in o.get("data", {})
    ]
    assert images


def test_save_round_trip_preserves_cells_and_outputs(app, notebook_path, tmp_path):
    """Saving writes a valid ipynb with sources, markdown and recorded outputs."""
    doc, nb = _open(app, notebook_path)
    _run_all(nb)
    out = tmp_path / "out.ipynb"
    assert app.model.save_document(app.model.documents.index(doc), path=out)
    roundtrip = ipynb.read(out)
    assert [c.cell_type for c in roundtrip.cells] == ["code", "code", "markdown", "code"]
    assert roundtrip.cells[0].source == "x = 21"
    assert roundtrip.cells[2].source == "# A heading"
    assert len(roundtrip.cells[3].outputs) >= 1


def test_reload_replays_saved_output(app, notebook_path):
    """Reloading replays the stored outputs onto the cells."""
    doc, nb = _open(app, notebook_path)
    _run_all(nb)
    index = app.model.documents.index(doc)
    assert app.model.save_document(index, path=notebook_path, overwrite=True)
    assert app.model.reload_document(index, discard_changes=True)
    nb = app.model.documents[index].notebook
    assert nb.cells[0].editor.text == "x = 21"
    assert any("image/png" in (o.get("data") or {}) for o in nb.cells[3].outputs)


def test_corrupt_ipynb_falls_back_to_text(app, tmp_path):
    """An unparseable ``.ipynb`` opens as a plain text tab, not a notebook."""
    bad = tmp_path / "broken.ipynb"
    bad.write_text("this is { not json", encoding="utf-8")
    doc = app.model.open_file(bad)
    assert doc.notebook is None
    assert doc.text == "this is { not json"


def test_shipped_notebooks_finds_examples():
    """The shipped-notebooks helper lists the curated examples/notebooks."""
    notebooks = shipped_notebooks()
    assert len(notebooks) > 10
    assert all(path.suffix == ".ipynb" for path in notebooks)


def test_host_save_writes_nbformat(app, notebook_path, tmp_path):
    """The editor's save writes a notebook (format 4), which reopens as a notebook."""
    doc, _nb = _open(app, notebook_path)
    out = tmp_path / "host_save.ipynb"
    assert app.model.save_document(app.model.documents.index(doc), path=out)
    assert ipynb.read(out).nbformat == 4
    fresh = make_editor_app(str(tmp_path))
    try:
        other = fresh.model.open_file(out)
        assert other.notebook is not None
        assert [c.cell_type for c in other.notebook.cells] == ["code", "code", "markdown", "code"]
    finally:
        fresh.close()


def test_markdown_cell_run_renders_without_dirty(app, notebook_path):
    """Running a markdown cell renders it and does not mark the notebook modified."""
    doc, nb = _open(app, notebook_path)
    nb.cells[2].edit_markdown = True
    nb.run_cell(2)
    assert nb.cells[2].edit_markdown is False
    assert not doc.is_modified
    driver, painter = _draw(app)
    assert "A heading" in [t[5] for t in painter.texts]


def test_insert_between_reorders_cells(app):
    """A cell inserted after the first sits between the others; each cell offers an insert."""
    doc = app.model.new_document("Untitled.ipynb")
    nb = doc.notebook
    initial = nb.cells[0]
    first = nb.add_cell("code", "a = 1")
    last = nb.add_cell("code", "b = 2")
    inserted = nb.add_cell("code", "mid", index=1)
    assert nb.cells == [initial, inserted, first, last]
    _driver, painter = _draw(app)
    assert [t[5] for t in painter.texts].count("＋") == 4
    nb.remove_cell(nb.cells.index(inserted))
    assert nb.cells == [initial, first, last]
    _driver, painter = _draw(app)
    assert [t[5] for t in painter.texts].count("＋") == 3


def test_run_cell_mirrors_to_terminal():
    """Executed source and its output are echoed into the notebook's terminal."""
    nb = _new([("code", "print('sum', x + 21)")])
    nb.cells[0].editor.text = "x = 21"
    nb.run_cell(0)
    nb.run_cell(1)
    text = "\n".join(nb.terminal_output)
    assert "print('sum', x + 21)" in text
    assert "sum 42" in text
    assert "In [" in text


def test_run_cell_busy_says_to_wait():
    """A cell requested while the notebook runs is refused with a message, not a deadlock."""
    nb = _new()
    nb.cells[0].editor.text = "1 + 1"
    nb.is_running = True
    assert nb.start_cell(0) is False
    assert "wait for it to finish" in nb.error
    nb.is_running = False


# -- layout: every surface is sized to what it holds -------------------------------------------- #


def _cell_app(app, sources, size=SIZE):
    doc = app.model.new_document("Untitled.ipynb")
    nb = doc.notebook
    nb.cells[0].editor.text = sources[0]
    for source in sources[1:]:
        nb.add_cell("code", source)
    return nb


def test_empty_output_takes_no_height(app):
    """A cell that has not run yet contributes no output height at all."""
    nb = _cell_app(app, ["a = 1"])
    _draw(app)
    assert nb.cells[0].outputs == [] and nb.cells[0].output_height == 0


def test_output_height_tracks_line_count(app):
    """Three lines of output are taller than one, and neither is a fixed block."""
    nb = _cell_app(app, ["print('a')", "print('a')\nprint('b')\nprint('c')"])
    nb.run_cell(0)
    nb.run_cell(1)
    _draw(app)
    one, many = nb.cells[0].output_height, nb.cells[1].output_height
    assert 0 < one < many
    assert many >= 1.5 * one  # two more lines, not a fixed block


def test_long_output_is_clamped_and_scrolls(app):
    """Runaway output stops growing at MAX_OUTPUT_HEIGHT and scrolls inside its cell."""
    nb = _cell_app(app, ["for i in range(200):\n    print(i)"])
    nb.run_cell(0)
    _draw(app)
    assert nb.cells[0].output_height == MAX_OUTPUT_HEIGHT


def test_source_editor_does_not_scroll_while_it_fits(app):
    """A five-line cell shows five lines, not four and a scrollbar."""
    nb = _cell_app(app, ["\n".join(f"a{i} = {i}" for i in range(5))])
    _draw(app)
    from emtk import im  # noqa: F401  (line height of the editor's font)

    height = nb.cells[0].editor_height
    assert height >= 5 * 17.0 and height < 6 * 20.0 + 14.0


def test_figure_is_scaled_into_the_output_width(app):
    """A figure wider than the cell is shrunk, not clipped or scrolled sideways."""
    nb = _cell_app(
        app,
        [FIGURE.replace("plt.subplots()", "plt.subplots(figsize=(9, 3))")],
    )
    nb.run_cell(0)
    driver, painter = _draw(app, size=(520, 700))
    images = [o for o in nb.cells[0].outputs if "image/png" in o.get("data", {})]
    assert images
    texture = next(iter(nb.cells[0]._textures.values()))
    assert texture.width > 520  # the figure is wider than the window ...
    assert nb.cells[0].output_height < texture.height  # ... and was drawn shrunk


def test_returned_figure_does_not_also_print_its_repr(app):
    """``fig`` as the last expression yields the image only, not ``<Figure ...>``."""
    nb = _cell_app(app, [FIGURE])
    nb.run_cell(0)
    _driver, painter = _draw(app)
    assert not any("<Figure" in t[5] for t in painter.texts)


def test_figure_is_not_mirrored_into_the_terminal(app):
    """The plot belongs to the cell that drew it; the terminal gets no image."""
    nb = _cell_app(app, [FIGURE])
    nb.run_cell(0)
    assert any("image/png" in o.get("data", {}) for o in nb.cells[0].outputs)
    assert not any("image/png" in line or "<Figure" in line for line in nb.terminal_output)


def test_traceback_ansi_is_rendered_not_printed(app):
    """A coloured traceback reaches the cell as text in colour, not as escape bytes."""
    nb = _cell_app(app, ["raise ValueError('boom')"])
    nb.run_cell(0)
    _driver, painter = _draw(app)
    drawn = "\n".join(t[5] for t in painter.texts)
    assert "ValueError" in drawn and "boom" in drawn
    assert "\x1b" not in drawn
    assert "[91m" not in drawn and "[0m" not in drawn


def test_rendered_markdown_cell_keeps_its_gutter(app):
    """A rendered markdown cell can still be deleted and re-edited."""
    doc = app.model.new_document("Untitled.ipynb")
    nb = doc.notebook
    nb.cells[0].set_type("markdown")
    nb.cells[0].editor.text = "# Title"
    nb.cells[0].edit_markdown = False
    _driver, painter = _draw(app)
    drawn = [t[5] for t in painter.texts]
    assert "Title" in drawn and "×" in drawn and "Edit Markdown" in drawn


def test_reloading_leaves_no_ghost_cells(app, notebook_path):
    """Reloading replaces the cells; the old ones are not drawn or kept."""
    doc, nb = _open(app, notebook_path)
    first = nb.cells[0]
    nb.reload(notebook_path.read_text(encoding="utf-8"))
    assert first not in nb.cells and len(nb.cells) == 4


def test_toolbar_actions(app):
    """Run all, clear and restart act on every cell without touching the source."""
    nb = _cell_app(app, ["a = 1", "print(a + 1)"])
    nb.run_all()
    assert "2" in "".join(o.get("text", "") for o in nb.cells[1].outputs)
    nb.clear_outputs()
    assert nb.cells[1].outputs == []
    _draw(app)
    assert nb.cells[1].output_height == 0
    nb.restart_shell()
    assert nb.shell is None  # a fresh shell on the next run: no variables left
    assert [c.execution_count for c in nb.cells] == [None, None]
    assert nb.cells[0].editor.text == "a = 1"


def test_terminal_toggle_shows_and_hides_the_terminal():
    """Without a host the Terminal button shows the terminal under the cells, and hides it."""
    nb = _new()
    from emtk.app import ImApp

    host = ImApp(lambda: nb.draw(800, 600))
    driver = Driver(host, (900, 700))
    assert "Notebook terminal" not in [t[5] for t in driver.frame(2).texts]
    driver.click("Terminal")
    assert "Notebook terminal" in [t[5] for t in driver.frame(2).texts]
    driver.click("Hide terminal")
    assert "Notebook terminal" not in [t[5] for t in driver.frame(2).texts]


# -- the kernel terminal is a dock of the editor window, beside Diagnostics and Output ------------ #


def test_the_editor_window_builds_with_its_options(tmp_path):
    """The editor window takes its options (project folder) and builds."""
    application = make_editor_app(str(tmp_path))
    try:
        assert application.model.project_root == tmp_path
    finally:
        application.close()


def test_every_panel_is_a_dock_of_the_window(app):
    """All of the editor's panels are docks of one dock manager, each with its own key."""
    docks = app.editor_gui.docks
    keys = ["files", "symbols", "diagnostics", "output", "kernel", "agent"]
    assert all(key in docks.windows for key in keys)
    assert len(set(keys)) == len(keys)


def test_kernel_dock_sits_with_diagnostics_and_output(app):
    """The kernel terminal is a bottom panel tabbed with the other two."""
    docks = app.editor_gui.docks
    region = docks.region_of("kernel")
    assert region == docks.region_of("output") == docks.region_of("diagnostics")


def test_kernel_dock_holds_the_open_notebooks_terminal(app, notebook_path):
    """The dock shows the notebook's own terminal, on the notebook's shell."""
    _doc, nb = _open(app, notebook_path)
    nb.run_cell(0)
    app.editor_gui.docks.focus("kernel")
    _driver, painter = _draw(app)
    drawn = [t[5] for t in painter.texts]
    assert "Notebook terminal" in drawn and "sample.ipynb" in drawn
    assert any(line.startswith("In [") for line in nb.terminal_output)


def test_kernel_dock_follows_the_active_tab(app, notebook_path, tmp_path):
    """Two notebooks mean two kernels; the dock shows the one in front."""
    second = tmp_path / "second.ipynb"
    second.write_text(
        ipynb.writes(ipynb.v4.new_notebook(cells=[ipynb.v4.new_code_cell(source="y = 1")])),
        encoding="utf-8",
    )
    _open(app, notebook_path)
    _open(app, second)
    app.editor_gui.docks.focus("kernel")
    for doc in list(app.model.documents):
        if doc.notebook is None:
            continue
        app.model.active_index = app.model.documents.index(doc)
        _driver, painter = _draw(app)
        assert doc.name in [t[5] for t in painter.texts]


def test_terminal_button_toggles_the_dock_when_hosted(app, notebook_path):
    """A hosted notebook's Terminal button shows or hides the Kernel dock."""
    _open(app, notebook_path)
    gui = app.editor_gui
    driver, _painter = _draw(app)
    gui.docks.focus("kernel")
    driver.frame(2)
    assert gui.docks.is_shown("kernel")
    driver.click("Terminal")
    assert not gui.docks.is_shown("kernel")
    driver.click("Terminal")
    assert gui.docks.is_shown("kernel")


def test_kernel_dock_is_disabled_without_a_notebook(app):
    """A plain text tab has no kernel, and the dock says so instead of lying."""
    app.editor_gui.docks.focus("kernel")
    _driver, painter = _draw(app)
    assert "Open a notebook to get a kernel terminal." in [t[5] for t in painter.texts]
