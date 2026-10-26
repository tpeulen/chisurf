"""No plugin UI asks the user for an input file: data enters ChiSurf through one drop.

The owner's rule (okf/specs/data-workspace.md, *Acceptance*): the shell's drop is the only place
the UI takes an input file; a plugin takes its input from the Datasets workspace (its manifest's
``accepts[].from_workspace``, chisurf.core.plugin.workspace_input). Saving and exporting outputs
keep their save dialogs, and the API and CLI keep their file paths.

This scans the plugins' GUI code (everything under ``chisurf/plugins`` except tests and CLIs) for
the three ways an input file used to come in:

* ``dialog`` -- an emtk ``FileDialog`` that is not a save dialog, or a helper asked for one
  (``choose_file``, ``ask``, ``open_file_dialog``, ... called with mode ``"open"``/``"folder"``);
* ``drop`` -- a drop hook (``files_dropped``, ``on_files_dropped``, ``on_paths_dropped``,
  ``take_drop``): files dropped on a plugin go to the workspace through the shell;
* ``mmfdb`` -- the MMFDB ``DatasetPicker``, which hands a plugin a local file path.

A dialog that is not an input -- it repairs a link, or names where an output goes -- carries a
``# not-input: <reason>`` comment on its line or the line above, and its file is named with that
reason in :data:`NOT_INPUT` here: the exception is explicit, reviewed, and does not spread.

``test/input_file_dialog_allowlist.txt`` lists what is still there (``<file>: <kind>``). It only
**shrinks**: a migrated plugin is struck from it, a new entry fails, and a stale entry (the code
is gone) fails too, so the list stays the truth.
"""

from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "chisurf" / "plugins"
ALLOWLIST = ROOT / "test" / "input_file_dialog_allowlist.txt"

DROP_HOOKS = {"files_dropped", "on_files_dropped", "on_paths_dropped", "take_drop"}
#: Helpers that open a file dialog for their caller; asked for an input when called with an open
#: or folder mode (a save mode is fine).
DIALOG_HELPERS = {
    "choose_file", "ask", "open_file_dialog", "choose_open", "choose_folder", "_ask_path",
    "ask_path", "_open_dialog", "open_dialog", "_dialog",
}
INPUT_MODES = {"open", "folder"}
PRAGMA = "# not-input:"
#: Files whose ``# not-input:`` dialogs are allowed for good, with the reason. Not a worklist.
NOT_INPUT = {
    "chisurf/plugins/core/project_data/gui/app.py": (
        "Locate missing data: 'Search in folder…' / 'Use this file' find the moved original of a "
        "linked dataset -- a repair of the project, not data entering it."
    ),
    "chisurf/plugins/fluorescence_decay/lltf/gui/app.py": (
        "Output directory: where the fit's JSON and plot are written, an output."
    ),
}


def _skipped(path: pathlib.Path) -> bool:
    parts = set(path.relative_to(PLUGINS).parts)
    return bool(parts & {"test", "tests", "cli", "cookiecutter-chisurf-plugin"}) or (
        path.name.startswith("test_")
    )


def _mode_of(call: ast.Call, positional_index: int) -> str | None:
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            return str(kw.value.value)
    if len(call.args) > positional_index:
        arg = call.args[positional_index]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    return None


def _name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _pragma(lines: list[str], lineno: int) -> bool:
    """Whether the call on *lineno* (1-based) is marked ``# not-input:`` on its line or above."""
    return any(PRAGMA in lines[i] for i in (lineno - 1, lineno - 2) if 0 <= i < len(lines))


def findings_of(path: pathlib.Path, *, pragmas: list[int] | None = None) -> set[str]:
    """``{"dialog", "drop", "mmfdb"}`` -- which of the three input routes *path* still has.

    Dialogs marked ``# not-input:`` are left out and their line numbers appended to *pragmas*.
    """
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
    except (SyntaxError, UnicodeDecodeError):
        return set()
    lines = text.splitlines()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in DROP_HOOKS:
            found.add("drop")
        if not isinstance(node, ast.Call):
            continue
        name = _name(node.func)
        if name in ("FileDialog", *DIALOG_HELPERS) and _pragma(lines, node.lineno):
            if pragmas is not None:
                pragmas.append(node.lineno)
            continue
        if name == "FileDialog":
            mode = _mode_of(node, 1)
            if mode in (None, *INPUT_MODES):  # the dialog opens for reading unless told to save
                found.add("dialog")
        elif name in DIALOG_HELPERS:
            mode = _mode_of(node, 1)
            if mode in INPUT_MODES:
                found.add("dialog")
        elif name == "DatasetPicker":
            found.add("mmfdb")
    return found


def current_entries() -> set[str]:
    """Every ``<file>: <kind>`` the plugins' GUI code holds today."""
    entries: set[str] = set()
    for path in sorted(PLUGINS.rglob("*.py")):
        if _skipped(path):
            continue
        for kind in findings_of(path):
            entries.add(f"{path.relative_to(ROOT).as_posix()}: {kind}")
    return entries


def allowed_entries() -> set[str]:
    return {
        line.strip()
        for line in ALLOWLIST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_no_new_input_file_dialog_drop_hook_or_mmfdb_path_in_a_plugin_ui():
    new = sorted(current_entries() - allowed_entries())
    assert not new, (
        "A plugin UI asks for an input file. Data enters ChiSurf by the one drop and lives in the "
        "workspace: declare accepts[].from_workspace in the manifest and use the generated Input "
        "section (chisurf.core.plugin.workspace_input). New:\n  " + "\n  ".join(new)
    )


def test_the_allowlist_only_shrinks():
    stale = sorted(allowed_entries() - current_entries())
    assert not stale, (
        "These are gone from the code -- strike them from test/input_file_dialog_allowlist.txt:\n  "
        + "\n  ".join(stale)
    )


def test_a_not_input_dialog_is_only_allowed_where_the_guard_names_its_reason():
    marked = {}
    for path in sorted(PLUGINS.rglob("*.py")):
        if _skipped(path):
            continue
        lines: list[int] = []
        findings_of(path, pragmas=lines)
        if lines:
            marked[path.relative_to(ROOT).as_posix()] = lines
    unexplained = sorted(set(marked) - set(NOT_INPUT))
    assert not unexplained, (
        "'# not-input:' dialogs in files NOT_INPUT does not name (a dialog that adds data is an "
        f"input; a repair or output dialog is named there with its reason): {unexplained}"
    )
    assert not sorted(set(NOT_INPUT) - set(marked)), "NOT_INPUT names a file with no marked dialog"


def test_the_scanner_sees_each_route():
    import textwrap

    def scan(code: str) -> set[str]:
        tmp = PLUGINS / "_scanner_probe.py"
        tmp.write_text(textwrap.dedent(code), encoding="utf-8")
        try:
            return findings_of(tmp)
        finally:
            tmp.unlink()

    assert scan("FileDialog('Open', mode='open')") == {"dialog"}
    assert scan("FileDialog('Open')") == {"dialog"}
    assert scan("FileDialog('Save', mode='save')") == set()
    assert scan("self.ask('Open', 'open', filters, cb)") == {"dialog"}
    assert scan("self.ask('Save', 'save', filters, cb)") == set()
    assert scan("class A:\n    def on_paths_dropped(self, paths):\n        pass") == {"drop"}
    assert scan("DatasetPicker(kinds=['raw_data'])") == {"mmfdb"}
    assert scan("# not-input: repair\nFileDialog('Find', mode='folder')") == set()
