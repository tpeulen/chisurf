"""Integrity contracts for the detached, UID-based history audit projection."""

from chisurf.history.projection import build_target_state


def test_checkpoint_only_preserves_navigation():
    """A checkpoint with no delta retains its complete navigation inventory."""
    navigation = {
        "datasets": ["d"],
        "dataset_uids": ["du"],
        "fits": ["f"],
        "fit_uids": ["fu"],
        "selected_dataset": "d",
        "selected_dataset_uid": "du",
        "selected_fit": "f",
        "selected_fit_uid": "fu",
    }
    assert build_target_state({"navigation": navigation}, []).navigation == navigation


def test_navigation_delta_operates_on_checkpoint_uid_pairs():
    """UID operations preserve duplicate names and untouched base entities."""
    base = {
        "navigation": {
            "datasets": ["same", "same", "other"],
            "dataset_uids": ["d1", "d2", "d3"],
            "fits": ["same", "same"],
            "fit_uids": ["f1", "f2"],
            "selected_dataset": "same",
            "selected_dataset_uid": "d1",
            "selected_fit": "same",
            "selected_fit_uid": "f1",
        }
    }
    events = [
        {
            "action_type": "dataset.remove",
            "payload": {"removed_names": ["same"], "removed_uids": ["d1"]},
        },
        {"action_type": "fit.close", "source_uid": "f1", "payload": {"fit_name": "same"}},
        {
            "action_type": "dataset.group",
            "payload": {"group_name": "group", "group_uid": "g", "member_uids": ["d2"]},
        },
        {
            "action_type": "dataset.ungroup",
            "payload": {
                "group_names": ["group"],
                "group_uids": ["g"],
                "expanded_names": ["same"],
                "expanded_uids": ["d2"],
            },
        },
        {"action_type": "dataset.select", "payload": {"dataset_uid": "d3"}},
        {"action_type": "fit.select", "payload": {"fit_uid": "f2"}},
    ]
    navigation = build_target_state(base, events).navigation
    assert navigation["datasets"] == ["other", "same"]
    assert navigation["dataset_uids"] == ["d3", "d2"]
    assert navigation["fits"] == ["same"]
    assert navigation["fit_uids"] == ["f2"]
    assert navigation["selected_dataset"] == "other"
    assert navigation["selected_dataset_uid"] == "d3"
    assert navigation["selected_fit_uid"] == "f2"


def test_parameter_delta_preserves_metadata_and_unlink_clears_uid():
    """A value edit preserves bounds/fixed state; unlink clears both references."""
    checkpoint = {
        "parameters": {
            "entry": {
                "fit_group": "f",
                "local_fit": "l",
                "parameter_name": "p",
                "value": 1.0,
                "fixed": True,
                "bounds_on": True,
                "bounds": [0.0, 10.0],
                "link": {"fit_group": "target", "local_fit": "local", "parameter_name": "p"},
                "link_uid": ["tf", "tl", "tp"],
            }
        }
    }
    payload = {"fit_group": "f", "local_fit": "l", "parameter_name": "p"}
    state = build_target_state(
        checkpoint, [{"action_type": "parameter.value", "payload": {**payload, "new_value": 3.0}}]
    )
    assert state.parameters[("f", "l", "p")]["fixed"] is True
    assert state.parameters[("f", "l", "p")]["bounds"] == (0.0, 10.0)
    assert state.parameters[("f", "l", "p")]["link_uid"] == ("tf", "tl", "tp")
    state = build_target_state(
        checkpoint, [{"action_type": "parameter.unlink", "payload": payload}]
    )
    assert state.parameters[("f", "l", "p")]["link"] is None
    assert state.parameters[("f", "l", "p")]["link_uid"] is None


