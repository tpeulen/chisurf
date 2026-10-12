"""Tests for the coarse-grained structure representation.

Coarse-graining keeps the backbone plus a CB pseudo-atom placed at the
side-chain centre of mass. It is a modelling choice, not a speed optimisation:
side chains no longer block the accessible volume, and every residue's quenching
centre collapses onto that pseudo-atom.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.core import build_donor_from_project, simulate_project
from chisurf.plugins.quenching_estimator.core.dye_diffusion import (
    STANDARD_AMINO_ACID_RESIDUES,
    default_amino_acid_interactions,
)
from chisurf.plugins.quenching_estimator.core.structure import Structure

PDB_PATH = Path(__file__).parent / "148l.pdb"

# Atoms kept by the coarse representation: backbone, the CB pseudo-atom, and
# proline's CG/CD, which the ring geometry needs.
COARSE_ATOMS = {"N", "CA", "C", "O", "CB", "H", "CG", "CD"}


def _project(**overrides):
    project = {
        "tau0": 4.2,
        "n_photons": 4000,
        "t_max": 400.0,
        "t_step": 0.02,
        "dg": 0.9,
        "critical_distance": 8.5,
        "slow_radius": 8.5,
        "av_parameter": {"linker_length": 21.5, "linker_width": 0.5, "radius1": 3.5},
        "amino_acid_interactions": default_amino_acid_interactions(slow_factor=0.1),
        "attachment": {"chain": "E", "residue": 155, "atom": "CB"},
        "pdb": str(PDB_PATH),
        "n_bins": 64,
        "parallel_trajectories": 1,
        "fret": {"enabled": False, "dyes": [{"name": "D0", "D": 7.0, "random_seed": 5}]},
    }
    project.update(overrides)
    return project


class TestStructureCoarseGraining:
    def test_coarse_structure_drops_side_chain_atoms(self) -> None:
        """Regression: this used to raise KeyError on hydrogen-free structures."""
        all_atom = Structure(str(PDB_PATH), make_coarse=False)
        coarse = Structure(str(PDB_PATH), make_coarse=True, auto_update=False)

        assert coarse.is_coarse is True
        assert len(coarse.atoms) < len(all_atom.atoms)

        # Only *amino acids* are coarse-grained. Scoping the assertion to them
        # is the point, not a loosening: since QuEst stopped stripping HETATM,
        # ligands and cofactors reach `to_coarse`, and it keeps them whole
        # because there is no backbone-plus-CB reduction of a bound sugar.
        amino_acids = {name for name in STANDARD_AMINO_ACID_RESIDUES}
        kept = {
            str(atom["atom_name"]).strip().upper()
            for atom in coarse.atoms
            if str(atom["res_name"]).strip().upper() in amino_acids
        }
        assert kept <= COARSE_ATOMS, f"unexpected atoms kept: {kept - COARSE_ATOMS}"
        # Side-chain atoms that drive PET are gone.
        assert "NE1" not in kept
        assert "SD" not in kept

    def test_coarse_graining_keeps_ligands_whole(self) -> None:
        """A bound ligand is a steric obstacle at every resolution.

        Dropping untemplated residues here would silently reinstate the HETATM
        stripping `quest/core/structure/reader.py` stopped doing, and coarse-graining would
        quietly open pockets that are physically closed.
        """
        all_atom = Structure(str(PDB_PATH), make_coarse=False)
        coarse = Structure(str(PDB_PATH), make_coarse=True, auto_update=False)

        def hetero_atoms(structure):
            return sorted(
                (str(a["res_name"]).strip(), str(a["atom_name"]).strip())
                for a in structure.atoms
                if str(a["res_name"]).strip().upper() not in STANDARD_AMINO_ACID_RESIDUES
            )

        assert hetero_atoms(coarse) == hetero_atoms(all_atom)
        # And their names survived: IMP calls them "HET: C1", which truncates to
        # a useless "HET:" in the |U5 field unless the prefix is stripped.
        assert all(name and not name.startswith("HET") for _, name in hetero_atoms(coarse))

    def test_cb_moves_to_the_side_chain_centre_of_mass(self) -> None:
        all_atom = Structure(str(PDB_PATH), make_coarse=False)
        coarse = Structure(str(PDB_PATH), make_coarse=True, auto_update=False)

        def cb_of(structure, res_id: int):
            atoms = structure.atoms
            mask = (atoms["res_id"] == res_id) & (
                np.char.strip(atoms["atom_name"].astype(str)) == "CB"
            )
            return atoms["coord"][mask]

        # Tryptophan has a large side chain, so its CB must move noticeably.
        trp_ids = sorted(
            {
                int(atom["res_id"])
                for atom in all_atom.atoms
                if str(atom["res_name"]).strip().upper() == "TRP"
            }
        )
        assert trp_ids

        moved = False
        for res_id in trp_ids:
            before, after = cb_of(all_atom, res_id), cb_of(coarse, res_id)
            if len(before) and len(after):
                if np.linalg.norm(before[0] - after[0]) > 1.0:
                    moved = True
        assert moved, "coarse CB should sit at the side-chain centre of mass"

    def test_torsion_rebuild_reports_that_it_is_unavailable(self) -> None:
        """The cStructure extension is not shipped; say so instead of NameError."""
        coarse = Structure(str(PDB_PATH), make_coarse=True, auto_update=False)
        with pytest.raises(NotImplementedError, match="cStructure"):
            coarse.update()


class TestCoarseGrainedSimulation:
    def test_project_flag_selects_the_representation(self) -> None:
        all_atom = build_donor_from_project(_project(coarse_grained=False))
        coarse = build_donor_from_project(_project(coarse_grained=True))

        assert all_atom.coarse_grained is False
        assert coarse.coarse_grained is True
        assert len(coarse.structure.atoms) < len(all_atom.structure.atoms)

    def test_quench_centres_collapse_onto_cb(self) -> None:
        coarse = build_donor_from_project(_project(coarse_grained=True))
        slow_centers, quench_centers, names = coarse.residue_site_data
        names = np.asarray(names)
        offsets = np.linalg.norm(slow_centers - quench_centers, axis=1)

        # Without side-chain atoms the quenching centre falls back to CB, which
        # now sits at the side-chain centre of mass. Proline is the exception:
        # its ring atoms (CG, CD) survive coarse-graining.
        assert np.allclose(offsets[names != "PRO"], 0.0)
        assert np.all(offsets[names == "PRO"] > 0.0)

        # The all-atom representation keeps the moiety centres distinct from CB.
        all_atom = build_donor_from_project(_project(coarse_grained=False))
        slow_centers, quench_centers, names = all_atom.residue_site_data
        names = np.asarray(names)
        offsets = np.linalg.norm(slow_centers - quench_centers, axis=1)
        assert np.all(offsets[names == "TRP"] > 2.5)
        assert np.all(offsets[names == "MET"] > 2.0)

    def test_simulation_runs_and_still_attributes_quenching(self) -> None:
        result = simulate_project(_project(coarse_grained=True))
        assert 0.0 < result.quantum_yield_donor <= 1.0
        assert result.av_volume and result.av_volume > 0.0

        rows = {row["residue_name"]: row for row in (result.aa_residence or [])}
        assert rows, "expected residue-type metrics"
        assert rows["ALA"]["mean_quench_rate"] == 0.0

    def test_coarse_accessible_volume_is_larger(self) -> None:
        """Removing side chains frees space the dye can reach."""
        all_atom = simulate_project(_project(coarse_grained=False))
        coarse = simulate_project(_project(coarse_grained=True))
        assert coarse.av_volume is not None and all_atom.av_volume is not None
        assert coarse.av_volume > all_atom.av_volume
