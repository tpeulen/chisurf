"""Which pages a fit window has: plot keys from a model's ``view.json`` resolved to page classes.

A model names its fit-window pages by key in ``view_spec().plots`` (``"line"``,
``"residual"``, ``"distribution"``, ...) and never imports one. This module is the one
place a key becomes a class: :data:`PLOT_CLASSES` declares the shipped pages as
``"module:Class"`` strings, imported only when a fit window asks for that page, and
:func:`register_plot` lets a plugin add or override one. :func:`model_plot_specs` is
what a fit window calls: the model's pages, their accessors resolved, then the
fit-level pages (:data:`FIT_PLOT_KEYS`) every fit window has.

Toolkit-free: the fit windows (:mod:`chisurf.emtk.fit_window`) read their pages from here.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable

_log = logging.getLogger(__name__)

#: key -> ``"module:Class"`` of the shipped fit-window pages, imported on first use.
PLOT_CLASSES: dict[str, str] = {
    "line": "chisurf.emtk.fit_pages.pages.lineplot.lineplot:LinePlot",
    "residual": "chisurf.emtk.fit_pages.pages.wr_plot:ResidualPlot",
    "fit_info": "chisurf.emtk.fit_pages.pages.fitinfo:FitInfo",
    "fit_table": "chisurf.emtk.fit_pages.pages.table_plot_emtk:FitTablePlotEmtk",
    "parameter_scan": "chisurf.emtk.fit_pages.pages.parameter_scan.parameter_scan:ParameterScanPlot",
    "distribution": "chisurf.emtk.fit_pages.pages.distribution:DistributionPlot",
    "residual2d": "chisurf.emtk.fit_pages.pages.residual_image:Residual2DPlot",
    "mfd_2d": "chisurf.emtk.fit_pages.pages.mfd_2d:MfdMarginalPlot",
    "mfd_marginals": "chisurf.emtk.fit_pages.pages.mfd_2d:MfdMarginalPlot",
    "mfd_map": "chisurf.emtk.fit_pages.pages.mfd_map:MfdMapPlot",
    "lcurve": "chisurf.emtk.fit_pages.pages.lcurve:LCurvePlot",
    "pr_ci": "chisurf.emtk.fit_pages.pages.deer_pr:DeerPrCIPlot",
    "posterior_graph": "chisurf.emtk.fit_pages.pages.posterior_graph:PosteriorGraphPlot",
    "sampling_diagnostics": "chisurf.emtk.fit_pages.pages.sampling_diagnostics:SamplingDiagnosticsPlot",
    "conditional_scan": "chisurf.emtk.fit_pages.pages.conditional_scan:ConditionalScanPlot",
    # The Acquisition fit window's pages; each class docstring is the page's description.
    "acq_decay": "chisurf.emtk.fit_pages.pages.acquisition:DecayPage",
    "acq_correlation": "chisurf.emtk.fit_pages.pages.acquisition:CorrelationPage",
    "acq_count_rate": "chisurf.emtk.fit_pages.pages.acquisition:CountRatePage",
    "acq_mcs": "chisurf.emtk.fit_pages.pages.acquisition:McsPage",
    "acq_macrotime": "chisurf.emtk.fit_pages.pages.acquisition:MacrotimePage",
    "proteinmc_structure": "chisurf.emtk.fit_pages.pages.proteinMC:ProteinMCStructurePlot",
    "proteinmc_network": "chisurf.emtk.fit_pages.pages.proteinMC:ProteinMCDistanceNetworkPlot",
    "proteinmc_traces": "chisurf.emtk.fit_pages.pages.proteinMC:ProteinMCPlot",
    "state_scheme": "chisurf.emtk.fit_pages.pages.state_scheme_emtk:StateSchemePlot",
}

#: The fit-level pages every fit window has after the model's own (unless the model declared them).
FIT_PLOT_KEYS = ("posterior_graph", "sampling_diagnostics", "conditional_scan")

#: key -> factory returning the class: pages a plugin registered (they win over :data:`PLOT_CLASSES`).
_REGISTERED: dict[str, Callable[[], type]] = {}


def register_plot(key: str, factory: Callable[[], type]) -> None:
    """Register (or override) the page class of *key*; *factory* returns the class when asked."""
    _REGISTERED[str(key)] = factory


def get_plot_class(key: str) -> type | None:
    """The page class of *key* (``None`` for an unknown key).

    A shipped page whose module fails to import raises: a missing page must not look like a
    model that declared none.
    """
    factory = _REGISTERED.get(key)
    if factory is not None:
        return factory()
    path = PLOT_CLASSES.get(key)
    if path is None:
        return None
    module, _, name = path.partition(":")
    return getattr(importlib.import_module(module), name)


def resolve_plot_specs(view: Any) -> list[tuple[type, dict]]:
    """``(page class, options)`` of each plot a :class:`ModelView` declares; unknown keys are dropped."""
    specs: list[tuple[type, dict]] = []
    for plot in getattr(view, "plots", ()):
        plot_class = get_plot_class(plot.key)
        if plot_class is not None:
            specs.append((plot_class, dict(plot.options)))
    return specs


def resolve_accessor(accessor: str) -> Callable | None:
    """An accessor name of a page's options as the callable.

    Bare names (``"interleaved_to_two_columns"``) resolve against
    :mod:`chisurf.core.math.datatools`; a dotted or ``module:function`` path
    (``"chisurf.core.models.pda2c.common:get_pda_distribution"``) is imported, so
    model-specific accessors stay authorable in JSON.
    """
    if ":" in accessor or "." in accessor:
        if ":" in accessor:
            module, _, name = accessor.partition(":")
        else:
            module, _, name = accessor.rpartition(".")
        try:
            return getattr(importlib.import_module(module), name, None)
        except Exception:  # noqa: BLE001 - an unresolvable accessor draws nothing
            return None
    import chisurf.core.math.datatools as datatools

    return getattr(datatools, accessor, None)


def resolve_distribution_options(options: dict) -> dict:
    """A distribution page's options with the accessors under ``distribution_options`` resolved."""
    resolved = dict(options)
    dist = resolved.get("distribution_options")
    if isinstance(dist, dict):
        new_dist = {}
        for name, cfg in dist.items():
            cfg = dict(cfg)
            if isinstance(cfg.get("accessor"), str):
                cfg["accessor"] = resolve_accessor(cfg["accessor"])
            new_dist[name] = cfg
        resolved["distribution_options"] = new_dist
    return resolved


