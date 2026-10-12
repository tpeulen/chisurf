"""A least-squares run that stops on ``xtol`` far from the minimum is resumed (found 2026-10-12).

The joint VV/VH fit of the bundled 8 ps recording, after its members had been fitted alone, stopped
with MINPACK ``info == 2`` (the trust region below ``xtol``) at chi2r 21.7; pressing **Fit** again
reached 1.4. The manual's figure of that step showed the stalled fit. ``minimize`` now resumes such
a run while the resume still lowers chi2.
"""

from __future__ import annotations

from chisurf.core.fitting import minimizer as M


class _Minimiser:
    """Stands in for the bff minimiser: one ``(info, chi2)`` per run."""

    def __init__(self, runs):
        self.runs = list(runs)
        self.x = [1.0]
        self.calls = 0
        self._chi2 = None

    def run(self):
        info, self._chi2 = self.runs[self.calls]
        self.calls += 1
        return info

    def get_chi2(self):
        return self._chi2

    def set_initial_values(self, values):
        self.x = list(values)


def test_an_xtol_stop_is_resumed_while_it_pays():
    m = _Minimiser([(2, 100.0), (2, 10.0), (1, 9.0)])
    assert M._run_restarting_on_xtol(m) == 1
    assert m.calls == 3


def test_a_converged_xtol_stop_is_resumed_once_and_left():
    m = _Minimiser([(2, 10.0), (2, 10.0), (2, 9.0)])
    assert M._run_restarting_on_xtol(m) == 2
    assert m.calls == 2


def test_other_stops_are_not_resumed():
    for info in (1, 3, 4, 5):
        m = _Minimiser([(info, 10.0), (1, 1.0)])
        assert M._run_restarting_on_xtol(m) == info
        assert m.calls == 1


def test_resumes_are_bounded():
    m = _Minimiser([(2, 100.0 / (k + 1)) for k in range(M.XTOL_RESTARTS + 3)])
    M._run_restarting_on_xtol(m)
    assert m.calls == M.XTOL_RESTARTS + 1
