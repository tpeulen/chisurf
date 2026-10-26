"""ProteinMC's fps.json readers: score-set filtering of the labelling potential, FlexFit move maps.

These lived in the FPS JSON editor's tests (the editor moved into ChiMOL); they test
ProteinMC code, so they live with it. The score-set tests drive the real
``DirectLabelingPotential`` filtering, with only the structure lookup stubbed.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.modelling.proteinmc.model import DirectLabelingPotential


@pytest.fixture
def simple_payload() -> dict:
    """Minimal fps.json without χ²."""
    return {
        "Positions": {
            "p1": {"chain_identifier": "A", "residue_seq_number": 1},
            "p2": {"chain_identifier": "A", "residue_seq_number": 2},
        },
        "Distances": {
            "p1_p2": {
                "distance": 25.0,
                "error_neg": 1.0,
                "error_pos": 1.0,
                "position1_name": "p1",
                "position2_name": "p2",
                "Forster_radius": 52.0,
                "distance_type": "RDAMean",
            }
        },
    }


@pytest.fixture
def payload_with_score_sets() -> dict:
    """Payload with two χ² score sets and an extra section (FlexFit)."""
    return {
        "Distances": {
            "d1": {
                "distance": 10.0,
                "error_neg": 1.0,
                "error_pos": 1.0,
                "position1_name": "p1",
                "position2_name": "p2",
                "Forster_radius": 52.0,
                "distance_type": "RDAMean",
            },
            "d2": {
                "distance": 20.0,
                "error_neg": 1.0,
                "error_pos": 1.0,
                "position1_name": "p1",
                "position2_name": "p3",
                "Forster_radius": 52.0,
                "distance_type": "RDAMean",
            },
            "d3": {
                "distance": 30.0,
                "error_neg": 1.0,
                "error_pos": 1.0,
                "position1_name": "p2",
                "position2_name": "p3",
                "Forster_radius": 52.0,
                "distance_type": "RDAMean",
            },
        },
        "Positions": {
            "p1": {"chain_identifier": "A", "residue_seq_number": 1},
            "p2": {"chain_identifier": "A", "residue_seq_number": 2},
            "p3": {"chain_identifier": "A", "residue_seq_number": 3},
        },
        "χ²": {
            "group_a": {
                "distances": ["d1", "d2"],
                "maximum_NaNs_allowed": 0,
                "penalty_NaN": 0,
            },
            "group_b": {
                "distances": ["d2", "d3"],
            },
        },
        "FlexFit": {
            "FexResSet1": {
                "Flexible residues": [
                    {"chain_identifier": "A", "residue_seq_number": 10},
                ],
                "Bonds": [],
            }
        },
    }


@pytest.fixture
def tmp_json(tmp_path: Path, payload_with_score_sets) -> Path:
    """Write a sample fps.json to a temp file."""
    fn = tmp_path / "test.fps.json"
    fn.write_text(json.dumps(payload_with_score_sets), encoding="utf-8")
    return fn


# ---------------------------------------------------------------------------
# Tests: payload round-trip
# ---------------------------------------------------------------------------


class _Potential(DirectLabelingPotential):
    """The real score-set filtering, without resolving positions on a structure."""

    def _resolve_position_index(self, position):
        return 0


def _potential(tmp_path, payload, score_set=""):
    path = tmp_path / "plan.fps.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return _Potential(structure=None, labeling_file=path, score_set=score_set)


class TestDirectLabelingPotentialScoreSet:
    """The potential uses only the distances (and positions) of its score set."""

    def test_all_distances_when_empty_score_set(self, tmp_path, payload_with_score_sets):
        assert set(_potential(tmp_path, payload_with_score_sets).distances) == {"d1", "d2", "d3"}

    def test_filters_to_group_a(self, tmp_path, payload_with_score_sets):
        assert set(_potential(tmp_path, payload_with_score_sets, "group_a").distances) == {
            "d1",
            "d2",
        }

    def test_filters_to_group_b(self, tmp_path, payload_with_score_sets):
        assert set(_potential(tmp_path, payload_with_score_sets, "group_b").distances) == {
            "d2",
            "d3",
        }

    def test_unknown_score_set_returns_all(self, tmp_path, payload_with_score_sets):
        potential = _potential(tmp_path, payload_with_score_sets, "nonexistent")
        assert set(potential.distances) == {"d1", "d2", "d3"}

    def test_no_chi_section(self, tmp_path, simple_payload):
        assert set(_potential(tmp_path, simple_payload, "whatever").distances) == {"p1_p2"}

    def test_distances_preserved_unchanged(self, tmp_path, payload_with_score_sets):
        potential = _potential(tmp_path, payload_with_score_sets, "group_a")
        assert potential.distances["d1"]["distance"] == 10.0
        assert potential.distances["d2"]["distance"] == 20.0

    def test_used_positions_follow_the_score_set(self, tmp_path, payload_with_score_sets):
        # group_a: d1 (p1-p2), d2 (p1-p3); group_b: d2 (p1-p3), d3 (p2-p3)
        assert set(_potential(tmp_path, payload_with_score_sets, "group_a").positions) == {
            "p1",
            "p2",
            "p3",
        }
        assert set(_potential(tmp_path, payload_with_score_sets, "group_b").positions) == {
            "p1",
            "p2",
            "p3",
        }
        payload_with_score_sets["χ²"]["only_d1"] = {"distances": ["d1"]}
        assert set(_potential(tmp_path, payload_with_score_sets, "only_d1").positions) == {
            "p1",
            "p2",
        }


class TestFlexFitMoveMap:
    """build_move_map_from_flexfit must map FlexFit residues to structure indices."""

    def test_list_flexfit_sets(self, tmp_json, payload_with_score_sets):
        from chisurf.plugins.modelling.proteinmc.model import list_flexfit_sets

        sets = list_flexfit_sets(tmp_json)
        assert sets == ["FexResSet1"]

    def test_list_flexfit_sets_no_file(self):
        from chisurf.plugins.modelling.proteinmc.model import list_flexfit_sets

        assert list_flexfit_sets("/nonexistent/path.json") == []

    def test_list_flexfit_sets_no_flexfit(self, tmp_path):
        from chisurf.plugins.modelling.proteinmc.model import list_flexfit_sets

        fn = tmp_path / "noflex.json"
        fn.write_text(json.dumps({"Distances": {}, "Positions": {}}))
        assert list_flexfit_sets(fn) == []

    def test_build_move_map_no_flexfit(self, tmp_path):
        from chisurf.plugins.modelling.proteinmc.model import build_move_map_from_flexfit

        fn = tmp_path / "noflex.json"
        fn.write_text(json.dumps({"Distances": {}, "Positions": {}}))
        result = build_move_map_from_flexfit(None, fn, None)
        assert result is None

    def test_build_move_map_returns_none_on_no_match(self, tmp_path):
        """When FlexFit residues don't match any structure residue, return None."""
        from chisurf.plugins.modelling.proteinmc.model import build_move_map_from_flexfit

        fn = tmp_path / "flex.json"
        fn.write_text(
            json.dumps(
                {
                    "Distances": {},
                    "Positions": {},
                    "FlexFit": {
                        "S1": {
                            "Flexible residues": [
                                {"chain_identifier": "Z", "residue_seq_number": 9999},
                            ],
                            "Bonds": [],
                        }
                    },
                }
            )
        )
        atoms = np.zeros(3, dtype=[("chain", "S1"), ("res_id", "i4")])
        atoms["chain"] = [b"A", b"A", b"A"]
        atoms["res_id"] = [1, 2, 3]

        class MockStructure:
            n_residues = 3

            @property
            def residue_dict(self):
                return {1: {}, 2: {}, 3: {}}

            @property
            def atoms(self):
                return atoms

        result = build_move_map_from_flexfit(MockStructure(), fn, "S1")
        assert result is None

    def test_build_move_map_matching_residues(self, tmp_path):
        """When FlexFit residues match, the move_map has 1.0 at those indices."""
        from chisurf.plugins.modelling.proteinmc.model import build_move_map_from_flexfit

        fn = tmp_path / "flex.json"
        fn.write_text(
            json.dumps(
                {
                    "Distances": {},
                    "Positions": {},
                    "FlexFit": {
                        "S1": {
                            "Flexible residues": [
                                {"chain_identifier": "A", "residue_seq_number": 2},
                            ],
                            "Bonds": [],
                        }
                    },
                }
            )
        )

        atoms = np.zeros(3, dtype=[("chain", "S1"), ("res_id", "i4")])
        atoms["chain"] = [b"A", b"A", b"A"]
        atoms["res_id"] = [1, 2, 3]

        class MockStructure:
            n_residues = 3

            @property
            def residue_dict(self):
                return {1: {}, 2: {}, 3: {}}

            @property
            def atoms(self):
                return atoms

        result = build_move_map_from_flexfit(MockStructure(), fn, "S1")
        assert result is not None
        assert result.shape == (3,)
        assert result[0] == 0.0
        assert result[1] == 1.0
        assert result[2] == 0.0

    def test_build_move_map_defaults_to_first_set(self, tmp_path):
        """When flexfit_set=None, the first set is used."""
        from chisurf.plugins.modelling.proteinmc.model import build_move_map_from_flexfit

        fn = tmp_path / "flex.json"
        fn.write_text(
            json.dumps(
                {
                    "Distances": {},
                    "Positions": {},
                    "FlexFit": {
                        "First": {
                            "Flexible residues": [
                                {"chain_identifier": "A", "residue_seq_number": 1},
                            ],
                            "Bonds": [],
                        },
                        "Second": {
                            "Flexible residues": [
                                {"chain_identifier": "A", "residue_seq_number": 3},
                            ],
                            "Bonds": [],
                        },
                    },
                }
            )
        )

        atoms = np.zeros(3, dtype=[("chain", "S1"), ("res_id", "i4")])
        atoms["chain"] = [b"A", b"A", b"A"]
        atoms["res_id"] = [1, 2, 3]

        class MockStructure:
            n_residues = 3

            @property
            def residue_dict(self):
                return {1: {}, 2: {}, 3: {}}

            @property
            def atoms(self):
                return atoms

        result = build_move_map_from_flexfit(MockStructure(), fn, None)
        assert result is not None
        assert result[0] == 1.0
        assert result[1] == 0.0
        assert result[2] == 0.0

    def test_build_move_map_empty_residues_returns_none(self, tmp_path):
        """A FlexFit set with no Flexible residues returns None."""
        from chisurf.plugins.modelling.proteinmc.model import build_move_map_from_flexfit

        fn = tmp_path / "flex.json"
        fn.write_text(
            json.dumps(
                {
                    "Distances": {},
                    "Positions": {},
                    "FlexFit": {
                        "S1": {
                            "Flexible residues": [],
                            "Bonds": [],
                        }
                    },
                }
            )
        )

        atoms = np.zeros(0, dtype=[("chain", "S1"), ("res_id", "i4")])

        class MockStructure:
            n_residues = 0

            @property
            def residue_dict(self):
                return {}

            @property
            def atoms(self):
                return atoms

        result = build_move_map_from_flexfit(MockStructure(), fn, "S1")
        assert result is None

    def test_build_move_map_nonexistent_set_returns_none(self, tmp_path):
        """Requesting a nonexistent FlexFit set returns None."""
        from chisurf.plugins.modelling.proteinmc.model import build_move_map_from_flexfit

        fn = tmp_path / "flex.json"
        fn.write_text(
            json.dumps(
                {
                    "Distances": {},
                    "Positions": {},
                    "FlexFit": {
                        "S1": {
                            "Flexible residues": [
                                {"chain_identifier": "A", "residue_seq_number": 1},
                            ],
                            "Bonds": [],
                        }
                    },
                }
            )
        )

        atoms = np.zeros(1, dtype=[("chain", "S1"), ("res_id", "i4")])
        atoms["chain"] = [b"A"]
        atoms["res_id"] = [1]

        class MockStructure:
            n_residues = 1

            @property
            def residue_dict(self):
                return {1: {}}

            @property
            def atoms(self):
                return atoms

        result = build_move_map_from_flexfit(MockStructure(), fn, "NONEXISTENT")
        assert result is None
