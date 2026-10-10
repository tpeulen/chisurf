# core package - non-GUI chisurf internals
"""Non-GUI ChiSurf internals.

Submodules are bound lazily on first attribute access, so ``cs.core.actions``
works without a prior ``import chisurf.core.actions`` somewhere else. About fifty
call sites spell it that way; before this hook they worked only when some other
import had happened to load the subpackage first.
"""

from __future__ import annotations

import importlib
import importlib.util


def __getattr__(name: str):
    """Import and bind a submodule of ``chisurf.core`` on first access."""
    if name.startswith("_"):
        raise AttributeError(name)
    qualified = f"{__name__}.{name}"
    if importlib.util.find_spec(qualified) is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(qualified)
    globals()[name] = module
    return module
