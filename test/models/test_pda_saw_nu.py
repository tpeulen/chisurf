"""Tests for the SAW-ν polymer-distance PDA model."""

from __future__ import annotations

import json
import pathlib

import numpy as np


def test_saw_nu_distances_distribution():
    from chisurf.core.models.pda.saw_nu import PdaSawNuDistances

    g = PdaSawNuDistances(fit=None)
    d = g.distribution
    assert d.shape == (2, 96)                 # (r, p) on the rda_axis grid
    assert abs(float(d[1].sum()) - 1.0) < 1e-6
    assert len(g) == 1
    # nu controls the shape: an expanded chain peaks further out.
    g._nu.value = 0.7
    peak_exp = d[0][np.argmax(PdaSawNuDistances(fit=None).distribution[1])]
    assert np.all(g.distribution[1] >= 0)


def test_saw_nu_model_resolves_and_declares_view():
    from chisurf.core.models.model import ModelCurve
    from chisurf.core.models.pda.saw_nu import PdaSawNuModel
    from chisurf.core.models.pda.pdagauss import PdaGaussianDistanceModel

    assert issubclass(PdaSawNuModel, ModelCurve)
    assert issubclass(PdaSawNuModel, PdaGaussianDistanceModel)  # reuses machinery
    assert PdaSawNuModel.name.strip()
    assert PdaSawNuModel.view_spec_file == "saw_nu.view.json"


def test_saw_nu_view_spec_is_valid_and_targets_distances():
    p = pathlib.Path("chisurf/core/models/pda/saw_nu.view.json")
    v = json.loads(p.read_text())
    assert "sections" in v and "plots" in v
    dist_panels = [s for s in v["sections"] if s.get("title") == "Distance distribution"]
    assert dist_panels, "no distance-distribution panel"
    inner = dist_panels[0]["sections"]
    assert any(s.get("type") == "parameter_group_table" and s.get("target") == "distances"
               for s in inner)
