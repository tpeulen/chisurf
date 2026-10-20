"""``csc quest analyse``: the quenching analysis from the command line.

The output formats run in process on the analytic stand-in site model of
``test_inference_graph_fit.py`` (seconds). One run is the real thing: a subprocess of ``csc``
on the shipped MalE example, stage B with a tiny fit, which reads (or builds once) the 18
Atto655 site tables of the default cache. Its cost is loading those tables (``Site``'s row
de-duplication, ~2 s each on an idle machine), not the fit.
"""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from chisurf.plugins.quenching_estimator.cli.cli import cli
from chisurf.plugins.quenching_estimator.core import runs
from chisurf.plugins.quenching_estimator.core.inference import columns, site_model
from chisurf.plugins.quenching_estimator.core.inference import graph_fit as gf

from .test_inference_graph_fit import FakeLibrary

REPO = Path(__file__).resolve().parents[4]
TINY = ["--quick", "--set", "n_starts=1", "--set", "search_maxiter=2", "--set",
        "joint_max_nfev=1", "--no-profile", "--workers", "1"]
ESTIMATE_COLUMNS = [c["column"] for c in columns.columns("fit_estimates", gf.RESULT_COLUMNS)]


@pytest.fixture
def fake_sites(tmp_path, monkeypatch):
    monkeypatch.setattr(site_model, "SiteLibrary", lambda **kwargs: FakeLibrary())
    monkeypatch.setenv(runs.QUEST_RUNS_DIR_ENV, str(tmp_path / "runs"))


def _invoke(args):
    result = CliRunner().invoke(cli, ["analyse", "-q", *args], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    return result.output


def test_table_output_and_the_declared_files(fake_sites, tmp_path):
    out = tmp_path / "out"
    text = _invoke(["--stage", "B", *TINY, "-o", str(out)])
    assert "## Stage B" in text
    assert "parameter" in text and "scale" in text
    record = json.loads((out / "run.json").read_text())
    assert record["kind"] == "analysis" and record["stages"] == ["B"]
    assert record["fit_overrides"] == {"n_starts": 1, "search_maxiter": 2, "joint_max_nfev": 1}
    for table in record["tables"]:
        assert (out / f"{table}.csv").exists()


def test_json_output_is_the_rpc_payload(fake_sites):
    payload = json.loads(_invoke(["--stage", "B", *TINY, "--format", "json", "--no-save"]))
    assert list(payload["stages"]) == ["B"]
    assert payload["run"]["directory"] is None and payload["run"]["files"] == []
    rows = payload["stages"]["B"]["tables"]["estimates"]
    assert list(rows[0]) == ESTIMATE_COLUMNS
    assert "plots" in payload["stages"]["B"]


def test_csv_output_is_the_declared_table(fake_sites, tmp_path):
    text = _invoke(["--stage", "B", "--stage", "naive_h2o", *TINY, "--format", "csv",
                    "--table", "B.estimates", "--project-dir", str(tmp_path)])
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == ESTIMATE_COLUMNS and len(rows) > 5
    (run,) = runs.list_runs(tmp_path)["runs"]
    assert run["kind"] == "analysis" and run["stages"] == ["B", "naive_h2o"]
    # stdout is byte for byte the file the run wrote
    stored = runs.read_run_table(run["job_id"], "B.estimates", tmp_path)
    assert text == stored.read_text()


def test_a_nested_fit_setting_edits_only_its_key(fake_sites):
    payload = json.loads(_invoke(["--stage", "B", *TINY, "--set",
                                  "profile_likelihood.points=3", "--format", "json",
                                  "--no-save"]))
    assert payload["stages"]["B"]


@pytest.mark.parametrize("args, needle", [
    (["--stage", "Z"], "declared"),
    (["--preset", "slow"], "declared"),
    (["--set", "no_such=1"], "not a declared fit setting"),
    (["--set", "n_starts"], "KEY=VALUE"),
])
def test_bad_arguments_are_usage_errors(fake_sites, args, needle):
    result = CliRunner().invoke(cli, ["analyse", "-q", *args])
    assert result.exit_code == 2 and needle in result.output


def test_csc_quest_analyse_on_the_shipped_male_data(tmp_path):
    """The real command on the real data: stage B, a one-search fit, the declared tables."""
    out = tmp_path / "out"
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen",
               QUEST_RUNS_DIR=str(tmp_path / "runs"))
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO / p) for p in ("modules/mmfdb/src", "modules/chinet",
                                 "modules/imp-tricks/src", ".")]
        + [env.get("PYTHONPATH", "")])
    proc = subprocess.run(
        [sys.executable, "-c", "import sys; from chisurf.core.cli import cli; sys.exit(cli())",
         "quest", "analyse", "--stage", "B", *TINY, "-o", str(out), "--format", "json"],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=1800,
    )
    assert proc.returncode == 0, proc.stderr[-4000:]
    payload = json.loads(proc.stdout)
    stage = payload["stages"]["B"]
    assert stage["title"].startswith("Stage B")
    # Atto655 in D2O: 18 lifetimes (9 sites, APO and HOLO), a 19-parameter graph, 8 slopes
    assert len(stage["tables"]["predictions"]) == 18
    assert payload["graphs"]["heavy_water"]["n_parameters"] == 19
    assert payload["graphs"]["heavy_water"]["n_slopes"] == 8
    assert "[100%] done" in proc.stderr
    record = json.loads((out / "run.json").read_text())
    assert record["kind"] == "analysis"
    with open(out / "B.estimates.csv", newline="") as fh:
        assert next(csv.reader(fh)) == ESTIMATE_COLUMNS
    for table in record["tables"]:
        assert (out / f"{table}.csv").stat().st_size > 0
