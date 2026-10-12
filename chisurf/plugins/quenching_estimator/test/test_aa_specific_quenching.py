"""Tests for amino-acid specific PET quenching.

Quenching in QuEst is resolved per residue type: each residue contributes its
own rate (``kQ``) inside its own contact radius (``quench_radius``), measured
from the dye centre to a quenching centre that sits on the residue's
redox-active moiety (``quench_atoms``) rather than on CB.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.core import (
    build_donor_from_project,
    calculate_aa_quenching,
    simulate_project,
)
from chisurf.plugins.quenching_estimator.core.dye_diffusion import (
    DEFAULT_QUENCHER_ATOMS,
    REFERENCE_PET_QUENCHING,
    default_amino_acid_interactions,
    normalize_amino_acid_interactions,
)

PDB_PATH = Path(__file__).parent / "148l.pdb"


def _project(**overrides):
    project = {
        "tau0": 4.2,
        "n_photons": 5000,
        "t_max": 500.0,
        "t_step": 0.02,
        "dg": 0.8,
        "critical_distance": 8.5,
        "slow_radius": 8.5,
        "av_parameter": {"linker_length": 21.5, "linker_width": 0.5, "radius1": 3.5},
        "amino_acid_interactions": default_amino_acid_interactions(slow_factor=0.1),
        "attachment": {"chain": "E", "residue": 10, "atom": "CB"},
        "pdb": str(PDB_PATH),
        "n_bins": 64,
        "parallel_trajectories": 1,
        "fret": {"enabled": False, "dyes": [{"name": "D0", "D": 7.0, "random_seed": 3}]},
    }
    project.update(overrides)
    return project


class TestInteractionTable:
    def test_defaults_cover_every_standard_residue(self) -> None:
        table = normalize_amino_acid_interactions()
        assert len(table) == 20
        for residue, params in table.items():
            assert set(params) == {"slow_factor", "kQ", "quench_radius", "quench_atoms"}
            assert params["quench_atoms"] == list(DEFAULT_QUENCHER_ATOMS[residue])

    def test_quench_atoms_are_the_redox_active_moiety(self) -> None:
        table = normalize_amino_acid_interactions()
        # The indole ring, not CB, mediates PET for tryptophan.
        assert "NE1" in table["TRP"]["quench_atoms"]
        assert "CB" not in table["TRP"]["quench_atoms"]
        # Sulfur-centred quenchers are single atoms.
        assert table["MET"]["quench_atoms"] == ["SD"]
        assert table["CYS"]["quench_atoms"] == ["SG"]
        # The imidazole ring for histidine.
        assert set(table["HIS"]["quench_atoms"]) == {"CG", "ND1", "CD2", "CE1", "NE2"}

    def test_legacy_scalar_entry_is_read_as_slow_factor(self) -> None:
        table = normalize_amino_acid_interactions({"TRP": 0.25})
        assert table["TRP"]["slow_factor"] == 0.25
        assert table["TRP"]["kQ"] == 0.0

    def test_partial_override_keeps_defaults(self) -> None:
        table = normalize_amino_acid_interactions({"TYR": {"kQ": 9.0}})
        assert table["TYR"]["kQ"] == 9.0
        assert table["TYR"]["quench_atoms"] == list(DEFAULT_QUENCHER_ATOMS["TYR"])
        assert table["TRP"]["kQ"] == 0.0

    @pytest.mark.parametrize("bad", [None, 0.0, -1.0, "nonsense", float("nan")])
    def test_invalid_quench_radius_falls_back_to_global(self, bad) -> None:
        table = normalize_amino_acid_interactions({"TRP": {"quench_radius": bad}})
        assert table["TRP"]["quench_radius"] is None

    def test_slow_factor_is_clamped(self) -> None:
        table = normalize_amino_acid_interactions(
            {"TRP": {"slow_factor": 5.0}, "TYR": {"slow_factor": -2.0}}
        )
        assert table["TRP"]["slow_factor"] == 1.0
        assert table["TYR"]["slow_factor"] == 0.0

    def test_reference_defaults_scale_with_dye_size(self) -> None:
        small = default_amino_acid_interactions(dye_radius=3.0)
        large = default_amino_acid_interactions(dye_radius=5.0)
        # The radius is centre-to-centre, so a bigger dye reaches contact sooner.
        assert large["TRP"]["quench_radius"] - small["TRP"]["quench_radius"] == pytest.approx(2.0)
        assert small["TRP"]["kQ"] == large["TRP"]["kQ"]

    def test_kq_scale_only_touches_quenching_residues(self) -> None:
        table = default_amino_acid_interactions(kQ_scale=0.5)
        assert table["TRP"]["kQ"] == pytest.approx(REFERENCE_PET_QUENCHING["TRP"]["kQ"] * 0.5)
        assert table["ALA"]["kQ"] == 0.0
        assert table["ALA"]["quench_radius"] is None


class TestQuenchingCentres:
    @pytest.fixture(scope="class")
    def model(self):
        donor = build_donor_from_project(_project())
        return donor

    def test_quench_centre_sits_on_the_moiety_not_on_cb(self, model) -> None:
        slow, quench, names = model.residue_site_data
        names = np.asarray(names)

        # Tryptophan's indole centroid is several Angstrom away from CB.
        trp_offset = np.linalg.norm(slow[names == "TRP"] - quench[names == "TRP"], axis=1)
        assert trp_offset.size > 0
        assert np.all(trp_offset > 2.5)

        # Methionine quenches at the thioether sulfur.
        met_offset = np.linalg.norm(slow[names == "MET"] - quench[names == "MET"], axis=1)
        assert np.all(met_offset > 2.0)

        # Glycine has no side chain, so both centres coincide.
        gly_offset = np.linalg.norm(slow[names == "GLY"] - quench[names == "GLY"], axis=1)
        assert np.allclose(gly_offset, 0.0)

    def test_custom_quench_atoms_move_the_centre(self) -> None:
        donor = build_donor_from_project(
            _project(
                amino_acid_interactions=normalize_amino_acid_interactions(
                    {"TRP": {"kQ": 1.0, "quench_atoms": ["CB"]}}
                )
            )
        )
        slow, quench, names = donor.residue_site_data
        names = np.asarray(names)
        offset = np.linalg.norm(slow[names == "TRP"] - quench[names == "TRP"], axis=1)
        assert np.allclose(offset, 0.0)

    def test_per_residue_radius_falls_back_to_critical_distance(self, model) -> None:
        _slow, _quench, names = model.residue_site_data
        radii = model._quench_radii_for_residue_names(names)
        names = np.asarray(names)
        # TRP defines its own radius, ALA inherits the project critical_distance.
        assert np.allclose(radii[names == "TRP"], 8.5)
        assert np.allclose(radii[names == "ALA"], 8.5)

        donor = build_donor_from_project(_project(critical_distance=3.0))
        _s, _q, names2 = donor.residue_site_data
        radii2 = donor._quench_radii_for_residue_names(names2)
        names2 = np.asarray(names2)
        assert np.allclose(radii2[names2 == "ALA"], 3.0)
        assert np.allclose(radii2[names2 == "TRP"], 8.5)


class TestQuenchingDecomposition:
    def test_contributions_split_by_residue_type(self) -> None:
        # Two quenchers of different type at known positions; the dye sits on
        # top of the first for every frame.
        trajectory = np.zeros((10, 3))
        contributions = calculate_aa_quenching(
            trajectory,
            {"TRP": np.array([[0.0, 0.0, 0.0]]), "TYR": np.array([[100.0, 0.0, 0.0]])},
            quench_radii={"TRP": 2.0, "TYR": 2.0},
            quench_rates={"TRP": 3.0, "TYR": 1.0},
        )
        assert contributions["TRP"]["mean_quench_rate"] == pytest.approx(3.0)
        assert contributions["TRP"]["quench_rate_fraction"] == pytest.approx(1.0)
        # The out-of-range residue type is still reported, with no contribution.
        assert contributions["TYR"]["mean_quench_rate"] == 0.0
        assert contributions["TYR"]["fraction_frames_quenched"] == 0.0

    def test_overlapping_centres_add_up(self) -> None:
        trajectory = np.zeros((4, 3))
        contributions = calculate_aa_quenching(
            trajectory,
            {"TRP": np.array([[0.5, 0.0, 0.0], [-0.5, 0.0, 0.0]])},
            quench_radii={"TRP": 2.0},
            quench_rates={"TRP": 1.5},
        )
        assert contributions["TRP"]["mean_quench_rate"] == pytest.approx(3.0)
        assert contributions["TRP"]["fraction_frames_quenched"] == pytest.approx(1.0)

    def test_zero_rate_residues_are_omitted(self) -> None:
        contributions = calculate_aa_quenching(
            np.zeros((3, 3)),
            {"ALA": np.array([[0.0, 0.0, 0.0]])},
            quench_radii={"ALA": 5.0},
            quench_rates={"ALA": 0.0},
        )
        assert contributions == {}

    def test_empty_trajectory_is_handled(self) -> None:
        assert calculate_aa_quenching(None, {}, quench_radii={}, quench_rates={}) == {}


class TestSimulationIsResidueSpecific:
    def test_result_reports_per_residue_quenching(self) -> None:
        result = simulate_project(_project(attachment={"chain": "E", "residue": 155, "atom": "CB"}))
        rows = {row["residue_name"]: row for row in (result.aa_residence or [])}

        quenching = {name: row for name, row in rows.items() if row["mean_quench_rate"] > 0}
        assert quenching, "expected at least one residue type to quench at this site"

        # Contributions are a decomposition, so the shares sum to one.
        assert sum(row["quench_rate_fraction"] for row in quenching.values()) == pytest.approx(1.0)

        for row in quenching.values():
            assert row["kQ"] > 0.0
            assert row["quench_radius"] > 0.0
            assert 0.0 <= row["fraction_frames_quenched"] <= 1.0

        # Residues without a redox-active side chain never contribute.
        assert rows["ALA"]["mean_quench_rate"] == 0.0
        assert rows["LEU"]["mean_quench_rate"] == 0.0

    def test_disabling_a_residue_type_removes_its_contribution(self) -> None:
        with_trp = simulate_project(
            _project(attachment={"chain": "E", "residue": 155, "atom": "CB"})
        )
        trp_share = next(
            row["quench_rate_fraction"]
            for row in (with_trp.aa_residence or [])
            if row["residue_name"] == "TRP"
        )
        assert trp_share > 0.0

        table = default_amino_acid_interactions(slow_factor=0.1)
        table["TRP"]["kQ"] = 0.0
        without_trp = simulate_project(
            _project(
                attachment={"chain": "E", "residue": 155, "atom": "CB"},
                amino_acid_interactions=table,
            )
        )
        trp_row = next(
            row for row in (without_trp.aa_residence or []) if row["residue_name"] == "TRP"
        )
        assert trp_row["mean_quench_rate"] == 0.0
        # Removing the dominant quencher must raise the quantum yield.
        assert without_trp.quantum_yield_donor > with_trp.quantum_yield_donor

    def test_quenching_is_site_dependent(self) -> None:
        """A site with quenchers in reach must quench more than an exposed one.

        Re-picked 2026-10-12, when IMP.bff's AV search became FPS's link search
        (the three-voxel cube hop from every node): the volumes grew and the
        former pair inverted -- E155 0.896 against E10 0.721 under this project.
        Scanned all 151 chain-E CB sites here; the classic E99 quenches strongly
        (0.242) and E96 not at all (1.000), so the pair is those two. Re-measure,
        do not widen, if it moves again.
        """
        near_quenchers = simulate_project(
            _project(attachment={"chain": "E", "residue": 99, "atom": "CB"})
        )
        far_site = simulate_project(
            _project(attachment={"chain": "E", "residue": 96, "atom": "CB"})
        )
        assert near_quenchers.quantum_yield_donor < 0.5
        assert far_site.quantum_yield_donor == pytest.approx(1.0)
