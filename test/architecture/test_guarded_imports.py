"""A guarded import that stops resolving must fail loudly, not silently.

``try: from x import y / except: y = None`` is how an optional dependency is
handled, and it is also how a *renamed* module turns into a missing feature that
nothing reports. Three real cases were found the day this test was written: the
trace browser and the MMFDB admin tool had both lost their ndX
integration to a package reorganisation, and the proteinMC widget had been
opening labelling files as raw text since the FPS editor was renamed — no
error, no log line, just a button that did less than it used to.

This walks the tree, collects every absolute import that a ``try`` body depends
on, and checks it still resolves. Genuinely optional things are listed in
:data:`OPTIONAL` with the reason; anything else that fails is a defect.
"""
from __future__ import annotations

import ast
import importlib
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2] / "chisurf"

#: Top-level packages that may legitimately be absent, and why.
OPTIONAL = {
    # hardware / vendor SDKs
    "mcculw": "Measurement Computing DAQ SDK, Windows-only",
    "quest": "optional QuEsT accessible-volume extension",
    # platform
    "ctypes": "ctypes.wintypes exists on Windows only",
    "shiboken6": "PySide6 binding; the tree runs on PyQt5",
    # heavy or niche third-party extras
    "OpenGL": "3-D viewers degrade without it",
    "pyopencl": "GPU acceleration is optional",
    "docx": "python-docx, report export only",
    "ptpython": "nicer REPL for the chimol shell",
    "latex2mathml": "formula rendering in the agent panel",
    "imagecodecs": "extra TIFF codecs",
    "cellpose": "external segmentation tool",
    "torch": "optional ML backend",
    "jax": "optional ML backend",
    "wandb": "optional experiment tracking",
    "openai": "optional LLM provider",
    "anthropic": "optional LLM provider",
    "google": "optional LLM provider",
    # compiled extensions that are built separately
    "chisurf.core.structure.av.fps_": "compiled AV kernel; modelling lives in imp-tricks now",
    # the port runtime that replaced chinet (phase 3): the parameter/project
    # layers import it guarded because an environment that never fits
    # anything runs without it, and they fail loudly at first use instead.
    "IMP": "IMP.bff port runtime; separate build, deliberately optional",
}


def _imports_in(nodes) -> list[tuple[str, list[str], int]]:
    """Return ``(module, names, lineno)`` for absolute imports in *nodes*.

    Nested ``try`` handlers are skipped: an ``except ImportError`` that imports
    something else is a deliberate fallback, not a dependency.
    """
    out: list[tuple[str, list[str], int]] = []
    for node in nodes:
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Try):
                out.extend(_imports_in(stmt.body))
                break
            if isinstance(stmt, ast.Import):
                out.extend((a.name, [], stmt.lineno) for a in stmt.names)
            elif isinstance(stmt, ast.ImportFrom) and stmt.module and stmt.level == 0:
                out.append((stmt.module, [a.name for a in stmt.names], stmt.lineno))
    return out


def _imported_names(nodes) -> set[str]:
    """Return every name bound by an import in *nodes*."""
    names: set[str] = set()
    for node in nodes:
        for stmt in ast.walk(node):
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                names.update(a.asname or a.name for a in stmt.names)
    return names


def _guarded_imports(tree: ast.AST):
    """Yield every absolute import a ``try``/``except`` body depends on.

    A handler that re-imports the *same names* from somewhere else is a
    version shim — ``scipy.optimize.minpack`` then ``scipy.optimize._minpack_py``
    — and its first branch is expected to fail on some installs. A handler that
    imports something *different* is a fallback feature, so the first branch is
    still a dependency and is checked.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try) or not node.handlers:
            continue
        body = _imports_in(node.body)
        handler_names = _imported_names([h for h in node.handlers])
        if handler_names and handler_names >= _imported_names(node.body):
            continue
        yield from body


def _is_optional(module: str) -> bool:
    """Whether *module* (or a parent of it) is a declared optional."""
    parts = module.split(".")
    return any(".".join(parts[: i + 1]) in OPTIONAL for i in range(len(parts)))


def _resolves(module: str, names: list[str]) -> str:
    """Return an empty string when the import resolves, else why it does not."""
    try:
        mod = importlib.import_module(module)
    except ImportError as exc:
        return str(exc)
    except Exception:
        # A module that imports but raises on side effects is a different
        # problem, and not one this test can judge.
        return ""
    for name in names:
        if name == "*" or hasattr(mod, name):
            continue
        # `from pkg import sub` is valid for a not-yet-imported submodule.
        try:
            importlib.import_module(f"{module}.{name}")
        except ImportError:
            return f"{module} has no {name!r}"
        except Exception:
            continue
    return ""


def test_every_guarded_import_still_resolves():
    """No guarded import may point at something that has moved or gone."""
    pytest.importorskip("tttrlib")
    broken: list[str] = []
    for path in sorted(ROOT.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError:
            continue
        for module, names, lineno in _guarded_imports(tree):
            if _is_optional(module):
                continue
            why = _resolves(module, names)
            if why:
                rel = path.relative_to(ROOT.parent)
                broken.append(f"{rel}:{lineno}  {module} -- {why}")

    assert not broken, (
        "guarded imports that no longer resolve (the feature behind each is "
        "silently missing; fix the path or declare the dependency optional in "
        "OPTIONAL):\n  " + "\n  ".join(broken)
    )
