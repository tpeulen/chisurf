"""Selected GS state rows retain raw photon/file/burst identity and exact lineage."""

import shutil
from pathlib import Path

import numpy as np
import pytest
import tttrlib

from chisurf.core.datastore import column_names
from chisurf.core.fio.pto import Measurement
from chisurf.plugins.burst.burst_gs import core

DATA = (
    Path(__file__).resolve().parents[2]
    / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"
)


def _analyse(bursts, info):
    """Run the actual native likelihood/decoder with a short qualified fit."""
    return core.analyse(
        bursts,
        initial_rates=[1000.0, 1000.0],
        initial_efficiencies=[0.2, 0.8],
        max_iterations=5,
        decode_states=True,
        info=info,
    )


@pytest.fixture(scope="module")
def measured(tmp_path_factory):
    """Load the actual measured BH subset, preserving original BUR positions."""
    folder = tmp_path_factory.mktemp("gs-measured-identity")
    raw = folder / "m000.spc"
    bur = folder / "m000.bur"
    shutil.copy2(DATA / "m000.spc", raw)
    shutil.copy2(DATA / "burst_analysis_handoff/bi4_bur/m000.bur", bur)
    bursts, info = core.load_photons([bur], folder, file_type="SPC-130")
    return raw, bur, bursts, info


def test_real_selected_indices_join_exact_raw_photons(measured):
    """A selected subset never implies raw photon indices start at zero."""
    raw, bur, bursts, info = measured
    identity = info["photon_identity"]
    assert bursts.n_photons == 17282
    assert identity["Photon"][0] == 1786
    stream = tttrlib.TTTR(str(raw), "SPC-130")
    indices = np.asarray(identity["Photon"], dtype=np.int64)
    np.testing.assert_array_equal(
        bursts.times, np.asarray(stream.macro_times)[indices] * info["macro_time_resolution"]
    )
    routing = np.asarray(stream.routing_channels)[indices]
    # Colours index the declared streams; routing channels are detector IDs.
    assert np.isin(routing, [0, 8, 1, 9]).all()
    expected_colors = np.where(np.isin(routing, [0, 8]), 0, 1)
    np.testing.assert_array_equal(bursts.colors, expected_colors)
    lines = bur.read_text().splitlines()
    names = lines[0].rstrip("\t").split("\t")
    for row in np.unique(identity["Burst Row"]):
        values = lines[int(row) + 1].split("\t")
        first, last = (
            int(values[names.index("First Photon")]),
            int(values[names.index("Last Photon")]),
        )
        selected = indices[np.asarray(identity["Burst Row"]) == row]
        assert selected.min() >= first and selected.max() <= last
    assert set(identity["First File"]) == {"m000.spc"}
    assert set(identity["Source"]) == {str(raw.resolve())}


def _raw(path, reverse=False):
    """Write a real small SPC stream whose local indices are independently known."""
    stream = tttrlib.TTTR()
    stream.append_events(
        np.arange(12, dtype=np.uint64) * 1000,
        np.arange(12, dtype=np.uint16),
        (np.arange(12) % 2 if not reverse else 1 - np.arange(12) % 2).astype(np.int8),
        np.zeros(12, dtype=np.int8),
        False,
        0,
    )
    stream.header.set_macro_time_resolution(12.5e-9)
    path.parent.mkdir(parents=True, exist_ok=True)
    stream.write(str(path))
    return path


