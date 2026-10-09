"""Lazy experiment-controller exports (PEP 562).

Importing this package used to eagerly import every experiment controller
(``pda2c``, ``tcspc``, ``fcs``, ``ics``, ``pch`` and the heavy ``modelling``
stack). That import chain costs seconds of cold-start and was paid whenever
*any* submodule of the package — or ``chisurf.gui.autoform`` via
``fitting.parameter_widgets`` — was first touched, i.e. on the splash critical
path in every startup.

Names are resolved on first access instead. The mapping below mirrors the
previous star-import surface exactly; extend it when a new controller module
gains public names.
"""

from __future__ import annotations

# Public names the package previously re-exported via star imports, mapped to
# the module that defines them. Anything not listed raises AttributeError just
# as it would have before the modules were imported eagerly.
_EXPORTS: dict[str, str] = {
    # chisurf.gui.widgets.experiments.fcs
    "FCSController": "chisurf.gui.widgets.experiments.fcs",
    # chisurf.gui.widgets.experiments.pch
    "PCHController": "chisurf.gui.widgets.experiments.pch",
    # chisurf.gui.widgets.experiments.ics
    "ICSController": "chisurf.gui.widgets.experiments.ics",
    # chisurf.gui.widgets.experiments.widgets
    "ExperimentalDataSelector": "chisurf.gui.widgets.experiments.widgets",
    # chisurf.gui.widgets.experiments.sample_selector_widget
    "SampleLookupDialog": "chisurf.gui.widgets.experiments.sample_selector_widget",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    import importlib

    if name in _EXPORTS:
        module = importlib.import_module(_EXPORTS[name])
        try:
            value = getattr(module, name)
        except AttributeError as exc:
            raise AttributeError(
                f"module {__name__!r} re-exports {name!r} from "
                f"{_EXPORTS[name]!r}, which no longer defines it"
            ) from exc
        # Cache on the package so subsequent accesses skip this hook.
        globals()[name] = value
        return value
    # Submodule attribute access (``experiments.pda2c``) used to work because
    # the eager imports bound every submodule as a package attribute. Try the
    # import before rejecting the name.
    try:
        return importlib.import_module(f"{__name__}.{name}")
    except ModuleNotFoundError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))