def _resolve_options(opts: dict) -> dict:
    """Every accessor a page's options name, as callables (JSON cannot hold one)."""
    opts = dict(opts)
    if "distribution_options" in opts:
        opts = resolve_distribution_options(opts)
    if isinstance(opts.get("accessor"), str):
        opts["accessor"] = resolve_accessor(opts["accessor"])
    # Multi-source image pages name one accessor per source, and optionally one for the count.
    if isinstance(opts.get("sources"), dict):
        opts["sources"] = {
            key: (
                {**spec, "accessor": resolve_accessor(spec["accessor"])}
                if isinstance(spec, dict) and isinstance(spec.get("accessor"), str)
                else spec
            )
            for key, spec in opts["sources"].items()
        }
    if isinstance(opts.get("max_frames_accessor"), str):
        opts["max_frames_accessor"] = resolve_accessor(opts["max_frames_accessor"])
    return opts


def fit_plot_specs(present: set) -> list[tuple[type, dict]]:
    """The fit-level pages (:data:`FIT_PLOT_KEYS`) a model did not declare itself."""
    specs: list[tuple[type, dict]] = []
    for key in FIT_PLOT_KEYS:
        cls = get_plot_class(key)
        if cls is not None and cls not in present:
            specs.append((cls, {}))
    return specs


def model_plot_specs(model: Any) -> list[tuple[type, dict]]:
    """``[(page class, options), ...]`` of a fit window for *model*.

    The model's ``view_spec().plots`` with their accessors resolved, then the fit-level pages.
    An empty list when the model declares no plots: a fit window with no pages is a visible,
    fixable state; substituting another model's pages is not.
    """
    try:
        view = model.view_spec()
    except Exception as exc:  # noqa: BLE001 - a model without a view has no pages
        _log.debug("model_plot_specs: view_spec() failed: %s", exc)
        return []
    if view is None:
        return []
    try:
        specs = [(cls, _resolve_options(opts)) for cls, opts in resolve_plot_specs(view)]
    except Exception as exc:  # noqa: BLE001 - logged; the window opens without pages
        _log.error("model_plot_specs: could not resolve plots: %s", exc)
        return []
    if not specs:
        return []
    return specs + fit_plot_specs({cls for cls, _ in specs})