def _table(path, rows):
    """Write logical rows, including skipped observations, without padding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "First File\tFirst Photon\tLast Photon\n"
        + "\n".join("\t".join(map(str, row)) for row in rows)
        + "\n"
    )
    return path


@pytest.fixture
def mixed(tmp_path):
    """Two measurements restart raw indices; overlaps keep separate burst contexts."""
    one, two = _raw(tmp_path / "one.spc"), _raw(tmp_path / "two.spc", True)
    bur = _table(
        tmp_path / "input.bur",
        [[one.name, 2, 6], [0, 0, 0], [one.name, 3, 7], [two.name, 2, 6], [two.name, 8, 8]],
    )
    bursts, info = core.load_photons([bur], tmp_path, file_type="SPC-130", min_photons=1)
    return one, two, bur, bursts, info


def test_skipped_singletons_overlap_and_max_bursts_keep_original_rows(mixed):
    """Mapping follows the existing final fit filter, not compacted row numbers."""
    one, two, bur, bursts, info = mixed
    identity = info["photon_identity"]
    np.testing.assert_array_equal(identity["Photon"], [2, 3, 4, 5, 6, 3, 4, 5, 6, 7, 2, 3, 4, 5, 6])
    np.testing.assert_array_equal(identity["Burst Row"], [0] * 5 + [2] * 5 + [3] * 5)
    assert bursts.offsets.tolist() == [0, 5, 10, 15]
    limited, limited_info = core.load_photons(
        [bur], one.parent, file_type="SPC-130", min_photons=1, max_bursts=2
    )
    np.testing.assert_array_equal(limited.times, bursts.times[:10])
    np.testing.assert_array_equal(
        limited_info["photon_identity"]["Photon"], identity["Photon"][:10]
    )
    assert limited_info["photon_identity"]["Burst Row"] == identity["Burst Row"][:10]


def test_export_splits_file_local_photons_and_declares_units_context(mixed):
    """Each source gets only its selected rows, with the shared joint-fit context."""
    one, two, bur, bursts, info = mixed
    analysis = _analyse(bursts, info)
    with Measurement.create(one) as measurement:
        measurement.put_metadata({"flr_sample": {"sample_description": "GS identity test"}})
    returned = core.write_container(one, analysis, parameters={"run": "A"})
    assert returned == str(one.with_suffix(".pto"))
    for raw, expected_rows in ((one, 10), (two, 5)):
        with Measurement.open(raw.with_suffix(".pto")) as measurement:
            objects = measurement.artifacts(artifact_kind="state_trajectory")
            assert len(objects) == 1
            obj = objects[0]
            table = measurement.get_store(obj.uid)
            assert table.n_rows() == expected_rows
            assert {"Photon", "Burst Row", "First File", "Source", "State"} <= set(
                column_names(table)
            )
            selected = np.asarray(info["photon_identity"]["Source"]) == str(raw.resolve())
            np.testing.assert_array_equal(
                np.asarray(table["Photon"]), np.asarray(info["photon_identity"]["Photon"])[selected]
            )
            np.testing.assert_array_equal(np.asarray(table["State"]), analysis.state_path[selected])
            assert measurement.column_units(table, "Photon") == "dimensionless"
            assert measurement.column_units(table, "Burst Row") == "dimensionless"
            provenance = measurement.provenance(obj.uid)
            assert provenance["grain"] == "photon"
            assert set(provenance["settings"]["gs_sources"]) == {
                str(one.resolve()),
                str(two.resolve()),
            }
            assert measurement.verify() == []
            if raw == one:
                assert "GS identity test" in measurement.metadata()


def test_exact_state_uid_lineage_survives_a_b_a(measured):
    """Identical labels across settings must never resolve another run's parent."""
    raw, _, bursts, info = measured
    analysis = _analyse(bursts, info)
    for run in ("A", "B", "A"):
        core.write_container(raw, analysis, parameters={"run": run})
        with Measurement.open(raw.with_suffix(".pto")) as measurement:
            matching = [
                obj
                for obj in measurement.artifacts()
                if measurement.provenance(obj.uid)["settings"].get("run") == run
            ]
            states = next(obj for obj in matching if obj.name == "gs states")
            for obj in matching:
                if obj.name in {"gs rates", "gs state path"}:
                    assert measurement.parents(obj.uid) == [states.uid]
            assert measurement.verify() == []


@pytest.mark.parametrize(
    "missing", ["photon_identity", "Source", "Photon", "Burst Row", "First File"]
)
def test_missing_measured_identity_fails_before_any_instrument_write(mixed, missing):
    """An unjoinable decoded subset cannot be attached to an unrelated raw stream."""
    one, _, _, bursts, info = mixed
    info = dict(info)
    if missing == "photon_identity":
        info.pop(missing, None)
    elif "photon_identity" in info:
        info["photon_identity"] = {
            key: value for key, value in info["photon_identity"].items() if key != missing
        }
    analysis = _analyse(bursts, info)
    with pytest.raises(ValueError, match="identity"):
        core.write_container(one, analysis)
    assert not one.with_suffix(".pto").exists()


def test_simulation_never_attaches_to_real_instrument_but_standalone_persists(tmp_path):
    """Simulation photons have ordinal identity in their own explicit context."""
    raw = _raw(tmp_path / "raw.spc")
    bursts = core.simulate_two_state(n_bursts=2, photons_per_burst=8, seed=11)
    analysis = _analyse(bursts, {"source": "simulation"})
    with pytest.raises(ValueError, match="simulation"):
        core.write_container(raw, analysis)
    assert not raw.with_suffix(".pto").exists()
    standalone = tmp_path / "simulation.pto"
    with Measurement.create_empty(standalone):
        pass
    core.write_container(standalone, analysis)
    with Measurement.open(standalone) as measurement:
        assert measurement.instrument_uids == []
        obj = measurement.artifacts(artifact_kind="state_trajectory")[0]
        table = measurement.get_store(obj.uid)
        np.testing.assert_array_equal(np.asarray(table["Photon"]), np.arange(bursts.n_photons))
        assert "First File" not in column_names(table)
        assert measurement.provenance(obj.uid)["settings"]["gs_photon_index_scope"] == "simulation"
        assert measurement.verify() == []


