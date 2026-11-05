"""A reference dye's IRF is extracted once per content: Burst MLE prepares ahead of Next and again
at it, and a new setup re-reads its references -- each histograms the same reference again, and
the rotation's search and deconvolutions (seconds per dye) gave the same IRF every time."""

from __future__ import annotations

import threading
import time

import numpy as np

from chisurf.plugins.fluorescence_decay.irf_estimator.core import extraction as ex
from test.fluorescence.test_irf_from_references import DT, _decay_of


def _counts(seed: int = 7):
    rng = np.random.default_rng(seed)
    vv, vh = _decay_of(4.0, rho=0.2)
    total = vv.sum() + vh.sum()
    return (rng.poisson(vv / total * 4e5 + 100.0).astype(float),
            rng.poisson(vh / total * 4e5 + 100.0).astype(float))


def _counting(monkeypatch):
    calls = []
    inner = ex._irf_from_reference

    def counted(*args, **kwargs):
        calls.append(1)
        return inner(*args, **kwargs)

    monkeypatch.setattr(ex, "_irf_from_reference", counted)
    monkeypatch.setattr(ex, "_reference_cache", type(ex._reference_cache)())
    return calls, inner


def test_the_same_reference_is_extracted_once_and_gives_the_same_irf(monkeypatch):
    calls, inner = _counting(monkeypatch)
    vv, vh = _counts()
    kwargs = dict(listed_tau_ns=4.0, name="Rh110.ptu", dye="Rh110", window=(10, 600))
    first = ex.irf_from_reference(vv, vh, DT, **kwargs)
    # histogrammed again: new arrays, the same numbers
    again = ex.irf_from_reference(vv.copy(), vh.copy(), DT, **kwargs)
    assert len(calls) == 1
    fresh = inner(vv, vh, DT, **kwargs)
    for got in (first, again):
        np.testing.assert_array_equal(got.irf, fresh.irf)
        assert (got.text, got.source, got.counts, got.info) == (fresh.text, fresh.source,
                                                                 fresh.counts, fresh.info)
    # each caller owns its copy: editing one leaves the kept IRF as it was
    first.irf[:] = 0.0
    first.info["rho_ns"] = -1.0
    third = ex.irf_from_reference(vv, vh, DT, **kwargs)
    np.testing.assert_array_equal(third.irf, fresh.irf)
    assert third.info == fresh.info and len(calls) == 1


def test_other_counts_or_settings_are_extracted_again(monkeypatch):
    calls, _inner = _counting(monkeypatch)
    vv, vh = _counts()
    ex.irf_from_reference(vv, vh, DT, tau_ns=4.0, rho_ns=0.2)
    ex.irf_from_reference(vv, vh, DT, tau_ns=4.0, rho_ns=0.2, window=(10, 600))  # another gate
    ex.irf_from_reference(vv, vh, DT * 2, tau_ns=4.0, rho_ns=0.2)  # another binning
    ex.irf_from_reference(vv, vh, DT, tau_ns=4.0, rho_ns=0.2, g_factor=1.1)
    vv2 = vv.copy()
    vv2[300] += 1.0  # one photon more
    ex.irf_from_reference(vv2, vh, DT, tau_ns=4.0, rho_ns=0.2)
    ex.irf_from_reference(vv, None, DT, tau_ns=4.0)  # one polarisation
    assert len(calls) == 6


def test_concurrent_hand_overs_extract_once(monkeypatch):
    # the preparation ahead of Next and the one at Next may ask at the same moment
    calls = []
    inner = ex._irf_from_reference

    def slow(*args, **kwargs):
        calls.append(1)
        time.sleep(0.2)
        return inner(*args, **kwargs)

    monkeypatch.setattr(ex, "_irf_from_reference", slow)
    monkeypatch.setattr(ex, "_reference_cache", type(ex._reference_cache)())
    vv, vh = _counts()
    got = []
    threads = [threading.Thread(target=lambda: got.append(
        ex.irf_from_reference(vv, vh, DT, tau_ns=4.0, rho_ns=0.2))) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1 and len(got) == 3
    for g in got[1:]:
        np.testing.assert_array_equal(g.irf, got[0].irf)
