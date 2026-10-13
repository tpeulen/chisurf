"""ProbCh0's interleaved (amplitude, pch0) spectrum round-trips, and a link follows it.

The setter indexed species ``2i`` and ``2i+1`` instead of ``i`` (an IndexError
for any second species), and a linked group returned the target's bare ``pch0``
-- half the spectrum -- instead of its spectrum.
"""

from __future__ import annotations

import numpy as np


def _group(n: int):
    from chisurf.core.models.pda2c.simple import ProbCh0

    g = ProbCh0(normalize_amplitudes=False)
    for _ in range(n):
        g.append()
    return g


def test_setting_the_spectrum_writes_each_species_once():
    g = _group(3)
    g.pch0_spectrum = np.array([0.2, 0.1, 0.3, 0.4, 0.5, 0.7])
    np.testing.assert_allclose(g.amplitudes, [0.2, 0.3, 0.5])
    np.testing.assert_allclose(g.pch0, [0.1, 0.4, 0.7])
    np.testing.assert_allclose(g.pch0_spectrum, [0.2, 0.1, 0.3, 0.4, 0.5, 0.7])


def test_a_linked_group_reports_the_targets_whole_spectrum():
    target = _group(2)
    target.pch0_spectrum = np.array([0.6, 0.2, 0.4, 0.9])
    follower = _group(1)
    follower.link = target
    np.testing.assert_allclose(follower.pch0_spectrum, target.pch0_spectrum)
