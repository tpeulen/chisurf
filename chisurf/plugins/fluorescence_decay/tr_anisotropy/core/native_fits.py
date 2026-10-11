"""Construct the wizard's linked VV, VH and global fits without GUI objects."""

from __future__ import annotations

import re

import numpy as np

from chisurf.core.data import ExperimentDataCurveGroup
from chisurf.core.models.description import for_family
from chisurf.core.models.global_model.globalfit import GlobalFitModel
from chisurf.emtk.datasets import build_fit_group, publish_fit_group, register_dataset

from .fits import apply_link_plan, build_link_plan


def configure_components(model, key, pairs):
    pairs = np.asarray(pairs, dtype=float)
    if pairs.ndim != 2 or pairs.shape[1] != 2 or not len(pairs) or not np.isfinite(pairs).all():
        raise ValueError(f"{key} needs finite amplitude/value pairs.")
    if np.any(pairs[:, 0] < 0) or np.any(pairs[:, 1] <= 0):
        raise ValueError(f"{key} amplitudes must be nonnegative and times positive.")

    def group():
        return next(group for group in model._groups.values() if group.key == key)

    for _ in range(abs(len(group().component_parameters()) // 2 - len(pairs))):
        count = len(group().component_parameters()) // 2
        if not model.change_components(key, 1 if count < len(pairs) else -1):
            raise ValueError(f"The model cannot represent {len(pairs)} {key} components.")
    parameters = group().component_parameters()
    for parameter, value in zip(parameters, pairs.reshape(-1)):
        parameter.value = float(value)


class LocalLinkClient:
    """Replay the established link plan against live pure fitting parameters."""

    def __init__(self, fits):
        self.fits = fits

    def parameter(self, index, name):
        model = self.fits[index].model
        canonical = {
            "n0": "instrument.n0",
            "lb": "instrument.response_background",
            "g": "anisotropy.g",
            "l1": "anisotropy.l1",
            "l2": "anisotropy.l2",
        }.get(name)
        match = re.fullmatch(r"(xL|tL)(\d+)", name)
        if match:
            canonical = f"lifetime.{'amplitude' if match[1] == 'xL' else 'tau'}.{int(match[2]) - 1}"
        match = re.fullmatch(r"(b|rho)\((\d+)\)", name)
        if match:
            canonical = f"rotation.{'amplitude' if match[1] == 'b' else 'time'}.{int(match[2]) - 1}"
        for parameter in model.parameters_all:
            if parameter.canonical_id == canonical or parameter.name == name:
                return parameter
        raise KeyError(f"Missing anisotropy parameter: {name}")

    def link_parameters(self, parameter_name, target_parameter_name, fit_index, target_fit_index):
        follower = self.parameter(fit_index, parameter_name)
        master = self.parameter(target_fit_index, target_parameter_name)
        master.is_link_master = True
        follower.is_link_master = False
        follower.link = master

    def set_parameter_value(self, parameter_name, value, fit_index):
        self.parameter(fit_index, parameter_name).value = value

    def set_parameter_fixed(self, parameter_name, fixed, fit_index):
        self.parameter(fit_index, parameter_name).fixed = fixed

    def update_fit(self, fit_index):
        self.fits[fit_index].update()


def set_response_window(model, window, dt):
    """Use only the IRF channels ``[start, stop)`` (``window``) in *model*'s convolution.

    The model clips the background-subtracted IRF at zero, so a noisy tail used over the
    whole range adds a constant offset to the model decay (see
    :func:`..irf.response_window`). The window is the model's own *IRF start / stop*
    (ns), so the user sees and can change it in the model editor.
    """
    start, stop = (int(v) for v in window)
    if stop <= start or dt <= 0:
        return
    # The description floors ``response_start / dt``; nudge above the exact product so
    # binary rounding (40 * 0.05 / 0.05 = 39.999...) cannot drop a channel.
    eps = 1.0 + 1e-9
    model.set_scalar("response_start", start * dt * eps)
    model.set_scalar("response_stop", stop * dt * eps)


def create_linked_fits(data, lifetimes, rotations, corrections, irf_window=None):
    """Register four datasets, two polarized fits and their shared global fit.

    ``irf_window`` (channel indices ``(start, stop)``, from
    :func:`..irf.response_window`) restricts both IRFs to the channels they occupy.
    """
    required = ("irf_vv_bg_norm", "irf_vh_bg_norm", "data_vv", "data_vh")
    if any(data.get(key) is None for key in required):
        raise ValueError("Load all curves and normalize the IRFs first.")
    if any(np.asarray(data[key].y).sum() <= 0 for key in required[:2]):
        raise ValueError("Corrected IRFs contain no signal; choose a dark background region.")
    if corrections["g_factor"] <= 0 or not all(
        np.isfinite(value) for value in corrections.values()
    ):
        raise ValueError("Corrections must be finite and g-factor positive.")
    # Validate before altering the session registry.
    for label, pairs in (("lifetimes", lifetimes), ("rotations", rotations)):
        values = np.asarray(pairs, dtype=float)
        if (
            values.ndim != 2
            or values.shape[1] != 2
            or not len(values)
            or not np.isfinite(values).all()
            or np.any(values[:, 0] < 0)
            or np.any(values[:, 1] <= 0)
        ):
            raise ValueError(f"{label} require nonnegative amplitudes and positive times.")
    model_class = for_family("tcspc_polarized")
    groups = []
    for role in ("vv", "vh"):
        dataset = ExperimentDataCurveGroup([data[f"data_{role}"]])
        dataset.name = f"Anisotropy {role.upper()}"
        dataset.meta_data.update(corrections)
        group = build_fit_group(dataset, model_class, model_kw=corrections)
        model = group.model
        model.anisotropy.polarization_type = role
        model.convolve._irf = data[f"irf_{role}_bg_norm"]
        if irf_window is not None:
            x = np.asarray(data[f"irf_{role}_bg_norm"].x, dtype=float)
            set_response_window(model, irf_window, float(np.mean(np.diff(x))) if x.size > 1 else 0.0)
        configure_components(model, "lifetimes", lifetimes)
        configure_components(model, "rotations", rotations)
        for parameter in model.parameters_all:
            if parameter.canonical_id == "anisotropy.r0":
                parameter.value = float(np.asarray(rotations)[:, 0].sum())
        groups.append(group)
    apply_link_plan(
        LocalLinkClient(groups), build_link_plan(len(lifetimes), len(rotations), corrections), 0, 1
    )
    for group in groups:
        group.update()
    # Use the existing GlobalFitModel rather than duplicating its objective.
    global_data = ExperimentDataCurveGroup([data["data_vv"]])
    global_data.name = "Global anisotropy"
    global_group = build_fit_group(global_data, GlobalFitModel, model_kw={"fits": groups})
    global_group.name = "Global anisotropy"
    for key in required:
        register_dataset(data[key])
    for role, group in zip(("vv", "vh"), groups):
        publish_fit_group(group, data[f"data_{role}"], model_class.name)
    publish_fit_group(global_group, data["data_vv"], GlobalFitModel.name)
    return groups[0], groups[1], global_group
