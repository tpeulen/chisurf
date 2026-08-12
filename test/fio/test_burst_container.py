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
from types import SimpleNamespace
import pandas as pd
import pytest

from chisurf.core.fio.fluorescence.burst_container import (
    container_for,
    deinterleave_bursts,
    write_burst_artifact,
    write_per_source,
)
from chisurf.core.datastore import column_names, numeric_column, row_count
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
        assert row_count(m.get_store("dwells")) == 20
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
        mapping = m.get_store("fusion membership")
        assert row_count(mapping) == labels.size
        # every source burst is accounted for, and the many-to-one is recoverable
        fused = numeric_column(mapping, "fused_row").astype(int)
        counts = [int((fused == which).sum()) for which in sorted(set(fused.tolist()))]
        assert counts == [2, 3, 1, 14]
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
        assert row_count(m.get_store("bva")) == 3
        assert "First File" not in column_names(m.get_store("bva"))
    with Measurement.open(container_for(b)) as m:
        assert row_count(m.get_store("bva")) == 2


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
        out = m.get_store("padded")
    assert row_count(out) == 2
    assert column_names(out) == ["a", "b"]


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


def test_a_detector_qualifier_does_not_cost_a_column_its_unit(tmp_path: Path):
    """The same quantity, qualified by a detector, is the same quantity.

    The fallback table keys on the exact column name, so `Number of Photons`
    was photons and `Number of Photons (green)` -- in the same row of the same
    table -- was unitless. The qualifier is dropped and the table asked again,
    which also stops it needing one row per detector name it has never heard of.
    """
    import shutil

    raw = tmp_path / "m.ptu"
    shutil.copy(PTU, raw)
    write_burst_artifact(
        raw,
        pd.DataFrame(
            {
                "Number of Photons": np.arange(4, dtype=np.int64),
                "Number of Photons (green)": np.arange(4, dtype=np.int64),
                "Number of Photons (perpendicular)": np.arange(4, dtype=np.int64),
                "Tau (yellow)": np.linspace(1.0, 2.0, 4),
                "First Photon (green)": np.arange(4, dtype=np.int64),
            }
        ),
        name="bursts", artifact_kind="burst_table",
        operation_type="burst_selection", row_grain="burst", derived_from=(),
    )
    units = _column_units(raw)
    assert units["Number of Photons"] == "photons"
    assert units["Number of Photons (green)"] == "photons"
    # A detector this table has never heard of, and never will have to.
    assert units["Number of Photons (perpendicular)"] == "photons"
    assert units["Tau (yellow)"] == "nanoseconds"
    # Still an index, still not measured in anything.
    assert units["First Photon (green)"] == ""


def test_a_window_rate_says_khz_even_though_its_label_ends_in_a_range(tmp_path: Path):
    """`S prompt green (kHz) | 0-2048` carries both in-band conventions at once.

    The bar separates a micro-time *range*, not a unit, and the unit is in the
    bracket to its left -- so a reader that stops at the bar, or that tries the
    end-anchored suffix on the whole label, finds nothing on a column that
    plainly says kHz.
    """
    import shutil

    raw = tmp_path / "m.ptu"
    shutil.copy(PTU, raw)
    label = "S prompt green (kHz) | 0-2048"
    write_burst_artifact(
        raw,
        pd.DataFrame({label: np.linspace(1.0, 4.0, 4)}),
        name="bursts", artifact_kind="burst_table",
        operation_type="burst_selection", row_grain="burst", derived_from=(),
    )
    assert _column_units(raw)[label] == "kilohertz"


def test_a_writer_can_name_the_estimator_that_produced_its_table(tmp_path: Path):
    """`operation_type` is the coarse join key; `algorithm` is which estimator.

    Every per-burst lifetime is `burst_lifetime_fitting`, which is what lets a
    reader find them all -- and is exactly wrong for the reader who must not
    pool an MLE lifetime with a phasor one. The two are recorded separately so
    neither question costs the other.
    """
    import shutil

    from chisurf.core.fio.pto import Measurement

    raw = tmp_path / "m.ptu"
    shutil.copy(PTU, raw)
    write_burst_artifact(
        raw, pd.DataFrame({"Tau (green)": np.linspace(1.0, 4.0, 5)}),
        name="mle", artifact_kind="burst_table",
        operation_type="burst_lifetime_fitting", row_grain="burst",
        algorithm="mle", derived_from=(),
    )
    with Measurement.open(container_for(raw), writable=False) as m:
        obj = [o for o in m.artifacts() if o.name == "mle"][0]
        assert m.tag(obj.uid, "_mmfdb_operation.operation_type") == "burst_lifetime_fitting"
        assert m.tag(obj.uid, "_mmfdb_operation.algorithm") == "mle"


