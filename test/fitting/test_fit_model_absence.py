"""A fit without a model, and a group's own data.

``Fit.model`` used to return ``None`` while being typed as a model curve, so
every caller either checked for ``None`` or failed one attribute later with
``'NoneType' has no attribute``. It now raises an ``AttributeError`` subclass:
``getattr(fit, "model", None)`` and ``hasattr`` keep answering "no model"
exactly as before, and a direct access says what is missing.
"""

from __future__ import annotations

import numpy as np
import pytest


def _curve():
    from chisurf.core.data import DataCurve

    return DataCurve(x=np.arange(8.0), y=np.ones(8))


def test_a_fit_without_a_model_says_so():
    from chisurf.core.fitting.fit import Fit, NoModelError

    fit = Fit(data=_curve())
    assert getattr(fit, "model", None) is None
    assert not hasattr(fit, "model")
    with pytest.raises(NoModelError, match="no model"):
        _ = fit.model
    with pytest.raises(AttributeError):
        _ = fit.model_curve


def test_a_group_keeps_its_data_group_and_reads_the_members_curve():
    from chisurf.core.data import DataCurveGroup
    from chisurf.core.fitting.fit import FitGroup

    group = DataCurveGroup([_curve(), _curve()], name="pair")
    fit_group = FitGroup(group)
    assert fit_group.data_group is group
    assert fit_group.data is fit_group.grouped_fits[0].data
