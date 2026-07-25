"""Plugin-level tests: table reading, column guessing, the run, CLI and RPC."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.fret.lines import static_fret_line
from chisurf.plugins.burst.accurate_fret import core as _core

GAMMA, ALPHA, BETA, DELTA = 0.65, 0.08, 1.4, 0.06
TAU_D0, R0 = 4.0, 52.0
LINE = static_fret_line(TAU_D0, r0=R0, sigma=6.0)


def _simulate(seed: int = 5, efficiencies=(0.3, 0.75), n: int = 900):
    """Two FRET populations plus donor-only and acceptor-only bursts."""
    rng = np.random.default_rng(seed)
    dd, da, aa, tau = [], [], [], []
    for e in efficiencies:
        photons = rng.poisson(400, n).astype(float)
        dd.append(rng.poisson((1 - e) * photons))
        aa.append(rng.poisson(BETA * GAMMA * photons))
        da.append(rng.poisson(
            GAMMA * e * photons + ALPHA * (1 - e) * photons + DELTA * BETA * GAMMA * photons
        ))
        tau.append(rng.normal(float(LINE.lifetime_at(e)), 0.12, n))
    photons = rng.poisson(400, 300).astype(float)
    dd.append(rng.poisson(photons))
    da.append(rng.poisson(ALPHA * photons))
    aa.append(rng.poisson(2.0, 300))
    tau.append(rng.normal(TAU_D0, 0.12, 300))
    photons = rng.poisson(400, 300).astype(float)
    dd.append(rng.poisson(2.0, 300))
    aa.append(rng.poisson(BETA * GAMMA * photons))
    da.append(rng.poisson(DELTA * BETA * GAMMA * photons))
    tau.append(np.full(300, np.nan))
    return (np.concatenate(dd).astype(float), np.concatenate(da).astype(float),
            np.concatenate(aa).astype(float), np.concatenate(tau))


@pytest.fixture()
def burst_table(tmp_path):
    """Write a burst table with ndXplorer-style column names."""
    i_dd, i_da, i_aa, tau = _simulate()
    path = tmp_path / "bursts.csv"
    header = ("Green Count Rate (KHz),Red Count Rate (KHz),"
              "S delayed yellow (kHz),Tau (green),Duration (ms)")
    data = np.column_stack([i_dd, i_da, i_aa, tau, np.full(i_dd.size, 1.0)])
    np.savetxt(path, data, delimiter=",", header=header, comments="", fmt="%.6g")
    return path


def test_read_and_guess_columns(burst_table):
    """A burst table is read and its channels recognised by their column names."""
    columns = _core.read_burst_table(burst_table)
    assert len(columns) == 5
    guess = _core.guess_columns(columns)
    assert guess["i_dd"] == "Green Count Rate (KHz)"
    assert guess["i_da"] == "Red Count Rate (KHz)"
    assert guess["i_aa"] == "S delayed yellow (kHz)"
    assert guess["tau_f"] == "Tau (green)"


def test_calibrate_recovers_the_factors():
    """The plugin-level entry point reproduces the known correction factors."""
    i_dd, i_da, i_aa, tau = _simulate()
    result = _core.calibrate(
        i_dd, i_da, i_aa, tau, donor_lifetime=TAU_D0, forster_radius=R0, n_bootstrap=10
    )
    assert result.factors["gamma"] == pytest.approx(GAMMA, rel=0.04)
    assert result.factors["alpha"] == pytest.approx(ALPHA, abs=0.006)
    assert result.factors["delta"] == pytest.approx(DELTA, abs=0.006)
    assert result.factors["beta"] == pytest.approx(BETA, rel=0.04)
    assert len(result.factor_rows()) == 5
    assert len(result.population_rows()) == 2
    assert result.line is not None and result.dynamic_line is not None


def test_export_csv_documents_the_calibration(tmp_path):
    """The export carries the per-burst values and the calibration in its header."""
    i_dd, i_da, i_aa, tau = _simulate()
    result = _core.calibrate(i_dd, i_da, i_aa, tau, donor_lifetime=TAU_D0, n_bootstrap=0)
    out = tmp_path / "accurate.csv"
    _core.export_csv(out, result)
    text = out.read_text()
    assert "# Automatic FRET calibration" in text
    assert "E,label,S,tau_f,R_DA" in text
    assert len(text.strip().splitlines()) > i_dd.size


def test_view_model_end_to_end(burst_table):
    """The view-model loads, maps, calibrates and produces the plot series."""
    from chisurf.plugins.burst.accurate_fret.gui.view_model import AccurateFretViewModel

    model = AccurateFretViewModel()
    events: list[str] = []
    model.add_observer(events.append)
    model.set_filename(str(burst_table))
    assert model.column_i_dd == "Green Count Rate (KHz)"
    assert model.column_tau_f == "Tau (green)"
    assert model.can_run() is None

    model.n_bootstrap = 0
    model.donor_lifetime = TAU_D0
    assert model.compute() is True
    assert "result" in events
    assert model.result.factors["gamma"] == pytest.approx(GAMMA, rel=0.05)

    # one scatter series per burst class, plus the two FRET lines on the E-tau plot
    assert len(model.es_series()) >= 3
    tau_series = model.e_tau_series()
    names = [s["name"] for s in tau_series]
    assert "static FRET line" in names and "dynamic FRET line" in names
    assert model.efficiency_histogram()[0]["y"].sum() > 0
    assert "gamma" in model.results_html()
    assert model.factor_rows() and model.population_rows()


def test_view_model_reports_missing_columns(tmp_path):
    """A table without recognisable channels asks for a manual mapping."""
    from chisurf.plugins.burst.accurate_fret.gui.view_model import AccurateFretViewModel

    path = tmp_path / "odd.csv"
    np.savetxt(path, np.random.default_rng(0).normal(size=(50, 2)),
               delimiter=",", header="foo,bar", comments="")
    model = AccurateFretViewModel()
    model.set_filename(str(path))
    assert "map" in model.results_text
    assert model.can_run() is not None
    assert model.compute() is False


def test_rpc_calibrate_file(burst_table):
    """The RPC handler returns JSON-able factors and the static line."""
    from chisurf.plugins.burst.accurate_fret.backend import services

    reply = services.calibrate_file({
        "path": str(burst_table), "donor_lifetime": TAU_D0, "n_bootstrap": 0
    })
    assert reply["ok"], reply.get("error")
    result = reply["result"]
    assert result["factors"]["gamma"] == pytest.approx(GAMMA, rel=0.05)
    assert isinstance(result["static_line"]["tau_f"], list)
    assert "Automatic FRET calibration" in result["report"]
    assert result["columns"]["i_dd"] == "Green Count Rate (KHz)"


def test_rpc_rejects_a_table_without_channels(tmp_path):
    """A missing channel column is an error message, not a traceback."""
    from chisurf.plugins.burst.accurate_fret.backend import services

    path = tmp_path / "odd.csv"
    np.savetxt(path, np.zeros((10, 2)), delimiter=",", header="foo,bar", comments="")
    reply = services.calibrate_file({"path": str(path)})
    assert not reply["ok"] and "required" in reply["error"]


def test_cli_reports_the_calibration(burst_table):
    """The head-less CLI prints the report and writes the per-burst export."""
    from click.testing import CliRunner

    from chisurf.plugins.burst.accurate_fret.cli import cli

    out = burst_table.parent / "cli.csv"
    result = CliRunner().invoke(cli, [
        str(burst_table), "--tau-d0", str(TAU_D0), "--bootstrap", "0", "-o", str(out)
    ])
    assert result.exit_code == 0, result.output
    assert "Automatic FRET calibration" in result.output
    assert "gamma" in result.output
    assert out.exists()


def test_cli_lists_columns(burst_table):
    """``--list-columns`` shows what can be mapped."""
    from click.testing import CliRunner

    from chisurf.plugins.burst.accurate_fret.cli import cli

    result = CliRunner().invoke(cli, [str(burst_table), "--list-columns"])
    assert result.exit_code == 0
    assert "Tau (green)" in result.output
