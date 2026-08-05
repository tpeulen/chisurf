"""The console engine, exercised without Qt.

This suite is the acceptance bar for "at least as good as qtconsole". It runs
with no ``QApplication`` at all -- see :func:`test_engine_imports_no_qt`, which
enforces that -- because the console it replaces put execution inside an
in-process Jupyter kernel and could not be tested this way.
"""

from __future__ import annotations

import ast
import pathlib
import sys
import tempfile

import pytest

from chisurf.core.console import transform
from chisurf.core.console.history import HistoryManager
from chisurf.core.console.shell import Shell

CONSOLE_PACKAGE = pathlib.Path(__file__).resolve().parents[2] / "chisurf" / "core" / "console"


class Recorder:
    """Collects everything a shell writes, so assertions read naturally."""

    def __init__(self) -> None:
        self.chunks: list[tuple[str, str]] = []
        self.displays: list[tuple[dict, str]] = []

    def write(self, name: str, text: str) -> None:
        """Record a stream write.

        Parameters
        ----------
        name : str
        text : str
        """
        self.chunks.append((name, text))

    def display(self, data: dict, metadata: dict, kind: str, count: int | None) -> None:
        """Record a display bundle.

        Parameters
        ----------
        data : dict
        metadata : dict
        kind : str
        count : int or None
        """
        self.displays.append((data, kind))

    @property
    def stdout(self) -> str:
        """str: Everything written to stdout."""
        return "".join(t for n, t in self.chunks if n == "stdout")

    @property
    def stderr(self) -> str:
        """str: Everything written to stderr."""
        return "".join(t for n, t in self.chunks if n == "stderr")

    @property
    def results(self) -> list[str]:
        """list of str: The ``text/plain`` of each displayed result."""
        return [d.get("text/plain") for d, _k in self.displays]

    def clear(self) -> None:
        """Forget everything recorded so far."""
        self.chunks.clear()
        self.displays.clear()


@pytest.fixture()
def shell():
    """Return a shell with no persistent history and a recorder attached.

    Returns
    -------
    Shell
    """
    recorder = Recorder()
    instance = Shell(
        write=recorder.write,
        display=recorder.display,
        history=HistoryManager(path=False),
    )
    instance.recorder = recorder
    return instance


def run(shell, source: str):
    """Run *source*, clearing the recorder first.

    Parameters
    ----------
    shell : Shell
    source : str

    Returns
    -------
    ExecutionResult
    """
    shell.recorder.clear()
    return shell.run_cell(source)


# ----------------------------------------------------------------------
# the guard that makes this suite meaningful
# ----------------------------------------------------------------------

def test_engine_imports_no_qt():
    """No engine module may import Qt.

    The whole point of splitting the engine out of the widget is that it can be
    reasoned about and tested without a GUI. A single ``from qtpy import ...``
    would quietly undo that -- the suite would still pass, on a developer
    machine with Qt installed, while the engine had silently become
    untestable head-lessly and unusable from ``csc`` or the server.
    """
    offenders = []
    for path in sorted(CONSOLE_PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                root = name.split(".")[0]
                if root in ("qtpy", "PyQt5", "PyQt6", "PySide2", "PySide6"):
                    offenders.append(f"{path.name}:{node.lineno} imports {name}")
    assert not offenders, "the console engine must stay Qt-free: " + "; ".join(offenders)


def test_suite_runs_without_a_qapplication():
    """Guard that this module really did not need Qt to get here."""
    loaded = [m for m in sys.modules if m.split(".")[0] in ("PyQt5", "PyQt6", "PySide2", "PySide6")]
    if loaded:
        pytest.skip("another test in this process already imported Qt")
    assert "qtpy" not in sys.modules


# ----------------------------------------------------------------------
# completeness
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("1+1", "complete"),
        ("x = 5", "complete"),
        ("d = {1: 2}", "complete"),
        ("x = (1,\n2)", "complete"),
        ("for i in range(3):", "incomplete"),
        ("for i in range(3):\n    print(i)", "incomplete"),
        ("for i in range(3):\n    print(i)\n\n", "complete"),
        ("def f():\n    return 1\n\n", "complete"),
        ("d = {", "incomplete"),
        ("'''abc", "incomplete"),
        ("if x:\n    a=1\nelse:", "incomplete"),
        ("@dec", "incomplete"),
        ("x ===== 3", "invalid"),
    ],
)
def test_check_complete(source, expected):
    """A partially typed cell is classified the way a REPL should."""
    status, _indent = transform.check_complete(source)
    assert status == expected


