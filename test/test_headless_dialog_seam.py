"""Guard: a failure path must not raise a modal dialog nobody can dismiss.

``QMessageBox.critical(...)`` spins its own event loop until a button is
pressed. On the ``offscreen`` / ``minimal`` Qt platforms — every headless test
run, every CI job, every screenshot script — no button can ever be pressed. A
dialog on an ``except`` branch therefore does not report the error: it wedges
the process, and the traceback is never seen. That is strictly worse than a
crash, because a hung run looks like a slow one.

``chisurf/gui/dialogs.py`` (:func:`report_error` / :func:`report_warning` /
:func:`report_information`) always logs and shows the box only when a person
could actually dismiss it; interactive behaviour is unchanged.

Every file still calling a raw ``QMessageBox`` static from inside an ``except``
handler is listed in ``test/headless_dialog_allowlist.txt`` — the migration
tracker. This test fails if a **new** file does so (regression) or if a listed
file has already been migrated (stale entry). The end state is an empty
allow-list.

Note this is deliberately about ``except`` handlers only. A confirmation prompt
on a button click is fine: the user is right there, which is the whole point.
"""

from __future__ import annotations

import ast
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PKG = _ROOT / "chisurf"
_ALLOWLIST = _ROOT / "test" / "headless_dialog_allowlist.txt"
_STATICS = frozenset({"critical", "warning", "information"})


def _load_allowlist() -> set[str]:
    lines = _ALLOWLIST.read_text().splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}


def _is_messagebox_static(node: ast.AST) -> bool:
    """Whether ``node`` is a ``QMessageBox.critical/warning/information`` call."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr not in _STATICS:
        return False
    owner = func.value
    if isinstance(owner, ast.Attribute):          # QtWidgets.QMessageBox.critical
        return owner.attr == "QMessageBox"
    if isinstance(owner, ast.Name):               # QMessageBox.critical
        return owner.id == "QMessageBox"
    return False


def _offenders() -> set[str]:
    """Files calling a blocking ``QMessageBox`` static inside an ``except``."""
    found: set[str] = set()
    for path in _PKG.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), str(path))
        except SyntaxError:
            continue
        for handler in (n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)):
            if any(_is_messagebox_static(n) for n in ast.walk(handler)):
                found.add(path.relative_to(_ROOT).as_posix())
                break
    return found


def test_no_new_blocking_dialog_on_a_failure_path():
    """A new error path must report through ``chisurf.gui.dialogs``, not block."""
    new_offenders = sorted(_offenders() - _load_allowlist())
    assert not new_offenders, (
        "New blocking QMessageBox on an except path — a headless run would hang "
        "there instead of reporting. Use chisurf.gui.dialogs.report_error / "
        "report_warning / report_information:\n  " + "\n  ".join(new_offenders)
    )


def test_allowlist_has_no_stale_entries():
    """A migrated file must be struck from the tracker, so it can never regress."""
    stale = sorted(_load_allowlist() - _offenders())
    assert not stale, (
        "Allow-listed file(s) no longer raise a blocking dialog from an except "
        "handler — remove them from test/headless_dialog_allowlist.txt:\n  "
        + "\n  ".join(stale)
    )
