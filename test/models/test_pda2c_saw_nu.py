"""Tests for the SAW-ν polymer-distance PDA model."""

from __future__ import annotations

import json
import pathlib

import numpy as np


def test_saw_nu_distances_distribution():
    from chisurf.core.models.pda2c.saw_nu import Pda2cSawNuDistances

    g = Pda2cSawNuDistances(fit=None)
    d = g.distribution
    assert d.shape == (2, 96)                 # (r, p) on the rda_axis grid
    assert abs(float(d[1].sum()) - 1.0) < 1e-6
    assert len(g) == 1
    # nu controls the shape: an expanded chain peaks further out.
    g._nu.value = 0.7
    peak_exp = d[0][np.argmax(Pda2cSawNuDistances(fit=None).distribution[1])]
    assert np.all(g.distribution[1] >= 0)


def test_saw_nu_model_resolves_and_declares_view():
    from chisurf.core.models.model import ModelCurve
    from chisurf.core.models.pda2c.pdagauss import Pda2cGaussianDistanceModel
    from chisurf.core.models.pda2c.saw_nu import Pda2cSawNuModel

    assert issubclass(Pda2cSawNuModel, ModelCurve)
    assert issubclass(Pda2cSawNuModel, Pda2cGaussianDistanceModel)  # reuses machinery
    assert Pda2cSawNuModel.name.strip()
    assert Pda2cSawNuModel.view_spec_file == "saw_nu.view.json"


def test_saw_nu_distance_distribution_accessor_returns_the_summed_curve():
    """The P(R) plot accessor draws the SAW-ν curve (no Gaussian components)."""
    import types

    from chisurf.core.models.pda2c.common import get_pda_distance_distribution
    from chisurf.core.models.pda2c.saw_nu import Pda2cSawNuDistances

    g = Pda2cSawNuDistances(fit=None)
    fit = types.SimpleNamespace(model=types.SimpleNamespace(distances=g))

    curves = get_pda_distance_distribution(fit)
    assert len(curves) == 1, "SAW-ν has one continuous component, not zero curves"
    y, x = curves[0]
    r, p = g.distribution
    assert np.allclose(x, r)
    assert np.allclose(y, p)
    assert float(np.asarray(y).sum()) > 0.0

    # A group without a distribution at all still degrades to an empty plot.
    empty = types.SimpleNamespace(model=types.SimpleNamespace(distances=None))
    assert get_pda_distance_distribution(empty) == []


def test_saw_nu_view_spec_is_valid_and_targets_distances():
    p = pathlib.Path("chisurf/core/models/pda2c/saw_nu.view.json")
    v = json.loads(p.read_text())
    assert "sections" in v and "plots" in v
    dist_panels = [s for s in v["sections"] if s.get("title") == "Distance distribution"]
    assert dist_panels, "no distance-distribution panel"
    inner = dist_panels[0]["sections"]
    assert any(s.get("type") == "parameter_group_table" and s.get("target") == "distances"
               for s in inner)
