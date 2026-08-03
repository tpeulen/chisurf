"""The headless CLI must run every scheme and report the volume expansion."""

import json

import pytest
from click.testing import CliRunner

from chisurf.plugins.calculator.fcs_saturation_calc.cli.main import cli


@pytest.mark.parametrize("scheme", ["two-state", "triplet", "isomerisation"])
def test_cli_runs_each_scheme(scheme):
    result = CliRunner().invoke(cli, ["--scheme", scheme, "--power", "2.0", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["scheme"] == scheme
    assert payload["v_eff_over_v0"] >= 1.0
    assert 0.0 < payload["amplitude_ratio"]


def test_cli_zero_power_leaves_the_volume_unexpanded():
    result = CliRunner().invoke(cli, ["--power", "0", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["v_eff_over_v0"] == 1.0
    assert payload["amplitude_ratio"] == pytest.approx(1.0)


def test_cli_writes_csv(tmp_path):
    out = tmp_path / "curves.csv"
    result = CliRunner().invoke(cli, ["--out-csv", str(out)])
    assert result.exit_code == 0, result.output
    lines = out.read_text().strip().splitlines()
    assert lines[0] == "tau_ms,g_unperturbed,g_saturated"
    assert len(lines) == 301


def test_cli_reports_an_unknown_dye_instead_of_guessing():
    result = CliRunner().invoke(cli, ["--dye", "NotADyeAtAll", "--json"])
    assert result.exit_code != 0
    assert "no absorption spectrum" in result.output