def test_check_complete_matches_cpython_on_a_dangling_operator():
    """``1 +`` is a syntax error, not an incomplete cell.

    Worth pinning because the intuition goes the other way: the expression
    obviously *could* be continued. CPython's own REPL reports it immediately,
    and a console that waited for more input instead would swallow the error.
    """
    assert transform.check_complete("1 +")[0] == "invalid"


@pytest.mark.parametrize(
    ("source", "indent"),
    [
        ("for i in range(3):", 4),
        ("for i in range(3):\n    x = 1", 4),
        ("def f():\n    return 1", 0),
        ("if a:\n    if b:", 8),
    ],
)
def test_indent_hint(source, indent):
    """The next line is prefilled to the right depth."""
    assert len(transform.check_complete(source)[1]) == indent


# ----------------------------------------------------------------------
# transformation
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    ("typed", "fragment"),
    [
        ("%run -i 'x.py'", "run_line_magic('run'"),
        ("x = %timeit -o f()", "x = __chinsole__.run_line_magic('timeit'"),
        ("!ls -l", "system('ls -l')"),
        ("files = !ls", "getoutput('ls')"),
        ("!!ls", "getoutput('ls')"),
        ("obj?", "pinfo('obj', detail_level=0)"),
        ("obj??", "pinfo('obj', detail_level=1)"),
    ],
)
def test_transform_line(typed, fragment):
    """Each interactive escape becomes an ordinary call."""
    assert fragment in transform.transform_line(typed)


def test_magics_keep_their_indentation():
    """A magic inside a block stays inside it.

    Line-oriented transformation is what lets ``%time`` be used in a loop body;
    a cell-oriented one would move the call to column zero and change the
    program.
    """
    out = transform.transform_cell("for i in range(2):\n    %time f()")
    assert out.splitlines()[1].startswith("    __chinsole__")


def test_strip_prompts_leaves_ordinary_text_alone():
    """Pasting normal code must never be altered."""
    assert transform.strip_prompts("x = 1\ny = 2") == "x = 1\ny = 2"


def test_strip_prompts_removes_doctest_prompts():
    """Pasting a doctest snippet works."""
    assert transform.strip_prompts(">>> x = 1\n>>> y = 2") == "x = 1\ny = 2"


# ----------------------------------------------------------------------
# execution
# ----------------------------------------------------------------------

def test_trailing_expression_is_echoed(shell):
    """A trailing expression prints its value, like a real REPL."""
    run(shell, "1+1")
    assert shell.recorder.results == ["2"]


def test_none_is_not_echoed(shell):
    """``None`` is suppressed."""
    run(shell, "None")
    assert shell.recorder.results == []


def test_statement_is_not_echoed(shell):
    """An assignment produces no output."""
    run(shell, "x = 41")
    assert shell.recorder.results == []


def test_statements_then_expression(shell):
    """A cell's leading statements run and its trailing expression echoes."""
    run(shell, "a = 2\nb = 3\na * b")
    assert shell.recorder.results == ["6"]


def test_semicolon_suppresses_output(shell):
    """A trailing semicolon silences the echo."""
    run(shell, "5+5;")
    assert shell.recorder.results == []


def test_underscore_history(shell):
    """``_``, ``__`` and ``___`` rotate."""
    for source in ("1", "2", "3"):
        run(shell, source)
    assert shell.user_ns["_"] == 3
    assert shell.user_ns["__"] == 2
    assert shell.user_ns["___"] == 1


def test_out_cache(shell):
    """Results are available as ``Out[n]`` and ``_n``."""
    run(shell, "6*7")
    assert shell.Out[1] == 42
    assert shell.user_ns["_1"] == 42


def test_cache_size_zero_disables_out_but_still_displays(shell):
    """``get_ipython().cache_size = 0`` stops ``Out`` pinning objects.

    This exact line is in ChiSurf's shipped ``console_init``, so it is on every
    installation. It exists to stop the console holding on to large arrays; if
    the assignment were accepted and ignored, the leak it prevents would be
    back and nothing would say so.
    """
    run(shell, "get_ipython().cache_size = 0")
    run(shell, "99")
    assert shell.Out == {}
    assert shell.recorder.results == ["99"]


