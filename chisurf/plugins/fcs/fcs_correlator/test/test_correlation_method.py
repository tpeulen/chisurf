"""The correlation algorithm is a setting: laurence by default, wahl and felekyan on request.

The retired *TTTR: Correlate* tool offered the three tttrlib methods; the FCS
correlator had laurence hard-coded. Each method must reach tttrlib and be
recorded with the curve it produced (real photons: the repository's Leica PTU).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chisurf.plugins.fcs.fcs_correlator.correlator_model import METHODS, CorrelatorSettingsModel


FIXTURE = Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP5.ptu"


@pytest.fixture(scope="module")
def stream():
    from chisurf.core.fio.staging import open_tttr

    if not FIXTURE.is_file():
        pytest.skip("Real PTU fixture unavailable.")
    return open_tttr(FIXTURE, apply_lut=False, channel_shifts={})


def test_the_default_is_laurence_and_every_choice_is_a_tttrlib_method():
    import tttrlib

    assert CorrelatorSettingsModel().method == "laurence"
    available = set(tttrlib.Correlator().correlation_method_names())
    assert set(METHODS) <= available, available


def test_an_unknown_method_is_refused_not_silently_replaced(stream):
    model = CorrelatorSettingsModel()
    model.method = "default"
    with pytest.raises(ValueError, match="Unknown correlation method"):
        model._correlate_one(stream, [0], [1], model.get_correlation_settings(), 0)


@pytest.mark.parametrize("method", METHODS)
def test_each_method_reaches_tttrlib_and_is_recorded(method, stream, monkeypatch):
    import tttrlib

    seen = []
    original = tttrlib.Correlator

    class Spy(original):
        def set_macrotimes(self, *args, **kwargs):
            seen.append(self.method)
            return super().set_macrotimes(*args, **kwargs)

    monkeypatch.setattr(tttrlib, "Correlator", Spy)
    model = CorrelatorSettingsModel()
    model.method = method
    model.n_bins, model.n_casc = 4, 12
    result = model._correlate_one(stream, [0], [1], model.get_correlation_settings(), 0)
    assert seen == [method]
    assert result["correlation_settings"]["method"] == method
    assert len(result["x"]) == len(result["y"]) > 0
