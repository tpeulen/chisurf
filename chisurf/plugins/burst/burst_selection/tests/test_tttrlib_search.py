"""Registry-driven burst searches: discovery, dispatch and the generated form."""

import numpy as np
import pytest
import tttrlib

from chisurf.core.fluorescence.burst import tttrlib_search
from chisurf.plugins.burst.burst_selection.api.models import (
    BurstFilterMode,
    PhotonFilterSettings,
    TttrlibSearchSettings,
)

MACRO_TIME_RESOLUTION = 1e-9


@pytest.fixture(scope="module")
def photons():
    """Background plus 30 injected bursts, as a TTTR with a known time base."""
    rng = np.random.default_rng(0)
    times = [rng.uniform(0.0, 2.0, 4000)]
    times += [rng.uniform(0.05 * k, 0.05 * k + 1e-3, 60) for k in range(30)]
    t = np.sort(np.concatenate(times))
    ticks = np.round(t / MACRO_TIME_RESOLUTION).astype(np.uint64)
    n = ticks.size
    tttr = tttrlib.TTTR(
        ticks,
        np.zeros(n, np.uint16),
        np.zeros(n, np.int8),
        np.zeros(n, np.int8),
    )
    tttr.header.set_macro_time_resolution(MACRO_TIME_RESOLUTION)
    return tttr


def test_registry_is_published():
    """tttrlib advertises its burst searches with enough detail to build a UI."""
    algorithms = tttrlib_search.algorithms()
    assert tttrlib_search.is_available()
    assert {"sliding_window", "cusum_sprt", "maxtree"} <= set(algorithms)
    for name, spec in algorithms.items():
        assert spec["name"] == name
        assert spec["label"] and spec["summary"] and spec["method"]
        properties = spec["params_schema"]["properties"]
        assert properties, f"{name} publishes no parameters"
        for prop_name, prop in properties.items():
            # A generated form needs a type, a label and a starting value.
            assert prop["type"] in (
                "integer", "number", "boolean", "string", "array", "object"
            ), prop_name
            assert prop["title"] and prop["description"], prop_name
            if "default" not in prop:
                # Legitimate when only the caller can decide the value — a
                # detector grouping depends on the instrument, and inventing one
                # would silently search the wrong channels.
                continue
            if prop["type"] in ("integer", "number"):
                assert prop["minimum"] <= prop["default"] <= prop["maximum"], prop_name


def test_registry_methods_exist_and_accept_their_parameters(photons):
    """Every advertised method exists and takes exactly the advertised names."""
    for name, spec in tttrlib_search.algorithms().items():
        assert hasattr(photons, spec["method"]), spec["method"]
        defaults = tttrlib_search.defaults(name)
        required = set(spec["params_schema"].get("required", ()))
        if not required <= set(defaults):
            # Needs a value only the caller can supply; covered by
            # test_coincident_requires_a_grouping below.
            continue
        bursts = tttrlib_search.search(photons, name)
        assert bursts.ndim == 2 and bursts.shape[1] == 2, name


def test_coincident_requires_a_grouping(photons):
    """The multi-detector search cannot guess which detectors form a group."""
    with pytest.raises(ValueError, match="channel_groups"):
        tttrlib_search.search(photons, "coincident")
    # Supplied, it runs. The fixture is single-channel, so one group is all
    # that can agree and the result is just that group's own bursts.
    bursts = tttrlib_search.search(
        photons, "coincident", {"channel_groups": [[0]]}
    )
    assert bursts.ndim == 2 and bursts.shape[1] == 2


@pytest.mark.parametrize("algorithm", ["sliding_window", "cusum_sprt", "maxtree"])
def test_search_finds_the_injected_bursts(photons, algorithm):
    bursts = tttrlib_search.search(photons, algorithm)
    assert len(bursts) > 20, f"{algorithm} found {len(bursts)} of 30 bursts"
    assert (bursts[:, 0] <= bursts[:, 1]).all()
    assert bursts.min() >= 0 and bursts.max() < len(photons)


