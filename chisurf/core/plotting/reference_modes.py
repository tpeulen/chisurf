"""Plot reference modes that need nothing from a model but its curves.

A line plot can show a curve normalised to something -- its total photons, its
peak. What that takes is the plotted curve and the fit window, so the modes
are named here once and any model lists the names it offers: the classic
TCSPC models by calling :func:`photon_modes`, a BFF-described model by naming
them in its description's ``presentation.reference_modes``.
"""

from __future__ import annotations

import numpy as np

from chisurf import typing
import chisurf.core.plotting.transforms as plot_transforms


def _window(context: plot_transforms.PlotReferenceContext) -> np.ndarray:
    """The finite y-values normalised against: all of them, or the fit range."""
    y = np.asarray(context.y, dtype=float)
    if not bool(context.parameters.get("fit_range_only", False)):
        return y[np.isfinite(y)]
    try:
        data_x = np.asarray(getattr(getattr(context.fit, "data", None), "x", []), dtype=float)
        if y.size == data_x.size:
            xmin = int(getattr(context.fit, "xmin", 0))
            xmax = int(getattr(context.fit, "xmax", y.size))
            y = y[max(0, xmin):min(y.size, xmax)]
    except Exception:
        pass
    return y[np.isfinite(y)]


def total_photons(context: plot_transforms.PlotReferenceContext) -> plot_transforms.PlotReferenceResult:
    """Counts divided by the total photons in the window."""
    denominator = float(np.nansum(_window(context)))
    if not np.isfinite(denominator) or denominator == 0.0:
        raise ValueError("total photon count is zero")
    return plot_transforms.PlotReferenceResult(
        x=context.x, y=np.asarray(context.y, dtype=float) / denominator,
        y_label="counts / total photons")


def peak_photons(context: plot_transforms.PlotReferenceContext) -> plot_transforms.PlotReferenceResult:
    """Counts divided by the peak count in the window."""
    window = _window(context)
    if window.size == 0:
        raise ValueError("peak photon count is unavailable")
    denominator = float(np.nanmax(window))
    if not np.isfinite(denominator) or denominator == 0.0:
        raise ValueError("peak photon count is zero")
    return plot_transforms.PlotReferenceResult(
        x=context.x, y=np.asarray(context.y, dtype=float) / denominator,
        y_label="counts / peak photons")


def _fit_range_parameter() -> plot_transforms.PlotReferenceParameter:
    return plot_transforms.PlotReferenceParameter(
        key="fit_range_only", label="fit range", kind="bool", default=False)


def _total_photons_mode() -> plot_transforms.PlotReferenceMode:
    return plot_transforms.PlotReferenceMode(
        key="tcspc_total_photons", label="Total photons", callback=total_photons,
        parameters=(_fit_range_parameter(),), applies_to=("data", "model"),
        y_label="counts / total photons", y_range=(0, 1.0), y_padding=0.05)


def _peak_photons_mode() -> plot_transforms.PlotReferenceMode:
    return plot_transforms.PlotReferenceMode(
        key="tcspc_peak_photons", label="Peak photons", callback=peak_photons,
        parameters=(_fit_range_parameter(),), applies_to=("data", "model"),
        y_label="counts / peak photons", y_range=(0, 1.0), y_padding=0.05)


#: Name -> factory of a reference mode that reads only curves and the fit.
REFERENCE_MODES: typing.Dict[str, typing.Callable[[], plot_transforms.PlotReferenceMode]] = {
    "tcspc_total_photons": _total_photons_mode,
    "tcspc_peak_photons": _peak_photons_mode,
}


def photon_modes() -> typing.List[plot_transforms.PlotReferenceMode]:
    """The total- and peak-photon normalisations."""
    return [REFERENCE_MODES["tcspc_total_photons"](), REFERENCE_MODES["tcspc_peak_photons"]()]


def modes_named(names: typing.Iterable[str]) -> typing.List[plot_transforms.PlotReferenceMode]:
    """The registered modes for *names*; an unknown name is skipped."""
    return [REFERENCE_MODES[n]() for n in names if n in REFERENCE_MODES]
