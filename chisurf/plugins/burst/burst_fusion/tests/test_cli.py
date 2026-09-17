"""Headless CLI path of the burst-fusion step.

Every feature needs a way to run without the GUI; these tests are that path's
guardrail — ``csc fusion curve`` must report without writing, and
``csc fusion fuse`` must produce a folder.
"""

from __future__ import annotations

import pathlib
import shutil

import pytest
from click.testing import CliRunner

from chisurf.plugins.burst.burst_fusion.cli.main import cli

DATA = (
    pathlib.Path(__file__).resolve().parents[2]
    / "burst_selection"
    / "tests"
    / "data"
    / "bh_spc132_sm_dna"
)
ANALYSIS = "burstwise_All 0.1000#15"


@pytest.fixture
def folder(tmp_path):
    """Return a private copy of the burst analysis, beside its raw measurements."""
    if not DATA.is_dir():
        pytest.skip("burst-selection test data not available")
    target = tmp_path / "data"
    shutil.copytree(DATA, target)
    return target / ANALYSIS


def test_curve_reports_without_writing(folder):
    before = sorted(p.name for p in folder.parent.iterdir())
    result = CliRunner().invoke(cli, ["curve", str(folder), "--threshold", "0.5"])

    assert result.exit_code == 0, result.output
    assert "P_same >= 0.50" in result.output
    assert "Gaps fused" in result.output
    assert "capped by --max-gap" in result.output
    assert "Proximity ratio" in result.output
    assert sorted(p.name for p in folder.parent.iterdir()) == before


def test_curve_emits_json_when_asked(folder):
    import json

    result = CliRunner().invoke(cli, ["curve", str(folder), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["n_bursts_after"] < payload["n_bursts_before"]


def test_fuse_writes_a_folder(folder, tmp_path):
    # The fixture predates the reading manifest, so the detector definition is
    # given explicitly — the path a scripted run on an archived folder takes.
    import json

    definition = tmp_path / "channels.json"
    definition.write_text(
        json.dumps(
            {
                "detectors": {
                    "green": {"chs": [0, 8], "micro_time_ranges": [[0, 2048]]},
                    "red": {"chs": [1, 9], "micro_time_ranges": [[0, 2048]]},
                },
                "windows": {"prompt": [0, 2048]},
            }
        )
    )
    out = tmp_path / "fused"
    result = CliRunner().invoke(
        cli,
        [
            "fuse",
            str(folder),
            "--threshold",
            "0.5",
            "--max-gap",
            "2",
            "--detectors",
            str(definition),
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "gaps <= 2.000 ms" in result.output
    assert (out / "bi4_bur" / "m000.bur").is_file()
    assert (out / "Info" / "fusion.json").is_file()


def test_threshold_one_leaves_the_burst_count_alone(folder):
    result = CliRunner().invoke(cli, ["curve", str(folder), "--threshold", "1.0"])
    assert result.exit_code == 0, result.output
    assert "0 fused" in result.output
