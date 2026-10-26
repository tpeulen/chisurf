"""The data-kind vocabulary: every experiment has a kind, the DTO carries it, fits refuse non-curves."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core import data_kinds
from chisurf.core.data import DataCurve, DataCurveGroup
from chisurf.core.experiments.core.experiment import Experiment


def _registered_experiment_names() -> set[str]:
    import chisurf as cs
    from chisurf.core.experiments.bootstrap import ensure_experiments_registered

    ensure_experiments_registered()
    return {str(e.name) for e in cs.experiment.values()}


def test_every_registered_experiment_is_mapped_and_no_entry_is_stale():
    """A new experiment needs a kind decided, not guessed; a removed one leaves the table."""
    names = _registered_experiment_names()
    assert names == set(data_kinds.EXPERIMENT_KINDS), (
        f"unmapped: {sorted(names - set(data_kinds.EXPERIMENT_KINDS))}, "
        f"stale: {sorted(set(data_kinds.EXPERIMENT_KINDS) - names)}"
    )
    for kind in data_kinds.EXPERIMENT_KINDS.values():
        assert kind is None or kind in data_kinds.KINDS


def _curve(experiment: str, name: str = "c") -> DataCurve:
    curve = DataCurve(x=np.arange(4.0), y=np.ones(4), ey=np.ones(4), name=name)
    curve.experiment = Experiment(name=experiment)
    return curve


@pytest.mark.parametrize(
    "experiment, kind",
    [
        ("TCSPC", "decay"),
        ("FCS", "correlation"),
        ("PDA", "histogram"),
        ("DEER", "trace"),
        ("Global", None),
    ],
)
def test_a_curve_has_the_kind_of_its_experiment(experiment, kind):
    assert data_kinds.kind_of(_curve(experiment)) == kind


def test_a_class_that_is_a_kind_of_its_own_says_so():
    class Photons(DataCurve):
        data_kind = "photons"

    assert data_kinds.kind_of(Photons(x=np.arange(2.0), y=np.ones(2))) == "photons"


def test_an_unlisted_experiment_has_no_kind_and_is_reported(caplog):
    with caplog.at_level("WARNING"):
        assert data_kinds.kind_of_experiment("Brand new experiment") is None
    assert "has no data kind" in caplog.text


def test_the_dataset_dto_carries_the_kind():
    from chisurf.server.services.datasets import _dataset_dto

    assert _dataset_dto(_curve("TCSPC"), 0)["kind"] == "decay"
    assert _dataset_dto(_curve("FCS"), 1)["kind"] == "correlation"


def test_a_fit_refuses_data_of_a_kind_no_model_takes():
    from chisurf.core.fitting.fit import FitGroup

    class Photons(DataCurve):
        data_kind = "photons"

    stream = Photons(x=np.arange(4.0), y=np.ones(4), ey=np.ones(4), name="m000")
    with pytest.raises(ValueError, match="photons data"):
        FitGroup(data=DataCurveGroup([stream]), model_class=type)


def test_fittable_kinds():
    assert data_kinds.is_fittable("decay") and data_kinds.is_fittable(None)
    assert not data_kinds.is_fittable("photons") and not data_kinds.is_fittable("bursts")