def test_duplicate_parameter_display_names_keep_exact_uid_identity():
    """A delta changes only the addressed UID, even when all names are equal."""
    entries = {}
    for index in (1, 2):
        entries[str(index)] = {
            "fit_group": "same",
            "local_fit": "same",
            "parameter_name": "same",
            "fit_group_uid": f"f{index}",
            "local_fit_uid": f"l{index}",
            "parameter_uid": f"p{index}",
            "value": index,
            "fixed": True,
        }
    events = [
        {
            "action_type": "parameter.value",
            "payload": {
                "fit_group": "same",
                "local_fit": "same",
                "parameter_name": "same",
                "fit_uid": "f1",
                "local_fit_uid": "l1",
                "parameter_uid": "p1",
                "new_value": 9.0,
            },
        }
    ]
    parameters = build_target_state({"parameters": entries}, events).parameters
    assert set(parameters) == {("f1", "l1", "p1"), ("f2", "l2", "p2")}
    assert parameters[("f1", "l1", "p1")]["value"] == 9.0
    assert parameters[("f1", "l1", "p1")]["fixed"] is True
    assert parameters[("f2", "l2", "p2")]["value"] == 2


def test_projection_returns_detached_nested_checkpoint_and_event_data():
    """Mutating a projection cannot change any checkpoint or event source."""
    checkpoint = {
        "navigation": {"datasets": ["d"], "dataset_uids": ["du"]},
        "fit_ranges": {"fu": {"xmin": 1, "xmax": 10}},
        "setup": {"params": {"settings": [1]}},
        "models": {"fu": {"local_fits": {"lu": {"config": {"items": [1]}}}}},
    }
    payload = {"fit_uid": "fu", "local_fit_uid": "lu", "settings": [2]}
    events = [{"action_type": "model.update", "payload": payload}]
    state = build_target_state(checkpoint, events)
    state.navigation["datasets"].append("extra")
    state.fit_ranges["fu"]["xmin"] = 99
    state.models["fu"]["local_fits"]["lu"]["config"]["items"].append(99)
    state.models["fu"]["local_fits"]["lu"]["config"]["update"]["settings"].append(99)
    assert checkpoint["navigation"]["datasets"] == ["d"]
    assert checkpoint["fit_ranges"]["fu"]["xmin"] == 1
    assert checkpoint["models"]["fu"]["local_fits"]["lu"]["config"]["items"] == [1]
    assert payload["settings"] == [2]


def test_range_and_model_delta_share_uid_and_preserve_base_configuration():
    """Range and editor model configuration stay attached to the same fit UID."""
    checkpoint = {
        "fit_ranges": {"f1": {"xmin": 1, "xmax": 10}, "f2": {"xmin": 2, "xmax": 20}},
        "setup": {"experiment": "TCSPC", "setup": "measured", "params": {"old": 1}},
        "models": {
            "f1": {
                "local_fits": {
                    "l1": {
                        "components": [{"name": "a", "state": {"value": 1}}],
                        "config": {"existing": 2},
                    }
                }
            }
        },
    }
    events = [
        {
            "action_type": "fit.range.set",
            "payload": {"fit_uid": "f1", "fit_group": "same", "xmin": 3, "xmax": 8},
        },
        {
            "action_type": "model.set_correction",
            "source_uid": "f1",
            "payload": {"local_fit_uid": "l1", "correction_type": "pileup", "value": 0.1},
        },
        {"action_type": "setup.params.set", "payload": {"params": {"new": 2}}},
    ]
    state = build_target_state(checkpoint, events)
    assert state.fit_ranges == {"f1": {"xmin": 3, "xmax": 8}, "f2": {"xmin": 2, "xmax": 20}}
    assert state.setup == {
        "experiment": "TCSPC",
        "setup": "measured",
        "params": {"old": 1, "new": 2},
    }
    assert set(state.models["f1"]["local_fits"]) == {"l1"}
    assert state.models["f1"]["local_fits"]["l1"]["config"] == {
        "existing": 2,
        "correction_pileup": 0.1,
    }
    assert state.models["f1"]["local_fits"]["l1"]["components"] == [
        {"name": "a", "state": {"value": 1}}
    ]


def test_audit_projection_cannot_recreate_live_science_from_source_paths():
    """The retired audit entity synchronizer must fail before any live mutation."""
    import pytest

    from chisurf.history.replay import sync_domain_entities

    with pytest.raises(RuntimeError, match="canonical scientific snapshot"):
        sync_domain_entities({}, [])


