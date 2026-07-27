"""The Demo menu, and the script editor behind it.

Two things that turned out to be the same thing:

* a way to **try ChiMOL without a lot of clicking** -- pick a demo, watch it run;
* a **development harness**. Every demo is a plain ChiMOL script, one command per
  line, so a demo that stops working is a command that stopped working. Written
  in the command language rather than in Python on purpose: that makes them a
  test of *language parity with PyMOL* rather than of the internals, and they
  double as documentation that runs.

The editor
----------
"Open in editor" hands the script to **chisurf's code editor** when chisurf is
available, so a demo is a starting point to edit rather than a fixed recital. When
it is not -- ChiMOL running standalone -- a small editor ships here rather than
the menu entry going dead. It is deliberately plain: open, edit, save, run. The
point is that the path exists, not that it competes with a real editor.
"""

from __future__ import annotations

import pathlib

from qtpy import QtCore, QtGui, QtWidgets

#: Where the shipped scripts live.
DEMO_DIR = pathlib.Path(__file__).resolve().parent.parent / "demos"

#: Search path for the structures a demo names, so the scripts can say
#: ``load 148l.pdb`` rather than carrying an absolute path that only works on one
#: machine. Tried in order.
_DATA_DIRS = (
    pathlib.Path(__file__).resolve().parents[5]
    / "test" / "data" / "atomic_coordinates" / "pdb_files",
    pathlib.Path(__file__).resolve().parents[5]
    / "test" / "data" / "atomic_coordinates" / "trajectory" / "h5-file",
)

#: Demo order and one-line descriptions. The order is a tour: what the viewer
#: looks like, then how to drive it, then what it can do that PyMOL cannot.
DEMOS: tuple[tuple[str, str, str], ...] = (
    ("cartoon", "Cartoon and colour", "A structure, coloured N to C."),
    ("selections", "Selections", "The PyMOL selection grammar, in colour."),
    ("representations", "Every representation", "Including ChiMOL's own."),
    ("lighting", "Lighting presets", "simple, soft, flat, default in turn."),
    ("publication", "Publication figure", "Flat shading with silhouettes."),
    ("trajectory", "Trajectory + intra_fit", "Why fitting makes a movie readable."),
    ("measure", "Measuring", "Surface area, bonds, hydrogens."),
)


def resolve_structure(name: str) -> str:
    """Find a structure a demo script names, or return the name unchanged.

    Scripts say ``load 148l.pdb`` so they read like something a person would
    type; this is what lets that work from any working directory.
    """
    candidate = pathlib.Path(name)
    if candidate.is_absolute() and candidate.exists():
        return str(candidate)
    for directory in _DATA_DIRS:
        found = directory / candidate.name
        if found.exists():
            return str(found)
    return name


def demo_path(key: str) -> pathlib.Path:
    """Path of a shipped demo script."""
    return DEMO_DIR / f"{key}.pml"


def read_demo(key: str) -> str:
    """The text of a shipped demo, or an empty string when it is missing."""
    path = demo_path(key)
    try:
        return path.read_text()
    except OSError:
        return ""


