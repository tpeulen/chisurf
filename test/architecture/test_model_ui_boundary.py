"""Architectural boundary: the model layer must stay GUI-free.

ChiSurf is Model-View-Controller with :mod:`IMP.bff` as the model's backend.
The direction of dependency is the whole of the arrangement: the **view**
(:mod:`chisurf.gui`, Qt) knows about the model, and the **model**
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
:mod:`chisurf.core.presentation` -- ``notify`` for "this changed", ``defer``
for "this changed, but rebuild after I have finished". The view installs
itself as the presenter once, at start-up. Headless there is no presenter and
the callable runs inline, which is the behaviour the CLI, the server and most
of this suite depend on.

:data:`KNOWN_LEAKS` is the list of files that still break the rule, each with
why. It is a debt register, not an exemption: a new file may not join it (the
test fails if a violation appears outside the list) and a file that stops
leaking must be removed from it (the test fails on a stale entry, so the list
cannot rot into a lie).
"""
from __future__ import annotations

import ast
import pathlib

import chisurf.core

#: Module prefixes the model layer is forbidden to import.
FORBIDDEN_PREFIXES = ("qtpy", "PyQt5", "PyQt6", "PySide2", "PySide6",
                      "chisurf.gui")

#: The model layer. All of it.
CORE_ROOT = pathlib.Path(chisurf.core.__file__).parent

#: Files that still reach into the view, and what each is waiting for.
#:
#: Every one of these is the *same* defect seen from a different side: a
#: model that does presentation work. They are listed rather than silenced
#: because naming them is what turns "we should be MVC" into a finite amount
#: of remaining work.
KNOWN_LEAKS = {
    "experiments/bootstrap.py": (
        "Exists only to detect or create a QApplication, because several "
        "readers build Qt widgets deep inside get_data() and Qt aborts the "
        "process rather than raising when there is none. The leak is those "
        "readers; this module is the workaround and moves to the view with "
        "them."
    ),
    "experiments/core/reader.py": (
        "_prompt_for_sample opens a dialog: the model asking the user a "
        "question. Needs a request/response seam (the reader announces "
        "'this file has no sample', the controller asks), which is more "
        "than presentation.notify's fire-and-forget."
    ),
    "fio/fluorescence/burst_manifest.py": (
        "apply_state(form, stored) takes a *form* -- a view object -- so the "
        "function itself is a view helper filed under core. It moves rather "
        "than gets a seam."
    ),
    "plugin/registry.py": (
        "Constructs plugin windows and restores their geometry, which is "
        "view work. The registry should hand back a manifest and let the "
        "view build the window."
    ),
}


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
    new = {name: hits for name, hits in found.items()
           if name not in KNOWN_LEAKS}
    lines = [
        f"  chisurf/core/{name}:{lineno}: imports {module!r}"
        for name, hits in sorted(new.items()) for lineno, module in hits
    ]
    assert not new, (
        "chisurf.core is the model layer and must not depend on a view.\n"
        "When the model has to tell a view something, call\n"
        "chisurf.core.presentation.notify (or .defer) and let the view "
        "install itself.\nOffending imports:\n" + "\n".join(lines))


def test_the_debt_register_is_not_stale():
    """A file that stopped leaking must leave :data:`KNOWN_LEAKS`.

    Without this the list only ever grows, and a register that is allowed to
    contain fiction is worse than none -- it reads as "these four are the
    remaining work" while the real number is unknown.
    """
    found = _leaking_files()
    fixed = sorted(name for name in KNOWN_LEAKS if name not in found)
    assert not fixed, (
        "these no longer import a view; delete them from "
        "KNOWN_LEAKS:\n  " + "\n  ".join(fixed))


def test_the_boundary_is_nearly_closed():
    """A ratchet, so the debt cannot quietly grow back.

    Four files out of the ~460 under ``chisurf/core``. The number is pinned
    rather than merely listed so that "fix one, add one" fails.
    """
    assert len(KNOWN_LEAKS) <= 4, (
        "the model/view boundary regressed; KNOWN_LEAKS may only shrink")
