"""Burst results in the measurement's container, at whatever grain they are.

The `…4` companion format could hold exactly one shape: a table 1:1 with a burst
grid, merged by counting rows. These are the shapes it could not hold, which is
why H2MM's results ended up in five files outside it and why burst fusion wrote
into somebody else's analysis directory.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from chisurf.core.fio.fluorescence.burst_container import (
    container_for,
    deinterleave_bursts,
    write_burst_artifact,
    write_per_source,
)
from chisurf.core.fio.pto import Measurement

DATA = Path(__file__).resolve().parents[1] / "data"
PTU = DATA / "clsm" / "Leica_SP5.ptu"

pytestmark = pytest.mark.skipif(not PTU.exists(), reason="no instrument test data")


def _bursts(n=20):
    return pd.DataFrame(
        {
            "Number of Photons": np.arange(n, dtype=np.int32),
            "Mean Macro Time (ms)": np.linspace(0, 100, n),
        }
    )


@pytest.fixture
def measurement(tmp_path: Path) -> Path:
    raw = tmp_path / "m000.ptu"
    shutil.copy(PTU, raw)
    write_burst_artifact(
        raw, _bursts(),
        name="bursts", artifact_kind="burst_table",
        operation_type="burst_selection", row_grain="burst",
        parameters={"min_photons": 60}, derived_from=(),
    )
    return raw


# -- the shape that fits ---------------------------------------------------------


def test_a_per_burst_result_joins_the_burst_table(measurement: Path):
    write_burst_artifact(
        measurement,
        pd.DataFrame({"Proximity Ratio Mean": np.linspace(0, 1, 20)}),
        name="bva", artifact_kind="burst_table",
        operation_type="burst_variance_analysis", row_grain="burst",
        parameters={"window": 5},
    )
    with Measurement.open(container_for(measurement)) as m:
        uid = m._resolve("bva")
        assert m.parents(uid) == [m._resolve("bursts")]
        assert m.tag(uid, "_mmfdb_artifact.row_grain") == "burst"


# -- the shapes that did not ------------------------------------------------------


def test_a_finer_grained_result_carries_its_key(measurement: Path):
    """A dwell subdivides a burst, so it cannot be a row in a burst table.
    The companion format had nowhere to put it."""
    dwells = pd.DataFrame(
        {"burst": np.repeat(np.arange(5), 4), "state": np.tile([0, 1, 0, 1], 5)}
    )
    write_burst_artifact(
        measurement, dwells,
        name="dwells", artifact_kind="dwell_table",
        operation_type="photon_hmm", row_grain="dwell",
        parameters={"states": 2},
        source_row_column="burst", target_row_column="Number of Photons",
    )
    with Measurement.open(container_for(measurement)) as m:
        uid = m._resolve("dwells")
        assert len(m.get_table("dwells")) == 20
        assert m.tag(uid, "_mmfdb_artifact.row_grain") == "dwell"
        assert m.tag(uid, "_mmfdb_edge.source_row_column") == "burst"


def test_a_coarser_result_maps_many_source_rows_to_one(measurement: Path):
    """Burst fusion. The legacy writer had no way to say which sources made a
    fused burst, so it wrote the membership back into the *source* analysis's
    directory -- mutating another output to carry a relation."""
    labels = np.array([0, 0, 1, 1, 1, 2] + [3] * 14)
    fused = _bursts(4)
    with Measurement.open(container_for(measurement), writable=True) as m:
        bursts = m._resolve("bursts")
        fused_uid = m.put_table(
            "fused bursts", fused,
            artifact_kind="burst_table", operation_type="burst_fusion",
            row_grain="burst", parameters={"p_same": 0.8},
            derived_from=[m.instrument_uid, bursts],
        )
        m.put_table(
            "fusion membership",
            pd.DataFrame(
                {
                    "source_row": np.arange(labels.size, dtype=np.int64),
                    "fused_row": labels.astype(np.int64),
                }
            ),
            artifact_kind="row_mapping", operation_type="burst_fusion",
            row_grain="pair", parameters={"p_same": 0.8},
            derived_from=[bursts, fused_uid],
            source_row_column="source_row", target_row_column="fused_row",
        )

    with Measurement.open(container_for(measurement)) as m:
        fused_uid = m._resolve("fused bursts")
        assert len(m.parents(fused_uid)) == 2, "a fused burst has several parents"
        mapping = m.get_table("fusion membership")
        assert len(mapping) == labels.size
        # every source burst is accounted for, and the many-to-one is recoverable
        assert mapping.groupby("fused_row")["source_row"].count().tolist() == [2, 3, 1, 14]
        assert m.tag(m._resolve("fusion membership"), "_mmfdb_edge.target_row_column") == (
            "fused_row"
        )


def test_nothing_is_written_outside_the_measurement(measurement: Path, tmp_path: Path):
    before = {p.name for p in tmp_path.iterdir()}
    write_burst_artifact(
        measurement, pd.DataFrame({"x": [1.0, 2.0]}),
        name="whatever", artifact_kind="burst_table",
        operation_type="burst_fusion", row_grain="burst",
    )
    assert {p.name for p in tmp_path.iterdir()} == before
    assert not [p for p in tmp_path.iterdir() if p.is_dir()]


# -- splitting a multi-measurement frame -------------------------------------------


def test_a_frame_covering_several_files_goes_to_several_containers(tmp_path: Path):
    a, b = tmp_path / "a.ptu", tmp_path / "b.ptu"
    shutil.copy(PTU, a)
    shutil.copy(PTU, b)
    frame = pd.DataFrame(
        {
            "First File": [str(a)] * 3 + [str(b)] * 2,
            "Proximity Ratio Mean": [0.1, 0.2, 0.3, 0.4, 0.5],
        }
    )
    written = write_per_source(
        frame,
        name="bva", artifact_kind="burst_table",
        operation_type="burst_variance_analysis", row_grain="burst",
        derived_from=(),
    )
    assert len(written) == 2
    with Measurement.open(container_for(a)) as m:
        assert len(m.get_table("bva")) == 3
        assert "First File" not in m.get_table("bva").columns
    with Measurement.open(container_for(b)) as m:
        assert len(m.get_table("bva")) == 2


def test_a_frame_with_no_source_column_is_refused(tmp_path: Path):
    """Guessing would put one measurement's results in another's file."""
    with pytest.raises(KeyError, match="attributed"):
        write_per_source(
            pd.DataFrame({"x": [1.0]}),
            name="x", artifact_kind="burst_table",
            operation_type="burst_variance_analysis", row_grain="burst",
        )


# -- the interleave ------------------------------------------------------------------


def test_the_legacy_padding_is_stripped_on_the_way_in(measurement: Path):
    padded = pd.DataFrame(
        {"a": [0, 1, 0, 2, 0], "b": [0.0, 1.5, 0.0, 2.5, 0.0], "": [""] * 5}
    )
    write_burst_artifact(
        measurement, padded,
        name="padded", artifact_kind="burst_table",
        operation_type="burst_variance_analysis", row_grain="burst",
    )
    with Measurement.open(container_for(measurement)) as m:
        out = m.get_table("padded")
    assert len(out) == 2
    assert list(out.columns) == ["a", "b"]


def test_deinterleave_keeps_a_genuine_zero_row():
    """Only the even rows are padding; an odd row that is all zeros is data."""
    frame = pd.DataFrame({"a": [0, 0, 0, 5, 0], "b": [0.0, 0.0, 0.0, 5.0, 0.0]})
    assert list(deinterleave_bursts(frame)["a"]) == [0, 5]


# -- units -----------------------------------------------------------------------
#
# A number in a burst table means nothing without its unit, and the unit lived in
# the column name when whoever wrote it remembered. `Duration (ms)` and `Tau` sit
# in the same table.


def _column_units(path):
    import tttrlib

    with Measurement.open(container_for(path)) as m:
        store = tttrlib.pto_store(m._f, m._resolve("bursts"))
        return {store[i].name(): store[i].units() for i in range(store.n_columns())}


def test_a_written_table_says_what_its_numbers_are_in(tmp_path: Path):
    import shutil

    raw = tmp_path / "m.ptu"
    shutil.copy(PTU, raw)
    write_burst_artifact(
        raw,
        pd.DataFrame(
            {
                "Duration (ms)": np.linspace(1.0, 5.0, 6),
                "Count Rate (KHz)": np.linspace(10.0, 60.0, 6),
                "Tau (green)": np.linspace(2.0, 4.0, 6),
                "Number of Photons": np.arange(6, dtype=np.int32),
                "First Photon": np.arange(6, dtype=np.int64),
            }
        ),
        name="bursts", artifact_kind="burst_table",
        operation_type="burst_selection", row_grain="burst", derived_from=(),
    )
    units = _column_units(raw)
    assert units["Duration (ms)"] == "milliseconds"
    assert units["Count Rate (KHz)"] == "kilohertz"
    assert units["Tau (green)"] == "nanoseconds"
    assert units["Number of Photons"] == "photons"
    # An index is not a physical quantity, so it says nothing rather than
    # claiming to be dimensionless.
    assert units["First Photon"] == ""


def test_a_plugin_can_name_the_units_of_its_own_columns(tmp_path: Path):
    import shutil

    raw = tmp_path / "m.ptu"
    shutil.copy(PTU, raw)
    write_burst_artifact(
        raw,
        pd.DataFrame({"Transit Time": np.linspace(0.1, 0.5, 4)}),
        name="bursts", artifact_kind="burst_table",
        operation_type="burst_selection", row_grain="burst", derived_from=(),
        units={"Transit Time": "microseconds"},
    )
    assert _column_units(raw)["Transit Time"] == "microseconds"


def test_an_invented_unit_is_refused(tmp_path: Path):
    """The units vocabulary is the dictionary's, like every other term."""
    import shutil

    from chisurf.core.fio.pto import PtoMfdbError

    raw = tmp_path / "m.ptu"
    shutil.copy(PTU, raw)
    with pytest.raises(PtoMfdbError, match="not a value of"):
        write_burst_artifact(
            raw,
            pd.DataFrame({"x": [1.0, 2.0]}),
            name="bursts", artifact_kind="burst_table",
            operation_type="burst_selection", row_grain="burst", derived_from=(),
            units={"x": "furlongs"},
        )
