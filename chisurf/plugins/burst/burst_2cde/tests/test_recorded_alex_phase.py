import json
from types import SimpleNamespace

from chisurf.plugins.burst.burst_selection.api.selection import _recorded_alex
from chisurf.plugins.burst.burst_2cde.backend.services import settings_from_setup


def test_recorded_phase_roundtrip_to_engine_ticks():
    experiment = {"preset": "alex", "alex_period_us": 100.0,
                  "alex_windows_s": {"prompt": [2e-6, 40e-6], "delayed": [55e-6, 95e-6]}}
    tttr = SimpleNamespace(header=SimpleNamespace(
        json=json.dumps({"tags": [{"name": "ChiSurf_AcquisitionSettings",
                                   "value": json.dumps({"experiment": experiment})}]}),
        macro_time_resolution=1e-6))
    phase = _recorded_alex(tttr)
    setup = {"detectors": {"donor": {"chs": [0]}, "acceptor": {"chs": [1]}},
             "alex_phase": phase}
    settings = settings_from_setup(setup)
    assert settings["alternation_period_ticks"] == 100
    assert settings["donor_macro_phase_ranges"][0] == (2, 40)
    assert settings["acceptor_excitation_macro_phase_ranges"][0] == (55, 95)


def test_missing_phase_is_not_guessed():
    tttr = SimpleNamespace(header=SimpleNamespace(json='{"tags": []}', macro_time_resolution=1e-6))
    assert _recorded_alex(tttr) == {}
