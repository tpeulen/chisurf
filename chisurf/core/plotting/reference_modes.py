"""Plot reference modes that need nothing from a model but its curves.

A line plot can show a curve normalised to something -- its total photons, its
peak, its donor-only reference -- or show r(t) from a VV/VH pair. The modes
are named here once and a BFF-described model lists the names it offers in
its description's ``presentation.reference_modes``.
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


def _parameter(model, canonical: str, default: float) -> float:
    """A described model's parameter value, or ``default``."""
    for parameter in getattr(model, "parameters_all", ()) or ():
        if getattr(parameter, "canonical_id", None) == canonical:
            try:
                return float(parameter.value)
            except Exception:
                break
    return float(default)


def _group_channel(context: plot_transforms.PlotReferenceContext, code: float):
    """The curve of the group member whose model is set to polarization ``code``."""
    for fit in tuple(context.group_fits or ()) or (context.fit,):
        model = getattr(fit, "model", None)
        try:
            if float(model.get_scalar("polarization")) != code:
                continue
        except Exception:
            continue
        if context.curve_key == "model":
            return np.asarray(model.y, dtype=float)
        return np.asarray(getattr(fit.data, "y", []), dtype=float)
    return None


def anisotropy_rt(context: plot_transforms.PlotReferenceContext) -> plot_transforms.PlotReferenceResult:
    """r(t) from a fit group's VV and VH members, drawn once, on the selected member."""
    from chisurf.core.fluorescence.anisotropy.rt import rt_curves

    hidden = plot_transforms.PlotReferenceResult(context.x, context.y, visible=False)
    if context.curve_key not in ("data", "model"):
        return hidden
    if context.group_index is not None and context.selected_group_index is not None:
        if int(context.group_index) != int(context.selected_group_index):
            return hidden
    vv, vh = _group_channel(context, 1.0), _group_channel(context, 2.0)
    if vv is None or vh is None or vv.size != vh.size:
        return hidden
    p = context.parameters
    vv = vv - float(p.get("bg_vv", 0.0))
    vh = vh - float(p.get("bg_vh", 0.0))
    t = np.asarray(context.x, dtype=float)[:vv.size]
    shift = float(p.get("vh_shift", 0.0))
    if shift:
        vh = np.interp(t, t + shift, vh)
    tt, r_unc, r_cor = rt_curves(t, vv, vh, float(p.get("g", 1.0)), float(p.get("l1", 0.0)), float(p.get("l2", 0.0)))
    y = r_unc if str(p.get("variant", "corrected")) == "uncorrected" else r_cor
    return plot_transforms.PlotReferenceResult(x=tt, y=y, y_label="r(t)")


def _anisotropy_rt_mode(model=None) -> plot_transforms.PlotReferenceMode:
    P = plot_transforms.PlotReferenceParameter
    return plot_transforms.PlotReferenceMode(
        key="tcspc_anisotropy_rt", label="r(t) anisotropy", callback=anisotropy_rt,
        parameters=(
            P("g", "g", "float", _parameter(model, "anisotropy.g", 1.0), step=0.01),
            P("l1", "l1", "float", _parameter(model, "anisotropy.l1", 0.0), step=0.001),
            P("l2", "l2", "float", _parameter(model, "anisotropy.l2", 0.0), step=0.001),
            P("bg_vv", "BgVV", "float", 0.0, step=1.0),
            P("bg_vh", "BgVH", "float", 0.0, step=1.0),
            P("vh_shift", "dVH", "float", 0.0, step=0.01),
            P("variant", "variant", "choice", "corrected",
              choices=(("corrected", "corrected"), ("uncorrected", "uncorrected"))),
        ),
        applies_to=("data", "model"), y_label="r(t)", y_range=(-0.05, 0.45), y_padding=0.0)


def donor_reference(context: plot_transforms.PlotReferenceContext) -> plot_transforms.PlotReferenceResult:
    """A FRET curve divided by the donor-only decay the same model predicts.

    The reference is the model with its donor-only fraction at one -- the same
    donor, instrument and response -- so dividing leaves the transfer.
    """
    model = context.model
    parameter = next((p for p in getattr(model, "parameters_all", ()) or ()
                      if getattr(p, "canonical_id", None) == "fret.x_donly"), None)
    if parameter is None:
        raise ValueError("the model has no donor-only fraction to take a reference from")
    held = parameter.value
    try:
        parameter.value = 1.0
        model.update()
        reference = np.maximum(np.asarray(model.y, dtype=float), 0.0)
    finally:
        parameter.value = held
        model.update()
    peak = float(np.nanmax(reference)) if reference.size else 0.0
    if not np.isfinite(peak) or peak <= 0.0:
        raise ValueError("the donor reference is empty")
    scale = str(context.parameters.get("scale", "data_peak"))
    if scale == "data_peak":
        y_peak = float(np.nanmax(np.asarray(context.y, dtype=float)))
        if np.isfinite(y_peak) and y_peak > 0.0:
            reference = reference * (y_peak / peak)
    elif scale == "reference_peak":
        reference = reference / peak
    y = np.asarray(context.y, dtype=float)
    n = min(y.size, reference.size, np.asarray(context.x).size)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(np.abs(reference[:n]) > 1e-15, y[:n] / reference[:n], np.nan)
    return plot_transforms.PlotReferenceResult(x=np.asarray(context.x)[:n], y=out, y_label="counts / donor reference")


def _donor_reference_mode(model=None) -> plot_transforms.PlotReferenceMode:
    return plot_transforms.PlotReferenceMode(
        key="tcspc_donor_reference", label="Donor reference", callback=donor_reference,
        parameters=(plot_transforms.PlotReferenceParameter(
            key="scale", label="scale", kind="choice", default="data_peak",
            choices=(("data_peak", "data peak"), ("reference_peak", "reference peak"), ("none", "none"))),),
        applies_to=("data", "model"), y_label="counts / donor reference", y_range=(0, 1.0), y_padding=0.05)


#: Name -> factory of a reference mode. The photon modes read only curves and
#: the fit; r(t) reads the fit group's VV and VH members, and the donor
#: reference re-evaluates a described FRET model with its donor-only fraction at one.
REFERENCE_MODES: typing.Dict[str, typing.Callable[..., plot_transforms.PlotReferenceMode]] = {
    "tcspc_total_photons": _total_photons_mode,
    "tcspc_peak_photons": _peak_photons_mode,
    "tcspc_anisotropy_rt": _anisotropy_rt_mode,
    "tcspc_donor_reference": _donor_reference_mode,
}

_MODEL_AWARE = {"tcspc_anisotropy_rt", "tcspc_donor_reference"}


def photon_modes() -> typing.List[plot_transforms.PlotReferenceMode]:
    """The total- and peak-photon normalisations."""
    return [REFERENCE_MODES["tcspc_total_photons"](), REFERENCE_MODES["tcspc_peak_photons"]()]


def modes_named(names: typing.Iterable[str], model=None) -> typing.List[plot_transforms.PlotReferenceMode]:
    """The registered modes for *names*, their defaults read from *model*; an unknown name is skipped."""
    return [REFERENCE_MODES[n](model) if n in _MODEL_AWARE else REFERENCE_MODES[n]()
            for n in names if n in REFERENCE_MODES]
