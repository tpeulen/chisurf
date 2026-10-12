"""ProteinMC compares no curve, so asking its fit for a chi-squared must not log a failure.

The fit's data is a ``Structure``. The base model read ``fit.data.y`` for the residuals, so every
``chi2`` / ``chi2r`` read logged ``calculate_weighted_residuals: C++ path failed (Structure object
has no attribute 'y')`` and then died in the numpy fallback.
"""

import logging
import math
from pathlib import Path

import numpy as np

PDB = Path(__file__).resolve().parents[1] / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"


def _fit():
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.structure.proteinmc_model import ProteinMCModel
    from chisurf.core.structure import Structure

    fit = Fit(data=Structure(str(PDB)))
    fit.model = ProteinMCModel(fit)
    return fit


def test_a_structure_fit_has_no_residuals_and_no_chi2(caplog):
    fit = _fit()
    with caplog.at_level(logging.WARNING):
        assert fit.model.weighted_residuals.size == 0
        assert math.isnan(fit.chi2)
        assert math.isnan(fit.chi2r)
    assert "C++ path failed" not in caplog.text
    assert fit.model.n_points == 0
    assert isinstance(fit.model.weighted_residuals, np.ndarray)
