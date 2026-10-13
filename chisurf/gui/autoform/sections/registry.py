"""GUI-side registry that resolves view-spec keys to custom-section widgets.

A model describes its editor with string keys (see
:mod:`chisurf.core.models.view_spec`) and never references a Qt class. This
module is the GUI-side counterpart: it maps those keys to custom-section
factories. Plot keys resolve in :mod:`chisurf.emtk.fit_pages.plots`, re-exported
here for the sections that register or look up a page.
"""

from __future__ import annotations

import importlib

from chisurf import typing

# The fit-window pages live with the fit window (Qt-free); a section module still
# registers or looks a page up through these names.
from chisurf.emtk.fit_pages.plots import (  # noqa: F401 - re-exported
    get_plot_class,
    register_plot,
    resolve_plot_specs,
)

#: key -> custom-section factory ``(model, target, **options) -> QWidget``.
_SECTION_REGISTRY: typing.Dict[str, typing.Callable[..., typing.Any]] = {}


# Shipped registrations; test_fit_first_use checks these against the source ASTs.
_SECTION_MODULES = {
    "anisotropy_diagnostics": "anisotropy_diagnostics_section",
    "background_run": "background_run_section",
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
