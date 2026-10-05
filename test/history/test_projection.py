"""Headless characterization tests for the pure replay projection.

These pin the behaviour of ``chisurf.history.build_target_state`` so the Stage-1
extraction from ``main_helper.py`` is verifiably a move, not a rewrite, and so
later stages (MMFDB-backed log) can assert projection-equivalence against it.

No Qt, no DB — pure event lists in, ``DomainState`` out.
"""

from __future__ import annotations

import chisurf.history as history
from chisurf.history import replay as _hr


def _ev(action_type, payload=None, summary=""):
    return {
        "event_id": action_type + ":" + str(len(summary)),
        "timestamp": "2026-06-27T00:00:00+00:00",
        "action_type": action_type,
        "summary": summary or action_type,
        "payload": payload or {},
        "source_uid": None,
        "target_uid": None,
    }


def test_no_checkpoint_matches_reconstruct():
    """Without a checkpoint, the projection equals the raw reconstruct_* output."""
    events = [
        _ev("dataset.add", {"name": "ds0", "dataset_uid": "u0"}),
        _ev("fit.add", {"fit_name": "fit0", "fit_uid": "f0"}),
        _ev(
            "parameter.value",
            {"fit_group": "f0", "local_fit": "local_0", "name": "tau", "value": 4.0},
        ),
    ]

    state = history.build_target_state(None, events, events)

    assert isinstance(state, history.DomainState)
    assert state.navigation == _hr.reconstruct_navigation_state(events)
    assert state.parameters == _hr.reconstruct_parameter_state(events)
    assert state.fit_ranges == _hr.reconstruct_fit_range_state(events)
    assert state.setup == _hr.reconstruct_setup_state(events)
    assert state.models == _hr.reconstruct_model_state(events)


def test_empty_inputs_give_empty_state():
    state = history.build_target_state(None, [], [])
    assert state.navigation == _hr.reconstruct_navigation_state([])
    assert state.parameters == {}
    assert state.fit_ranges == {}
    assert state.models == {}


def test_checkpoint_seeds_then_delta_overrides():
    """A delta preserves checkpoint inventory and untouched parameter metadata."""
    checkpoint = {
        "navigation": {
            "datasets": ["ds0"],
            "dataset_uids": ["u0"],
            "fits": ["fit0"],
            "fit_uids": ["f0"],
            "selected_dataset": "ds0",
            "selected_dataset_uid": "u0",
            "selected_fit": "fit0",
            "selected_fit_uid": "f0",
        },
        # snapshot param format: keyed dict carrying fit_group/local_fit/parameter_name
        "parameters": {
            "f0|local_0|tau": {
                "fit_group": "fit0",
                "local_fit": "local_0",
                "parameter_name": "tau",
                "value": 2.0,
                "fixed": True,
                "bounds": [0.1, 10.0],
            }
        },
        "fit_ranges": {},
        "setup": {},
        "models": {},
    }
    delta_events = [
        _ev(
            "parameter.value",
            {
                "fit_group": "fit0",
                "local_fit": "local_0",
                "parameter_name": "tau",
                "new_value": 9.0,
            },
        ),
    ]

    state = history.build_target_state(checkpoint, delta_events, delta_events)

    assert state.navigation == checkpoint["navigation"]
    assert state.parameters[("fit0", "local_0", "tau")] == {
        "value": 9.0,
        "fixed": True,
        "bounds": (0.1, 10.0),
    }


def test_all_events_argument_is_optional_and_ignored():
    events = [_ev("dataset.add", {"name": "ds0", "dataset_uid": "u0"})]
    with_all = history.build_target_state(None, events, events)
    without_all = history.build_target_state(None, events)
    assert with_all.navigation == without_all.navigation