def test_defaults_round_trip(photons):
    """Passing the published defaults explicitly matches passing nothing."""
    defaults = tttrlib_search.defaults("maxtree")
    assert np.array_equal(
        tttrlib_search.search(photons, "maxtree"),
        tttrlib_search.search(photons, "maxtree", defaults),
    )


def test_parameters_take_effect(photons):
    """A stricter photon minimum yields fewer, larger bursts."""
    loose = tttrlib_search.search(photons, "maxtree", {"L": 20})
    strict = tttrlib_search.search(photons, "maxtree", {"L": 200})
    assert len(strict) < len(loose)


def test_mask_covers_bursts_inclusively(photons):
    """The mask includes the stop photon: tttrlib stops are inclusive."""
    bursts = tttrlib_search.search(photons, "maxtree")
    mask = tttrlib_search.tttrlib_burst_filter(photons, "maxtree")
    assert mask.shape == (len(photons),)
    assert mask.sum() == sum(stop - start + 1 for start, stop in bursts)
    for start, stop in bursts[:5]:
        assert mask[start] and mask[stop]


def test_unknown_algorithm_names_alternatives(photons):
    with pytest.raises(ValueError, match="unknown burst search"):
        tttrlib_search.search(photons, "not_an_algorithm")
    with pytest.raises(ValueError, match="does not take"):
        photons.burst_search_by_name("maxtree", not_a_parameter=1)


def test_settings_default_to_a_valid_request():
    """An untouched settings object is a fully specified search."""
    settings = PhotonFilterSettings(used_filter=BurstFilterMode.TTTRLIB)
    assert settings.tttrlib_search == TttrlibSearchSettings()
    assert settings.tttrlib_search.algorithm in tttrlib_search.algorithms()
    assert settings.tttrlib_search.parameters == {}


def test_apply_photon_filters_dispatches_to_the_registry(photons):
    from chisurf.plugins.burst.burst_selection.api.selection import apply_photon_filters

    settings = PhotonFilterSettings(
        used_filter=BurstFilterMode.TTTRLIB,
        tttrlib_search=TttrlibSearchSettings(algorithm="maxtree", parameters={"L": 30}),
    )
    selected = apply_photon_filters(photons, settings)
    assert selected.shape == (len(photons),)
    assert 0 < selected.sum() < len(photons)


def test_form_spec_is_generated_from_the_registry():
    """The GUI description is derived, not authored — no Qt needed to check it."""
    from chisurf.core.dataspec.rpc import RpcMethodView

    spec = tttrlib_search.describe("maxtree")
    view = RpcMethodView(spec, title=spec["label"])
    panel = view.view_spec().sections[0]
    assert panel.title == spec["label"]

    properties = spec["params_schema"]["properties"]
    assert len(panel.sections) == len(properties)
    labels = {section.label for section in panel.sections}
    assert labels == {prop["title"] for prop in properties.values()}
    assert view.params() == tttrlib_search.defaults("maxtree")


# --- composite entries: parameters delegated to another registry entry ---------

def test_composite_entry_nests_the_inner_schema():
    """The coincident search's inner parameters become a real nested panel.

    Rendered as a plain JSON Schema object they would be a text box to type JSON
    into; the schema's ``parameters_of`` link says which entry actually defines
    them, so they can be built as widgets instead.
    """
    from chisurf.core import tttrlib_registry as registry

    view = registry.entry_form_view_auto("burst_search", "coincident")
    panels = view.view_spec().sections
    assert len(panels) >= 2, "expected the entry's own panel plus nested ones"

    outer = {section.label for section in panels[0].sections}
    assert "Detector groups" in outer
    assert "Per-group search" in outer
    # The delegated property is replaced by panels, not shown as raw JSON.
    assert not any("parameters" in label.lower() for label in outer)

    # The inner schema is rendered in full, spread over its foldable groups.
    nested = {
        section.label for panel in panels[1:] for section in panel.sections
    }
    maxtree = registry.describe("burst_search", "maxtree")["params_schema"]
    assert nested == {prop["title"] for prop in maxtree["properties"].values()}


