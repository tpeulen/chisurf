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


class _MleStep:
    """Burst MLE's app as :meth:`BurstAnalysisHubApp._to_mle` sees it: the bursts it was
    handed are queued behind the job that prepares them ahead."""

    def __init__(self):
        self.ahead_key = "k1"
        self.queued = []
        self.model = SimpleNamespace(session=SimpleNamespace(bur_files=[]))

    @property
    def pending(self):
        return bool(self.queued)

    def attach_ahead(self, paths, settings, prepare_from, references):
        self.ahead_key = None
        self.queued.append(("attach_ahead", tuple(paths)))
        return True

    def take_bursts(self, paths, settings, prepare_from, references):
        self.queued.append(("take_bursts", tuple(paths)))


def test_bursts_attached_ahead_are_not_taken_again_while_the_attach_waits():
    # Next stored the bursts searched ahead; the step's preparation ahead still runs (its
    # session shows no bursts yet) and the attach waits behind it. Opening the step again
    # (``select``) must not queue a take of the same bursts: that read, prepared and fitted
    # them all a second time.
    selection, mle = _Selection(), _MleStep()
    selection.stored_key = "k1"
    hub = _hub(selection, mle)
    hub.context.bur_files, hub.context.burst_folder = ["m.pto/run"], "m.pto"
    hub._handed, hub._resync = {}, set()
    for name in ("_changed", "_mle_preparation"):
        setattr(hub, name, getattr(BurstAnalysisHubApp, name).__get__(hub))
    to_mle = BurstAnalysisHubApp._to_mle
    to_mle(hub, mle)  # the store's hand-over
    to_mle(hub, mle)  # the step selected
    assert mle.queued == [("attach_ahead", ("m.pto/run",))]
    hub.context.bur_files = ["m.pto/run (2)"]  # a new search is a new hand-over
    to_mle(hub, mle)
    assert mle.queued[-1] == ("take_bursts", ("m.pto/run (2)",))
