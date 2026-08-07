"""The curves the wizard plots after a fit, without needing a data set.

``test_mle_gui_end_to_end.py`` covers this path properly but is skipped
everywhere the BH smFRET DNA files are absent — which is everywhere except one
machine. That gap let a real regression ship: ``plot_fit_result`` read
``self.fit.data`` and ``self.fit.model``, attributes the *old* per-estimator
tttrlib fitter carried. The migrated ``Fit2x`` facade is reusable and holds no
per-fit state, so those attributes no longer exist and the wizard raised
``AttributeError: 'Fit2x' object has no attribute 'data'`` the moment anyone hit
auto-optimise.

These tests need no files: they pin the contract the plot depends on — that a
fit can hand back the model curve it computed, aligned with the data it was
given — using a synthetic decay.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.core.fluorescence.mle.fit2x import (
    HAVE_TTTRLIB,
    Fit2x,
    Fit2xModel,
    Fit2xSettings,
)

pytestmark = pytest.mark.skipif(not HAVE_TTTRLIB, reason="tttrlib is required")

N = 64
DT = 0.032
PERIOD = 32.0


def _settings() -> Fit2xSettings:
    t = np.arange(N) * DT
    irf = np.exp(-0.5 * ((t - 0.3) / 0.05) ** 2)
    irf = irf / irf.sum()
    return Fit2xSettings(
        dt=DT,
        period=PERIOD,
        irf=np.concatenate([irf, irf]),
        background=np.zeros(2 * N),
        g_factor=1.0,
        convolution_stop=N - 1,
    )


def _decay(settings: Fit2xSettings, total: int = 40000) -> np.ndarray:
    """A decay drawn from the model itself, so the fit has something to find."""
    t = np.arange(N) * DT
    half = np.convolve(np.exp(-t / 2.0), settings.irf[:N])[:N]
    curve = np.concatenate([half, half])
    curve = np.clip(curve, 1e-12, None)
    return np.random.default_rng(0).poisson(curve / curve.sum() * total).astype(float)


def test_a_fit_returns_the_model_curve_it_computed():
    """What the wizard plots comes from the *result*, not from the fitter."""
    settings = _settings()
    fitter = Fit2x(settings, model=Fit2xModel.FIT23)
    data = _decay(settings)

    result = fitter.fit(
        data, initial_values=[2.0, 0.0, 0.38, 1.2], fixed=[0, -1, -1, -1],
        include_model=True,
    )

    assert result.model_curve is not None
    assert len(result.model_curve) == len(data)
    assert np.all(np.isfinite(result.model_curve))
    assert float(np.sum(result.model_curve)) > 0.0


def test_the_fitter_exposes_no_per_fit_state():
    """Pins *why* the plot must read the result — and a trap in doing so.

    ``Fit2x`` is built once and reused for many decays, so it deliberately
    carries neither the data nor the curve of the last fit. Reading them off the
    fitter is reading state that does not exist, and would be reading the
    *previous* decay's curves if it did.

    The trap: ``fitter.data`` raises, which is loud, but ``fitter.model`` does
    **not** — it is the estimator *kind*. Anyone repairing the old
    ``self.fit.data`` / ``self.fit.model`` pair one line at a time therefore
    fixes the loud half and is left with an enum where a curve should be, which
    surfaces much further downstream.
    """
    fitter = Fit2x(_settings(), model=Fit2xModel.FIT23)
    assert not hasattr(fitter, "data")
    assert fitter.model is Fit2xModel.FIT23   # a model *kind*, never a curve
    assert not isinstance(fitter.model, np.ndarray)


def test_the_model_curve_is_omitted_unless_asked_for():
    """It costs a copy per fit, so a batch does not pay for it."""
    settings = _settings()
    fitter = Fit2x(settings, model=Fit2xModel.FIT23)
    result = fitter.fit(
        _decay(settings), initial_values=[2.0, 0.0, 0.38, 1.2], fixed=[0, -1, -1, -1]
    )
    assert result.model_curve is None


def test_residuals_can_be_formed_from_data_and_model():
    """The arithmetic the wizard's residual panel does, on aligned arrays."""
    settings = _settings()
    fitter = Fit2x(settings, model=Fit2xModel.FIT23)
    data = _decay(settings)
    result = fitter.fit(
        data, initial_values=[2.0, 0.0, 0.38, 1.2], fixed=[0, -1, -1, -1],
        include_model=True,
    )

    model = np.asarray(result.model_curve, dtype=float)
    residuals = np.zeros_like(data)
    mask = data > 0
    residuals[mask] = (data[mask] - model[mask]) / np.sqrt(data[mask])

    assert np.all(np.isfinite(residuals))
    # a fit to data drawn from its own model should not be wildly biased
    assert abs(float(np.mean(residuals[mask]))) < 1.0


