"""GUI-free marshalling of a wizard filter into ``PhotonFilterSettings``.

``photon_filter_settings_from_wizard`` is duck-typed — it reads attributes off
whatever object it is given — so its mapping and its default-handling can be
checked against a plain stand-in, without a Qt page. The full wizard path is
covered in ``test_filter_ui_elements.py``; this pins the defaults those tests
never hit (missing tttrlib fields, an unset micro-time window).
"""

from __future__ import annotations

from chisurf.plugins.burst.burst_selection.api.models import (
    BurstFilterMode,
    TttrlibSearchSettings,
)
from chisurf.plugins.burst.burst_selection.gui.adapter import (
    photon_filter_settings_from_wizard,
)


class _FakeFilter:
    """The minimal attribute surface the adapter reads off a wizard filter."""

    def __init__(self, **overrides):
        self.channels = [0, 8]
        self.microtime_ranges = [(0, 2048)]
        self.used_filter = "tttrlib"
        self.dT_min = 0.5
        self.dT_max = 2.0
        self.use_lower = True
        self.use_upper = False
        self.max_gap = 4
        self.use_gap_fill = True
        self.settings = {
            "filter_active": True,
            "invert_filter": False,
            "count_rate_filter": {"n_ph_max": 100, "time_window": 1e-3},
        }
        self.__dict__.update(overrides)


def test_maps_the_core_fields():
    settings = photon_filter_settings_from_wizard(_FakeFilter())
    assert settings.channels == [0, 8]
    assert settings.used_filter == BurstFilterMode.TTTRLIB
    assert settings.max_gap == 4
    assert settings.use_gap_fill is True
    assert settings.delta_macro_time_filter.dT_min == 0.5
    assert settings.delta_macro_time_filter.dT_min_active is True
    assert settings.delta_macro_time_filter.dT_max_active is False


def test_unset_micro_time_window_becomes_an_empty_mask():
    # microtime_ranges is None when the window is "All"; downstream, "apply no
    # mask" is the empty list, not None.
    settings = photon_filter_settings_from_wizard(_FakeFilter(microtime_ranges=None))
    assert settings.microtime_ranges == []


def test_missing_tttrlib_fields_fall_back_to_a_valid_search():
    # A wizard that never set the registry-search attributes still yields a
    # fully specified request: the default algorithm and an empty parameter dict
    # (which means "every parameter takes its registry default").
    fake = _FakeFilter()
    assert not hasattr(fake, "tttrlib_algorithm")
    settings = photon_filter_settings_from_wizard(fake)
    assert settings.tttrlib_search == TttrlibSearchSettings()
    assert settings.tttrlib_search.algorithm == "maxtree"
    assert settings.tttrlib_search.parameters == {}


def test_blank_tttrlib_algorithm_falls_back_to_maxtree():
    settings = photon_filter_settings_from_wizard(
        _FakeFilter(tttrlib_algorithm="", tttrlib_parameters=None)
    )
    assert settings.tttrlib_search.algorithm == "maxtree"
    assert settings.tttrlib_search.parameters == {}


def test_explicit_tttrlib_selection_is_carried_through():
    settings = photon_filter_settings_from_wizard(
        _FakeFilter(
            tttrlib_algorithm="sliding_window",
            tttrlib_parameters={"L": 42},
        )
    )
    assert settings.tttrlib_search.algorithm == "sliding_window"
    assert settings.tttrlib_search.parameters == {"L": 42}


def test_parameters_are_copied_not_aliased():
    # The adapter dict-copies the parameters, so mutating the source afterwards
    # does not reach into the settings object.
    source = {"L": 10}
    settings = photon_filter_settings_from_wizard(
        _FakeFilter(tttrlib_algorithm="maxtree", tttrlib_parameters=source)
    )
    source["L"] = 999
    assert settings.tttrlib_search.parameters == {"L": 10}
