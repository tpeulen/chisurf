"""The H2MM tables are openable by ndX, checked with ndX's own readers.

``export.py`` claims its tables are "openable directly in ndxplorer (ndX)". That
claim is only worth having if something checks it: the tables are plain CSV/HDF5,
so they *load* whatever is in them, and the ways they can be wrong are quiet —
one non-numeric column and ndX drops it, a missing ``Mean Macro Time (s)`` and
there is no time axis to select. These read every written table back through
ndX's reader rather than through pandas, so a change to either side that breaks
the hand-off fails here.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("tttrlib")
# ndX is a local source tree on PYTHONPATH, not an installed dependency.
pytest.importorskip("ndxplorer", reason="ndxplorer not on the path")

from ndxplorer.io.reader import read_csv, read_mfd_hdf5  # noqa: E402

from .test_export import _dataset_via_tttrlib  # noqa: E402

#: The column ndX renames burst macro times to, and auto-selects as the axis.
NDX_TIME_AXIS = "Mean Macro Time (s)"


def _frame(source):
    """The DataFrame behind an ndX DataSource, whatever it is called."""
    return getattr(source, "data", getattr(source, "df", source))


@pytest.fixture(scope="module")
def written(tmp_path_factory):
    """Every table a real H2MM run writes, on disk."""
    from chisurf.plugins.burst.burst_h2mm.api.models import H2mmSettings
    from chisurf.plugins.burst.burst_h2mm.backend.services import (
        H2mmAnalysisBundle,
        _result_from_analysis,
        write_result_tables,
    )
    from chisurf.plugins.burst.burst_h2mm.core.analysis import analyze

    data, meta = _dataset_via_tttrlib()
    ana = analyze(data, state_counts=(2,), base_time_s=1e-6, n_restarts=1, max_iter=150)
    settings = H2mmSettings()
    result = _result_from_analysis(ana, settings)
    bundle = H2mmAnalysisBundle(ana, data, settings)
    bundle.meta = meta
    bundle.micro_time_ns = 0.032

    out = tmp_path_factory.mktemp("h2mm")
    write_result_tables(result, bundle, out)
    return out, result


def _photon_table(out):
    """The photon table, whichever form it took.

    ``write_result_tables`` writes HDF5 **or** CSV, not both: the CSV is the
    fallback for an environment without pytables. Any consumer therefore has to
    look for both — which is exactly what ``burst_states.read_photon_table`` does.
    """
    h5, csv = out / "h2mm_photons.h5", out / "h2mm_photons.csv"
    if h5.is_file():
        return h5, read_mfd_hdf5
    assert csv.is_file(), "neither photon table was written"
    return csv, lambda paths: read_csv(paths)


@pytest.mark.parametrize(
    "name",
    ["h2mm_bursts.csv", "h2mm_dwells.csv", "h2mm_state_decays.csv"],
)
def test_ndx_opens_every_written_csv(written, name):
    """ndX's own CSV reader opens the table, with every column intact."""
    out, _ = written
    path = out / name
    assert path.is_file(), f"{name} was not written"

    df = _frame(read_csv([str(path)]))
    assert len(df) > 0, f"{name} opened empty"
    assert len(df.columns) > 1, f"{name} did not split into columns"

    # Every column numeric: ndX silently drops the ones that are not, so a stray
    # string column would lose data on import without any error.
    non_numeric = [c for c in df.columns if not np.issubdtype(df[c].dtype, np.number)]
    assert not non_numeric, f"{name} has non-numeric column(s): {non_numeric}"


@pytest.mark.parametrize("name", ["h2mm_bursts.csv", "h2mm_dwells.csv"])
def test_the_event_tables_carry_the_axis_ndx_selects(written, name):
    """One row per burst/dwell means a time axis, under ndX's own name."""
    out, _ = written
    df = _frame(read_csv([str(out / name)]))
    assert NDX_TIME_AXIS in df.columns, (
        f"{name} has no {NDX_TIME_AXIS!r} — ndX would open it with no axis to plot"
    )
    t = df[NDX_TIME_AXIS].to_numpy(dtype=float)
    assert np.isfinite(t).all() and (t >= 0).all()


def test_the_decay_table_is_a_histogram_not_an_event_table(written):
    """`h2mm_state_decays` is binned counts, so it carries bins rather than a clock.

    Stated so the missing time axis reads as the design it is, not as an
    oversight to "fix" by inventing one.
    """
    out, _ = written
    df = _frame(read_csv([str(out / "h2mm_state_decays.csv")]))
    assert NDX_TIME_AXIS not in df.columns
    assert {"State", "Stream", "Channel", "Micro Time", "Counts"} <= set(df.columns)
    assert (df["Counts"].to_numpy() >= 0).all()
    # One row per (state, stream, channel, bin) — the key the merge is done on.
    assert len(df.drop_duplicates(["State", "Stream", "Channel", "Micro Time"])) == len(df)


def test_ndx_opens_the_photon_table_in_whichever_form_it_took(written):
    """HDF5 when pytables is there, CSV when it is not — ndX opens either."""
    out, _ = written
    path, reader = _photon_table(out)
    df = _frame(reader([str(path)]))
    assert len(df) > 0
    assert NDX_TIME_AXIS in df.columns
    non_numeric = [c for c in df.columns if not np.issubdtype(df[c].dtype, np.number)]
    assert not non_numeric, non_numeric
    assert {"State", "Channel", "Stream", "Burst"} <= set(df.columns), (
        "the per-photon state assignment is what makes this table worth writing"
    )


