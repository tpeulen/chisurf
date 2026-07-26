"""Guard: every message box in ChiSurf goes through the one class.

``QMessageBox.critical(...)`` spins its own event loop until a button is
pressed. On the ``offscreen`` / ``minimal`` Qt platforms — every headless test
run, every CI job, every screenshot script — no button can ever be pressed. A
dialog on an ``except`` branch therefore does not report the error: it wedges
the process, and the traceback is never seen. That is strictly worse than a
crash, because a hung run looks like a slow one. A ``question`` box is worse
still: the answer it never gets is the one deciding whether a file is
overwritten or a record deleted.

:class:`chisurf.gui.dialogs.ChiSurfMessageBox` — used as ``dialogs.error`` /
``dialogs.warning`` / ``dialogs.information`` / ``dialogs.question`` /
``dialogs.confirm`` / ``dialogs.choice`` — always logs, shows the box only when
a person could dismiss it, and otherwise returns the caller-declared safe
default. Interactive behaviour is unchanged.

The migration is complete, so the rule is now the strong one: **no raw
``QMessageBox`` static and no hand-built ``QMessageBox`` instance anywhere in
``chisurf/``** (test files excepted — they may script a dialog). The two
allow-lists exist so a deliberate exception is a visible, reviewed line rather
than a silent regression; both are expected to stay empty.
"""

from __future__ import annotations

import ast
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PKG = _ROOT / "chisurf"
_ALLOWLIST = _ROOT / "test" / "headless_dialog_allowlist.txt"
_STATICS = frozenset({"critical", "warning", "information", "question", "about"})

#: The one module allowed to build a ``QMessageBox``: the class itself.
_IMPLEMENTATION = "chisurf/gui/dialogs.py"


def _load_allowlist() -> set[str]:
    lines = _ALLOWLIST.read_text().splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}


def _is_test(path: pathlib.Path) -> bool:
    """Whether *path* is test code (free to script dialogs)."""
    parts = set(path.parts)
    return "test" in parts or "tests" in parts or path.name.startswith("test_")


def _names(node: ast.AST) -> str | None:
    """Return the attribute/name spelling of a call target's owner."""
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _is_messagebox_static(node: ast.AST) -> bool:
    """Whether ``node`` is a blocking ``QMessageBox.<static>`` call."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr not in _STATICS:
        return False
    return _names(func.value) == "QMessageBox"


def _is_messagebox_construction(node: ast.AST) -> bool:
    """Whether ``node`` builds a ``QMessageBox`` instance (also modal)."""
    return isinstance(node, ast.Call) and _names(node.func) == "QMessageBox"


def _sources():
    """Yield ``(relative_path, parsed_tree)`` for every non-test module."""
    for path in sorted(_PKG.rglob("*.py")):
        if _is_test(path):
            continue
        rel = path.relative_to(_ROOT).as_posix()
        if rel == _IMPLEMENTATION:
            continue
        try:
            yield rel, ast.parse(path.read_text(encoding="utf-8", errors="ignore"), str(path))
        except SyntaxError:
            continue


def _offenders() -> set[str]:
    """Files that raise a ``QMessageBox`` themselves instead of via the class."""
    found: set[str] = set()
    for rel, tree in _sources():
        for node in ast.walk(tree):
            if _is_messagebox_static(node) or _is_messagebox_construction(node):
                found.add(rel)
                break
    return found


def test_no_raw_message_box_outside_the_one_class():
    """A box built by hand blocks head-lessly and is styled its own way."""
    new_offenders = sorted(_offenders() - _load_allowlist())
    assert not new_offenders, (
        "Raw QMessageBox outside chisurf/gui/dialogs.py — a headless run would "
        "hang there instead of reporting, and the box would not match the rest "
        "of the app. Use chisurf.gui.dialogs (error / warning / information / "
        "question / confirm / choice):\n  " + "\n  ".join(new_offenders)
    )


def test_allowlist_has_no_stale_entries():
    """A migrated file must be struck from the tracker, so it can never regress."""
    stale = sorted(_load_allowlist() - _offenders())
    assert not stale, (
        "Allow-listed file(s) no longer raise a raw QMessageBox — remove them "
        "from test/headless_dialog_allowlist.txt:\n  " + "\n  ".join(stale)
    )


def test_progress_is_reported_through_the_one_class():
    """A hand-built ``QProgressDialog`` is the same headless hang as a message box.

    ``chisurf.gui.progress.ChiSurfProgress`` picks an inline AutoForm bar, the
    shell's status bar, a modal dialog or the log, depending on where the work
    was started from — so the caller never has to decide, and never blocks a run
    with nobody at the keyboard.
    """
    offenders: set[str] = set()
    for rel, tree in _sources():
        if rel in {"chisurf/gui/progress.py", "chisurf/gui/widgets/progress.py"}:
            continue  # the implementation and its modal backend
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _names(node.func) == "QProgressDialog":
                offenders.add(rel)
                break
    assert not offenders, (
        "Raw QProgressDialog — use chisurf.gui.progress.ChiSurfProgress so the "
        "work reports into the panel, the status bar or the log as appropriate:"
        "\n  " + "\n  ".join(sorted(offenders))
    )
