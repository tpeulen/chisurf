"""An FCS model with added relaxation terms is recorded and restored with them.

The terms are the model's topology: a bunching term adds two parameters, and a
saved model that did not record how many it had was rebuilt without them, so
recording failed with "parameter count changed (44 != 46)" -- in the emtk
shell, on every change once a bunching term was added.
"""

from __future__ import annotations

import pytest

from chisurf.core.experiments.core.experiment import Experiment
from chisurf.core.fitting.fit import Fit
from chisurf.core.models.fcs.general import GeneralFCSModel
from chisurf.core.models.fcs.mdf import MdfFCSModel
from chisurf.core.project.session import capture_session, restore_session

KRISTINE = "test/data/fcs/kristine/Kristine_with_error.cor"


def _fit(cls):
    from chisurf.core.experiments.fcs.reader import FCS

    experiment = Experiment(name="fcs")
    experiment.add_model_class(cls)
    reader = FCS(experiment=experiment, experiment_reader="kristine", record_provenance=False)
    data = reader.get_data(filename=KRISTINE)[0]
    return data, Fit(model_class=cls, data=data)


@pytest.mark.parametrize("cls", [GeneralFCSModel, MdfFCSModel])
def test_added_relaxation_terms_survive_the_session_codec(cls):
    data, fit = _fit(cls)
    model = fit.model
    model.bunching.add_bunching()
    model.bunching.add_bunching(ba=0.2, bt=0.05)
    if hasattr(model, "anticorr"):
        model.anticorr.add_anticorr()
    model.find_parameters()

    restored = restore_session(capture_session([data], [fit])).fits[0].model
    assert len(restored.bunching) == 2
    assert restored.bunching.terms()[1] == pytest.approx((0.2, 0.05))
    if hasattr(model, "anticorr"):
        assert len(restored.anticorr) == 1


def test_a_term_count_is_set_not_accumulated():
    _, fit = _fit(GeneralFCSModel)
    terms = fit.model.bunching
    terms.set_count(3)
    terms.set_count(1)
    assert len(terms) == 1
    with pytest.raises(ValueError):
        terms.set_count(-1)
