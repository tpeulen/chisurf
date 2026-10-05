"""Canonical described-model state must win over constructor group defaults."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("IMP.bff")

from chisurf.core.data import DataCurve, DataCurveGroup
from chisurf.core.fitting.fit import Fit, FitGroup
from chisurf.core.models.description import for_family
from chisurf.core.project.session import _model_state, capture_session, restore_session
from chisurf.core.project.storage import load_file, save_file


def _rotation_state(model):
    """Return the scientific state that distinguishes the polarised topology."""
    state = model.get_state()
    return {
        "scalars": dict(state["scalars"]),
        "structure": state["structure"],
        "values": {
            name: state["values"][name]
            for name in (
                "rotation.amplitude.0",
                "rotation.amplitude.1",
                "rotation.time.0",
                "rotation.time.1",
            )
        },
    }


def test_group_restore_does_not_leak_constructor_group_position_into_snapshot(tmp_path):
    """A wrapped standalone polarised fit round-trips as its saved topology.

    A group of one ordinarily starts at the magic angle.  That interactive
    construction policy is not saved scientific state: this source was created
    outside a group and explicitly selects a two-rotation topology.  Saving it
    after a presentation wrapper is added must therefore retain the source
    topology rather than injecting the group policy before state restoration.
    """
    x = np.arange(128, dtype=float) * 0.05
    data = DataCurve(x=x, y=np.exp(-x / 3.0) * 1000.0 + 1.0, ey=np.ones_like(x))
    model_class = for_family("tcspc_polarized")
    source = Fit(model_class=model_class, data=data)
    source.model.structure = "lifetime.components.1.rotations.2"
    expected_values = {
        "rotation.amplitude.0": 0.31,
        "rotation.amplitude.1": 0.69,
        "rotation.time.0": 1.7,
        "rotation.time.1": 3.4,
    }
    for name, value in expected_values.items():
        port = source.model.problem.get_parameter(name)
        fixed = port.fixed
        port.fixed = False
        port.value = value
        port.fixed = fixed
    expected = _rotation_state(source.model)
    assert expected["scalars"] == {}
    assert expected["structure"] == "lifetime.components.1.rotations.2"
    assert expected["values"] == expected_values

    # This is the ordinary presentation wrapper path used by the actual-Main
    # probe: it does not re-create the scientific member or rewrite its state.
    group = FitGroup(DataCurveGroup([data]))
    group.grouped_fits[:] = [source]
    group._model.fits = group.grouped_fits

    project = capture_session([data], [group], name="wrapped-polarized")
    persisted = project.fits[0]["members"][0]["model"]["adapter_state"]
    assert {
        "scalars": persisted["scalars"],
        "structure": persisted["structure"],
        "values": {name: persisted["values"][name] for name in expected_values},
    } == expected

    path = save_file(project, tmp_path / "wrapped-polarized.cs.pto")
    restored = restore_session(load_file(path))
    restored_group = restored.fits[0]
    restored_model = restored_group.grouped_fits[0].model
    assert restored_model.fit.group is restored_group.grouped_fits
    assert _rotation_state(restored_model) == expected


def test_described_model_snapshot_records_stable_canonical_parameter_ids():
    """Description ports carry keys that remain valid when display order changes."""
    x = np.arange(48, dtype=float) * 0.05
    curves = [
        DataCurve(
            x=x,
            y=np.exp(-x / (2.0 + index)) * 1000.0 + 1.0,
            ey=np.ones_like(x),
            name=f"canonical-{index}",
        )
        for index in range(2)
    ]
    group = FitGroup(DataCurveGroup(curves), model_class=for_family("tcspc_polarized"))
    source_parameters = list(group.grouped_fits[0].model.parameters_all)
    snapshot = _model_state(group.grouped_fits[0].model)
    stored_ids = [state["canonical_id"] for state in snapshot["parameters"]]

    assert stored_ids == [parameter.canonical_id for parameter in source_parameters]
    assert len(stored_ids) == len(set(stored_ids))


@pytest.mark.parametrize(("size", "polarizations"), [(1, [0.0]), (2, [1.0, 2.0])])
def test_explicit_group_positions_round_trip_as_saved_scientific_state(
    tmp_path, size, polarizations
):
    """Real group positions persist explicitly instead of being inferred again."""
    x = np.arange(96, dtype=float) * 0.05
    curves = [
        DataCurve(
            x=x,
            y=np.exp(-x / (2.0 + index)) * 1000.0 + 1.0,
            ey=np.ones_like(x),
            name=f"polarized-{index}",
        )
        for index in range(size)
    ]
    group = FitGroup(DataCurveGroup(curves), model_class=for_family("tcspc_polarized"))
    expected = [
        {
            "scalars": dict(member.model.get_state()["scalars"]),
            "structure": member.model.get_state()["structure"],
            "values": dict(member.model.get_state()["values"]),
        }
        for member in group.grouped_fits
    ]
    assert [state["scalars"]["polarization"] for state in expected] == polarizations

    project = capture_session(curves, [group], name="explicit-group-positions")
    path = save_file(project, tmp_path / "explicit-group-positions.cs.pto")
    restored = restore_session(load_file(path)).fits[0]
    actual = [
        {
            "scalars": dict(member.model.get_state()["scalars"]),
            "structure": member.model.get_state()["structure"],
            "values": dict(member.model.get_state()["values"]),
        }
        for member in restored.grouped_fits
    ]
    assert actual == expected
    assert [
        member.model.get_scalar("polarization") for member in restored.grouped_fits
    ] == polarizations
    assert all(member.group is restored.grouped_fits for member in restored.grouped_fits)
