"""FRET must follow the donor's diffusion, and fail loudly when it cannot run.

The regression these guard: `calc_fret_rate` used to reduce both accessible
volumes to a single scalar rate and add it to every frame, so the FRET channel
was completely independent of the trajectory QuEst exists to simulate. A
broken acceptor specification degraded silently to a donor-only result.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.core import av as fps
from chisurf.plugins.quenching_estimator.core import build_donor_from_project
from chisurf.plugins.quenching_estimator.core.av import fret_rate_trace
from chisurf.plugins.quenching_estimator.core.project import (
    DEFAULT_FORSTER_RADIUS,
    template_project,
)

STRUCTURE = Path(__file__).parent / "148l.pdb"


class TestFretRateKernel:
    def test_rate_at_the_forster_radius_is_one_over_tau0(self) -> None:
        """By definition transfer and emission are equally likely at r = R0."""
        donor = np.array([[0.0, 0.0, 0.0]])
        acceptor = np.array([[52.0, 0.0, 0.0]])
        rate = fret_rate_trace(donor, acceptor, R0=52.0, tau0=4.0, r_min=1.0)
        assert rate[0] == pytest.approx(1.0 / 4.0)

    def test_rate_follows_the_sixth_power(self) -> None:
        acceptor = np.array([[40.0, 0.0, 0.0]])
        near = fret_rate_trace(np.array([[0.0, 0.0, 0.0]]), acceptor, 50.0, 4.0, r_min=1.0)[0]
        far = fret_rate_trace(np.array([[-40.0, 0.0, 0.0]]), acceptor, 50.0, 4.0, r_min=1.0)[0]
        # Twice the distance is 2^6 = 64 times slower.
        assert near / far == pytest.approx(64.0, rel=1e-6)

    def test_the_rate_tracks_the_donor_position(self) -> None:
        acceptor = np.array([[60.0, 0.0, 0.0]])
        trajectory = np.array([[0.0, 0.0, 0.0], [20.0, 0.0, 0.0], [40.0, 0.0, 0.0]])
        rates = fret_rate_trace(trajectory, acceptor, 52.0, 4.0, r_min=1.0)
        assert rates[0] < rates[1] < rates[2]

    def test_the_acceptor_volume_is_averaged_over(self) -> None:
        trajectory = np.array([[0.0, 0.0, 0.0]])
        cloud = np.array([[40.0, 0.0, 0.0], [80.0, 0.0, 0.0]])
        rate = fret_rate_trace(trajectory, cloud, 52.0, 4.0, r_min=1.0)[0]
        singles = [
            fret_rate_trace(trajectory, cloud[i : i + 1], 52.0, 4.0, r_min=1.0)[0] for i in range(2)
        ]
        # The *rate* is averaged (fast-acceptor limit), not the distance.
        assert rate == pytest.approx(sum(singles) / 2.0)

    def test_overlapping_clouds_do_not_diverge(self) -> None:
        """Both clouds hold dye centres and can overlap; (R0/r)^6 must not blow up."""
        coincident = np.array([[10.0, 10.0, 10.0]])
        rate = fret_rate_trace(coincident, coincident, 52.0, 4.0, r_min=7.0)[0]
        assert np.isfinite(rate)
        # Equal to the rate at exactly the floor distance.
        floored = fret_rate_trace(
            np.array([[0.0, 0.0, 0.0]]), np.array([[7.0, 0.0, 0.0]]), 52.0, 4.0, r_min=7.0
        )[0]
        assert rate == pytest.approx(floored)

    def test_an_empty_acceptor_volume_is_an_error(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            fret_rate_trace(np.array([[0.0, 0.0, 0.0]]), np.empty((0, 3)), 52.0, 4.0)

    def test_large_clouds_are_subsampled_but_still_averaged(self) -> None:
        trajectory = np.array([[0.0, 0.0, 0.0]])
        cloud = np.tile(np.array([[45.0, 0.0, 0.0]]), (5000, 1))
        rate = fret_rate_trace(trajectory, cloud, 52.0, 4.0, r_min=1.0, max_acceptor_points=64)[0]
        single = fret_rate_trace(trajectory, cloud[:1], 52.0, 4.0, r_min=1.0)[0]
        assert rate == pytest.approx(single)


def _fret_project(**overrides):
    project = template_project(with_fret=True)
    project["pdb"] = str(STRUCTURE)
    project["attachment"] = {"chain": "E", "residue": 55, "atom": "CB"}
    project["fret"]["dyes"][0]["attachment"] = dict(project["attachment"])
    project["fret"]["dyes"][1]["attachment"] = {"chain": "E", "residue": 82, "atom": "CB"}
    project.update(n_photons=2000, t_max=200.0, t_step=0.05, n_bins=128, random_seed=11)
    project.update(overrides)
    return project


@pytest.fixture(scope="module")
def simulated_donor():
    model = build_donor_from_project(_fret_project())
    model.update_all(verbose=False)
    return model


class TestFretFollowsTheTrajectory:
    def test_the_rate_varies_along_the_trajectory(self, simulated_donor) -> None:
        """The regression: a scalar rate made FRET blind to the diffusion."""
        rates = simulated_donor.calc_fret_rate_trace()
        assert rates.shape[0] == simulated_donor.diffusion._traj.shape[0]
        assert rates.min() < rates.max()
        # Not a rounding wobble: the dye samples a wide range of separations.
        assert rates.max() / max(rates.min(), 1e-12) > 1.5

    def test_the_rate_is_positive_and_finite(self, simulated_donor) -> None:
        rates = simulated_donor.calc_fret_rate_trace()
        assert np.all(np.isfinite(rates))
        assert np.all(rates > 0.0)

    def test_efficiency_comes_from_the_two_decays(self, simulated_donor) -> None:
        efficiency = simulated_donor.fret_efficiency
        expected = 1.0 - simulated_donor.quantum_yield_fret / simulated_donor.quantum_yield
        assert efficiency == pytest.approx(expected)
        assert 0.0 < efficiency < 1.0

    def test_rda_mean_e_stays_available_as_a_diagnostic(self, simulated_donor) -> None:
        distance = simulated_donor.rda_mean_e(n_samples=5000)
        # T4L 55 -> 132 with 21.5 A linkers: tens of Angstrom, not metres.
        assert 10.0 < distance < 100.0

    def test_r0_is_read_in_angstrom(self, simulated_donor) -> None:
        assert simulated_donor.fret_R0 == pytest.approx(DEFAULT_FORSTER_RADIUS)
        assert simulated_donor.fret_R0_angstrom == pytest.approx(DEFAULT_FORSTER_RADIUS)


class TestFretFailsLoudly:
    def test_enabling_fret_without_an_acceptor_raises(self) -> None:
        project = _fret_project()
        # Keep fret enabled but drop the acceptor, the shape that used to give a
        # donor-only result with no warning anywhere.
        project["fret"]["dyes"] = project["fret"]["dyes"][:1]
        model = build_donor_from_project(project)
        model.update_all(verbose=False)

        with pytest.raises(ValueError, match="acceptor"):
            model.calc_fret_rate_trace()

    def test_rates_lazily_run_the_diffusion(self) -> None:
        """`DonorDecay.diffusion` simulates on first access, so rates never
        silently come back empty for want of a trajectory."""
        model = build_donor_from_project(_fret_project())
        assert model._diffusion is None

        rates = model.calc_fret_rate_trace()

        assert model._diffusion is not None
        assert rates.shape[0] == model.diffusion._traj.shape[0]


class TestThePairedRateKernel:
    """`fret_rate_pair_trace`: both dyes resolved in time."""

    def test_rate_at_the_forster_radius_is_one_over_tau0(self) -> None:
        donor = np.zeros((3, 3))
        acceptor = np.zeros((3, 3))
        acceptor[:, 0] = 50.0
        rates = fps.fret_rate_pair_trace(donor, acceptor, R0=50.0, tau0=4.0, r_min=1.0)
        assert rates == pytest.approx(np.full(3, 0.25))

    def test_it_follows_the_sixth_power(self) -> None:
        donor = np.zeros((2, 3))
        acceptor = np.array([[50.0, 0.0, 0.0], [100.0, 0.0, 0.0]])
        rates = fps.fret_rate_pair_trace(donor, acceptor, R0=50.0, tau0=4.0, r_min=1.0)
        assert rates[0] / rates[1] == pytest.approx(64.0)

    def test_the_acceptor_moving_changes_the_rate(self) -> None:
        """The whole point: a static acceptor and a moving one differ."""
        donor = np.zeros((4, 3))
        still = np.tile([50.0, 0.0, 0.0], (4, 1))
        moving = np.array([[40.0, 0, 0], [50.0, 0, 0], [60.0, 0, 0], [50.0, 0, 0]])
        a = fps.fret_rate_pair_trace(donor, still, R0=50.0, tau0=4.0, r_min=1.0)
        b = fps.fret_rate_pair_trace(donor, moving, R0=50.0, tau0=4.0, r_min=1.0)
        assert not np.allclose(a, b)
        # r^-6 is convex, so excursions raise the mean rate above the static one.
        assert b.mean() > a.mean()

    def test_overlapping_dyes_do_not_diverge(self) -> None:
        coincident = np.zeros((2, 3))
        rates = fps.fret_rate_pair_trace(coincident, coincident, R0=50.0, tau0=4.0, r_min=8.0)
        assert np.all(np.isfinite(rates))
        assert rates == pytest.approx(np.full(2, (50.0 / 8.0) ** 6 / 4.0))

    def test_mismatched_lengths_are_an_error(self) -> None:
        """Truncating would silently change the sampled time window."""
        with pytest.raises(ValueError, match="same number of"):
            fps.fret_rate_pair_trace(np.zeros((10, 3)), np.zeros((7, 3)), R0=50.0, tau0=4.0)

    def test_an_empty_trajectory_is_an_error(self) -> None:
        with pytest.raises(ValueError, match="frames"):
            fps.fret_rate_pair_trace(np.zeros((0, 3)), np.zeros((0, 3)), R0=50.0, tau0=4.0)


class TestTheAcceptorDiffusesAndSticks:
    """The acceptor is a dye in its own right, not a static cloud.

    Its diffusion coefficient, stickiness radius and interaction table are its
    own; they merely *default* to the donor's, so old projects are unchanged.
    """

    def _project(self, **fret_overrides):
        from chisurf.plugins.quenching_estimator.core.project import template_project

        project = template_project()
        project["pdb"] = str(STRUCTURE)
        project["attachment"] = {"chain": "E", "residue": 55, "atom": "CB"}
        project["t_max"] = 200.0
        project["t_step"] = 0.02
        project["n_photons"] = 50_000
        project["random_seed"] = 5
        project["fret"]["enabled"] = True
        project["fret"]["dyes"][1] = {
            "name": "A0",
            "role": "acceptor",
            "attachment": {"chain": "E", "residue": 82, "atom": "CB"},
            "av_parameter": {"linker_length": 18.0, "linker_width": 0.5, "radius1": 4.0},
            "D": 2.5,
        }
        project["fret"].update(fret_overrides)
        return project

    def test_the_acceptor_parameters_are_its_own(self) -> None:
        from chisurf.plugins.quenching_estimator.api.local import build_donor_from_project

        project = self._project()
        project["fret"]["dyes"][1]["slow_radius"] = 12.0
        model = build_donor_from_project(project)

        assert model.acceptor_diffusion_coefficient_value == 2.5
        assert model.diffusion_coefficient != 2.5, "the donor must be unaffected"
        assert model.acceptor_slow_radius_value == 12.0
        assert model.slow_radius != 12.0

    def test_they_default_to_the_donors(self) -> None:
        """An old project says nothing about acceptor chemistry; it must still run."""
        from chisurf.plugins.quenching_estimator.api.local import build_donor_from_project

        project = self._project()
        project["fret"]["dyes"][1].pop("D")
        model = build_donor_from_project(project)

        assert model.acceptor_diffusion_coefficient_value == model.diffusion_coefficient
        assert model.acceptor_slow_radius_value == model.slow_radius
        assert model.acceptor_interactions == model.amino_acid_interactions

    def test_a_stickier_acceptor_is_a_different_dye(self) -> None:
        """Per-dye stickiness must actually reach the acceptor's walk."""
        from chisurf.plugins.quenching_estimator.api.local import build_donor_from_project

        project = self._project()
        project["fret"]["dyes"][1]["amino_acid_interactions"] = {
            "TRP": {"slow_factor": 0.001, "kQ": 0.0, "quench_radius": None, "quench_atoms": ["CB"]}
        }
        model = build_donor_from_project(project)

        assert model.acceptor_interactions["TRP"]["slow_factor"] == 0.001
        # The donor's own table is untouched by the acceptor's.
        assert model.amino_acid_interactions["TRP"]["slow_factor"] != 0.001

    def test_the_acceptor_walk_stays_inside_its_volume(self) -> None:
        from chisurf.plugins.quenching_estimator.api.local import build_donor_from_project

        model = build_donor_from_project(self._project())
        trajectory = model.acceptor_diffusion._traj
        assert trajectory is not None and trajectory.shape[0] > 100

        cloud = model.acceptor_av.points
        # Every frame must be within a grid step of some accessible point.
        low, high = cloud.min(axis=0) - 2.0, cloud.max(axis=0) + 2.0
        assert np.all(trajectory >= low) and np.all(trajectory <= high)

    def test_the_two_walks_are_independent(self) -> None:
        """Same seed for both dyes would move them in lockstep."""
        from chisurf.plugins.quenching_estimator.api.local import build_donor_from_project

        model = build_donor_from_project(self._project())
        donor = model.diffusion._traj
        acceptor = model.acceptor_diffusion._traj
        assert donor.shape == acceptor.shape
        assert not np.allclose(donor - donor.mean(axis=0), acceptor - acceptor.mean(axis=0))

    def test_the_two_walks_share_a_time_base(self) -> None:
        """They are paired frame by frame, so they must be pairable."""
        from chisurf.plugins.quenching_estimator.api.local import build_donor_from_project

        model = build_donor_from_project(self._project())
        assert model.diffusion.t_step == model.acceptor_diffusion.t_step
        assert model.diffusion._traj.shape[0] == model.acceptor_diffusion._traj.shape[0]

    def test_the_acceptor_is_not_quenched(self) -> None:
        """QuEst reports the donor's decay; the acceptor's PET is not modelled."""
        from chisurf.plugins.quenching_estimator.api.local import build_donor_from_project

        model = build_donor_from_project(self._project())
        assert not model.acceptor_diffusion.quenched.any()

    def test_the_two_regimes_disagree(self) -> None:
        """If they agreed, simulating the acceptor would be pointless."""
        from chisurf.plugins.quenching_estimator.api.local import simulate_project

        moving = simulate_project(self._project(acceptor_dynamics="trajectory"), save_outputs=False)
        averaged = simulate_project(self._project(acceptor_dynamics="averaged"), save_outputs=False)
        assert moving.fret_efficiency != pytest.approx(averaged.fret_efficiency, abs=1e-3)
        for result in (moving, averaged):
            assert result.fret_efficiency is not None and 0.0 < result.fret_efficiency < 1.0

    def test_trajectory_is_the_default(self) -> None:
        from chisurf.plugins.quenching_estimator.api.local import build_donor_from_project

        assert build_donor_from_project(self._project()).acceptor_dynamics == "trajectory"

    def test_an_unknown_regime_is_rejected(self) -> None:
        from chisurf.plugins.quenching_estimator.api.local import build_donor_from_project

        with pytest.raises(ValueError, match="acceptor_dynamics"):
            build_donor_from_project(self._project(acceptor_dynamics="teleport"))

    def test_a_slower_acceptor_changes_the_efficiency(self) -> None:
        """Its diffusion coefficient must reach the physics, not just the schema."""
        from chisurf.plugins.quenching_estimator.api.local import simulate_project

        fast = self._project()
        fast["fret"]["dyes"][1]["D"] = 20.0
        slow = self._project()
        slow["fret"]["dyes"][1]["D"] = 0.5

        assert simulate_project(fast, save_outputs=False).fret_efficiency != pytest.approx(
            simulate_project(slow, save_outputs=False).fret_efficiency, abs=1e-3
        )
