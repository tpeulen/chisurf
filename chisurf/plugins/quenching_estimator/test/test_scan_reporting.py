"""Tests for what a scan reports: quencher attribution and failure diagnostics.

The CLI and the WebUI both scan labelling sites and both summarise each site
with the residue types that quenched it, so they share `top_quenchers`. When a
site cannot be simulated the error has to say which selection was wrong --
a scan moves the donor but leaves the acceptor alone, so a stale acceptor makes
every site fail for a reason that has nothing to do with the site.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from chisurf.plugins.quenching_estimator.api import local as api

cli = importlib.import_module("chisurf.plugins.quenching_estimator.cli.cli")
from chisurf.plugins.quenching_estimator.core.av import AV
from chisurf.plugins.quenching_estimator.core.dye_diffusion import default_amino_acid_interactions

PDB_PATH = Path(__file__).parent / "148l.pdb"


class TestTopQuenchers:
    def test_orders_by_share_and_drops_silent_residues(self) -> None:
        rows = [
            {"residue_name": "PRO", "mean_quench_rate": 0.05, "quench_rate_fraction": 0.2},
            {"residue_name": "ALA", "mean_quench_rate": 0.0, "quench_rate_fraction": 0.0},
            {"residue_name": "TYR", "mean_quench_rate": 0.20, "quench_rate_fraction": 0.8},
        ]
        top = api.top_quenchers(rows)
        assert [row["residue_name"] for row in top] == ["TYR", "PRO"]
        assert top[0]["quench_rate_fraction"] == 0.8

    def test_honours_the_limit(self) -> None:
        rows = [
            {"residue_name": name, "mean_quench_rate": rate, "quench_rate_fraction": rate}
            for name, rate in (("TRP", 0.4), ("TYR", 0.3), ("MET", 0.2), ("HIS", 0.1))
        ]
        assert len(api.top_quenchers(rows, limit=2)) == 2
        assert [row["residue_name"] for row in api.top_quenchers(rows, limit=2)] == ["TRP", "TYR"]

    @pytest.mark.parametrize("value", [None, []])
    def test_tolerates_a_missing_residence_table(self, value) -> None:
        assert api.top_quenchers(value) == []


class TestAttachmentErrors:
    def test_a_missing_atom_names_the_site(self) -> None:
        """Regression: this used to be a bare 'Invalid selection of attachment atom'."""
        with pytest.raises(ValueError, match=r"No attachment atom Z:9999:CB"):
            AV(
                str(PDB_PATH),
                residue_seq_number=9999,
                atom_name="CB",
                chain_identifier="Z",
                linker_length=21.5,
                linker_width=0.5,
                radius1=3.5,
            )

    def test_a_stale_acceptor_is_reported_as_such(self, tmp_path: Path) -> None:
        """Otherwise every scanned site fails for a reason that looks like its own."""
        project = _project()
        project["fret"] = {
            "enabled": True,
            "dyes": [
                {"name": "D0", "D": 7.0, "random_seed": 5},
                {
                    "name": "A0",
                    "D": 7.0,
                    "attachment": {"chain": "Z", "residue": 9999, "atom": "CB"},
                },
            ],
            "R0_matrix": [[None, 52.0], [52.0, None]],
        }
        with pytest.raises(ValueError, match=r"Acceptor dye: No attachment atom Z:9999:CB"):
            api.simulate_project(project, project_dir=tmp_path, save_outputs=False)


def _project(residue: int = 18):
    return {
        "tau0": 4.2,
        "n_photons": 2000,
        "t_max": 200.0,
        "t_step": 0.02,
        "dg": 0.5,
        "critical_distance": 8.5,
        "slow_radius": 8.5,
        "av_parameter": {"linker_length": 21.5, "linker_width": 0.5, "radius1": 3.5},
        "amino_acid_interactions": default_amino_acid_interactions(slow_factor=0.1),
        "attachment": {"chain": "E", "residue": residue, "atom": "CB"},
        "pdb": str(PDB_PATH),
        "n_bins": 64,
        "parallel_trajectories": 1,
        "fret": {"enabled": False, "dyes": [{"name": "D0", "D": 7.0, "random_seed": 5}]},
    }


class TestScanCommand:
    def test_reports_quenchers_and_writes_no_job_directories(self, tmp_path: Path) -> None:
        project_path = tmp_path / "project.json"
        project_path.write_text(json.dumps(_project()), encoding="utf8")

        sites = {
            "Positions": {
                f"E{residue}": {
                    "chain_identifier": "E",
                    "residue_seq_number": residue,
                    "atom_name": "CB",
                }
                # 17 has no accessible volume since radii moved to IMP's.
                for residue in (36, 18)
            }
        }
        sites_path = tmp_path / "fps.json"
        sites_path.write_text(json.dumps(sites), encoding="utf8")
        output_path = tmp_path / "scan.json"

        result = CliRunner().invoke(
            cli.cli,
            [
                "scan",
                "-p",
                str(project_path),
                "-l",
                str(sites_path),
                "-o",
                str(output_path),
            ],
        )
        assert result.exit_code == 0, result.output

        rows = json.loads(output_path.read_text(encoding="utf8"))
        assert len(rows) == 2
        for row in rows.values():
            assert row["status"] == "success", row.get("error")
            assert "dominant_quencher" in row
            assert isinstance(row["quenchers"], list)
            for quencher in row["quenchers"]:
                assert quencher["mean_quench_rate"] > 0.0

        # The scan writes one summary row per site; per-run job directories are
        # never read and used to cost more than the simulation itself.
        assert not (tmp_path / "jobs").exists()
