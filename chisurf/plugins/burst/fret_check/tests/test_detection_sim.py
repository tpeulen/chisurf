"""Detection over simulated measurements (tttrlib's photon simulator).

Every scenario in :data:`smfretweb.sim.SCENARIOS` -- cw, PIE with pulses in
any order, gap and period, µsALEX with and without micro times, MFD with
ChiSurf's 0/8, 1/9 routing, extra noise channels, one-colour data -- must be
detected as what it is: excitation, donor and acceptor channels, unassigned
channels, the PIE windows around their pulses, and a warning where the data
cannot settle a guess.
"""
import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")
if not hasattr(tttrlib, "SimEngine"):
    pytest.skip("tttrlib without the simulator", allow_module_level=True)

from chisurf.plugins.burst.fret_check.detect import detect_experiment, with_phase  # noqa: E402
from chisurf.plugins.burst.fret_check.pipeline import analyse  # noqa: E402
from chisurf.plugins.burst.fret_check.sim import SCENARIOS, simulate  # noqa: E402

_cache = {}


def _detected(sc):
    if sc.name not in _cache:
        data = simulate(sc)
        _cache[sc.name] = (data, detect_experiment(data))
    return _cache[sc.name]


@pytest.mark.parametrize("sc", SCENARIOS, ids=[s.name for s in SCENARIOS])
def test_channels_and_excitation(sc):
    _, e = _detected(sc)
    assert e.excitation == ("cw" if sc.excitation == "cw" else "alternating")
    if sc.excitation == "pie":
        assert e.alternation == "PIE"
    if sc.excitation == "usalex":
        assert e.alternation == "µsALEX"
    assert e.donor_channels == sorted(sc.donor)
    assert e.acceptor_channels == sorted(sc.acceptor)
    assert e.unassigned_channels == sorted(sc.extra)
    for ch in sc.extra:
        assert any(f"channel {ch} not assigned" in w for w in e.warnings)
    assert e.polarization == (len(sc.donor) == 2)


@pytest.mark.parametrize("sc", [s for s in SCENARIOS if s.excitation == "pie"],
                         ids=[s.name for s in SCENARIOS if s.excitation == "pie"])
def test_pie_windows_hold_their_pulses(sc):
    _, e = _detected(sc)
    win = {w.name: w for w in e.windows}
    per_ns = 4096 / sc.laser_period_ns
    for name, pulse in (("donor", sc.donor_pulse_ns), ("acceptor", sc.acceptor_pulse_ns)):
        peak = pulse * per_ns + 0.5 * per_ns  # the decay's first half nanosecond
        assert win[name].start <= peak < win[name].stop, (name, win[name], peak)


def test_guesses_are_warnings():
    _, e = _detected(next(s for s in SCENARIOS if s.name == "cw 2c, no donor-only"))
    assert any("guessed from channel order" in w for w in e.warnings)
    _, e = _detected(next(s for s in SCENARIOS if s.name.startswith("1c")))
    assert any("one-colour" in w for w in e.warnings)


@pytest.mark.parametrize("sc", [s for s in SCENARIOS if s.excitation != "cw"],
                         ids=[s.name for s in SCENARIOS if s.excitation != "cw"])
def test_alternating_gives_stoichiometry(sc):
    data, e = _detected(sc)
    if e.alex_period:
        data = with_phase(data, e.alex_period)
    b = analyse(data, e)
    assert b.n > 50
    # FRET molecules sit at intermediate S, donor-only high, acceptor-only low.
    fret = np.mean((b.S > 0.3) & (b.S < 0.8))
    assert fret > 0.3, fret


@pytest.mark.parametrize("name", ["PIE 2c", "cw 2c", "µsALEX with micro time"])
def test_2cde_on_the_burst_neighbourhoods_equals_the_whole_stream(name, monkeypatch):
    """2CDE is computed only on photons within the kernel's reach of a burst;
    the values must equal those from the whole stream, bit for bit."""
    from chisurf.plugins.burst.fret_check import pipeline
    from chisurf.plugins.burst.fret_check.pipeline import BurstSettings, find_bursts

    sc = next(s for s in SCENARIOS if s.name == name)
    data, exp = _detected(sc)
    if exp.alex_period:
        data = with_phase(data, exp.alex_period)
    settings = BurstSettings()
    bursts = find_bursts(data, settings)
    sub, _ = pipeline._near_bursts(data, bursts, settings.cde_tau)
    near = pipeline._two_cde(data, exp, bursts, settings.cde_tau)
    monkeypatch.setattr(pipeline, "_near_bursts", lambda d, b, tau: (d, b))
    whole = pipeline._two_cde(data, exp, bursts, settings.cde_tau)
    for a, b in zip(near, whole):
        assert (a is None) == (b is None)
        if a is not None:
            assert np.array_equal(a, b, equal_nan=True)
