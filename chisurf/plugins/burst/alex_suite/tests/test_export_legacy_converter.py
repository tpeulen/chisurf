"""The ALEX-Suite CSV converter command: the old export's only surface now that the pipeline is pto end to end.

The workflow has no export step any more (its analysis lands in the ``.pto`` container); a script or spreadsheet
built on the old five-file layout gets those files from ``csc alex-suite export-legacy`` — from a loose ``.bur``
table or straight from a container run, which is what the pipeline itself produces.
"""

from __future__ import annotations

import numpy as np
import pytest
from click.testing import CliRunner

from chisurf.plugins.burst.alex_suite.cli.main import cli


def _columns(n=120, e_true=0.45, seed=7, *, first_file=False):
    rng = np.random.default_rng(seed)
    total = rng.poisson(200, n).astype(float) + 20.0
    green = total * 0.5
    i_da = rng.binomial(green.astype(int), e_true).astype(float)
    cols = {
        "Number of Photons (green)": green - i_da,
        "Number of Photons (red)": i_da,
        "Number of Photons (yellow)": total - green,
        "Duration (ms)": np.full(n, 1.0),
    }
    if first_file:
        cols = {"First File": np.full(n, "m000.spc", dtype=object), **cols}
    return cols


@pytest.fixture
def bur_table(tmp_path):
    cols = _columns()
    path = tmp_path / "sample.bur"
    lines = ["\t".join(cols)]
    lines += ["\t".join(f"{v:.10g}" for v in row) for row in np.column_stack(list(cols.values()))[1:]]
    path.write_text("\n".join(lines) + "\n")
    return path


def test_the_converter_writes_the_old_files_from_a_bur_table(tmp_path, bur_table):
    result = CliRunner().invoke(
        cli, ["export-legacy", str(bur_table), str(tmp_path / "run"), "--sample", "dsDNA"]
    )
    assert result.exit_code == 0, result.output
    written = sorted(p.name for p in tmp_path.glob("run_*.csv"))
    assert written == [
        "run_hist_2D.csv",
        "run_hist_E.csv",
        "run_hist_S.csv",
        "run_meta.csv",
    ], written
    meta = (tmp_path / "run_meta.csv").read_text()
    assert "EXPERIMENTAL" in meta and "dsDNA" in meta


def test_the_histogram_command_has_no_export_option_any_more(tmp_path, bur_table):
    """The export flag left the pipeline command: the converter command is the way."""
    result = CliRunner().invoke(cli, ["histogram", str(bur_table), "--export", "run"])
    assert result.exit_code != 0
    assert "No such option" in result.output


def test_the_converter_reads_a_container_run(tmp_path):
    """The pipeline's own output (a ``.pto`` run) converts straight to the old files."""
    import pathlib

    from chisurf.core.datastore import store_from_rows
    from chisurf.plugins.burst.burst_selection.api.io import write_container

    source = (
        pathlib.Path(__file__).parents[3]
        / "burst"
        / "burst_selection"
        / "tests"
        / "data"
        / "bh_spc132_sm_dna"
        / "m000.spc"
    )
    cols = _columns(n=60, e_true=0.3, seed=3, first_file=True)
    rows = [dict(zip(cols, values)) for values in zip(*cols.values())]
    frame = store_from_rows(rows)
    container = write_container(
        source,
        frame,
        parameters={"probe": True},
        out_dir=tmp_path,
        run="sliding_window_All 0.1500#60",
    )
    run = f"{container}/sliding_window_All 0.1500#60"
    result = CliRunner().invoke(
        cli, ["export-legacy", run, str(tmp_path / "from_pto"), "--parts", "meta,hist_E"]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "from_pto_meta.csv").is_file()
    assert (tmp_path / "from_pto_hist_E.csv").is_file()
    assert not (tmp_path / "from_pto_hist_S.csv").exists()


def test_an_unknown_part_is_refused(tmp_path, bur_table):
    result = CliRunner().invoke(
        cli, ["export-legacy", str(bur_table), str(tmp_path / "run"), "--parts", "meta,nope"]
    )
    assert result.exit_code != 0
    assert "unknown part(s)" in result.output