def test_an_invented_estimator_is_refused(tmp_path: Path):
    """The algorithm is a dictionary term like every other. Absent is allowed --
    it means *unrecorded* -- but wrong is not."""
    import shutil

    from chisurf.core.fio.pto import PtoMfdbError

    raw = tmp_path / "m.ptu"
    shutil.copy(PTU, raw)
    with pytest.raises(PtoMfdbError, match="not a value of"):
        write_burst_artifact(
            raw, pd.DataFrame({"x": [1.0, 2.0]}),
            name="bursts", artifact_kind="burst_table",
            operation_type="burst_lifetime_fitting", row_grain="burst",
            algorithm="vibes", derived_from=(),
        )


def test_every_writer_that_knows_its_estimator_records_it(tmp_path: Path):
    """The mapping tables, checked against the vocabulary rather than by eye.

    Three writers know which method they ran and can say so: the burst search
    (from `used_filter`), the IRF extraction (from `irf_model`) and burst
    fusion. Each maps its own internal name to an `_mmfdb_operation.algorithm`
    term, and a mapping that names a term mmfdb does not declare would be
    caught only at write time on a real run -- which is too late.
    """
    from chisurf.core.fio.pto import _terms, _ALGORITHM
    from chisurf.plugins.burst.burst_mle_analysis.core.export import _IRF_ALGORITHM
    from chisurf.plugins.burst.burst_selection.api.selection import _FILTER_ALGORITHM

    allowed = _terms(_ALGORITHM)
    assert allowed, "mmfdb declares no algorithm enumeration"

    invented = sorted(
        {v for v in _IRF_ALGORITHM.values() if v not in allowed}
        | {v for v in _FILTER_ALGORITHM.values() if v not in allowed}
        | ({"recurrence_probability"} - allowed)
        | ({"mle"} - allowed)
    )
    assert not invented, (
        f"these writers map to terms mmfdb does not declare: {invented}. "
        "Add them to mmfdb rather than to the mapping."
    )


@pytest.mark.parametrize(
    "mode, extra, expected",
    [
        ("COUNT_RATE", {}, "sliding_window"),
        ("BURST", {}, "sliding_window"),
        ("BOCPD", {}, "bocpd"),
        ("KALMAN", {}, "kalman"),
        ("CUSUM", {}, "cusum_sprt"),
        ("TTTRLIB", {"algorithm": "maxtree"}, "maxtree"),
    ],
)
def test_the_search_that_ran_reaches_the_container(tmp_path: Path, mode, extra, expected):
    """End to end: `used_filter` -> the tag a reader gets out.

    The mapping table being right is not the same as it being *reached*: the
    term crosses three functions (`selection` -> `io.write_container` ->
    `pto.put_table`), any of which could drop it silently, and the settings
    hash would still differ so nothing else would notice.

    `TTTRLIB` is the case worth spelling out. Its settings carry an
    `algorithm` field that holds `"maxtree"` whether or not that search ran, so
    reading it unconditionally would stamp every container with a method it
    did not use -- it is read only when `used_filter` says that mode is the one
    that ran.
    """
    from chisurf.plugins.burst.burst_selection.api.selection import _selection_algorithm
    from chisurf.plugins.burst.burst_selection.api.io import write_container
    from chisurf.plugins.burst.burst_selection.api.models import BurstFilterMode

    settings = SimpleNamespace(
        used_filter=BurstFilterMode[mode],
        tttrlib_search=SimpleNamespace(algorithm=extra.get("algorithm", "maxtree")),
    )
    assert _selection_algorithm(settings) == expected

    source = tmp_path / "m000.ptu"
    source.write_bytes(b"")
    out = write_container(
        source,
        {"First Photon": np.array([0, 9]), "Last Photon": np.array([4, 14])},
        parameters={"mode": mode},
        algorithm=_selection_algorithm(settings),
        run="a_run",
    )
    from chisurf.core.fio.pto import Measurement

    with Measurement.open(out, writable=False) as m:
        tagged = [o.name for o in m.artifacts()
                  if m.tag(o.uid, "_mmfdb_operation.algorithm") == expected]
    assert tagged, (
        f"{mode} ran a {expected} search and the container does not say so; "
        "the term is dropped somewhere between selection and put_table."
    )