def test_namespace_is_shared_between_globals_and_locals(shell):
    """A comprehension can see names from an earlier cell.

    Running a cell with separate globals and locals is the classic way to make
    ``[x for _ in y]`` raise ``NameError`` in a REPL only.
    """
    run(shell, "x = 7")
    run(shell, "[x for _ in range(2)]")
    assert shell.recorder.results == ["[7, 7]"]


def test_future_import_persists_across_cells(shell):
    """``from __future__ import annotations`` stays in force."""
    run(shell, "from __future__ import annotations")
    run(shell, "def f(a: int) -> int: return a\nf.__annotations__['a']")
    assert shell.recorder.results == ["'int'"]


def test_syntax_error_is_reported_with_a_caret(shell):
    """A malformed cell shows where it went wrong."""
    result = run(shell, "x ===== 3")
    assert result.error_before_exec is not None
    assert "SyntaxError" in shell.recorder.stderr
    assert "^" in shell.recorder.stderr


def test_traceback_hides_the_console_frames(shell):
    """A user sees their own frame, not the console's plumbing.

    The naive implementation shows six frames of ``shell.py`` and
    ``interpreter.py`` above the line the user typed, which buries the actual
    error.
    """
    run(shell, "1/0")
    assert "ZeroDivisionError" in shell.recorder.stderr
    assert "chisurf/core/console" not in shell.recorder.stderr


def test_traceback_keeps_user_frames(shell):
    """Frames from the user's own functions are kept."""
    run(shell, "def inner():\n    return 1/0\n\n")
    run(shell, "inner()")
    assert shell.recorder.stderr.count("in ") >= 2


def test_exception_does_not_leave_streams_swapped(shell):
    """A failing cell restores ``sys.stdout``."""
    saved = sys.stdout
    run(shell, "1/0")
    assert sys.stdout is saved


def test_reentrant_execution_is_refused(shell):
    """A cell cannot start while another is running.

    The interrupt pump runs the Qt event loop mid-cell, so a second execution
    really can be requested; without this guard the two would share one
    namespace mutation and one ``execution_count``.
    """
    def reenter():
        return shell.run_cell("1")

    shell.user_ns["reenter"] = reenter
    run(shell, "reenter()")
    assert "already running" in shell.recorder.stderr


# ----------------------------------------------------------------------
# magics
# ----------------------------------------------------------------------

def test_run_dash_i_shares_the_namespace(shell, tmp_path):
    """``%run -i`` runs in the interactive namespace.

    Spelled exactly the way the ChiSurf code editor sends it, single quotes
    included, because that call site is the reason this flag matters.
    """
    script = tmp_path / "script.py"
    script.write_text("marker = 'ran'\n", encoding="utf-8")
    run(shell, f"%run -i '{script}'")
    assert shell.user_ns["marker"] == "ran"


def test_run_sets_dunder_name_to_main(shell, tmp_path):
    """A script's ``__main__`` guard fires under ``%run``."""
    script = tmp_path / "guarded.py"
    script.write_text("was_main = __name__ == '__main__'\n", encoding="utf-8")
    run(shell, f"%run -i '{script}'")
    assert shell.user_ns["was_main"] is True


def test_run_restores_argv(shell, tmp_path):
    """``%run`` leaves ``sys.argv`` as it found it."""
    script = tmp_path / "argv.py"
    script.write_text("seen = list(__import__('sys').argv)\n", encoding="utf-8")
    saved = list(sys.argv)
    run(shell, f"%run -i '{script}' one two")
    assert sys.argv == saved
    assert shell.user_ns["seen"][1:] == ["one", "two"]


def test_unknown_magic_reports_itself(shell):
    """An unknown magic says so instead of raising ``SyntaxError``."""
    run(shell, "%nosuchmagic")
    assert "unknown magic" in shell.recorder.stderr


def test_config_accepts_an_unknown_trait(shell):
    """``%config Completer.use_jedi = False`` must succeed.

    It is in the shipped ``console_init`` and chinsole has no jedi to disable.
    Erroring would print a warning on every start, on every installation,
    forever -- ChiSurf never overwrites a user's settings file.
    """
    result = run(shell, "%config Completer.use_jedi = False")
    assert result.success
    assert shell.recorder.stderr == ""
    assert shell.config["Completer"]["use_jedi"] is False


def test_timeit_returns_a_result_with_dash_o(shell):
    """``%timeit -o`` hands back the measurement."""
    run(shell, "r = %timeit -o -q -n 2 -r 2 sum(range(10))")
    assert shell.user_ns["r"].loops == 2