class ScriptEditor(QtWidgets.QDialog):
    """A plain editor for ChiMOL scripts: open, edit, save, run.

    Used only when chisurf's own code editor is unavailable. It exists so the
    "edit this demo" path is never a dead menu entry in a standalone ChiMOL, not
    to compete with a real editor -- which is why it has four buttons and no
    settings.
    """

    def __init__(self, parent=None, *, run_script=None, text: str = "",
                 path: pathlib.Path | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ChiMOL script")
        self.resize(720, 520)
        self._run_script = run_script
        self._path = path

        self.editor = QtWidgets.QPlainTextEdit(self)
        self.editor.setPlainText(text)
        font = QtGui.QFont("Menlo")
        font.setStyleHint(QtGui.QFont.Monospace)
        font.setPointSize(11)
        self.editor.setFont(font)
        self.editor.setTabStopDistance(4 * self.editor.fontMetrics().horizontalAdvance(" "))

        buttons = QtWidgets.QHBoxLayout()
        for label, slot in (
            ("Open…", self.open_file),
            ("Save", self.save_file),
            ("Run", self.run),
        ):
            button = QtWidgets.QPushButton(label, self)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        close = QtWidgets.QPushButton("Close", self)
        close.clicked.connect(self.reject)
        buttons.addWidget(close)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.editor, 1)
        layout.addLayout(buttons)

    def open_file(self) -> None:
        """Load a script from disk."""
        name, _filter = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open ChiMOL script", str(DEMO_DIR),
            "ChiMOL scripts (*.pml *.cmd *.txt);;All files (*)",
        )
        if not name:
            return
        self._path = pathlib.Path(name)
        try:
            self.editor.setPlainText(self._path.read_text())
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Open failed", str(exc))

    def save_file(self) -> None:
        """Save, asking for a name when there is not one yet."""
        if self._path is None:
            name, _filter = QtWidgets.QFileDialog.getSaveFileName(
                self, "Save ChiMOL script", str(DEMO_DIR),
                "ChiMOL scripts (*.pml);;All files (*)",
            )
            if not name:
                return
            self._path = pathlib.Path(name)
        try:
            self._path.write_text(self.editor.toPlainText())
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Save failed", str(exc))

    def run(self) -> None:
        """Run what is in the editor, line by line."""
        if self._run_script is None:
            return
        self._run_script(self.editor.toPlainText())


def open_script_editor(window, text: str = "", path=None):
    """Open a script editor: chisurf's if it is there, the shipped one if not.

    Parameters
    ----------
    window : MolViewPluginWindow
        Parent, and the source of the command runner.
    text : str, optional
        Initial contents.
    path : pathlib.Path, optional
        File the text came from.

    Returns
    -------
    QWidget
        Whichever editor was opened.
    """
    runner = getattr(window, "run_script_text", None)

    try:
        from chisurf.plugins.core.code_editor import CodeEditor  # type: ignore

        editor = CodeEditor(parent=window)
        if hasattr(editor, "setPlainText"):
            editor.setPlainText(text)
        elif hasattr(editor, "set_text"):
            editor.set_text(text)
        editor.show()
        return editor
    except Exception:
        # chisurf's editor is not available -- standalone ChiMOL, or a version
        # whose editor takes a different shape. Ship our own rather than let the
        # menu entry do nothing.
        editor = ScriptEditor(window, run_script=runner, text=text, path=path)
        editor.show()
        return editor


def build_demo_menu(window, menu_bar) -> QtWidgets.QMenu:
    """Add the Demo menu to a window's menu bar.

    Each entry runs a shipped script; the last two open one for editing and open
    the folder, so a demo is a starting point rather than a fixed recital.
    """
    menu = menu_bar.addMenu("&Demo")
    window._demo_actions = []

    for key, title, description in DEMOS:
        action = menu.addAction(title)
        action.setStatusTip(description)
        action.setToolTip(description)
        action.triggered.connect(
            lambda _checked=False, k=key: window.run_demo(k)
        )
        window._demo_actions.append(action)

    menu.addSeparator()
    edit_action = menu.addAction("Edit a demo script…")
    edit_action.setToolTip(
        "Open a demo in the script editor -- a demo is a starting point, not a "
        "fixed recital."
    )
    edit_action.triggered.connect(lambda: window.edit_demo_script())
    window._demo_actions.append(edit_action)

    new_action = menu.addAction("New script…")
    new_action.triggered.connect(lambda: window.edit_demo_script(blank=True))
    window._demo_actions.append(new_action)

    menu.setToolTipsVisible(True)
    return menu


__all__ = [
    "DEMOS",
    "DEMO_DIR",
    "ScriptEditor",
    "build_demo_menu",
    "demo_path",
    "open_script_editor",
    "read_demo",
    "resolve_structure",
]
