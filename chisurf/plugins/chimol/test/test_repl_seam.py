"""The prompt's command-or-Python rule, and the seam that lets a host own it.

Why this exists
---------------
``chimol.cli`` used to import ``chisurf.core.console.dispatch`` at module
scope. That is a toolkit-free module with a hard dependency on ChiSurf, which
is the dependency the relocation is about -- and it hid behind the Qt audit,
because the CLI has no Qt in it at all.

The fix was not to leave the CLI in the integration layer but to make the
routing attachable. So there are two things to check, and the second is the one
that usually rots: that a host *can* take the decision over, and that the
answer chimol gives when nobody does is the **real rule** rather than a stub
that quietly routes everything one way.
"""

from __future__ import annotations

import pathlib

import pytest
from chimol import repl


@pytest.fixture(autouse=True)
def _clean():
    """Every test starts with no host attached, and leaves none behind."""
    repl.detach()
    yield
    repl.detach()


# --------------------------------------------------------------------------- #
# The seam
# --------------------------------------------------------------------------- #
def test_nothing_is_attached_by_default():
    """Importing chimol must not require a host to have registered."""
    assert not repl.attached()
    assert repl.router() is not None


def test_a_host_takes_the_decision_over():
    """Whatever a host answers is what the prompt uses."""

    class AlwaysCommand:
        def is_command(self, line, namespace=None):
            return True

        def is_incomplete_python(self, line):
            return False

    repl.attach(AlwaysCommand())
    assert repl.attached()
    # `1 + 1` is unambiguously Python, so only the host can be answering.
    assert repl.router().is_command("1 + 1")


def test_a_module_is_a_valid_host():
    """The protocol is named after the functions a console already exports.

    This is what makes the ChiSurf integration a single ``attach`` call rather
    than an adapter class -- so it has to keep working for a plain module.
    """
    import types

    mod = types.ModuleType("fake_console")
    mod.is_command = lambda line, namespace=None: line.startswith("!")
    mod.is_incomplete_python = lambda line: False
    repl.attach(mod)
    assert repl.router().is_command("!fetch 1crn")
    assert not repl.router().is_command("fetch 1crn")


def test_an_incomplete_host_is_refused_by_name():
    """Failing at ``attach`` names the missing method.

    Failing later means a prompt routing every line to the wrong language with
    no indication why, which is a bad afternoon.
    """

    class Half:
        def is_command(self, line, namespace=None):
            return False

    with pytest.raises(TypeError, match="is_incomplete_python"):
        repl.attach(Half())
    assert not repl.attached()


def test_detach_restores_chimols_own_answer():
    class AlwaysCommand:
        def is_command(self, line, namespace=None):
            return True

        def is_incomplete_python(self, line):
            return False

    repl.attach(AlwaysCommand())
    repl.detach()
    assert not repl.router().is_command("1 + 1")


# --------------------------------------------------------------------------- #
# The fallback is the real rule, not a stub
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("line", "is_cmd", "why"),
    [
        ("1 + 1", False, "unambiguous Python"),
        ("", False, "an empty line is neither"),
        ("   ", False, "whitespace is neither"),
        ("fetch 1crn", True, "does not compile, and is a command"),
        ("color red", True, "two undefined names juxtaposed"),
        ("viewer.objects", False, "attribute access on a defined name"),
    ],
)
def test_the_builtin_rule_routes_each_kind(line, is_cmd, why):
    # `viewer` is bound at a real prompt; an undefined name is a *command*,
    # which is the next test's subject rather than this one's.
    ns = {"viewer": object()}
    assert repl.router().is_command(line, namespace=ns) is is_cmd, why


def test_a_defined_name_wins_over_a_command_of_the_same_name():
    """The case the rule exists to protect.

    The naive version -- "is the first word a command" -- sent ``set`` to
    chimol's ``set`` rather than the builtin. A name that exists in Python is
    Python.
    """
    assert not repl.router().is_command("set()")
    assert not repl.router().is_command("objects", namespace={"objects": []})
    # ... and the same word is a command when nothing defines it.
    assert repl.router().is_command("objects xyz")


def test_an_unfinished_block_is_neither_language_yet():
    """Without this, ``for i in range(3):`` is swallowed as a command.

    The body could then never be typed -- the prompt would dispatch the header
    and start again.
    """
    router = repl.router()
    assert router.is_incomplete_python("for i in range(3):")
    assert not router.is_incomplete_python("for i in range(3): pass")
    assert not router.is_incomplete_python("fetch 1crn")


def test_the_builtin_rule_needs_nothing_but_the_standard_library():
    """Chimol runs where there is no ChiSurf, so the fallback must be portable.

    Checked as an import graph rather than by reading: the point is that the
    module a browser build ships cannot reach ChiSurf or a toolkit.
    """
    import ast
    import pathlib

    source = pathlib.Path(repl.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".")[0]] if node.level == 0 else []
        else:
            continue
        for name in names:
            assert name not in {"chisurf", "qtpy", "PyQt5", "PySide2", "wgpu"}, (
                f"chimol.repl imports {name}, which a browser build has no way "
                "to provide -- the fallback exists precisely for that build"
            )