def test_no_wizard_code_reads_curves_off_the_fitter():
    """A guard for the whole class of bug, not one call site.

    This was fixed twice and missed twice, because ``Fit2x.data`` raises while
    ``Fit2x.model`` silently returns the estimator *kind* — so a grep for the
    crash finds one site and leaves the other, and ``getattr(self.fit, "model",
    [])`` is worse still: the default never fires and numpy is handed an enum.

    The curves live on ``self._fit_view``, recorded when the fit ran. Nothing in
    the wizard may read them off ``self.fit``, whatever the spelling.
    """
    import re

    source = (
        pathlib.Path(__file__).resolve().parents[1] / "wizard.py"
    ).read_text()

    offenders = []
    for n, line in enumerate(source.splitlines(), start=1):
        code = line.split("#", 1)[0]          # ignore prose about the bug
        if re.search(r"self\.fit\.(data|model)\b", code) or re.search(
            r"getattr\(\s*self\.fit\s*,\s*[\"']\s*(data|model)", code
        ):
            offenders.append(f"{n}: {line.strip()}")

    assert not offenders, (
        "read the fitted curves from self._fit_view, not from the fitter:\n"
        + "\n".join(offenders)
    )


def test_a_result_is_read_by_name_and_not_subscripted():
    """The same class of bug, one layer on: the *result* is not a mapping.

    ``update_fit_ui`` subscripted ``res`` — ``res['x']``, ``'twoIstar' in
    res`` — which the estimators stopped returning when the typed
    :class:`Fit2xResult` replaced the dict. Every fit therefore raised
    ``'Fit2xResult' object is not subscriptable`` on the line *after* the plot
    was drawn, so the curves updated and the numbers beside them did not.

    It also read the anisotropies from ``x[6]``/``x[7]``. Those slots do not
    exist: the free parameters and the derived result columns were separated
    precisely so that no caller has to know a per-estimator layout, and reading
    them positionally is what the split was meant to stop.
    """
    settings = _settings()
    fitter = Fit2x(settings, model=Fit2xModel.FIT23)
    result = fitter.fit(
        _decay(settings), initial_values=[2.0, 0.0, 0.38, 1.2],
        fixed=[0, -1, -1, -1], include_model=True,
    )

    with pytest.raises(TypeError):
        result["x"]                       # the shape the call site assumed

    assert np.asarray(result.x).size >= 4
    assert np.isfinite(float(result.twoIstar))
    assert "rho" in result.as_dict()
    # NaN when the estimator does not report it -- a value either way, so the
    # panel never has to guess from the length of x.
    for value in (result.r_scatter, result.r_experimental):
        assert isinstance(float(value), float)


def test_the_wizard_does_not_subscript_a_fit_result():
    """A guard for the call sites, since the end-to-end test is skipped here."""
    import re

    source = (
        pathlib.Path(__file__).resolve().parents[1] / "wizard.py"
    ).read_text()

    offenders = []
    for n, line in enumerate(source.splitlines(), start=1):
        code = line.split("#", 1)[0]
        # Named keys only: `res` is also a DataFrame in the export path, where
        # subscripting it is exactly right.
        if re.search(r"\bres\[[\"'](x|twoIstar|fixed|results|model_curve)[\"']\]", code) \
                or re.search(r"[\"'](x|twoIstar)[\"']\s+in\s+res\b", code):
            offenders.append(f"{n}: {line.strip()}")

    assert not offenders, (
        "a Fit2xResult is read by attribute (res.x, res.twoIstar, "
        "res.as_dict(), res.result(name)), never subscripted:\n"
        + "\n".join(offenders)
    )
