"""The hub starts Burst MLE on the bursts Burst Selection searched ahead, drops it when the
search settings change, keeps it when Next stored those bursts, and hands it over to the run."""

from __future__ import annotations

from types import SimpleNamespace

from chisurf.plugins.burst.burst_analysis.gui.native import BurstAnalysisHubApp


class _Selection:
    def __init__(self):
        self.found = None
        self.stored_key = None

    def ahead_bursts(self):
        return self.found


class _Mle:
    def __init__(self):
        self.ahead_key = None
        self.calls = []

    def take_ahead(self, tables, key, settings, prepare_from, references):
        self.calls.append(("take", key, tuple(prepare_from)))
        self.ahead_key = key

    def drop_ahead(self):
        self.calls.append(("drop", self.ahead_key))
        self.ahead_key = None


def _hub(selection, mle):
    context = SimpleNamespace(
        channel_settings={"detectors": {}}, raw_files=["m.ptu"], irf_background_patterns=None,
        references=lambda: {"buffer": []},
    )
    hub = SimpleNamespace(children={"selection": selection, "mle": mle}, context=context,
                          wants_frame=False)
    hub.ensure_child = lambda role: hub.children.get(role)
    return hub


def test_the_hub_runs_mle_ahead_and_follows_the_search_settings():
    selection, mle = _Selection(), _Mle()
    hub = _hub(selection, mle)
    run = BurstAnalysisHubApp._mle_ahead
    run(hub)
    assert mle.calls == [], "nothing found ahead yet"
    selection.found = ("k1", {"m.ptu": object()})
    run(hub)
    run(hub)
    assert mle.calls == [("take", "k1", ("m.ptu",))], "once per search"
    selection.found = None  # a setting changed: the bursts on show went
    run(hub)
    assert mle.calls[-1] == ("drop", "k1") and mle.ahead_key is None
    selection.found = ("k2", {"m.ptu": object()})
    run(hub)
    assert mle.calls[-1] == ("take", "k2", ("m.ptu",))
    selection.found, selection.stored_key = None, "k2"  # Next stored them
    run(hub)
    assert mle.ahead_key == "k2", "kept for the run Next wrote"
