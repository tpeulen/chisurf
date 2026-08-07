"""What goes into a container is what comes out of it.

Asked directly, because it cannot be answered by reading a container: if the
decoder were wrong, every viewer built on it would show the same wrong numbers
and agree with itself. A real session produced a burst table with
``Duration (ms) = 0.0`` beside 1951 photons and a mean macro time ten million
times longer than the measurement, and "is the extractor mangling it?" was a
fair question that the container's own reader could not settle.

It is settled by writing values chosen to break a decoder — every dtype the
tables use, text beside numbers, the extremes of the float range, values that
survive a float32 round-trip and values that do not — and demanding them back
unchanged. A store read back through the same API it was written through is
exactly the claim a viewer rests on.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import column_names, row_count, store_from_arrays
from chisurf.core.fio.pto import Measurement

DATA = (
    Path(__file__).resolve().parents[2]
    / "chisurf" / "plugins" / "burst" / "burst_selection"
    / "tests" / "data" / "bh_spc132_sm_dna"
)
SPC = DATA / "m000.spc"

pytestmark = pytest.mark.skipif(not SPC.exists(), reason="no BH SPC test data")


def _adversarial_table():
    """A table whose values are chosen to expose a lossy round-trip."""
    return store_from_arrays(
        {
            # Photon indices: int64, past the float64 exact-integer range would
            # be absurd, but past float32's is not — 16_777_217 is the first
            # integer a float32 cannot hold.
            "First Photon": np.array([0, 72, 16_777_217, 2**40], dtype=np.int64),
            "Last Photon": np.array([0, 2022, 16_777_219, 2**40 + 7], dtype=np.int64),
            # Durations and times: the values that actually went wrong, plus a
            # denormal and a very large one.
            "Duration (ms)": np.array(
                [0.0, 11986.712985600001, 5e-324, 1.7976931348623157e308]
            ),
            "Mean Macro Time (ms)": np.array(
                [7136629033695.356, 26747632640574.285, -0.0, 0.1 + 0.2]
            ),
            "Number of Photons": np.array([0, 1951, 1, 2_000_000_000], dtype=np.int64),
            # Text beside numbers, including one that looks numeric and one
            # with the separator the format uses.
            "First File": np.array(["m000.spc", "0", "a\tb", "ü"], dtype=object),
        }
    )


def test_a_table_comes_back_out_exactly_as_it_went_in(tmp_path: Path):
    from chisurf.plugins.core.tttr_to_pto import api as pto_api

    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    container = pto_api.convert(source)

    written = _adversarial_table()
    with Measurement.open(container, writable=True) as m:
        m.put_table(
            "probe",
            written,
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"probe": True},
        )

    with Measurement.open(container, writable=False) as m:
        read = m.get_store("probe")

    assert column_names(read) == column_names(written)
    assert row_count(read) == row_count(written)
    for name in column_names(written):
        want, got = np.asarray(written[name]), np.asarray(read[name])
        if want.dtype.kind in "fiu":
            # Exact, not approximate: a decoder that rounds is the failure this
            # is looking for, and every value here is representable.
            np.testing.assert_array_equal(got.astype(want.dtype), want, err_msg=name)
        else:
            assert [str(v) for v in got] == [str(v) for v in want], name


def test_the_values_that_went_wrong_survive_the_round_trip(tmp_path: Path):
    """The specific numbers from the report, isolated.

    If the extractor were responsible, these are what it would have mangled.
    """
    from chisurf.plugins.core.tttr_to_pto import api as pto_api

    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    container = pto_api.convert(source)

    suspicious = np.array([7136629033695.356, 13013676910103.46,
                           22770159362442.85, 26747632640574.285])
    with Measurement.open(container, writable=True) as m:
        m.put_table(
            "probe",
            store_from_arrays({"Mean Macro Time (ms)": suspicious}),
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
        )
    with Measurement.open(container, writable=False) as m:
        got = np.asarray(m.get_store("probe")["Mean Macro Time (ms)"], dtype=float)

    np.testing.assert_array_equal(got, suspicious)


def test_the_photon_stream_reads_back_the_same_from_a_container(tmp_path: Path):
    """The other half a viewer rests on: the photons, not just the tables."""
    import chisurf.core.fio.staging as staging
    from chisurf.plugins.core.tttr_to_pto import api as pto_api

    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    direct = staging.open_tttr(str(source))
    container = pto_api.convert(source)
    through = staging.open_tttr(str(container))

    assert len(through) == len(direct)
    np.testing.assert_array_equal(
        np.asarray(through.macro_times), np.asarray(direct.macro_times)
    )
    np.testing.assert_array_equal(
        np.asarray(through.micro_times), np.asarray(direct.micro_times)
    )
    np.testing.assert_array_equal(
        np.asarray(through.routing_channels), np.asarray(direct.routing_channels)
    )
    assert through.header.macro_time_resolution == direct.header.macro_time_resolution


def test_a_merged_container_reads_back_as_the_files_concatenated(tmp_path: Path):
    """Eleven files packed into one is one stream, in file order, monotone.

    The report's table looked like a broken time axis, so this is the check
    that the axis is not broken: each file's photons follow the previous
    file's, and no macro time goes backwards at a boundary.
    """
    import chisurf.core.fio.staging as staging
    from chisurf.plugins.core.tttr_to_pto import api as pto_api

    sources = sorted(DATA.glob("m00*.spc"))
    assert len(sources) >= 3
    for src in sources:
        (tmp_path / src.name).write_bytes(src.read_bytes())
    container = pto_api.convert(sorted(tmp_path.glob("*.spc")))

    merged = staging.open_tttr(str(container))
    parts = [staging.open_tttr(str(tmp_path / s.name)) for s in sources]

    assert len(merged) == sum(len(p) for p in parts)
    macro = np.asarray(merged.macro_times, dtype=np.int64)
    assert np.all(np.diff(macro) >= 0), "a macro time went backwards at a boundary"

    resolution = merged.header.macro_time_resolution
    span = (macro.max() - macro.min()) * resolution
    longest = max(
        float(np.ptp(np.asarray(p.macro_times, dtype=np.int64))) * resolution
        for p in parts
    )
    assert span > longest, "the merged span is no longer than one file's"