def test_every_written_path_is_reported(written):
    """``output_paths`` is how a caller finds these files; it must name them all."""
    out, result = written
    reported = {str(p) for p in result.output_paths.values()}
    for name in ("h2mm_bursts.csv", "h2mm_dwells.csv", "h2mm_state_decays.csv"):
        assert str(out / name) in reported, f"{name} written but not reported"
    photons, _ = _photon_table(out)
    assert str(photons) in reported, "the photon table is written but not reported"


def _write_with(tmp_path, **flags):
    """Write the tables with the given format flags, return the output dir."""
    from chisurf.plugins.burst.burst_h2mm.api.models import H2mmSettings
    from chisurf.plugins.burst.burst_h2mm.backend.services import (
        H2mmAnalysisBundle,
        _result_from_analysis,
        write_result_tables,
    )
    from chisurf.plugins.burst.burst_h2mm.core.analysis import analyze

    data, meta = _dataset_via_tttrlib(n_bursts=12, burst_len=40)
    ana = analyze(data, state_counts=(2,), base_time_s=1e-6, n_restarts=1, max_iter=50)
    settings = H2mmSettings(**flags)
    result = _result_from_analysis(ana, settings)
    bundle = H2mmAnalysisBundle(ana, data, settings)
    bundle.meta = meta
    bundle.micro_time_ns = 0.032
    write_result_tables(result, bundle, tmp_path)
    return result


def test_both_photon_formats_can_be_written(tmp_path):
    """HDF5 and CSV are independent choices, not a fallback chain.

    The formats used to be try/except: HDF5, and CSV *only* if that raised. So a
    folder could never carry both, and which one you got depended on whether
    pytables happened to be importable.
    """
    result = _write_with(tmp_path, photon_hdf5=True, photon_csv=True)
    assert (tmp_path / "h2mm_photons.csv").is_file()
    assert "photons_csv" in result.output_paths
    if (tmp_path / "h2mm_photons.h5").is_file():
        assert "photons_hdf5" in result.output_paths


def test_csv_only_writes_no_hdf5(tmp_path):
    result = _write_with(tmp_path, photon_hdf5=False, photon_csv=True)
    assert (tmp_path / "h2mm_photons.csv").is_file()
    assert not (tmp_path / "h2mm_photons.h5").exists()
    assert "photons_hdf5" not in result.output_paths


def test_asking_for_neither_still_writes_one(tmp_path):
    """The state assignment must never end up nowhere: it is what step 7 reads."""
    _write_with(tmp_path, photon_hdf5=False, photon_csv=False)
    assert (tmp_path / "h2mm_photons.h5").is_file() or (
        tmp_path / "h2mm_photons.csv"
    ).is_file()


def test_the_burst_companions_line_up_with_the_bur_rows(tmp_path):
    """Per-measurement `.bh4` files, in the shape a burst folder already speaks.

    One table for the whole folder cannot be joined back: H2MM numbers only the
    bursts it kept, so one dropped burst shifts every later row. These are one
    file per measurement, one row per burst *of that measurement*, so they line
    up positionally exactly as `bv4`/`2c4` do.
    """
    import numpy as np
    import pandas as pd

    from chisurf.plugins.burst.burst_h2mm.core.export import (
        H2MM_COMPANION,
        H2MM_COMPANION_COLUMNS,
        write_burst_companions,
    )

    class _Data:
        burst_offsets = np.array([0, 3, 6])

    # Four bursts in the table; H2MM kept rows 0 and 2 (1 and 3 were too short),
    # and the padding row the .bur zero-interleaving leaves behind reads as "0".
    burst_df = pd.DataFrame({"First File": ["m000.spc", "m000.spc", "m000.spc", "0"]})
    path = np.array([0, 0, 1, 1, 1, 1])
    written = write_burst_companions(
        burst_df, [0, 2], _Data(), path, np.array([0.2, 0.8]), tmp_path
    )

    assert [p.name for p in written] == [f"m000.{H2MM_COMPANION}"], (
        "the zero padding row must not become a companion file"
    )
    text = written[0].read_text().splitlines()
    assert text[0].split("\t")[: len(H2MM_COMPANION_COLUMNS)] == H2MM_COMPANION_COLUMNS
    body = np.loadtxt(written[0], skiprows=1, delimiter="\t")
    # 3 real bursts for this measurement → zero-interleaved 2*3+1 rows.
    assert body.shape == (7, len(H2MM_COMPANION_COLUMNS))
    data_rows = body[1::2]
    fitted = data_rows[:, H2MM_COMPANION_COLUMNS.index("H2MM Fitted")]
    assert fitted.tolist() == [1.0, 0.0, 1.0], (
        "an unfitted burst keeps its row rather than shifting the ones after it"
    )
    states = data_rows[:, H2MM_COMPANION_COLUMNS.index("H2MM State")]
    assert states[0] == 0.0 and states[2] == 1.0


def test_ndx_merges_the_companions_without_being_told_about_them(tmp_path):
    """ndX discovers any sibling `*4` folder — the companion needs no ndX config."""
    from ndxplorer.io.reader import _discover_burst_extra_endings

    from chisurf.plugins.burst.burst_h2mm.core.export import H2MM_COMPANION

    (tmp_path / "bi4_bur").mkdir()
    (tmp_path / H2MM_COMPANION).mkdir()
    assert H2MM_COMPANION in _discover_burst_extra_endings(tmp_path), (
        "a burst folder must load everything it holds, not only what is configured"
    )
    # …and the base burst directory is never mistaken for a companion.
    assert "bi4_bur" not in _discover_burst_extra_endings(tmp_path)
