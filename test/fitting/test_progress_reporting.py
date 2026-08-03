"""Progress must reach the bar, and cancellation must reach the caller.

A fit's progress callback used to be built by the GUI and then dropped on the
floor: the controller reaches its fits through the JSON-RPC facade, which
carries JSON, so the service called ``fit.run()`` with no arguments and the
closure was never invoked. The dialog was created, sat at zero, and closed
saying "Fitting finished!" -- which reads as a missing progress bar.

The sink is therefore attached to the *fit* (:meth:`Fit.reporting_progress`)
rather than threaded through the call, and cancellation comes back the same way:
raising through the service turns into a generic error result, so the fit
records it and the caller reads :attr:`Fit.last_run_cancelled`.
"""
from __future__ import annotations

import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.models.parse
from chisurf.core.fitting.fit import _StagedProgress
from chisurf.core.math.optimization.leastsqbound import OptimizationCancelled


def _fit(seed: int = 0):
    """Return a single ``c + a*x**2`` fit, deliberately started off-target."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 5.0, 48)
    curve = chisurf.core.data.DataCurve(
        x=x, y=3.0 + 1.2 * x ** 2 + rng.normal(0, 0.05, x.size),
        ey=np.full_like(x, 0.05),
    )
    fit = chisurf.core.fitting.fit.Fit(
        data=curve, model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = 'c+a*x**2'
    fit.model.find_parameters()
    return fit


def _group(n_datasets: int = 2, seed: int = 0):
    """Return a group of such fits."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 5.0, 48)
    curves = [
        chisurf.core.data.DataCurve(
            x=x, y=(3.0 + 0.3 * k) + 1.2 * x ** 2 + rng.normal(0, 0.05, x.size),
            ey=np.full_like(x, 0.05))
        for k in range(n_datasets)
    ]
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup(curves),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    for f in fit:
        f.fit_range = 0, len(f.model.y)
        f.model.func = 'c+a*x**2'
        f.model.find_parameters()
    fit._model.find_parameters()
    return fit


def test_run_reports_to_the_installed_sink():
    """``run()`` with no arguments -- exactly how the service calls it."""
    fit = _fit()
    seen = []
    with fit.reporting_progress(lambda done, total: seen.append((done, total))):
        fit.run()
    assert seen, "no progress reported: the sink was never called"
    assert all(t and t > 0 for _, t in seen), "a bar cannot be drawn against a null total"
    fractions = [d / t for d, t in seen]
    assert fractions == sorted(fractions), "the bar went backwards"
    assert fractions[-1] == pytest.approx(1.0), "a finished fit left the bar unfilled"


def test_a_two_argument_callback_is_honoured():
    """The documented signature is ``callback(evaluated, total)``.

    The optimiser offers ``chi2`` / ``chi2r`` as extras, and a callback written
    to the documented signature used to raise ``TypeError`` on them straight
    into a blanket ``except Exception: pass`` -- so a correct callback silently
    never fired.
    """
    from chisurf.core.math.optimization.leastsqbound import leastsqbound

    x = np.linspace(0.0, 5.0, 48)
    residual = lambda p: (3.0 + 1.2 * x ** 2) - (p[0] + p[1] * x ** 2)  # noqa: E731

    two_arg, four_arg = [], []
    leastsqbound(residual, [1.0, 1.0], bounds=[(0.0, 10.0)] * 2,
                 progress_callback=lambda d, t: two_arg.append(d))
    leastsqbound(residual, [1.0, 1.0], bounds=[(0.0, 10.0)] * 2,
                 progress_callback=lambda d, t, **kw: four_arg.append(d))
    assert two_arg, "a callback with the documented signature was never called"
    assert len(two_arg) == len(four_arg)


def test_a_broken_callback_does_not_break_the_fit():
    """The fallback must not turn a bug in the bar into a failed fit."""
    fit = _fit()

    def broken(done, total, **kwargs):
        raise RuntimeError("the bar is on fire")

    with fit.reporting_progress(broken):
        fit.run()
    assert fit.last_run_cancelled is False


def test_sink_is_scoped_to_the_block():
    """It must not outlive the block; a stale Qt closure would be called later."""
    fit = _fit()
    assert fit._progress_callback is None
    with fit.reporting_progress(lambda *_: None):
        assert fit._progress_callback is not None
    assert fit._progress_callback is None
    # ...and it is a class attribute, so it never enters the instance state
    # that gets pickled into a saved fit.
    assert "_progress_callback" not in fit.__dict__


def test_nested_blocks_restore_the_outer_sink():
    fit = _fit()
    outer, inner = [], []
    with fit.reporting_progress(lambda d, t: outer.append(d)):
        with fit.reporting_progress(lambda d, t: inner.append(d)):
            fit.run()
        assert not outer
        fit.run()
    assert outer, "the outer sink was not restored"


def test_cancellation_is_readable_after_the_fact():
    """The RPC service swallows the exception, so the flag is the only channel."""
    fit = _fit()

    def cancel_after_three(done, total):
        if done >= 3:
            raise OptimizationCancelled()

    with fit.reporting_progress(cancel_after_three):
        with pytest.raises(OptimizationCancelled):
            fit.run()
    assert fit.last_run_cancelled is True

    # A completed run clears it again -- otherwise one cancelled fit would make
    # every later fit report as cancelled.
    with fit.reporting_progress(lambda *_: None):
        fit.run()
    assert fit.last_run_cancelled is False


def test_group_shares_one_bar_across_its_stages():
    """Members and the global fit each count from zero; the bar must not reset."""
    fit = _group(2)
    seen = []
    with fit.reporting_progress(lambda done, total: seen.append(done / total)):
        fit.run(local_first=True)
    assert len(seen) > 3
    assert seen == sorted(seen), "the group's bar went backwards between stages"
    assert seen[-1] > 0.5, "the final stage never reached the top of the bar"


def test_staged_progress_maps_stages_onto_subranges():
    seen = []
    staged = _StagedProgress(lambda d, t: seen.append(d / t), 4)
    staged.stage(0)(5, 10)
    assert seen[-1] == pytest.approx(0.125)
    staged.stage(2)(5, 10)
    assert seen[-1] == pytest.approx(0.625)


def test_staged_progress_never_retreats():
    """A stage restarting at zero must stall the bar, not rewind it."""
    seen = []
    staged = _StagedProgress(lambda d, t: seen.append(d / t), 2)
    staged.stage(0)(10, 10)          # first stage finished -> 0.5
    staged.stage(1)(0, 10)           # second stage starts   -> would be 0.5
    staged.stage(1)(1, 10)           # -> 0.55
    assert seen == sorted(seen)
    assert seen[-1] == pytest.approx(0.55)


def test_staged_progress_without_a_sink_is_inert():
    """Callers must not have to branch on whether they have a bar."""
    staged = _StagedProgress(None, 3)
    assert staged.stage(0) is None
