"""GUI-side registry that resolves view-spec keys to concrete widgets/plots.

A model describes its editor with string keys (see
:mod:`chisurf.core.models.view_spec`) and never references a Qt class. This
module is the GUI-side counterpart: it maps those keys to real plot classes and
custom-section factories. Keeping the mapping here — and only here — is what
lets the model layer stay GUI-free while still driving a rich UI.
"""

from __future__ import annotations

import importlib

from chisurf import typing

#: key -> plot class (resolved lazily so importing this module is cheap).
_PLOT_REGISTRY: typing.Dict[str, typing.Callable[[], type]] = {}
#: key -> custom-section factory ``(model, target, **options) -> QWidget``.
_SECTION_REGISTRY: typing.Dict[str, typing.Callable[..., typing.Any]] = {}


# Shipped registrations; test_fit_first_use checks these against the source ASTs.
_SECTION_MODULES = {
    "anisotropy_diagnostics": "anisotropy_diagnostics_section",
    "background_run": "background_run_section",
    "chimol": "chimol_section",
    "code_editor": "code_editor_section",
    "data_source": "data_source_section",
    "data_table": "data_table_section",
    "decay_conv": "decay_conv_section",
    "decay_panel": "decay_panel_section",
    "embed": "embed_section",
    "equation_editor": "equation_editor_section",
    "fit_mixer": "builtin",
    "fitting_parameter": "registry",
    "global_parameter_table": "global_parameter_table",
    "help": "help_section",
    "image": "builtin",
    "image_browser": "image_browser_section",
    "kappa2_controls": "builtin",
    "lcurve": "builtin",
    "level_histogram": "level_histogram_section",
    "lifetime_amplitude_options": "builtin",
    "memory_editor": "memory_editor_section",
    "node_graph": "node_graph_section",
    "path_list": "path_list_section",
    "phasor": "phasor_section",
    "progress": "progress_section",
    "quiver": "quiver_section",
    "rate_matrix": "rate_matrix_section",
    "region_list": "region_list_section",
    "scalar_table": "scalar_table_section",
    "setup_selector": "setup_selector_section",
    "state_scheme": "state_scheme_section",
    "state_table": "state_table_section",
    "store_table": "store_table_section",
    "waterfall": "waterfall_section",
}
_PLOT_MODULES = {
    "conditional_scan": "builtin",
    "distribution": "builtin",
    "fit_info": "builtin",
    "fit_table": "builtin",
    "lcurve": "builtin",
    "line": "builtin",
    "mfd_2d": "builtin",
    "mfd_map": "builtin",
    "mfd_marginals": "builtin",
    "parameter_scan": "builtin",
    "posterior_graph": "builtin",
    "pr_ci": "builtin",
    "proteinmc_network": "builtin",
    "proteinmc_structure": "builtin",
    "proteinmc_traces": "builtin",
    "residual": "builtin",
    "residual2d": "builtin",
    "sampling_diagnostics": "builtin",
    "state_scheme": "state_scheme_section",
}


def register_plot(key: str, factory: typing.Callable[[], type]) -> None:
    """Register a plot class factory under ``key``.

    Parameters
    ----------
    key : str
        The key emitted by a model's :class:`~chisurf.core.models.view_spec.PlotSpec`.
    factory : callable
        Zero-argument callable returning the plot *class*. A factory (rather
        than the class directly) avoids importing the GUI plots eagerly.
    """
    if getattr(factory, "__module__", None) == f"{__package__}.{_PLOT_MODULES.get(key)}":
        # A direct builtin import must not replace an earlier custom override.
        _PLOT_REGISTRY.setdefault(key, factory)
    else:
        _PLOT_REGISTRY[key] = factory


def get_plot_class(key: str) -> typing.Optional[type]:
    """Return the plot class registered under ``key`` (or ``None``)."""
    if key not in _PLOT_REGISTRY and key in _PLOT_MODULES:
        importlib.import_module(f"{__package__}.{_PLOT_MODULES[key]}")
    factory = _PLOT_REGISTRY.get(key)
    return factory() if factory is not None else None


def register_section(key: str):
    """Decorator registering a custom-section widget factory under ``key``.

    The decorated callable is invoked as ``factory(model=..., target=..., **options)``
    and must return a ``QWidget``.
    """

    def _decorator(factory: typing.Callable[..., typing.Any]):
        if getattr(factory, "__module__", None) == f"{__package__}.{_SECTION_MODULES.get(key)}":
            _SECTION_REGISTRY.setdefault(key, factory)
        else:
            _SECTION_REGISTRY[key] = factory
        return factory

    return _decorator


def get_section_factory(key: str) -> typing.Optional[typing.Callable[..., typing.Any]]:
    """Return the custom-section factory registered under ``key`` (or ``None``)."""
    if key not in _SECTION_REGISTRY and key in _SECTION_MODULES:
        importlib.import_module(f"{__package__}.{_SECTION_MODULES[key]}")
    return _SECTION_REGISTRY.get(key)


def resolve_plot_specs(view) -> typing.List[typing.Tuple[type, dict]]:
    """Translate a :class:`ModelView` into ``(plot_class, options)`` pairs.

    This is where a view spec's plot *keys* become the classes the fit-subwindow
    plot loader instantiates; a key with no registered class is dropped. Keeping
    the mapping here is what lets a model name its plots without importing one —
    the last hard dependency the compute side had on the GUI.
    """
    specs: typing.List[typing.Tuple[type, dict]] = []
    for plot in getattr(view, "plots", ()):  # PlotSpec items
        plot_class = get_plot_class(plot.key)
        if plot_class is not None:
            specs.append((plot_class, dict(plot.options)))
    return specs


@register_section("fitting_parameter")
def _fitting_parameter_section_factory(model, target: str, **opts):
    """Render a single FittingParameter as a FittingParameterWidget.

    An optional ``prior`` option (a prior-state dict or ``None``) declared in
    the view spec is applied to the parameter before the widget is built, so a
    single-parameter section can ship a default prior just like a
    ``parameter_group`` section's ``priors`` map.

    ``label`` is accepted as the spelling of the caption, because that is what
    :class:`~chisurf.core.dataspec.FittingParameterSection` declares and
    therefore what a view spec author writes; the widget's own keyword is
    ``label_text``. Passing the declared name through unmapped raised
    ``unexpected keyword argument 'label'``, which the renderer logged and then
    skipped the section -- an editor missing one control and otherwise looking
    correct.
    """
    from chisurf.gui.widgets.fitting.parameter_widgets import FittingParameterWidget

    fp = getattr(model, target)
    if "prior" in opts:
        spec = opts.pop("prior")
        try:
            from chisurf.core.fitting.priors import as_prior

            fp.prior = as_prior(spec) if spec is not None else None
        except Exception:
            import chisurf.logging

            chisurf.logging.warning("fitting_parameter: invalid prior spec for %r ignored", target)
    if "label" in opts:
        opts.setdefault("label_text", opts.pop("label"))
    return FittingParameterWidget(fitting_parameter=fp, **opts)
