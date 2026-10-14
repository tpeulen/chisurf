"""Every EMTK app's event handlers must accept the host's call shapes.

A host forwards pointer/keyboard events with a fixed arity
(``pointer_move(x, y, buttons, modifiers)`` and so on — the ``ImApp`` base
signatures). An app that overrides a handler with a narrower signature imports
fine, renders fine, and then crashes with a ``TypeError`` the first time the
mouse moves over it, which is how ``UnifiedSettingsApp`` shipped. This sweep
parses every plugin app module statically, so a deviation fails here instead
of on the user's next mouse move.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

#: Handler name -> how many positional arguments (beyond ``self``) the host
#: passes. An override must accept at least these, positionally.
HOST_PROTOCOL = {
    "pointer_press": 5,  # x, y, button, modifiers, clicks
    "pointer_release": 4,  # x, y, button, modifiers
    "pointer_move": 4,  # x, y, buttons, modifiers
    "wheel": 4,  # x, y, steps, modifiers
    "scroll": 1,  # rows (notches)
    "key": 3,  # key, text, modifiers
}

_APP_GLOBS = ("chisurf/plugins/**/app.py", "chisurf/plugins/**/gui/app.py")


def _plugin_app_modules() -> list[pathlib.Path]:
    root = pathlib.Path(__file__).resolve().parents[2]
    found: set[pathlib.Path] = set()
    for pattern in _APP_GLOBS:
        for path in root.glob(pattern):
            if "__pycache__" in path.parts or "test" in path.parts:
                continue
            found.add(path)
    return sorted(found)


def _accepts(node: ast.FunctionDef, positional: int) -> bool:
    """Whether *node* can be called with *positional* positional arguments."""
    args = node.args
    if args.vararg is not None:
        return True
    named = [a for a in args.posonlyargs + args.args if a.arg != "self"]
    required = len(named) - len(args.defaults)
    if required > positional:
        return False
    return positional <= len(named) or args.kwarg is not None


def test_host_event_overrides_accept_host_arity():
    bad: list[str] = []
    checked = 0
    modules = _plugin_app_modules()
    # The tripwire is on the module count, not the handler count: plugins are
    # deleted and merged on purpose (the File tools hub took five handlers
    # with it), while a broken glob shows up as almost no modules at all.
    assert len(modules) > 80, f"sweep found only {len(modules)} app modules; the glob broke"
    root = pathlib.Path(__file__).resolve().parents[2]
    for path in modules:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - broken files fail their own tests
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            bound = HOST_PROTOCOL.get(node.name)
            if bound is None:
                continue
            checked += 1
            if not _accepts(node, bound):
                bad.append(
                    f"{path.relative_to(root)}:{node.lineno} "
                    f"def {node.name}(...) must accept {bound} positional args"
                )
    assert checked, "no app module overrides a host event handler; the sweep is blind"
    assert not bad, "event handlers that reject the Qt host's call shape:\n" + "\n".join(bad)


@pytest.mark.parametrize("name", sorted(HOST_PROTOCOL))
def test_protocol_names_exist_on_imapp(name):
    """Guard the table against drift from the ImApp base signatures."""
    import inspect

    from emtk.app import ImApp

    method = getattr(ImApp, name, None)
    assert method is not None, f"ImApp lost {name!r}; update HOST_PROTOCOL"
    sig = inspect.signature(method)
    positional = (
        len(
            [
                p
                for p in sig.parameters.values()
                if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
            ]
        )
        - 1
    )
    assert positional == HOST_PROTOCOL[name], (
        f"ImApp.{name} takes {positional} args; HOST_PROTOCOL says {HOST_PROTOCOL[name]}"
    )