def test_shell_escape_captures_output(shell):
    """``x = !cmd`` returns the lines."""
    run(shell, "out = !echo chinsole")
    assert shell.user_ns["out"].s == "chinsole"


# ----------------------------------------------------------------------
# completion
# ----------------------------------------------------------------------

def test_completion_never_calls_user_code(shell):
    """Tab must not execute anything.

    A completer that evaluates whatever is left of the cursor turns a keystroke
    into arbitrary execution.
    """
    shell.run_cell(
        "fired = []\n"
        "def launch():\n"
        "    fired.append(1)\n"
        "    return 1\n"
    )
    for line in ("launch().", "launch().re", "launch()[0]."):
        shell.complete(line, len(line))
    assert shell.user_ns["fired"] == []


def test_attribute_completion_uses_the_live_object(shell):
    """Attributes come from the real object, not from static analysis."""
    shell.run_cell("class T:\n    unusual_name = 1\n\nt = T()\n")
    result = shell.complete("t.unus", 6)
    assert "t.unusual_name" in result.matches


def test_dict_key_completion(shell):
    """String subscripts complete against the container's keys."""
    shell.run_cell("d = {'alpha': 1, 'beta': 2}")
    result = shell.complete("d['a", 4)
    assert result.matches == ["alpha']"]
    assert result.kind == "key"


def test_magic_name_completion(shell):
    """``%ru`` offers ``%run``."""
    result = shell.complete("%ru", 3)
    assert "%run" in result.matches


def test_completion_hides_private_names_unless_asked(shell):
    """Dunders do not drown out the name you were reaching for."""
    shell.run_cell("class T:\n    visible = 1\n\nt = T()\n")
    assert all(not m.rpartition(".")[2].startswith("_") for m in shell.complete("t.", 2).matches)
    assert any(m.startswith("t.__") for m in shell.complete("t.__", 4).matches)


# ----------------------------------------------------------------------
# history
# ----------------------------------------------------------------------

def test_history_collapses_consecutive_duplicates():
    """Running the same command twice leaves one entry."""
    history = HistoryManager(path=False)
    history.append("a")
    history.append("a")
    history.append("b")
    assert list(history) == ["a", "b"]


def test_history_round_trips_multiline_cells(tmp_path):
    """A multi-line cell survives being saved and reloaded."""
    path = tmp_path / "history.txt"
    first = HistoryManager(path=path)
    first.append("for i in range(3):\n    print(i)")
    first.save()
    second = HistoryManager(path=path)
    assert list(second) == ["for i in range(3):\n    print(i)"]


def test_history_prefix_search_is_most_recent_first():
    """Up-arrow filtering returns the newest match first."""
    history = HistoryManager(path=False)
    for source in ("print(1)", "x = 2", "print(3)"):
        history.append(source)
    assert history.search_prefix("print") == ["print(3)", "print(1)"]


# ----------------------------------------------------------------------
# output formatting
# ----------------------------------------------------------------------

def test_huge_container_repr_is_bounded(shell):
    """A gigantic container cannot wedge the console.

    One enormous insert is worse than a runaway print loop, because it arrives
    as a single operation with no point at which the GUI can be pumped. Two
    mechanisms bound it -- :mod:`reprlib` elides a long container's middle, and
    a character cap catches everything else -- so this asserts the *property*
    rather than which one fired.
    """
    from chisurf.core.console.formatters import MAX_REPR_CHARS, format_text

    text = format_text(list(range(2_000_000)))
    assert len(text) < MAX_REPR_CHARS


def test_huge_scalar_repr_is_truncated(shell):
    """The character cap catches a long repr that is not a container.

    A container gets elided by :mod:`reprlib` before the cap is reached, so
    without a non-container case the cap would never be exercised and could
    rot unnoticed.
    """
    from chisurf.core.console.formatters import MAX_REPR_CHARS, format_text

    text = format_text("x" * (MAX_REPR_CHARS * 2))
    assert len(text) < MAX_REPR_CHARS + 200
    assert "truncated" in text


def test_broken_repr_does_not_break_the_console(shell):
    """An object whose ``__repr__`` raises still produces output."""
    shell.run_cell(
        "class Bad:\n"
        "    def __repr__(self):\n"
        "        raise RuntimeError('nope')\n"
    )
    run(shell, "Bad()")
    assert "unprintable" in (shell.recorder.results[0] or "")
