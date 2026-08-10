"""Render the notebook editor headlessly so its layout can be inspected.

Opens a realistic notebook (markdown, code, printed output, an inline
matplotlib figure), runs every cell, and writes PNGs of the notebook widget on
its own and of the full ``CodeEditor`` window that hosts it.

Usage
-----
``QT_QPA_PLATFORM=offscreen python -m build_tools.dev_utils.grab_notebook_editor``
"""

from __future__ import annotations

import argparse
import os
import pathlib
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

NOTEBOOK_SOURCE = [
    (
        "markdown",
        "# Photon-stream demo\n\n"
        "This notebook shows a **short** analysis: a few numbers, a printed\n"
        "table, and a figure. It exists to exercise the notebook editor's\n"
        "layout with realistic content.\n",
    ),
    (
        "code",
        "import numpy as np\n\nt = np.linspace(0, 10, 512)\ndecay = np.exp(-t / 2.4)\ndecay[:4]",
    ),
    (
        "code",
        "for name, value in [('tau', 2.4), ('n', decay.size), ('peak', decay.max())]:\n"
        "    print(f'{name:>6s} = {value}')",
    ),
    ("markdown", "## The figure\n\nA plot should sit directly under the cell that made it."),
    (
        "code",
        "import matplotlib.pyplot as plt\n\n"
        "fig, ax = plt.subplots(figsize=(4.2, 2.6))\n"
        "ax.semilogy(t, decay, lw=1.5)\n"
        "ax.set_xlabel('time / ns')\n"
        "ax.set_ylabel('intensity')\n"
        "fig.tight_layout()\n"
        "fig",
    ),
    ("code", "x = 21\nx * 2"),
]


def _write_notebook(path: pathlib.Path) -> pathlib.Path:
    """Write the demo notebook to *path* and return it."""
    import nbformat

    nb = nbformat.v4.new_notebook()
    nb.metadata.setdefault(
        "kernelspec", {"display_name": "Python 3", "language": "python", "name": "python3"}
    )
    cells = []
    for kind, source in NOTEBOOK_SOURCE:
        if kind == "markdown":
            cells.append(nbformat.v4.new_markdown_cell(source=source))
        else:
            cells.append(nbformat.v4.new_code_cell(source=source))
    nb.cells = cells
    nbformat.write(nb, str(path))
    return path


def main() -> int:
    """Grab the notebook editor and its host window; return a process code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="/tmp/notebook_editor", help="output PNG prefix")
    parser.add_argument("--width", type=int, default=1180)
    parser.add_argument("--height", type=int, default=880)
    args = parser.parse_args()

    from qtpy import QtCore, QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    from chisurf.plugins.core.code_editor.editor import CodeEditor
    from chisurf.plugins.core.code_editor.notebook_editor import NotebookEditor

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="nbgrab-"))
    nb_path = _write_notebook(tmp / "demo.ipynb")

    host = CodeEditor(can_load=False, enable_lsp=None)
    host.resize(args.width, args.height)
    host.show()
    host.open_file(str(nb_path))

    notebook = None
    for index in range(host.tab_widget.count()):
        widget = host.tab_widget.widget(index)
        if isinstance(widget, NotebookEditor):
            notebook = widget
            host.tab_widget.setCurrentIndex(index)
            break
    if notebook is None:
        print("no notebook tab was created")
        return 1

    for _ in range(3):
        app.processEvents()
    notebook.run_all()
    for _ in range(6):
        app.processEvents()
        QtCore.QThread.msleep(20)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    host.grab().save(f"{out}_host.png")
    notebook.grab().save(f"{out}_widget.png")

    # A tall grab of the scrolled content shows every cell at once.
    container = notebook.container
    container.grab().save(f"{out}_cells.png")

    print(f"{out}_host.png   {host.width()}x{host.height()}")
    print(f"{out}_widget.png {notebook.width()}x{notebook.height()}")
    print(f"{out}_cells.png  {container.width()}x{container.height()}")

    _grab_edge_cases(app, host, notebook, out, args)
    return 0


def _grab_edge_cases(app, host, notebook, out: pathlib.Path, args) -> None:
    """Grab the states a happy-path notebook never shows.

    A traceback, output long enough to be clamped and scroll, a markdown cell
    opened for editing, the terminal hidden, and a narrow window (which brings
    horizontal scrollbars into the source editors).
    """
    from qtpy import QtCore

    for cell in list(notebook.cells()):
        notebook.remove_cell(cell)
    notebook.add_cell(cell_type="markdown", source="## Edited markdown\n\nDouble-clicked open.")
    notebook.cells()[-1]._set_edit_mode(True)
    notebook.add_cell(cell_type="code", source="raise ValueError('a deliberate failure')")
    notebook.add_cell(
        cell_type="code",
        source="for i in range(60):\n    print(f'line {i}: ' + 'x' * 60)",
    )
    notebook.add_cell(
        cell_type="code",
        source="'a very '  * 3 + 'long single line of source that will not fit'",
    )
    notebook.terminal_button.setChecked(False)
    for _ in range(3):
        app.processEvents()
    notebook.run_all()
    for _ in range(6):
        app.processEvents()
        QtCore.QThread.msleep(20)
    host.grab().save(f"{out}_states.png")
    notebook.container.grab().save(f"{out}_states_cells.png")

    host.resize(560, args.height)
    for _ in range(6):
        app.processEvents()
        QtCore.QThread.msleep(20)
    host.grab().save(f"{out}_narrow.png")
    print(f"{out}_states.png {host.width()}x{host.height()}")
    print(f"{out}_narrow.png {host.width()}x{host.height()}")


if __name__ == "__main__":
    raise SystemExit(main())
