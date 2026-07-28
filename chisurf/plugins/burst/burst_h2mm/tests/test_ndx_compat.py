"""The H2MM tables are openable by ndXplorer, checked with ndX's own readers.

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
# ndXplorer is a local source tree on PYTHONPATH, not an installed dependency.
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
    look for both — which is exactly what ``state_mle.read_photon_table`` does.
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
