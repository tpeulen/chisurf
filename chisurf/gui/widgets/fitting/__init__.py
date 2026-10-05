"""Public fitting widgets, imported when their controls are requested."""

from importlib import import_module

_EXPORTS = {
    "FittingControllerWidget": "fit_controller",
    "ModelDataRepresentationSelector": "fit_list",
    "FitSubWindow": "fit_subwindow",
    "FittingParameterDetailPopup": "parameter_widgets",
    "FittingParameterGroupWidget": "parameter_widgets",
    "FittingParameterProxyController": "parameter_widgets",
    "FittingParameterWidget": "parameter_widgets",
    "ParameterActionsMixin": "parameter_widgets",
    "make_fitting_parameter_group_widget": "parameter_widgets",
    "make_fitting_parameter_widget": "parameter_widgets",
}
_MODULES = frozenset(_EXPORTS.values()) | {"fitting_client", "widgets"}
__all__ = list(_EXPORTS) + ["parameter_settings", "presentation_fit_members"]


def presentation_fit_members(fit):
    """Return the actual scientific members presented by a Fit or FitGroup."""
    from chisurf.core.fitting.fit import Fit, FitGroup

    if isinstance(fit, FitGroup):
        return tuple(fit.grouped_fits)
    if isinstance(fit, Fit):
        return (fit,)
    raise TypeError("fit presentation requires a Fit or FitGroup")


def __getattr__(name: str):
    """Resolve and cache the existing public widgets and module imports."""
    if name == "parameter_settings":
        value = import_module("chisurf.core.settings").parameter
    elif name in _EXPORTS:
        value = getattr(import_module(f"{__name__}.{_EXPORTS[name]}"), name)
    elif name in _MODULES:
        value = import_module(f"{__name__}.{name}")
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value
    return value


def __dir__():
    """Expose lazy names to introspection without importing their widgets."""
    return sorted(set(globals()) | set(__all__) | _MODULES)
