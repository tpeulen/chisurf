"""Architectural boundary: the model layer must stay GUI-free.

ChiSurf is Model-View-Controller with :mod:`IMP.bff` as the model's backend.
The direction of dependency is the whole of the arrangement: the **view**
(:mod:`chisurf.emtk`) knows about the model, and the **model**
(:mod:`chisurf.core` -- data, parameters, fits, equations, IO) knows nothing
about any view. A model that imports a widget toolkit cannot be driven by a
script, cannot serve the HTTP layer, cannot be tested headlessly, and cannot
be reasoned about on its own.

That rule is only worth stating if it is checked, so this walks the tree with
the AST and fails on any import of a GUI toolkit or of ``chisurf.gui`` from
under ``chisurf/core``. It used to check two packages
(``chisurf.core.models`` and ``chisurf.core.dataspec``) out of the roughly
thirty under ``chisurf.core``; it now checks all of them, which is what makes
"ChiSurf follows MVC" a property of the tree rather than an intention.

**When the model has to tell a view something**, it calls
:mod:`chisurf.core.runtime.presentation` -- ``notify`` for "this changed", ``defer``
for "this changed, but rebuild after I have finished". The view installs
itself as the presenter once, at start-up. Headless there is no presenter and
the callable runs inline, which is the behaviour the CLI, the server and most
of this suite depend on.

:data:`KNOWN_LEAKS` was the debt register of files that broke the rule; it is
empty since the Qt shell was retired, and a new entry fails the test.
"""

from __future__ import annotations

import ast
import pathlib

import chisurf.core

#: Module prefixes the model layer is forbidden to import.
FORBIDDEN_PREFIXES = ("qtpy", "PyQt5", "PyQt6", "PySide2", "PySide6", "chisurf.gui")

#: The model layer. All of it.
CORE_ROOT = pathlib.Path(chisurf.core.__file__).parent

#: Files that still reach into the view, and why. Empty since the Qt shell went (the
#: last four -- the experiment bootstrap's QApplication, the reader's sample dialog,
#: the AutoForm state helper and the registry's plugin windows -- closed with it).
#: A new entry is a regression; the test below keeps it empty.
KNOWN_LEAKS: dict[str, str] = {}


def _forbidden_imports(source: str, filename: str):
    """Yield ``(lineno, module)`` for every forbidden import in ``source``."""
    tree = ast.parse(source, filename=filename)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(FORBIDDEN_PREFIXES):
                    yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith(FORBIDDEN_PREFIXES):
                yield node.lineno, module


def _leaking_files():
    """Return ``{relative path: [(lineno, module), ...]}`` over the model."""
    found = {}
    for path in sorted(CORE_ROOT.rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        hits = list(_forbidden_imports(source, str(path)))
        if hits:
            found[path.relative_to(CORE_ROOT).as_posix()] = hits
    return found


def test_the_model_layer_does_not_import_a_view():
    """No new file under ``chisurf/core`` may reach into the GUI."""
    found = _leaking_files()
    new = {name: hits for name, hits in found.items() if name not in KNOWN_LEAKS}
    lines = [
        f"  chisurf/core/{name}:{lineno}: imports {module!r}"
        for name, hits in sorted(new.items())
        for lineno, module in hits
    ]
    assert not new, (
        "chisurf.core is the model layer and must not depend on a view.\n"
        "When the model has to tell a view something, call\n"
        "chisurf.core.runtime.presentation.notify (or .defer) and let the view "
        "install itself.\nOffending imports:\n" + "\n".join(lines)
    )


def test_the_boundary_is_closed():
    """The debt register is empty and stays empty: the model imports no view at all."""
    assert not KNOWN_LEAKS, "the model/view boundary regressed; KNOWN_LEAKS must stay empty"
