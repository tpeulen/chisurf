import importlib
import json
import os
from pathlib import Path

import pytest

from chisurf.plugins.quenching_estimator.api import local as api

cli = importlib.import_module("chisurf.plugins.quenching_estimator.cli.cli")


class DummyResult:
    def __init__(self, time, donor_counts, fret_counts=None):
        self.time = time
        self.donor_counts = donor_counts
        self.fret_counts = fret_counts
        self.quantum_yield_donor = 1.0
        self.quantum_yield_fret = None
        self.collisions_fraction = 0.1
        self.fret_efficiency = None
        self.project = {"dummy": True}
        self.aa_residence = []


def test_set_path_nested():
    target = {}
    cli._set_path(target, "a.b.c", 5)
    assert target == {"a": {"b": {"c": 5}}}


def test_clone_overrides():
    base = {"a": {"b": 1}, "x": 2}
    clone = cli._clone_with_overrides(base, [("a.b", 3), ("y", 4)])
    assert clone["a"]["b"] == 3
    assert clone["x"] == 2
    assert clone["y"] == 4
    # original untouched
    assert base == {"a": {"b": 1}, "x": 2}


def test_build_runs_cartesian():
    base = {"p": 1}
    runs = cli._build_runs(base, [("a", [1, 2]), ("b", ["x", "y"])])
    tags = [t for _proj, t in runs]
    assert len(runs) == 4
    assert {"a": 1, "b": "x"} in tags
    assert {"a": 2, "b": "y"} in tags


def test_resolve_output_path_multiple(tmp_path):
    project_path = tmp_path / "proj.quest.json"
    project_path.write_text("{}", encoding="utf8")
    out = cli._resolve_output_path(
        output_path=None,
        project_path=project_path,
        idx=0,
        tags={"a": 1, "b": "x"},
        multiple=True,
    )
    assert "a-1" in out.stem and "b-x" in out.stem
    assert out.suffix == ".csv"


def test_validate_project_missing_key_raises():
    import click

    bad = {"tau0": 1.0}  # missing many keys
    with pytest.raises(click.ClickException):
        cli._validate_project(bad)


def test_simulate_set_and_grid(monkeypatch, tmp_path):
    interactions = {
        residue: {"slow_factor": 1.0, "kQ": 0.0}
        for residue in [
            "ALA",
            "ARG",
            "ASN",
            "ASP",
            "CYS",
            "GLN",
            "GLU",
            "GLY",
            "HIS",
            "ILE",
            "LEU",
            "LYS",
            "MET",
            "PHE",
            "PRO",
            "SER",
            "THR",
            "TRP",
            "TYR",
            "VAL",
        ]
    }
    project = {
        "tau0": 4.2,
        "n_photons": 10,
        "t_max": 10.0,
        "t_step": 0.1,
        "dg": 0.0,
        "critical_distance": 8.5,
        "av_parameter": 1000,
        "amino_acid_interactions": interactions,
        "pdb": str(tmp_path / "dummy.pdb"),
        "fret": {"dyes": [{"D": 7.5}]},
    }
    Path(project["pdb"]).write_text("PDB", encoding="utf8")
    proj_path = tmp_path / "proj.json"
    proj_path.write_text(json.dumps(project), encoding="utf8")

    # stub api.load_project and simulate_project
    monkeypatch.setattr(api, "load_project", lambda path: project)

    def fake_sim(project, pdb_path=None, nbins=None, tac_range=None, **kwargs):
        import numpy as np

        return DummyResult(time=np.array([0.0, 1.0]), donor_counts=np.array([1.0, 2.0]))

    monkeypatch.setattr(api, "simulate_project", fake_sim)

    import click.testing

    runner = click.testing.CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            "simulate",
            "-p",
            str(proj_path),
            "--set",
            "tau0=3.0",
            "--grid",
            "fret.dyes.0.D=7.5,8.5",
            "-o",
            str(tmp_path / "out.json"),
        ],
    )
    assert result.exit_code == 0
    # two runs written
    outs = list(tmp_path.glob("out_fret.dyes.0.D-*.json"))
    assert len(outs) == 2
    payload = json.loads(outs[0].read_text(encoding="utf8"))
    assert payload["aa_residence"] == []


@pytest.mark.skipif(
    os.environ.get("QUEST_RUN_1ANF_REGRESSION") != "1",
    reason="1anf CLI residence diagnostic is opt-in because it is slow and may need PDB cache/network.",
)
def test_1anf_cli_aa_sticking_increases_event_residence(tmp_path):
    project = cli._template_project(with_fret=False)
    project.update(
        {
            "pdb": "1anf",
            "attachment": {"chain": "A", "residue": 72, "atom": "CB"},
            "av_parameter": {"linker_length": 21.5, "linker_width": 0.5, "radius1": 3.5},
            "dg": 0.5,
            "slow_radius": 8.5,
            "t_max": 2000,
            "t_step": 0.02,
            "n_photons": 1000,
            "n_bins": 128,
            "tau0": 4.2,
            "critical_distance": 4.0,
            "save_avs": False,
            "random_seed": 123,
        }
    )
    project["fret"]["dyes"][0].update(
        {
            "name": "D0",
            "role": "donor",
            "D": 7.0,
            "attachment": project["attachment"],
            "av_parameter": project["av_parameter"],
        }
    )

    project_path = tmp_path / "1anf.json"
    project_path.write_text(json.dumps(project), encoding="utf8")

    import click.testing

    runner = click.testing.CliRunner()
    control = runner.invoke(
        cli.cli,
        [
            "simulate",
            "-p",
            str(project_path),
            "-o",
            str(tmp_path / "control.json"),
            "--set",
            "amino_acid_interactions.ASP.slow_factor=1.0",
            "--set",
            "amino_acid_interactions.GLU.slow_factor=1.0",
        ],
    )
    sticky = runner.invoke(
        cli.cli,
        [
            "simulate",
            "-p",
            str(project_path),
            "-o",
            str(tmp_path / "sticky.json"),
            "--set",
            "amino_acid_interactions.ASP.slow_factor=0.00001",
            "--set",
            "amino_acid_interactions.GLU.slow_factor=0.00001",
        ],
    )
    assert control.exit_code == 0, control.output
    assert sticky.exit_code == 0, sticky.output

    def by_residue(path: Path):
        payload = json.loads(path.read_text(encoding="utf8"))
        return {row["residue_name"]: row for row in payload["aa_residence"]}

    control_rows = by_residue(tmp_path / "control.json")
    sticky_rows = by_residue(tmp_path / "sticky.json")
    control_acidic_total = sum(
        control_rows[aa]["attributed_total_time_ns"] for aa in ("ASP", "GLU")
    )
    sticky_acidic_total = sum(sticky_rows[aa]["attributed_total_time_ns"] for aa in ("ASP", "GLU"))
    control_acidic_max = max(
        control_rows[aa]["attributed_max_event_time_ns"] for aa in ("ASP", "GLU")
    )
    sticky_acidic_max = max(
        sticky_rows[aa]["attributed_max_event_time_ns"] for aa in ("ASP", "GLU")
    )
    assert sticky_acidic_total > control_acidic_total
    assert sticky_acidic_max > control_acidic_max
