"""The burst background estimate runs the shared excitation-window pre-flight on its gates.

:func:`estimate_background_from_bursts` and :func:`background_diagnostics_from_bursts` take a
detector's photons inside its micro-time gates (``[start, stop)``); given a ``warnings`` list they
append the line of the shared check of those gates against the measurement's excitation pulses.
On the simulated PIE demo of Excitation Windows (pulses at 2 and 52 ns, routing 0 donor / 1
acceptor): gates of another instrument warn, PIE's standard split (green and red prompt, yellow
delayed on the red channel) and ungated detectors say nothing, a donor-only measurement gives no
false warning, and without a list nothing is checked.
"""

from __future__ import annotations

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.core.fluorescence.burst import background  # noqa: E402

PIE = {
    "green": {"chs": [0], "micro_time_ranges": [[0, 1613]]},
    "red": {"chs": [1], "micro_time_ranges": [[0, 1613]]},
    "yellow": {"chs": [1], "micro_time_ranges": [[1613, 3125]]},
}
WRONG = {
    "green": {"chs": [0], "micro_time_ranges": [[2048, 4095]]},
    "red": {"chs": [1], "micro_time_ranges": [[0, 2048]]},
}


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    from chisurf.plugins.core.excitation_windows.demo import make_demo

    return tttrlib.TTTR(str(make_demo(tmp_path_factory.mktemp("demo"))))


@pytest.fixture(scope="module")
def donor_only(tmp_path_factory):
    from chisurf.plugins.core.excitation_windows import demo as d
    from chisurf.plugins.tttr import demo_lib

    macro, micro, routing = d.photon_stream(n_photons=100_000)
    keep = ~((routing == 1) & (micro.astype(float) * d.RESOLUTION_S * 1e9 > 51.0))
    path = tmp_path_factory.mktemp("donly") / "donor_only.ptu"
    cfg = demo_lib.config(macro_resolution_s=d.MACRO_S, micro_resolution_s=d.RESOLUTION_S,
                          n_micro=d.N_MICRO)
    demo_lib.write_ptu(path, cfg, macro[keep], micro[keep], np.asarray(routing)[keep])
    return tttrlib.TTTR(str(path))


def test_gates_of_another_instrument_warn(demo):
    warnings: list[str] = []
    rates = background.estimate_background_from_bursts(demo, WRONG, warnings=warnings)
    assert set(rates) == {"green", "red"}
    assert len(warnings) == 1 and "detector green (2048–4095)" in warnings[0], warnings
    diag: list[str] = []
    background.background_diagnostics_from_bursts(demo, WRONG, warnings=diag)
    assert diag == warnings


def test_the_pie_split_says_nothing(demo):
    warnings: list[str] = []
    background.estimate_background_from_bursts(demo, PIE, warnings=warnings)
    assert warnings == []


def test_ungated_detectors_are_not_checked(demo):
    ungated = {"green": {"chs": [0]}, "red": {"chs": [1], "micro_time_ranges": []}}
    assert background.gate_warning(demo, ungated) is None


def test_a_donor_only_measurement_gives_no_false_warning(donor_only):
    assert background.gate_warning(donor_only, PIE) is None


def test_without_a_list_nothing_is_checked(demo, monkeypatch):
    monkeypatch.setattr(background, "gate_warning", lambda *a: pytest.fail("checked"))
    background.estimate_background_from_bursts(demo, WRONG)
