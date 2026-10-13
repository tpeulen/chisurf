"""Render the code editor's notebook headlessly so its layout can be inspected.

Opens a realistic notebook (markdown, code, printed output, an inline matplotlib figure) in the
emtk code editor, runs every cell, shows the Kernel dock and writes PNGs of the window; then the
states a happy-path notebook never shows (a traceback, output long enough to be clamped, a
markdown cell open for editing) and a narrow window. ``--figure`` also writes the guide's
``docs/guides/figures/notebook_editor.png``.

Usage
-----
``python -m build_tools.dev_utils.grab_notebook_editor [--out PREFIX] [--figure]``
"""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import tempfile

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

REPO = pathlib.Path(__file__).resolve().parents[2]


def _write_notebook(path: pathlib.Path) -> pathlib.Path:
    """Write the demo notebook to *path* and return it."""
    from chisurf.plugins.core.code_editor import ipynb

    nb = ipynb.v4.new_notebook()
    nb.metadata.setdefault(
        "kernelspec", {"display_name": "Python 3", "language": "python", "name": "python3"}
    )
    nb.cells = [
        ipynb.v4.new_markdown_cell(source=source)
        if kind == "markdown"
        else ipynb.v4.new_code_cell(source=source)
        for kind, source in NOTEBOOK_SOURCE
    ]
    path.write_text(ipynb.writes(nb), encoding="utf-8")
    return path


def main() -> int:
    """Grab the notebook in the editor window; return a process code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="/tmp/notebook_editor", help="output PNG prefix")
    parser.add_argument("--width", type=int, default=1180)
    parser.add_argument("--height", type=int, default=880)
    parser.add_argument(
        "--figure", action="store_true", help="also write docs/guides/figures/notebook_editor.png"
    )
    args = parser.parse_args()

    from emtk.testing import Driver

    from chisurf.plugins.core.code_editor.gui.editor_app import make_editor_app

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="nbgrab-"))
    nb_path = _write_notebook(tmp / "demo.ipynb")
    app = make_editor_app(str(tmp))
    try:
        doc = app.model.open_file(nb_path)
        notebook = doc.notebook
        if notebook is None:
            print("no notebook tab was created")
            return 1
        notebook.run_all()
        app.editor_gui.docks.focus("kernel")
        driver = Driver(app, (args.width, args.height))
        driver.frame(4)
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        driver.screenshot(f"{out}_window.png")
        print(f"{out}_window.png {args.width}x{args.height}")
        if args.figure:
            target = REPO / "docs/guides/figures/notebook_editor.png"
            shutil.copyfile(f"{out}_window.png", target)
            print(f"wrote {target}")

        # The states a happy-path notebook never shows.
        for _ in range(len(notebook.cells)):
            notebook.remove_cell(0)
        notebook.cells[0].set_type("markdown")
        notebook.cells[0].editor.text = "## Edited markdown\n\nOpened for editing."
        notebook.cells[0].edit_markdown = True
        notebook.add_cell("code", "raise ValueError('a deliberate failure')")
        notebook.add_cell("code", "for i in range(60):\n    print(f'line {i}: ' + 'x' * 60)")
        notebook.add_cell("code", "'a very '  * 3 + 'long single line of source that will not fit'")
        notebook.run_all()
        driver.frame(4)
        driver.screenshot(f"{out}_states.png")
        driver.draw(frames=4, size=(620, args.height))
        driver.screenshot(f"{out}_narrow.png")
        print(f"{out}_states.png {out}_narrow.png")
    finally:
        app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
