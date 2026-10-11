"""``csc accurate-fret --simulate`` calibrates the table it has just written.

The simulation writes its declared truth as a ``#`` preamble above the header,
and the burst-table reader rejected any file with a preamble ("no numeric columns
found"), so the guide's "try it without data" command crashed every time.
"""

from __future__ import annotations

import numpy as np
from click.testing import CliRunner

from chisurf.core.fluorescence.burst.table import read_burst_table
from chisurf.plugins.burst.accurate_fret.cli.main import cli


def test_a_comment_preamble_is_skipped(tmp_path):
    path = tmp_path / "t.csv"
    path.write_text("# made by a simulation\n#   gamma=0.65\ni_dd,i_da,i_aa\n1,2,3\n4,5,6\n")
    columns = read_burst_table(path)
    assert sorted(columns) == ["i_aa", "i_da", "i_dd"]
    np.testing.assert_array_equal(columns["i_da"], [2.0, 5.0])


def test_the_simulated_table_is_calibrated(tmp_path):
    out = tmp_path / "demo_bursts.csv"
    result = CliRunner().invoke(
        cli, ["--simulate", str(out), "--simulate-photons", "120000"], catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert "gamma" in result.output and out.is_file()