def test_composite_params_fold_the_nested_values_back():
    from chisurf.core import tttrlib_registry as registry

    view = registry.entry_form_view_auto("burst_search", "coincident")
    params = view.params()
    assert set(params) >= {"channel_groups", "algorithm", "min_groups", "L",
                           "parameters"}
    assert params["parameters"] == registry.defaults("burst_search", "maxtree")


def test_composite_tracks_which_inner_entry_it_was_built_for():
    """The nested panel is stale when the selector names a different entry."""
    from chisurf.core import tttrlib_registry as registry

    view = registry.entry_form_view_auto("burst_search", "coincident")
    assert view.selector_value == "maxtree"
    assert view.should_rebuild("maxtree") is False
    assert view.should_rebuild("kalman") is True
    assert view.should_rebuild(None) is True


def test_composite_rebuilds_against_a_different_inner_entry():
    from chisurf.core import tttrlib_registry as registry

    view = registry.entry_form_view_auto(
        "burst_search", "coincident",
        values={"algorithm": "kalman", "channel_groups": [[0], [1]]},
    )
    assert view.selector_value == "kalman"
    params = view.params()
    assert params["channel_groups"] == [[0], [1]]
    assert set(params["parameters"]) == set(
        registry.defaults("burst_search", "kalman")
    )
    inner = {s.label for s in view.view_spec().sections[1].sections}
    assert "Detection threshold (sigma)" in inner   # a Kalman-only parameter


def test_plain_entries_are_not_composite():
    """Only entries that delegate get the composite treatment.

    A plain entry still gets foldable groups; what it must not get is a nested
    panel for some other entry's parameters.
    """
    from chisurf.core import tttrlib_registry as registry

    view = registry.entry_form_view_auto("burst_search", "maxtree")
    assert not isinstance(view, registry.CompositeEntryView)
    assert set(view.params()) == set(registry.defaults("burst_search", "maxtree"))


def test_parameters_are_split_into_foldable_groups():
    """A dozen parameters in one column is unreadable; the schema says how to
    group them, so the grouping is the algorithm's decision, not the GUI's."""
    from chisurf.core import tttrlib_registry as registry

    panels = registry.entry_form_view_auto(
        "burst_search", "maxtree"
    ).view_spec().sections
    titles = [panel.title for panel in panels]
    assert len(panels) > 1, "expected the parameters to be grouped"
    assert registry.ADVANCED_GROUP in titles
    # Advanced is the panel a user should be able to ignore: last, and folded.
    assert titles[-1] == registry.ADVANCED_GROUP
    assert panels[-1].collapsed is True
    # Every parameter still appears exactly once across the panels.
    labels = [s.label for panel in panels for s in panel.sections]
    schema = registry.describe("burst_search", "maxtree")["params_schema"]
    assert sorted(labels) == sorted(
        prop["title"] for prop in schema["properties"].values()
    )


def test_nested_values_reach_the_search(photons):
    """The folded parameters are what the inner search actually receives."""
    from chisurf.core import tttrlib_registry as registry

    view = registry.entry_form_view_auto(
        "burst_search", "coincident",
        values={"channel_groups": [[0]], "parameters": {"L": 400}},
    )
    params = view.params()
    assert params["parameters"]["L"] == 400
    strict = tttrlib_search.search(photons, "coincident", params)
    params["parameters"]["L"] = 20
    loose = tttrlib_search.search(photons, "coincident", params)
    assert len(strict) < len(loose)


# --- the "you selected the whole trace" guard ----------------------------------

