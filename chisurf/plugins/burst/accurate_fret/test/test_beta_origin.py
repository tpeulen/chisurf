"""Beta's *Determined by* names where beta came from.

tttrlib's calibration reported which of alpha, delta and gamma the data
identified but not beta, so the factor table said "source not reported" next to a
beta the 1/S = Omega + Sigma*E fit had measured (guide 14's figure). tttrlib now
reports ``estimated["beta"]``; one FRET population still reads as the 1:1
labelling assumption and no ALEX as not identified.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.fret.accurate import auto_calibrate

from .test_accurate_fret_plugin import _simulate


def test_beta_from_two_fret_populations_is_a_data_estimate():
    dd, da, aa, _ = _simulate()
    result = auto_calibrate(dd, da, aa)
    assert result.estimated["beta"] is True
    assert result.factor_provenance["beta"] == "data"


def test_beta_from_one_population_is_the_labelling_assumption():
    dd, da, aa, _ = _simulate(efficiencies=(0.5,))
    assert auto_calibrate(dd, da, aa).factor_provenance["beta"] == "stoichiometry_assumption"


def test_beta_without_alex_is_not_identified():
    dd, da, _, _ = _simulate()
    result = auto_calibrate(dd, da, None)
    assert result.factor_provenance["beta"] == "not_identified"
    assert np.isfinite(result.factors["beta"])
