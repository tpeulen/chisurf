from __future__ import annotations

import numpy as np

import chisurf.core.plotting.transforms as plot_transforms
from chisurf.core.plotting import reference_modes


class _Curve:
    """Small curve object for transform tests."""

    def __init__(self, x, y):
        """Initialize the curve.

        Parameters
        ----------
        x : array_like
            X-values.
        y : array_like
            Y-values.
        """
        self.x = np.asarray(x, dtype=float)
        self.y = np.asarray(y, dtype=float)


class _Fit:
    """Small fit object for transform tests."""

    def __init__(self, x, y):
        """Initialize the fit.

        Parameters
        ----------
        x : array_like
            X-values.
        y : array_like
            Y-values.
        """
        self.data = _Curve(x, y)
        self.xmin = 1
        self.xmax = 3


def _context(model, y, parameters=None, curve_key="data", group_fits=()):
    """Create a plot reference context for TCSPC tests.

    Parameters
    ----------
    model : object
        Model object.
    y : array_like
        Curve values.
    parameters : dict, optional
        Plot-only parameters.
    curve_key : str
        Curve key.

    Returns
    -------
    PlotReferenceContext
        Context object.
    """
    x = np.arange(len(y), dtype=float)
    fit = _Fit(x, y)
    return plot_transforms.PlotReferenceContext(
        fit=fit,
        model=model,
        curve_key=curve_key,
        x=x,
        y=np.asarray(y, dtype=float),
        curves={},
        group_fits=tuple(group_fits),
        parameters=parameters or {},
    )


def test_tcspc_total_photon_mode_uses_fit_range_parameter():
    """TCSPC total-photon mode should use optional fit-range denominator."""
    context = _context(None, [1.0, 2.0, 3.0, 4.0], {"fit_range_only": True})
    result = reference_modes.total_photons(context)
    np.testing.assert_allclose(result.y, np.array([1.0, 2.0, 3.0, 4.0]) / 5.0)


def test_tcspc_peak_photon_mode_uses_peak_denominator():
    """TCSPC peak-photon mode should divide by the selected peak."""
    context = _context(None, [1.0, 2.0, 3.0, 4.0], {"fit_range_only": False})
    result = reference_modes.peak_photons(context)
    np.testing.assert_allclose(result.y, np.array([1.0, 2.0, 3.0, 4.0]) / 4.0)


class _Parameter:
    def __init__(self, canonical_id, value):
        self.canonical_id, self.value = canonical_id, value


class _DonorOnlyModel:
    """A described FRET model stub: the curve is the donor-only fraction's doing."""

    def __init__(self):
        self.x_donly = _Parameter("fret.x_donly", 0.2)
        self.parameters_all = [self.x_donly]
        self.y = None

    def update(self):
        self.y = np.array([1.0, 2.0, 4.0]) * (1.0 if self.x_donly.value == 1.0 else 0.5)


def test_tcspc_donor_reference_divides_by_the_model_at_donor_only_and_restores_it():
    model = _DonorOnlyModel()
    context = _context(model, [2.0, 4.0, 8.0], {"scale": "reference_peak"})
    result = reference_modes.donor_reference(context)
    np.testing.assert_allclose(result.y, np.array([8.0, 8.0, 8.0]))
    assert model.x_donly.value == 0.2


class _Polarized:
    def __init__(self, code, y):
        self.code = code
        self.y = np.asarray(y, dtype=float)

    def get_scalar(self, name):
        return self.code


class _GroupFit:
    def __init__(self, code, y):
        self.data = _Curve(np.arange(len(y)), y)
        self.model = _Polarized(code, y)


def test_tcspc_anisotropy_rt_reads_the_groups_vv_and_vh():
    group = [_GroupFit(1.0, [4.0, 4.0]), _GroupFit(2.0, [1.0, 1.0])]
    context = _context(
        group[0].model,
        [0.0, 0.0],
        {
            "g": 1.0,
            "l1": 0.0,
            "l2": 0.0,
            "bg_vv": 0.0,
            "bg_vh": 0.0,
            "vh_shift": 0.0,
            "variant": "corrected",
        },
        group_fits=group,
    )
    result = reference_modes.anisotropy_rt(context)
    np.testing.assert_allclose(result.y, np.array([0.5, 0.5]))


def test_the_rt_defaults_come_from_the_described_model():
    class _Model:
        parameters_all = [_Parameter("anisotropy.g", 1.3), _Parameter("anisotropy.l1", 0.03)]

    (mode,) = reference_modes.modes_named(["tcspc_anisotropy_rt"], model=_Model())
    defaults = {p.key: p.default for p in mode.parameters}
    assert defaults["g"] == 1.3 and defaults["l1"] == 0.03 and defaults["l2"] == 0.0
