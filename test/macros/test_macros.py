"""Macro execution through the main window.

This file began as a *consolidation* of ``test_macro_exec.py`` and
``test_simple_macro.py`` — both were pasted in verbatim, at module scope, and
neither original was removed. So the same code ran three times per session, and
none of it was a test: no ``test_`` functions, no assertions, only prints.

Worse, the pasted body exec'd the **Pong game plugin** as a macro. ``run_macro``
execs with ``__name__`` set to ``"__main__"``, which is exactly the branch a
plugin uses to launch itself standalone, so pong called ``app.exec()`` and the
pytest session stopped dead in Qt's event loop — during *collection*, with no
output and no failing test to blame. See ``test_macro_exec.py`` for the full
account.

What remains here is the part the consolidation genuinely added: how one macro
run relates to the next. Plain-``exec`` semantics live in
``test_simple_macro.py``, and the main-window entry point in
``test_macro_exec.py``.
"""

import pytest
from qtpy import QtWidgets

# Building the ChiSurf main window needs a running QApplication: without one
# Qt does not raise, it aborts the whole process and takes the test session
# with it. The non-GUI suite has no application, so skip at import time.
if QtWidgets.QApplication.instance() is None:
    pytest.skip("the ChiSurf main window needs a QApplication", allow_module_level=True)


@pytest.fixture(scope="module")
def main_window():
    from chisurf.gui.main import Main

    return Main()


def test_exec_executor_sees_the_macro_globals(main_window, tmp_path):
    """``__file__`` reaches the macro, so it can find its own resources."""
    marker = tmp_path / "seen.txt"
    macro = tmp_path / "reports_its_file.py"
    macro.write_text(f"import pathlib\npathlib.Path(r'{marker}').write_text(__file__)\n")

    main_window.onRunMacro(filename=macro, executor="exec")

    assert marker.read_text() == str(macro)


def test_two_macros_do_not_share_state(main_window, tmp_path):
    """Each run gets its own globals.

    Leaking names between macros would make a macro's behaviour depend on
    whatever the user happened to run before it.
    """
    first = tmp_path / "sets_a_name.py"
    first.write_text("LEAKED = 'from the first macro'\n")

    marker = tmp_path / "leak.txt"
    second = tmp_path / "looks_for_it.py"
    second.write_text(
        f"import pathlib\npathlib.Path(r'{marker}').write_text(str('LEAKED' in dir()))\n"
    )

    main_window.onRunMacro(filename=first, executor="exec")
    main_window.onRunMacro(filename=second, executor="exec")

    assert marker.read_text() == "False"
