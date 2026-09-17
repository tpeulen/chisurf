"""Code in the documentation has to be code.

A snippet is copied and pasted; if it does not parse, or names a module that
moved, the reader finds out and the page does not. Two of them were teaching a
call that had changed shape, which is what prompted this.

Three levels, weakest first, so that adding a snippet costs nothing but a
*broken* one always fails:

**every Python block compiles.** Syntax only — no imports are executed, so a
block may reference data or a GUI it cannot have here.

**every dotted ``chisurf.…`` name resolves.** A module that moved is the
failure this catches; it is the one that actually happened.

**a block marked** ```` ```python run ```` **is executed**, in a temporary
directory, and must not raise. Mark a block that way when it is self-contained;
leave the marker off when it needs a measurement, a GUI or a file the reader
supplies — it is still compiled and its names are still checked.
"""

from __future__ import annotations

import ast
import importlib
import re

import pytest

from chisurf.plugins.core.help.api.toc import docs_root, repository_root

#: Fenced blocks, with whatever follows the language on the fence line.
_FENCE = re.compile(r"^```(?P<lang>[\w-]*)(?P<info>[^\n]*)\n(?P<body>.*?)^```", re.M | re.S)
#: ``.. code-block:: python`` with its indented body.
_RST = re.compile(
    r"^(?P<indent>[ \t]*)\.\.\s+code-block::\s*(?P<lang>\S+)\s*\n"
    r"(?:^[ \t]*:\S+:.*\n)*\s*\n"
    r"(?P<body>(?:(?:^(?P=indent)[ \t]+.*|^\s*)\n)*)",
    re.M,
)
#: ``chisurf.a.b`` occurrences a snippet relies on.
_DOTTED = re.compile(r"\b(chisurf(?:\.[a-z_][a-z_0-9]*)+)\b")
#: Names that are values in a session, not importable modules.
_NOT_MODULES = {"chisurf.fits", "chisurf.imported_datasets", "chisurf.current_fit"}


def _blocks() -> list[tuple[str, int, str, bool]]:
    """Return ``(page, line, code, runnable)`` for every Python block."""
    found = []
    for page in sorted(docs_root().rglob("*")):
        if page.suffix.lower() not in (".md", ".rst") or "_build" in page.parts:
            continue
        text = page.read_text(encoding="utf-8", errors="ignore")
        relative = page.relative_to(repository_root()).as_posix()
        for match in _FENCE.finditer(text):
            language = (match.group("lang") or "").lower()
            if language not in ("python", "py"):
                continue
            line = text[: match.start()].count("\n") + 1
            runnable = "run" in (match.group("info") or "").split()
            found.append((relative, line, match.group("body"), runnable))
        for match in _RST.finditer(text):
            if match.group("lang").lower() not in ("python", "py"):
                continue
            body = match.group("body")
            indents = [len(l) - len(l.lstrip()) for l in body.splitlines() if l.strip()]
            if not indents:
                continue
            strip = min(indents)
            code = "\n".join(l[strip:] if l.strip() else "" for l in body.splitlines())
            line = text[: match.start()].count("\n") + 1
            found.append((relative, line, code, False))
    return found


BLOCKS = _blocks()

#: Sections whose code is *shipped* documentation. `development/` holds design
#: notes and migration plans that deliberately describe APIs which do not exist
#: yet, so their names are not checked — but their syntax still is, because a
#: block that cannot be parsed was never run by anyone.
SHIPPED = ("getting_started/", "concepts/", "guides/", "manual/", "reference/", "references/")
CHECKED_NAMES = [b for b in BLOCKS if any(s in b[0] for s in SHIPPED)]


def _identify(value):
    page, line = value[0], value[1]
    return f"{page}:{line}"


@pytest.mark.parametrize("block", BLOCKS, ids=[_identify(b) for b in BLOCKS])
def test_python_block_compiles(block):
    """A snippet that does not parse cannot have been run by its author."""
    page, line, code, _ = block
    # A block may legitimately show a fragment — a call, a signature, a
    # continuation — so a bare expression or an ellipsis is not a failure.
    if code.strip() in ("", "..."):
        return
    try:
        ast.parse(code)
    except SyntaxError as error:
        pytest.fail(f"{page}:{line} does not parse: {error}")


@pytest.mark.parametrize("block", CHECKED_NAMES, ids=[_identify(b) for b in CHECKED_NAMES])
def test_python_block_names_resolve(block):
    """Every ``chisurf.…`` name a snippet uses must still exist."""
    page, line, code, _ = block
    unresolved = []
    for dotted in sorted(set(_DOTTED.findall(code))):
        if dotted in _NOT_MODULES:
            continue
        parts = dotted.split(".")
        for split in range(len(parts), 0, -1):
            try:
                module = importlib.import_module(".".join(parts[:split]))
            except Exception:
                continue
            target = module
            ok = True
            for attribute in parts[split:]:
                if not hasattr(target, attribute):
                    ok = False
                    break
                target = getattr(target, attribute)
            if not ok:
                unresolved.append(dotted)
            break
        else:
            unresolved.append(dotted)
    assert not unresolved, f"{page}:{line} names {unresolved}"


RUNNABLE = [b for b in BLOCKS if b[3]]


@pytest.mark.parametrize("block", RUNNABLE, ids=[_identify(b) for b in RUNNABLE] or None)
def test_runnable_block_runs(block, tmp_path, monkeypatch):
    """A block marked ```python run``` is executed and must not raise."""
    page, line, code, _ = block
    monkeypatch.chdir(tmp_path)
    namespace: dict = {"__name__": "__doc_block__"}
    try:
        exec(compile(code, f"{page}:{line}", "exec"), namespace)  # noqa: S102
    except Exception as error:  # pragma: no cover - the failure is the point
        pytest.fail(f"{page}:{line} raised {type(error).__name__}: {error}")


def test_there_are_blocks_to_check():
    """Guard against the collector silently matching nothing."""
    assert len(BLOCKS) > 50, len(BLOCKS)
