"""The burst workflow's BVA, 2CDE and H2MM carry the excitation-window pre-flight of their ranges.

The detectors' inclusive micro-time windows (:meth:`Detector.bva_ranges`, the H2MM streams) are
held against the excitation pulses of the simulated PIE demo (pulses at 2 and 52 ns, routing 0
donor / 1 acceptor): a setup of another instrument puts the line into each result's
``warnings``; PIE's standard setup (green and red prompt, yellow delayed on the red channel) and
an ungated setup say nothing.
"""

from __future__ import annotations

import pytest

pytest.importorskip("tttrlib")

from chisurf.plugins.burst.burst_analysis.api.workflow import (  # noqa: E402
    Bursts,
    Detector,
    Setup,
)
from chisurf.plugins.burst.burst_bva.tests import pie_folder  # noqa: E402
from chisurf.plugins.burst.burst_bva.tests.pie_folder import (  # noqa: E402
    DELAYED,
    PROMPT,
    WRONG_DONOR,
)


@pytest.fixture(scope="module")
def burst_data(tmp_path_factory):
    from chisurf.plugins.burst.burst_bva.core.computation import read_burst_analysis

    folder = pie_folder.build(tmp_path_factory.mktemp("pie"))
    return read_burst_analysis(folder, "PTU", pattern="bi4_bur")


def _bursts(burst_data, detectors):
    table, tttrs = burst_data
    return Bursts(names=list(tttrs), dataset_uuids=[], table=table,
                  setup=Setup(detectors=detectors), _tttrs=dict(tttrs))


PIE = [
    Detector("green", (0,), (PROMPT,)),
    Detector("red", (1,), (PROMPT,)),
    Detector("yellow", (1,), (DELAYED,)),
]


def test_a_setup_of_another_instrument_warns(burst_data):
    bursts = _bursts(burst_data, [Detector("green", (0,), (WRONG_DONOR,)), Detector("red", (1,))])
    bva = bursts.bva()
    assert len(bva.warnings) == 1 and "do not match the data" in bva.warnings[0], bva.warnings
    assert bursts.two_cde().warnings == bva.warnings
    h2mm = bursts.h2mm(states=(1,), engine="em").warnings  # red is ungated here: not proposed
    assert len(h2mm) == 1 and "detector green (2048–4095)" in h2mm[0], h2mm


def test_the_pie_setup_says_nothing(burst_data):
    bursts = _bursts(burst_data, PIE)
    assert bursts.bva().warnings == []
    assert bursts.two_cde().warnings == []
    assert bursts.two_cde(donor="green", acceptor="red", acceptor_excitation="yellow",
                          variant="alex").warnings == []
    assert bursts.h2mm(states=(1,), engine="em").warnings == []


def test_an_ungated_setup_is_checked_as_the_full_axis(burst_data):
    """Unset windows are BVA's full 12-bit axis (0-4095): it holds the demo's 3125 channels."""
    bursts = _bursts(burst_data, [Detector("green", (0,)), Detector("red", (1,))])
    assert bursts.bva().warnings == []
    assert bursts.h2mm(states=(1,), engine="em").warnings == []