def test_degenerate_coverage_is_warned_and_still_masked(photons, monkeypatch, caplog):
    """A search that selects almost everything is flagged, not silently accepted.

    A background estimate is not valid when bursts are not a minority, so a
    search can "succeed" over the whole stream and produce meaningless numbers.
    The mask itself is still returned (with the inclusive stop advanced by one);
    only a warning is added.
    """
    n = len(photons)
    covering = np.array([[0, n - 1]], dtype=np.int64)  # one burst = the whole trace
    monkeypatch.setattr(tttrlib_search, "search", lambda *a, **k: covering)

    with caplog.at_level("WARNING"):
        mask = tttrlib_search.tttrlib_burst_filter(photons, "maxtree")

    assert mask.shape == (n,)
    assert mask.all()  # inclusive stop n-1, advanced to n, covers every photon
    assert any("whole measurement" in rec.message for rec in caplog.records)


def test_plausible_coverage_is_not_warned(photons, monkeypatch, caplog):
    """A normal selection of a fraction of the stream draws no warning."""
    n = len(photons)
    fifth = np.array([[0, n // 5]], dtype=np.int64)
    monkeypatch.setattr(tttrlib_search, "search", lambda *a, **k: fifth)

    with caplog.at_level("WARNING"):
        tttrlib_search.tttrlib_burst_filter(photons, "maxtree")

    assert not any("whole measurement" in rec.message for rec in caplog.records)


def test_warn_if_degenerate_threshold_is_the_documented_fraction(caplog):
    """The boundary sits at IMPLAUSIBLE_COVERAGE: just under is quiet, at/over warns."""
    n = 1000
    threshold = tttrlib_search.IMPLAUSIBLE_COVERAGE

    below = int(threshold * n) - 2  # a hair under the fraction
    quiet = np.array([[0, below - 1]], dtype=np.int64)
    with caplog.at_level("WARNING"):
        tttrlib_search._warn_if_degenerate("maxtree", quiet, n)
    assert not caplog.records

    caplog.clear()
    over = np.array([[0, n - 1]], dtype=np.int64)
    with caplog.at_level("WARNING"):
        tttrlib_search._warn_if_degenerate("maxtree", over, n)
    assert caplog.records


def test_empty_search_masks_nothing(photons, monkeypatch):
    """No bursts found means an all-false mask, and no confidence bookkeeping."""
    monkeypatch.setattr(
        tttrlib_search, "search",
        lambda *a, **k: np.empty((0, 2), dtype=np.int64),
    )
    mask = tttrlib_search.tttrlib_burst_filter(photons, "maxtree")
    assert mask.shape == (len(photons),)
    assert mask.sum() == 0


# --- retired and unavailable modes in the dispatcher ---------------------------

def test_bocpd_mode_is_reported_as_removed(photons):
    """BOCPD is retired: the enum survives so old projects load, but it errors."""
    from chisurf.plugins.burst.burst_selection.api.selection import apply_photon_filters

    settings = PhotonFilterSettings(used_filter=BurstFilterMode.BOCPD)
    with pytest.raises(ValueError, match="BOCPD"):
        apply_photon_filters(photons, settings)


def test_tttrlib_mode_without_a_registry_falls_back(photons, monkeypatch):
    """Registry-only mode falls back to the built-in search instead of aborting.

    When tttrlib publishes no burst-search registry the analysis must still
    produce bursts (otherwise every downstream plot is empty); it falls back to
    the built-in sliding-window search and warns rather than raising.
    """
    import numpy as np

    from chisurf.plugins.burst.burst_selection.api import selection as selection_mod

    monkeypatch.setattr(selection_mod.tttrlib_search, "is_available", lambda: False)
    settings = PhotonFilterSettings(
        used_filter=BurstFilterMode.TTTRLIB,
        tttrlib_search=TttrlibSearchSettings(algorithm="maxtree"),
    )
    # Does not raise, and returns a per-photon 0/1 mask (fell back to BURST).
    mask = selection_mod.apply_photon_filters(photons, settings)
    mask = np.asarray(mask)
    assert mask.shape[0] == len(photons)
    assert set(np.unique(mask).tolist()) <= {0, 1}
