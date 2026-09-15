"""Compatibility shims for dependency APIs that were renamed out from under us.

ChiSurf has to run on the NumPy the user's environment happens to provide, and
NumPy 2 removed a batch of long-standing *aliases* — ``np.trapz`` became
``np.trapezoid``, ``np.bool8`` became ``np.bool_``, and so on. Every one of them
raises ``AttributeError`` at the call site, usually deep inside a computation and
often inside a ``try``/``except`` that turns it into a silent wrong answer. Three
such call sites in this tree (the Förster overlap integral, the fractal-dimension
transfer efficiency and the light-path spectral propagation) were dead under
NumPy 2 before this module existed.

Rewriting every call site is the wrong fix twice over: it does not help the code
in dependencies and submodules, and it pins the tree to one NumPy. So the aliases
are restored instead, **in both directions** — the new spelling is added on
NumPy 1, the old one on NumPy 2 — and the code can be written either way.

Everything here is a pure rename: the restored name is bound to the function that
replaced it, so nothing changes numerically. Anything with a behaviour change
belongs in a real port, not in this module.

Applied on import, and the package root imports it before anything else, so the
shim covers the GUI, the CLI, tests and bare scripts alike.
"""

from __future__ import annotations

__all__ = ["NUMPY_ALIASES", "apply_numpy_compat", "applied_shims"]

#: Pure renames NumPy 2 removed: ``old name -> new name``. Restored in whichever
#: direction is missing, so the same source runs on both major versions.
NUMPY_ALIASES: dict[str, str] = {
    "trapz": "trapezoid",
    "alltrue": "all",
    "sometrue": "any",
    "product": "prod",
    "cumproduct": "cumprod",
    "round_": "round",
    "in1d": "isin",
    "row_stack": "vstack",
    "float_": "float64",
    "complex_": "complex128",
    "unicode_": "str_",
    "string_": "bytes_",
    "bool8": "bool_",
    "NaN": "nan",
    "Inf": "inf",
    "Infinity": "inf",
    "NAN": "nan",
    "PINF": "inf",
}


def apply_numpy_compat() -> dict[str, str]:
    """Restore the NumPy aliases missing from the installed version.

    Both directions are covered: on NumPy 2 the removed old name is bound to its
    replacement, and on NumPy 1 the new name is bound to the old one — so code
    may use either spelling regardless of which NumPy is installed.

    Returns
    -------
    dict
        ``{restored_name: name it was bound to}``; empty when nothing was
        missing.
    """
    try:
        import numpy as np
    except Exception:  # pragma: no cover - NumPy is a hard dependency
        return {}

    restored: dict[str, str] = {}
    for old, new in NUMPY_ALIASES.items():
        has_old = hasattr(np, old)
        has_new = hasattr(np, new)
        if has_new and not has_old:
            setattr(np, old, getattr(np, new))       # NumPy 2: the removed name
            restored[old] = new
        elif has_old and not has_new:
            setattr(np, new, getattr(np, old))       # NumPy 1: the future name
            restored[new] = old
    return restored


#: What this process had to restore — useful when a bug report says "works here".
applied_shims: dict[str, str] = apply_numpy_compat()
