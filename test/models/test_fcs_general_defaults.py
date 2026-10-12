"""The general FCS model starts from an identifiable fit, and its editor shows only live panels.

Found walking the diffusion-FCS guide (2026-10-11): with the defaults, a single-focus fit
varied D, w_r and w_z together although the curve depends on D/w_r² and D/w_z² only, so the
reported D followed the start value (Kristine: 166 µm²/s from one start, 39 µm²/s after a
bunching term was added); and the *Outputs (MDF mode)* panel showed all-N/A rows in the Gauss
and two-focus modes, where nothing computes them.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit as F
from chisurf.core.models.fcs.general import GeneralFCSModel

VIEW = (
    Path(__file__).resolve().parents[2]
    / "chisurf"
    / "core"
    / "models"
    / "fcs"
    / "general.view.json"
)


def _fit():
    tau = np.logspace(-4.0, 2.5, 200)
    data = chisurf.core.data.DataCurve(x=tau, y=np.ones_like(tau), ey=np.full(tau.size, 1e-3))
    fit = F.Fit(model_class=GeneralFCSModel, data=data)
    fit.model.find_parameters()
    return fit


def test_single_focus_fixes_the_waist_and_two_focus_frees_it():
    model = _fit().model
    assert model.diffusion_mode == "gauss"
    assert model.gauss._w_r.fixed, "D and w_r are degenerate in one focus"
    assert not model.gauss._D.fixed and not model.gauss._w_z.fixed
    assert model.species._w_r.fixed
    assert not model.two_focus._w_r.fixed, "a known focus separation sets the length scale"
    free = {p.name for p in model.parameters_all if not p.fixed and not p.is_output}
    assert {"D", "w_r"} - free == {"w_r"}


def test_the_default_fit_is_not_rank_deficient():
    """D/w_r² and D/w_z²: the default free set has a full-rank Jacobian on a diffusion curve."""
    fit = _fit()
    model = fit.model
    free = [p for p in model.parameters_all if not p.fixed and not p.is_output]

    def curve():
        model.update()
        return np.asarray(model.y, dtype=float).copy()

    jac = []
    for p in free:
        v = float(p.value)
        p.value = v * (1 + 1e-4) + 1e-9
        up = curve()
        p.value = v
        jac.append((up - curve()) / (v * 1e-4 + 1e-9))
    s = np.linalg.svd(np.asarray(jac).T, compute_uv=False)
    assert s[-1] / s[0] > 1e-8, f"degenerate free set {[p.name for p in free]}: {s}"


@pytest.mark.parametrize("mode, shown", [("gauss", False), ("two_focus", False), ("mdf", True)])
def test_the_mdf_outputs_panel_shows_only_in_mdf_mode(mode, shown):
    spec = json.loads(VIEW.read_text("utf-8"))
    panel = next(s for s in spec["sections"] if s.get("title") == "Outputs (MDF mode)")
    rule = panel["hidden_when"]
    hidden = mode != rule["not_equals"] if "not_equals" in rule else mode == rule["equals"]
    assert rule["attr"] == "diffusion_mode"
    assert hidden is not shown
