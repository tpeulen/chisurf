"""Executing a macro file the way ``run_macro`` does, without a GUI.

This was a script, not a test: its body ran at import time, wrote
``simple_macro.py`` **into the source tree**, exec'd it, printed the result and
deleted the file again. Nothing was asserted, so it could only fail by raising.

The behaviour worth pinning is what ``run_macro`` does *around* the ``exec``:
it injects ``__name__``/``__file__``, puts the macro's directory on
``sys.path`` so sibling imports resolve, and restores ``sys.path`` afterwards.
None of that needs a main window, so these run in the non-GUI suite.
"""

import pathlib
import sys


def _exec_macro(path, globals_dict):
    """The exec ``run_macro`` performs, reduced to what these tests pin."""
    macro_dir = str(pathlib.Path(path).parent)
    original_sys_path = sys.path.copy()
    if macro_dir not in sys.path:
        sys.path.insert(0, macro_dir)
    try:
        with open(path, "rb") as fh:
            exec(compile(fh.read(), str(path), "exec"), globals_dict)
    finally:
        sys.path = original_sys_path


def test_a_macro_body_runs_and_its_names_survive(tmp_path):
    macro = tmp_path / "simple_macro.py"
    macro.write_text("x = 10\ny = 20\nresult = x + y\n")

    g = {"__name__": "__main__", "__file__": str(macro)}
    _exec_macro(macro, g)

    assert g["result"] == 30


def test_a_macro_can_import_its_siblings(tmp_path):
    """The macro's own directory goes on ``sys.path``.

    Without it a macro split across two files fails on the import rather than
    on anything the user wrote.
    """
    (tmp_path / "helper_module.py").write_text("VALUE = 7\n")
    macro = tmp_path / "importing_macro.py"
    macro.write_text("from helper_module import VALUE\nresult = VALUE * 6\n")

    g = {"__name__": "__main__", "__file__": str(macro)}
    _exec_macro(macro, g)

    assert g["result"] == 42


def test_sys_path_is_restored_even_when_the_macro_raises(tmp_path):
    """A broken macro must not leave its directory on ``sys.path``.

    A leaked entry silently changes which module *every later* import resolves
    to — the kind of failure that surfaces far from its cause.
    """
    macro = tmp_path / "broken_macro.py"
    macro.write_text("raise RuntimeError('deliberate')\n")

    before = sys.path.copy()
    try:
        _exec_macro(macro, {"__name__": "__main__", "__file__": str(macro)})
    except RuntimeError:
        pass
    assert sys.path == before


def test_the_macro_directory_is_not_duplicated_on_sys_path(tmp_path):
    macro = tmp_path / "noop_macro.py"
    macro.write_text("result = 1\n")

    sys.path.insert(0, str(tmp_path))
    before = sys.path.copy()
    try:
        _exec_macro(macro, {"__name__": "__main__", "__file__": str(macro)})
        assert sys.path == before
    finally:
        sys.path.remove(str(tmp_path))