# --------------------------------------------------------------------------- #
# The two routers must agree
# --------------------------------------------------------------------------- #
#: Lines that exercise each branch of the rule.
_CORPUS = [
    "1 + 1",
    "",
    "   ",
    "fetch 1crn",
    "color red",
    "viewer.objects",
    "set()",
    "objects",
    "objects xyz",
    "load file.pdb",
    "x = 3",
    "print(viewer)",
    "for i in range(3): pass",
    "]not python[",
    "show cartoon, chain A",
]


def test_the_fallback_agrees_with_the_console_it_stands_in_for():
    """The point of a fallback is that nobody can tell which one answered.

    chimol's rule and ChiSurf's are written independently -- one in
    :mod:`chimol.repl`, one in ``chisurf.core.console.dispatch`` -- and two
    independent implementations of the same rule drift. When they do, the same
    typed line means different things depending on whether chimol was launched
    inside ChiSurf or on its own, which is the confusing kind of bug: it
    reproduces for one person and not the other.

    Skipped rather than failed where ChiSurf is absent, because that is exactly
    the situation the fallback is for.
    """
    dispatch = pytest.importorskip("chisurf.core.console.dispatch")

    ns = {"viewer": object(), "objects": []}
    mine = repl.router()
    disagreements = [
        (line, mine.is_command(line, namespace=ns), dispatch.is_command(line, namespace=ns))
        for line in _CORPUS
        if mine.is_command(line, namespace=ns) is not dispatch.is_command(line, namespace=ns)
    ]
    assert not disagreements, (
        "chimol's built-in router and ChiSurf's console disagree about "
        "(line, chimol, chisurf): " + repr(disagreements)
    )


def test_the_fallback_agrees_about_unfinished_blocks():
    """Same reasoning, for the other half of the protocol."""
    dispatch = pytest.importorskip("chisurf.core.console.dispatch")

    mine = repl.router()
    disagreements = [
        line
        for line in _CORPUS
        if mine.is_incomplete_python(line) is not dispatch.is_incomplete_python(line)
    ]
    assert not disagreements, "the two routers disagree about which lines are unfinished: " + repr(
        disagreements
    )


# --------------------------------------------------------------------------- #
# The settings directory is injected, not asked for
# --------------------------------------------------------------------------- #
def test_chimol_defaults_to_its_own_settings_directory():
    """With no host and no override, chimol answers for itself.

    It used to import ``chisurf.core.settings`` inside a ``try`` and fall back
    when that raised. That worked and pointed the wrong way: chimol is packaged
    to run where there is no ChiSurf, so a module naming ChiSurf -- even
    guarded, even only in the fallback -- is one the move has to keep
    explaining away.
    """
    import os

    from chimol.core.settings import dirs as sd

    before, env = sd.injected_settings_dir(), os.environ.pop(sd.ENV_VAR, None)
    try:
        sd.set_settings_dir(None)
        assert sd.settings_dir() == pathlib.Path(sd.FALLBACK).expanduser()
    finally:
        sd.set_settings_dir(before)
        if env is not None:
            os.environ[sd.ENV_VAR] = env


def test_a_host_can_place_the_settings_directory(tmp_path):
    """What ChiSurf's plugin package does at import."""
    import os

    from chimol.core.settings import dirs as sd

    before, env = sd.injected_settings_dir(), os.environ.pop(sd.ENV_VAR, None)
    try:
        sd.set_settings_dir(tmp_path)
        assert sd.settings_dir() == tmp_path
        assert sd.settings_path("chimol_display.json") == tmp_path / "chimol_display.json"
    finally:
        sd.set_settings_dir(before)
        if env is not None:
            os.environ[sd.ENV_VAR] = env


def test_the_environment_overrides_a_host(tmp_path):
    """An operator has to be able to correct a host without editing it.

    Also what keeps the suite's own isolation working: the ChiSurf plugin
    package injects ``~/.chisurf`` the moment it is imported, which happens in
    most of these tests, and the throwaway directory has to win anyway.
    """
    import os

    from chimol.core.settings import dirs as sd

    before, env = sd.injected_settings_dir(), os.environ.get(sd.ENV_VAR)
    try:
        sd.set_settings_dir(tmp_path / "host")
        os.environ[sd.ENV_VAR] = str(tmp_path / "operator")
        assert sd.settings_dir() == tmp_path / "operator"
    finally:
        sd.set_settings_dir(before)
        if env is None:
            os.environ.pop(sd.ENV_VAR, None)
        else:
            os.environ[sd.ENV_VAR] = env


def test_chimols_settings_module_does_not_import_chisurf():
    """The point of the whole exercise, asserted on the import graph."""
    import ast

    from chimol.core.settings import dirs as sd

    source = pathlib.Path(sd.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".")[0]] if node.level == 0 else []
        else:
            continue
        assert "chisurf" not in names, (
            "chimol.core.settings.dirs imports ChiSurf again -- the host injects the "
            "directory now, see chisurf/plugins/chimol/__init__.py"
        )
