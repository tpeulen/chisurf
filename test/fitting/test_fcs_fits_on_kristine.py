"""Every FCS model fits the Kristine correlation curve from its defaults.

A fit that walks a physical parameter out of its domain ends at an infinite
chi2r, and a model whose only answer is its own inversion (MaxEnt) has nothing
free for the optimiser; both used to break the Fit button.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("IMP.bff")

import chisurf.core.fitting.fit as fit_mod
from chisurf.core.experiments.fcs import FCS
from chisurf.core.models.fcs.maxent_models import MaxEntFCSModel
from chisurf.core.models.fcs.mdf import MdfFCSModel

KRISTINE = "./test/data/fcs/kristine/Kristine_with_error.cor"


def _fit(model_class):
    data = FCS(name="Seidel Kristine", experiment_reader="kristine").read(filename=KRISTINE)
    group = fit_mod.FitGroup(data=data, model_class=model_class)
    member = group.grouped_fits[0]
    member.fit_range = (0, len(member.data.x))
    member.model.update()
    return group, member


def test_the_mdf_fit_stays_in_its_bounds():
    group, member = _fit(MdfFCSModel)
    start = member.chi2r
    group.run()
    assert math.isfinite(member.chi2r) and member.chi2r < start
    assert all(p.value > 0 for p in member.model.parameters if p.name in ("N", "D", "w0", "wem"))


def test_a_group_with_nothing_free_runs():
    group, member = _fit(MaxEntFCSModel)
    assert member.model.n_free == 0
    group.run()
    assert math.isfinite(member.chi2r)