def test_an_unmapped_search_records_nothing_rather_than_a_guess(tmp_path: Path):
    """The rule the mapping exists to keep: absent means unrecorded.

    A mode this table does not cover -- one added later, or one whose method
    has no honest mmfdb term -- must produce no tag at all. Falling back to the
    most common search would make a container assert something nobody checked,
    and a wrong provenance is worse than a missing one because it is believed.
    """
    from chisurf.plugins.burst.burst_selection.api.selection import _selection_algorithm

    assert _selection_algorithm(SimpleNamespace(used_filter="some_new_mode")) == ""
    assert _selection_algorithm(SimpleNamespace()) == ""


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


# -- several analyses, one file ---------------------------------------------------


def test_three_analyses_land_in_one_container(measurement: Path, tmp_path: Path):
    """What the whole exercise is for. The legacy layout put each of these in
    its own `…4` directory beside a `.bur`, related by filename, with a
    settings JSON inside each that the readers then skipped on purpose."""
    from chisurf.plugins.burst.burst_2cde.core.computation import (
        column_for_variant,
        write_2cde_container,
    )
    from chisurf.plugins.burst.burst_bva.core.computation import write_bva_container

    source = str(measurement)
    column = column_for_variant("fret")
    write_2cde_container(
        pd.DataFrame({"First File": [source] * 20, column: np.linspace(0, 1, 20)}),
        "fret",
        parameters={"tau": 50},
    )
    write_bva_container(
        pd.DataFrame(
            {
                "First File": [source] * 20,
                "Proximity Ratio Mean": np.linspace(0, 1, 20),
                "Proximity Ratio Std": np.linspace(0, 0.1, 20),
            }
        ),
        parameters={"window": 5},
    )

    with Measurement.open(container_for(measurement)) as m:
        names = [o.name for o in m.artifacts()]
        assert {"bursts", "2cde fret", "bva"} <= set(names)
        for name, op in (
            ("2cde fret", "burst_2cde"),
            ("bva", "burst_variance_analysis"),
        ):
            uid = m._resolve(name)
            assert m.tag(uid, "_mmfdb_operation.operation_type") == op
            assert m.parents(uid) == [m._resolve("bursts")]
            assert m.tag(uid, "_mmfdb_artifact.row_grain") == "burst"
        assert m.verify() == []

    # and nothing beside the measurement
    assert sorted(p.suffix for p in measurement.parent.iterdir()) == [".pto", ".ptu"]


def test_the_two_2cde_variants_do_not_overwrite_each_other(measurement: Path):
    """The variant is part of the run's settings, so computing ALEX after FRET
    adds a result rather than replacing one -- which a single `2c4/<stem>.2c4`
    could not express at all."""
    from chisurf.plugins.burst.burst_2cde.core.computation import (
        column_for_variant,
        write_2cde_container,
    )

    source = str(measurement)
    for variant in ("fret", "alex"):
        write_2cde_container(
            pd.DataFrame(
                {
                    "First File": [source] * 20,
                    column_for_variant(variant): np.linspace(0, 1, 20),
                }
            ),
            variant,
        )
    with Measurement.open(container_for(measurement)) as m:
        names = [o.name for o in m.artifacts()]
        assert "2cde fret" in names and "2cde alex" in names


def test_h2mm_writes_bursts_and_dwells_at_their_own_grains(measurement: Path):
    """The analysis the companion format could not hold. Its own docstring says
    why: h2mm_bursts.csv is indexed by a compacted burst number, so "one dropped
    burst shifts every later row" and it cannot be joined back at all."""
    from chisurf.plugins.burst.burst_h2mm.core.export import write_h2mm_container

    bursts = pd.DataFrame({"H2MM State": np.tile([0, 1], 10)})
    dwells = pd.DataFrame(
        {
            "Dwell": np.arange(30),
            "Burst": np.repeat(np.arange(10), 3),   # compacted: only 10 of 20
            "State": np.tile([0, 1, 0], 10),
            "Dwell Time (ms)": np.linspace(0.1, 3.0, 30),
            "FRET efficiency": np.linspace(0, 1, 30),
        }
    )
    write_h2mm_container(measurement, bursts, dwells, parameters={"states": 2})

    with Measurement.open(container_for(measurement)) as m:
        dwell_uid = m._resolve("h2mm dwells")
        assert m.tag(dwell_uid, "_mmfdb_artifact.row_grain") == "dwell"
        assert m.tag(dwell_uid, "_mmfdb_edge.source_row_column") == "Burst"
        assert m.parents(dwell_uid) == [m._resolve("h2mm")]
        assert row_count(m.get_store("h2mm dwells")) == 30
        # A compacted burst index is fine now: the join is declared, not counted.
        assert row_count(m.get_store("h2mm")) == 20
        assert m.verify() == []