def test_ambiguous_name_only_removal_is_rejected():
    """An audit name never guesses which of two UID entities to remove."""
    import pytest

    checkpoint = {"navigation": {"fits": ["same", "same"], "fit_uids": ["f1", "f2"]}}
    with pytest.raises(ValueError, match="ambiguous"):
        build_target_state(
            checkpoint, [{"action_type": "fit.close", "payload": {"fit_name": "same"}}]
        )


def test_model_delta_does_not_guess_local_fit_identity():
    """A model event with no exact local owner cannot invent local_0."""
    import pytest

    with pytest.raises(ValueError, match="local fit UID"):
        build_target_state(
            None,
            [
                {
                    "action_type": "model.add_component",
                    "source_uid": "f",
                    "payload": {"component_name": "a"},
                }
            ],
        )


def test_touched_parameter_keys_use_same_exact_uid_contract():
    """Touched-key reporting uses the same identities as parameter projection."""
    from chisurf.history.replay import touched_parameter_keys

    events = [
        {
            "action_type": "parameter.value",
            "payload": {
                "fit_group": "same",
                "local_fit": "same",
                "parameter_name": "same",
                "fit_uid": "f",
                "local_fit_uid": "l",
                "parameter_uid": "p",
                "new_value": 2,
            },
        }
    ]
    assert touched_parameter_keys(events) == {("f", "l", "p")}


def test_name_only_audit_selection_keeps_unambiguous_existing_uid():
    """Name-only metadata can select an existing entity without dropping its UID."""
    checkpoint = {"navigation": {"fits": ["fit"], "fit_uids": ["f"]}}
    events = [
        {
            "action_type": "parameter.value",
            "payload": {
                "fit_group": "fit",
                "local_fit": "local",
                "parameter_name": "p",
                "new_value": 2,
            },
        }
    ]
    state = build_target_state(checkpoint, events)
    assert state.navigation["selected_fit"] == "fit"
    assert state.navigation["selected_fit_uid"] == "f"


def test_ungroup_replaces_checkpoint_group_at_its_existing_position():
    """Ungrouping retains untouched neighbors and expands the original UID slot."""
    base = {
        "navigation": {
            "datasets": ["before", "group", "after"],
            "dataset_uids": ["d0", "g", "d3"],
        }
    }
    events = [
        {
            "action_type": "dataset.ungroup",
            "payload": {
                "group_names": ["group"],
                "group_uids": ["g"],
                "expanded_names": ["same", "same"],
                "expanded_uids": ["d1", "d2"],
            },
        }
    ]
    state = build_target_state(base, events)
    assert state.navigation["datasets"] == ["before", "same", "same", "after"]
    assert state.navigation["dataset_uids"] == ["d0", "d1", "d2", "d3"]


def test_checkpoint_model_metadata_normalizes_to_exact_owner_uids():
    """Stored display labels never become runtime model ownership keys."""
    checkpoint = {
        "models": {
            "display": {
                "fit_group_uid": "f",
                "local_fits": {
                    "display": {
                        "local_fit_uid": "l",
                        "config": {"base": 1},
                        "components": [],
                    }
                },
            }
        }
    }
    events = [
        {
            "action_type": "model.set_correction",
            "source_uid": "f",
            "payload": {
                "local_fit_uid": "l",
                "correction_type": "pileup",
                "value": 0.2,
            },
        }
    ]
    state = build_target_state(checkpoint, events)
    assert set(state.models) == {"f"}
    assert set(state.models["f"]["local_fits"]) == {"l"}
    assert state.models["f"]["local_fits"]["l"]["config"] == {"base": 1, "correction_pileup": 0.2}


def test_aggregated_multi_group_ungroup_does_not_guess_member_positions():
    """Incomplete aggregated audit rows reject positional reconstruction."""
    import pytest

    checkpoint = {
        "navigation": {
            "datasets": ["group", "between", "group"],
            "dataset_uids": ["g1", "d", "g2"],
        }
    }
    event = {
        "action_type": "dataset.ungroup",
        "payload": {
            "group_uids": ["g1", "g2"],
            "expanded_names": ["a", "b"],
            "expanded_uids": ["a", "b"],
        },
    }
    with pytest.raises(ValueError, match="per-group member"):
        build_target_state(checkpoint, [event])
