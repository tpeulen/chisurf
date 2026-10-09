"""Lazy tcspc subpackage exports (PEP 562).

Same rationale as ``chisurf.gui.widgets.experiments``: the previous eager
imports pulled the controller chain (``wizard`` → IMP/numba) into every
startup. Reader classes live in the core experiment package; this package
retains only the controller exports whose native ports remain pending.
"""

from __future__ import annotations

_EXPORTS: dict[str, str] = {
    "TCSPCTTTRReaderControlWidget": "chisurf.gui.widgets.experiments.tcspc.tcspc_tttr_reader_control_widget",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    import importlib

    if name in _EXPORTS:
        module = importlib.import_module(_EXPORTS[name])
        value = getattr(module, name)
        globals()[name] = value
        return value
    # Submodule attribute access (``tcspc.controller``) used
    # to work via the eager imports binding them on the package.
    try:
        return importlib.import_module(f"{__name__}.{name}")
    except ModuleNotFoundError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))