def test_duplicate_relative_keys_across_distinct_input_folders_are_refused(tmp_path):
    """Duplicate basenames cannot silently identify the wrong measurement."""
    a, b = tmp_path / "a", tmp_path / "b"
    _raw(a / "m000.spc")
    _raw(b / "m000.spc", True)
    one = _table(a / "input.bur", [["m000.spc", 2, 6]])
    two = _table(b / "input.bur", [["m000.spc", 2, 6]])
    with pytest.raises(ValueError, match="ambiguous"):
        core.load_photons([one, two], a, file_type="SPC-130", min_photons=2)


def test_missing_measurement_is_not_silently_omitted(tmp_path):
    """An absent raw file cannot become an unreported smaller joint fit."""
    raw = _raw(tmp_path / "present.spc")
    bur = _table(tmp_path / "input.bur", [[raw.name, 2, 6], ["missing.spc", 2, 6]])
    with pytest.raises(FileNotFoundError, match="missing.spc"):
        core.load_photons([bur], tmp_path, file_type="SPC-130", min_photons=2)


def test_distinct_absolute_sources_with_equal_basenames_remain_distinct(tmp_path):
    """Absolute references disambiguate file-local photon indices."""
    one = _raw(tmp_path / "a/m000.spc")
    two = _raw(tmp_path / "b/m000.spc", True)
    first = _table(tmp_path / "a/input.bur", [[str(one), 2, 6]])
    second = _table(tmp_path / "b/input.bur", [[str(two), 2, 6]])
    bursts, info = core.load_photons([first, second], tmp_path, file_type="SPC-130", min_photons=2)
    assert bursts.n_photons == 10
    assert info["photon_identity"]["Source"] == [str(one)] * 5 + [str(two)] * 5
    np.testing.assert_array_equal(info["photon_identity"]["Photon"], [2, 3, 4, 5, 6] * 2)


def test_state_path_mismatch_is_rejected_before_writing(mixed):
    """A decoder result must align exactly with the selected-photon mapping."""
    raw, _, _, bursts, info = mixed
    analysis = _analyse(bursts, info)
    analysis.state_path = analysis.state_path[:-1]
    with pytest.raises(ValueError, match="state path"):
        core.write_container(raw, analysis)
    assert not raw.with_suffix(".pto").exists()


def test_relative_tables_can_share_one_declared_measurement_directory(tmp_path):
    """Different BUR folders may legitimately refer to one common raw source."""
    raw = _raw(tmp_path / "raw/m000.spc")
    first = _table(tmp_path / "a/input.bur", [[raw.name, 2, 6]])
    second = _table(tmp_path / "b/input.bur", [[raw.name, 7, 11]])
    bursts, info = core.load_photons(
        [first, second], raw.parent, file_type="SPC-130", min_photons=2
    )
    assert bursts.n_photons == 10
    assert set(info["photon_identity"]["Source"]) == {str(raw.resolve())}
    np.testing.assert_array_equal(info["photon_identity"]["Photon"], list(range(2, 12)))


def test_export_records_declared_stream_colours_and_physical_clock(mixed):
    """Equal photon subsets with swapped colours remain distinguishable runs."""
    raw, _, bur, bursts, info = mixed
    first = _analyse(bursts, info)
    core.write_container(raw, first, parameters={"fit": "same"})
    swapped, changed = core.load_photons(
        [bur],
        raw.parent,
        file_type="SPC-130",
        min_photons=1,
        streams=[{"name": "donor", "channels": [1, 9]}, {"name": "acceptor", "channels": [0, 8]}],
    )
    np.testing.assert_array_equal(swapped.times, bursts.times)
    np.testing.assert_array_equal(
        changed["photon_identity"]["Photon"], info["photon_identity"]["Photon"]
    )
    core.write_container(raw, _analyse(swapped, changed), parameters={"fit": "same"})
    with Measurement.open(raw.with_suffix(".pto")) as measurement:
        states = measurement.artifacts(artifact_kind="fit_result")
        assert len(states) == 2
        definitions = []
        for obj in states:
            settings = measurement.provenance(obj.uid)["settings"]
            definitions.append(settings["gs_stream_definitions"])
            assert settings["gs_macro_time_resolution"] == info["macro_time_resolution"]
        assert definitions[0] != definitions[1]
