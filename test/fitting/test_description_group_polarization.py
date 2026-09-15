"""A group of described polarised fits takes VV, VH from position, as the classic ones did.

The rule is data: a description's ``presentation.group_position`` names the
scalar (``polarization``) and its values, so the view knows no family.
"""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("IMP.bff")

from chisurf.core.data import DataCurve, ExperimentDataCurveGroup
from chisurf.core.fitting.fit import FitGroup
from chisurf.core.models.description import for_family

VM, VV, VH = 0.0, 1.0, 2.0


def _group(family, n):
    x = np.arange(128) * 0.05
    curves = [DataCurve(x=x, y=np.exp(-x / 3.0) * 1000.0 + 1.0, name=f"d{i}") for i in range(n)]
    return FitGroup(data=ExperimentDataCurveGroup(curves), model_class=for_family(family))


@pytest.mark.parametrize("family", ["tcspc_polarized", "tcspc_fret_gaussian", "tcspc_pddem"])
@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_polarization_follows_the_position_in_the_group(family, n):
    group = _group(family, n)
    got = [f.model.get_scalar("polarization") for f in group.grouped_fits]
    assert got == ([VM] if n == 1 else [VV if i % 2 == 0 else VH for i in range(n)])


def test_a_family_without_the_rule_is_left_alone():
    """tcspc_lifetime has no polarization scalar and no rule: grouping sets nothing."""
    group = _group("tcspc_lifetime", 2)
    for fit in group.grouped_fits:
        assert "polarization" not in fit.model.scalar_names()
        assert fit.model._scalars == {}
