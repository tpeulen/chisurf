"""Headless tests of the MCTS model-selection stack.

The environment is an adapter over a real ChiSurf ``LifetimeModel`` fit
(built by the existing ``build_lifetime_fit``): its actions flip the fix/free
mask of the model's own parameters and its inner loop is the fit's own
``run()``. These tests pin that contract — the mask transitions, that the
reward prefers the true structure over both fewer and more components, that
the tree search finds it, that the network trains on the search's visit
distributions, and that the winning state transfers into a live fit.
"""

from __future__ import annotations

import json
import pathlib
import time

import numpy as np
import pytest

from chisurf.core.fluorescence.decay import (
    afterpulse_decay_pattern,
    sample_decay_shot_noise,
    synthetic_decay,
)
from chisurf.core.fluorescence.tcspc.irf import synthetic_irf
from chisurf.core.fitting.mcts import (
    DiscreteAction,
    EnvConfig,
    FitEnv,
    MCTSConfig,
    MCTSFittingEngine,
    TCSPCNet,
    masked_softmax,
)
from chisurf.core.fitting.mcts.apply import transfer_state_to_fit
from chisurf.core.fitting.mcts.network import NetConfig

N_CHANNELS = 128
DT = 0.048
TRUE_TAUS = (0.9, 3.2)
TRUE_FRACTIONS = (0.4, 0.6)
SCATTER = 0.04
BG_FRACTION = 0.02


def _two_component_decay(seed: int = 3):
    """A deterministic 2-component decay with scatter and background.

    No IRF shift — the shift toggle is the subtlest structural decision and
    the dedicated search test keeps the target unambiguous.
    """
    rng = np.random.default_rng(seed)
    time_ns = np.arange(N_CHANNELS) * DT
    irf = synthetic_irf(time_ns, center_ns=2.0, fwhm_ns=0.2, norm=True)
    species = [
        synthetic_decay(N_CHANNELS, [float(t)], bin_width=DT, irf=irf, normalize=True)
        for t in TRUE_TAUS
    ]
    expected = np.zeros(N_CHANNELS)
    for f, pattern in zip(TRUE_FRACTIONS, species):
        expected += (1.0 - SCATTER - BG_FRACTION) * f * pattern
    expected += SCATTER * irf
    expected += BG_FRACTION * afterpulse_decay_pattern(N_CHANNELS)
    return sample_decay_shot_noise(expected, photon_count=6.0e4, rng=rng), irf


@pytest.fixture(scope="module")
def decay_irf():
    return _two_component_decay()


@pytest.fixture()
def env(decay_irf) -> FitEnv:
    decay, irf = decay_irf
    env = FitEnv(
        decay=decay, irf=irf, bin_width=DT,
        config=EnvConfig(max_components=3, obs_length=64),
    )
    env.reset()
    return env


def _add_one(structure):
    """The ADD transition of the mask, without touching a fit."""
    from chisurf.core.fitting.mcts import ModelStructure
    active = list(structure.active)
    active[active.index(False)] = True
    return ModelStructure(
        tuple(active), structure.fit_irf_shift,
        structure.fit_scatter, structure.fit_background,
    )


def _state_for(env: FitEnv, n_components: int, scatter=True, background=True):
    """A fitted state with a requested structure (via the env's own path)."""
    state = env.state
    state = env.apply_action(state, DiscreteAction.TOGGLE_SCATTER) \
        if scatter and not state.structure.fit_scatter else state
    state = env.apply_action(state, DiscreteAction.TOGGLE_BACKGROUND) \
        if background and not state.structure.fit_background else state
    while state.structure.n_components < n_components:
        state = env.apply_action(state, DiscreteAction.ADD_LIFETIME_COMPONENT)
    while state.structure.n_components > n_components:
        state = env.apply_action(state, DiscreteAction.REMOVE_LIFETIME_COMPONENT)
    return state


class TestEnvironment:
    def test_reset_starts_from_the_minimal_model(self, env):
        assert env.state.structure.n_components == 1
        assert not env.state.structure.fit_scatter
        assert not env.state.structure.fit_background
        assert not env.state.structure.fit_irf_shift
        # One lifetime and its amplitude are free — nothing else.
        assert env.state.stats.n_free_parameters == 2

    def test_action_masking(self, env):
        actions = env.valid_actions(env.state.structure)
        assert DiscreteAction.REMOVE_LIFETIME_COMPONENT not in actions
        assert DiscreteAction.ADD_LIFETIME_COMPONENT in actions
        full = env.state.structure
        for _ in range(2):
            full = _add_one(full)
        actions = env.valid_actions(full)
        assert DiscreteAction.ADD_LIFETIME_COMPONENT not in actions

    def test_add_and_remove_are_inverse_in_count(self, env):
        two = env.apply_action(env.state, DiscreteAction.ADD_LIFETIME_COMPONENT)
        assert two.structure.n_components == 2
        one = env.apply_action(two, DiscreteAction.REMOVE_LIFETIME_COMPONENT)
        assert one.structure.n_components == 1
        assert np.all(np.isfinite(one.lifetimes))

    def test_step_api_and_termination(self, env):
        obs, reward, terminated, truncated, info = env.step(
            DiscreteAction.ADD_LIFETIME_COMPONENT
        )
        assert obs.shape == (env.config.obs_length, 3 + env.n_structure_features)
        assert np.isfinite(reward)
        assert not terminated and not truncated
        obs, reward, terminated, _, info = env.step(DiscreteAction.TERMINATE_FIT)
        assert terminated
        assert info["state"] is env.state

    def test_inner_loop_recovers_the_truth(self, env):
        state = _state_for(env, 2)
        assert state.stats.chi2_reduced < 3.0
        assert np.allclose(np.sort(state.lifetimes), TRUE_TAUS, rtol=0.25)

    def test_reward_rejects_under_and_overfitting(self, env):
        one = _state_for(env, 1)
        two = _state_for(env, 2)
        three = _state_for(env, 3)
        assert two.stats.reward > one.stats.reward
        assert two.stats.reward > three.stats.reward
        # The wrong structure shows correlated residuals; the true one does not.
        assert one.stats.autocorr_score > 0.1
        assert two.stats.autocorr_score < one.stats.autocorr_score

    def test_structures_carry_the_whole_state(self, env):
        two = _state_for(env, 2)
        again = _state_for(env, 2)
        assert two.structure.as_tuple() == again.structure.as_tuple()


class TestSearch:
    def _env(self, decay, irf):
        return FitEnv(
            decay=decay, irf=irf, bin_width=DT,
            config=EnvConfig(max_components=3, obs_length=64),
        )

    def test_search_selects_the_true_structure(self):
        """A pure two-exponential decay selects exactly two components."""
        rng = np.random.default_rng(5)
        time_ns = np.arange(N_CHANNELS) * DT
        irf = synthetic_irf(time_ns, center_ns=2.0, fwhm_ns=0.2, norm=True)
        species = [
            synthetic_decay(N_CHANNELS, [float(t)], bin_width=DT, irf=irf, normalize=True)
            for t in TRUE_TAUS
        ]
        expected = sum(f * p for f, p in zip(TRUE_FRACTIONS, species))
        decay = sample_decay_shot_noise(expected, photon_count=6.0e4, rng=rng)

        env = self._env(decay, irf)
        env.reset()
        engine = MCTSFittingEngine(
            env, None,
            MCTSConfig(n_simulations=1200, dirichlet_fraction=0.0),
        )
        result = engine.search()
        best = result.best_state
        assert best.structure.n_components == 2
        assert not best.structure.fit_scatter
        assert not best.structure.fit_background
        assert best.stats.chi2_reduced < 2.0
        assert result.n_simulations == 1200

    def test_search_resolves_nuisances_to_statistical_equivalence(self, env):
        """Scatter can be traded for an ultra-fast component at this SNR.

        On the module fixture (4 % scatter, 6·10⁴ photons) a third component
        is a legitimate statistical mimic of the prompt. The search's answer
        must therefore be *statistically sound* rather than identical to the
        generating structure: a good χ²ᵣ and a reward within one BIC unit of
        the true structure's sequential fit.
        """
        engine = MCTSFittingEngine(
            env, None,
            MCTSConfig(n_simulations=1200, dirichlet_fraction=0.0),
        )
        result = engine.search()
        best = result.best_state
        reference = _state_for(env, 2)
        bic_unit = 0.5 * np.log(reference.stats.n_photons)
        assert best.stats.chi2_reduced < 3.0
        assert best.stats.reward >= reference.stats.reward - bic_unit

    def test_search_never_revisits_a_structure_on_a_path(self, env):
        """Cycle prevention: every node's structure differs from its ancestors'."""
        engine = MCTSFittingEngine(
            env, None,
            MCTSConfig(n_simulations=500, dirichlet_fraction=0.0),
        )
        engine.search()
        violations = 0
        stack = [engine.root]
        while stack:
            node = stack.pop()
            if not node.terminal:  # TERMINATE shares its parent's structure
                ancestor = node.parent
                while ancestor is not None:
                    if (node.structure_id is not None
                            and node.structure_id == ancestor.structure_id):
                        violations += 1
                    ancestor = ancestor.parent
            stack.extend(node.children.values())
        assert violations == 0


class TestNetwork:
    def test_forward_shapes_and_ranges(self):
        net = TCSPCNet(obs_length=64, config=NetConfig(channels=(8, 12), hidden=16), seed=0)
        obs = np.random.default_rng(1).normal(size=(5, 64, net.n_obs_channels))
        feat = np.zeros((5, net.n_structure_features))
        logits, value = net.forward(obs, feat)
        assert logits.shape == (5, net.n_actions)
        assert value.shape == (5,)
        assert np.all(value > -1.0) and np.all(value < 1.0)

    def test_masked_softmax_excludes_invalid_actions(self):
        logits = np.array([1.0, 5.0, -1.0, 0.0, 2.0, 0.5])
        valid = np.array([True, False, True, False, False, True])
        probs = masked_softmax(logits, valid)
        assert probs[1] == 0.0 and probs[3] == 0.0
        assert probs.sum() == pytest.approx(1.0)
        assert probs[0] > probs[2]

    def test_training_reduces_the_loss(self):
        net = TCSPCNet(obs_length=64, config=NetConfig(channels=(8, 12), hidden=16), seed=0)
        rng = np.random.default_rng(2)
        examples = []
        for _ in range(40):
            obs = rng.normal(size=(64, net.n_obs_channels)) * 0.3
            feat = rng.random(net.n_structure_features)
            target = np.zeros(net.n_actions)
            target[int(rng.integers(0, 3))] = 1.0
            examples.append((obs, feat, target, float(rng.uniform(-1, 1))))
        first = net.train(examples, epochs=1, batch_size=16, rng=rng)[0]
        last = net.train(examples, epochs=30, batch_size=16, rng=rng)[-1]
        assert last < first

    def test_save_and_load_roundtrip(self, tmp_path):
        net = TCSPCNet(obs_length=64, config=NetConfig(channels=(8, 12), hidden=16), seed=0)
        path = tmp_path / "net.npz"
        net.save(path)
        loaded = TCSPCNet.load(path)
        obs = np.random.default_rng(3).normal(size=(2, 64, net.n_obs_channels))
        feat = np.zeros((2, net.n_structure_features))
        a = net.forward(obs, feat)
        b = loaded.forward(obs, feat)
        assert np.allclose(a[0], b[0]) and np.allclose(a[1], b[1])


class TestSelfPlay:
    def test_self_play_runs_and_produces_a_curve(self):
        from chisurf.core.fitting.mcts import (
            SelfPlayConfig,
            SimulateConfig,
            self_play_train,
        )

        net = TCSPCNet(obs_length=64, config=NetConfig(channels=(8, 12), hidden=16), seed=0)
        sim = SimulateConfig(
            n_channels=96, bin_width=DT, photon_count=4.0e4,
            n_components_choices=(1, 2),
        )
        env_cfg = EnvConfig(max_components=3, obs_length=64)
        t0 = time.perf_counter()
        _, report = self_play_train(
            net,
            sim_config=sim,
            env_config=env_cfg,
            mcts_config=MCTSConfig(n_simulations=40),
            self_play_config=SelfPlayConfig(
                n_games=4, sims_per_game=40, train_every=2, train_epochs=2,
                eval_every=4, n_eval=2, seed=7,
            ),
        )
        assert report.n_games == 4
        assert report.n_examples > 0
        assert len(report.losses) >= 1
        assert all(np.isfinite(report.losses))
        assert len(report.evaluations) >= 2  # at least the first round
        assert time.perf_counter() - t0 < 300  # guard against regressions


class TestTorchBackend:
    """The torch training backend and the NumPy inference net agree."""

    def test_torch_numpy_weight_parity(self, tmp_path):
        torch = pytest.importorskip("torch")
        from chisurf.core.fitting.mcts.torch_backend import TCSPCNetTorch

        cfg = NetConfig(channels=(8, 12), hidden=16)
        torch_net = TCSPCNetTorch(obs_length=64, config=cfg, seed=0, device="cpu")
        path = tmp_path / "weights.npz"
        torch_net.save(path)

        numpy_net = TCSPCNet.load(path)  # the inference side reads them as-is
        rng = np.random.default_rng(5)
        obs = rng.normal(size=(4, 64, numpy_net.n_obs_channels))
        feat = rng.random((4, numpy_net.n_structure_features))

        with torch.no_grad():
            logits_t, value_t = torch_net.forward(obs, feat)
        logits_n, value_n = numpy_net.forward(obs, feat)
        assert np.allclose(logits_t.cpu().numpy(), logits_n, atol=1e-4)
        assert np.allclose(value_t.cpu().numpy(), value_n, atol=1e-4)

        mask = np.zeros(numpy_net.n_actions, dtype=bool)
        mask[[0, 2, 3, 5]] = True
        probs_t, value_single_t = torch_net.predict(obs[0], feat[0], mask)
        probs_n, value_single_n = numpy_net.predict(obs[0], feat[0], mask)
        assert np.allclose(probs_t, probs_n, atol=1e-4)
        assert abs(value_single_t - value_single_n) < 1e-4


class TestApply:
    def test_state_transfers_into_a_fresh_fit(self, decay_irf):
        from chisurf.core.fluorescence.decay_fit_model import build_lifetime_fit

        decay, irf = decay_irf
        env = FitEnv(
            decay=decay, irf=irf, bin_width=DT,
            config=EnvConfig(max_components=3, obs_length=64),
        )
        env.reset()
        state = _state_for(env, 2)

        target = build_lifetime_fit(
            decay, bin_width=DT, irf=irf, n_components=1,
            tau_bounds=env.config.tau_bounds,
        )
        transfer_state_to_fit(state, target, env.config)
        model = target.model
        assert model.lifetimes.n == len(state.structure.active)
        free_pairs = [
            i for i, (t, a) in enumerate(zip(model.lifetimes._lifetimes,
                                             model.lifetimes._amplitudes))
            if not (t.fixed and a.fixed)
        ]
        assert len(free_pairs) == 2
        assert model.generic._sc.fixed == (not state.structure.fit_scatter)
        assert model.generic._bg.fixed == (not state.structure.fit_background)
        target.run()
        assert target.chi2r < 3.0


class TestGuiWiring:
    """The MCTS button is data — the view spec and the model's action."""

    def test_view_spec_declares_the_mcts_button(self):
        path = pathlib.Path(
            "chisurf/gui/widgets/fitting/fitting_controls.view.json"
        )
        spec = json.loads(path.read_text())
        buttons = [
            button
            for section in spec["sections"]
            for panel in section.get("sections", [])
            if panel.get("type") == "button_row"
            for button in panel.get("buttons", [])
        ]
        actions = [button.get("action") for button in buttons]
        assert "fit" in actions
        assert "mcts" in actions
        # The spec declares it directly next to Fit.
        assert abs(actions.index("mcts") - actions.index("fit")) == 1

    def test_controls_model_exposes_the_mcts_action(self):
        from chisurf.gui.widgets.fitting.fitting_controls import FittingControlsModel

        model = FittingControlsModel(controller=None)
        assert callable(model.mcts)


class TestFretEnvironment:
    """The FRET environment: Gaussian states, linked donor reference, and the
    agent-user dialogue for the reference."""

    @staticmethod
    def _two_state_fret(seed: int = 7):
        """A 2-state FRET measurement + donor-only reference, ground truth
        from the FRET model's own forward path."""
        from chisurf.core.fluorescence.decay_fit_model import build_fret_fit

        n, dt = 128, 0.048
        time_ns = np.arange(n) * dt
        irf = synthetic_irf(time_ns, center_ns=2.0, fwhm_ns=0.2, norm=True)
        template = build_fret_fit(
            np.ones(n), bin_width=dt, n_states=2, donor_lifetime=4.0,
            initial_distances=[35.0, 62.0], sigma=5.0, irf=irf,
        )
        model = template.model
        model.gaussians._gaussianAmplitudes[0].value = 0.5
        model.gaussians._gaussianAmplitudes[1].value = 0.5
        model.fret_parameters._xDonly.value = 0.10
        model.update()
        expected = np.asarray(model.y, dtype=float)
        expected = expected / expected.sum()
        rng = np.random.default_rng(seed)
        decay = sample_decay_shot_noise(expected, photon_count=3.0e5, rng=rng)
        donor_ref = sample_decay_shot_noise(
            synthetic_decay(n, [4.0], bin_width=dt, irf=irf, normalize=True),
            photon_count=2.0e5, rng=rng,
        )
        return decay, donor_ref, irf

    @staticmethod
    def _env(decay, donor_ref, irf, query_user=None, candidates=None):
        from chisurf.core.fitting.mcts import FretEnv, FretEnvConfig

        return FretEnv(
            decay, irf, 0.048,
            donor_decay=donor_ref, donor_irf=irf,
            config=FretEnvConfig(max_components=2, max_fret_states=3,
                                 obs_length=64, tau_bounds=(0.1, 20.0)),
            query_user=query_user, donor_reference_candidates=candidates,
        )

    def test_linked_reference_pins_the_donor(self):
        decay, donor_ref, irf = self._two_state_fret()
        env = self._env(decay, donor_ref, irf)
        env.reset()
        assert env.linked
        ref_tau = env.donor_fit.model.lifetimes._lifetimes[0].value
        assert abs(ref_tau - 4.0) < 0.1
        # The one-state root cannot be a good fit of a two-state truth; what
        # matters here is that it is finite and the search starts from it.
        assert np.isfinite(env.state.stats.chi2_reduced)

    def test_search_recovers_two_fret_states(self):
        decay, donor_ref, irf = self._two_state_fret()
        env = self._env(decay, donor_ref, irf)
        env.reset()
        engine = MCTSFittingEngine(
            env, None, MCTSConfig(n_simulations=250, dirichlet_fraction=0.0),
        )
        best = engine.search().best_state
        assert best.structure.n_fret_states == 2
        assert best.stats.chi2_reduced < 2.0
        fitted = np.sort(best.distances)
        assert np.allclose(fitted, (35.0, 62.0), atol=8.0)

    def test_instrument_parameters_are_frozen(self, env):
        """dt and rep are instrument factors: never reachable, even when a
        perturbation would move the model (periodic convolution)."""
        from chisurf.core.fitting.mcts import EnvConfig

        frozen = EnvConfig().protected_parameters
        assert {"dt", "rep"} <= set(frozen)
        names = [name for name, _p in env._registry]
        assert "dt" not in names and "rep" not in names
        valid = env.valid_actions(env.state.structure, env.state)
        assert all(
            env.action_name(a) not in ("TOGGLE dt", "TOGGLE rep") for a in valid
        )

    def test_fret_actions_masked_on_lifetime_env(self, env):
        actions = env.valid_actions(env.state.structure)
        assert DiscreteAction.ADD_FRET_STATE not in actions
        assert DiscreteAction.TOGGLE_DONOR_ONLY not in actions

    def test_agent_asks_for_the_missing_reference(self):
        decay, _donor_ref, irf = self._two_state_fret()
        asked = []

        def ask(question):
            asked.append(question)
            return 0  # link the first candidate

        candidate = np.asarray(self._two_state_fret()[1], dtype=float)
        env = self._env(
            decay, None, irf, query_user=ask,
            candidates=[{"label": "reference",
                         "data": (candidate, irf, 0.048)}],
        )
        assert asked and asked[0].kind == "donor_reference"
        assert env.linked

    def test_transfer_state_into_a_fret_fit(self):
        from chisurf.core.fluorescence.decay_fit_model import build_fret_fit
        from chisurf.core.fitting.mcts.apply import transfer_state_to_fit

        decay, donor_ref, irf = self._two_state_fret()
        env = self._env(decay, donor_ref, irf)
        env.reset()
        state = env.state
        state = env.apply_action(state, DiscreteAction.ADD_FRET_STATE)

        n = decay.size
        target = build_fret_fit(
            np.asarray(decay), bin_width=0.048, n_states=1, irf=np.asarray(irf),
        )
        transfer_state_to_fit(state, target, env.config)
        model = target.model
        free_means = [p for p in model.gaussians._gaussianMeans if not p.fixed]
        assert len(free_means) == state.structure.n_fret_states
        target.run()
        assert target.chi2r < 3.0

    def test_fret_simulator_rounds_trip(self):
        from chisurf.core.fitting.mcts import (
            FretEnvConfig, simulate_fret_decay,
        )

        spec = simulate_fret_decay(
            np.random.default_rng(3),
            env_config=FretEnvConfig(max_fret_states=3, obs_length=64),
        )
        env = spec.make_env(FretEnvConfig(max_fret_states=3, obs_length=64))
        assert env.linked
        env.reset()
        assert env.state.structure.n_fret_states == 1
        assert len(env.donor_fit.model.lifetimes) >= 1


class TestDirectFitOperation:
    """The architecture contract: the agent operates on the user's own fit.

    One fit object. The environment mutates its fix/free mask, the search
    explores by restoring, and ``apply_best`` leaves that same object in the
    winning state. No private copy, no transfer.
    """

    def test_lifetime_env_is_the_users_fit(self, decay_irf):
        from chisurf.core.fluorescence.decay_fit_model import build_lifetime_fit
        from chisurf.core.fitting.mcts.apply import environment_from_fit

        decay, irf = decay_irf
        user_fit = build_lifetime_fit(
            decay, bin_width=DT, irf=irf, n_components=1,
        )
        user_fit.run()
        root_chi2 = user_fit.chi2r

        env = environment_from_fit(
            user_fit, EnvConfig(max_components=3, obs_length=64)
        )
        assert env.fit is user_fit
        env.reset()
        result = MCTSFittingEngine(
            env, None, MCTSConfig(n_simulations=250, dirichlet_fraction=0.0),
        ).search()
        env.apply_best(result.best_state)

        assert env.fit is user_fit  # still the same object, no copy
        assert user_fit.chi2r < root_chi2
        free = [
            i for i, (t, a) in enumerate(zip(
                user_fit.model.lifetimes._lifetimes,
                user_fit.model.lifetimes._amplitudes))
            if not (t.fixed and a.fixed)
        ]
        assert len(free) == result.best_state.structure.n_components

    def test_fret_env_is_the_users_fit(self):
        from chisurf.core.fluorescence.decay_fit_model import (
            build_fret_fit, build_lifetime_fit,
        )
        from chisurf.core.fitting.mcts import FretEnv, FretEnvConfig

        decay, donor_ref, irf = TestFretEnvironment._two_state_fret()
        user_fret = build_fret_fit(
            np.asarray(decay), bin_width=0.048, n_states=1,
            initial_distances=[52.0], irf=np.asarray(irf),
        )
        user_donor = build_lifetime_fit(
            np.asarray(donor_ref), bin_width=0.048, irf=np.asarray(irf),
            n_components=1,
        )
        cfg = FretEnvConfig(max_components=2, max_fret_states=3,
                            obs_length=64, tau_bounds=(0.1, 20.0))
        env = FretEnv(fit=user_fret, donor_fit=user_donor, config=cfg)
        assert env.fit is user_fret
        assert env.donor_fit is user_donor
        assert user_fret.model.donor.link is user_donor.model.lifetimes
        env.reset()
        env.apply_best(env.state)
        assert env.fit is user_fret  # restored in place


class TestGeneralModelSelectionContract:
    """Contracts shared by lifetime, FRET, and anisotropy model adapters."""

    def test_all_tcspc_models_share_one_network_schema(self, decay_irf):
        from chisurf.core.fitting.mcts import FretEnvConfig

        decay, donor_ref, irf = TestFretEnvironment._two_state_fret()
        lifetime = FitEnv(
            decay=decay_irf[0], irf=decay_irf[1], bin_width=DT,
            config=EnvConfig(max_components=3, obs_length=64),
        )
        fret = TestFretEnvironment._env(decay, donor_ref, irf)
        lifetime.reset()
        fret.reset()

        assert lifetime.n_actions == fret.n_actions
        assert lifetime.n_structure_features == fret.n_structure_features
        assert lifetime.observation_space.shape == fret.observation_space.shape
        net = TCSPCNet(obs_length=64)
        assert net.n_actions == lifetime.n_actions
        assert net.n_structure_features == lifetime.n_structure_features
        assert net.n_obs_channels == lifetime.observation_space.shape[1]

    def test_protected_parameters_preserve_initial_fixed_state(self, decay_irf):
        from chisurf.core.fluorescence.decay_fit_model import build_lifetime_fit

        decay, irf = decay_irf
        user_fit = build_lifetime_fit(decay, bin_width=DT, irf=irf)
        aniso = user_fit.model.anisotropy
        aniso.polarization_type = "vv"
        protected = (aniso._g, aniso._l1, aniso._l2,
                     user_fit.model.convolve._dt,
                     user_fit.model.convolve._rep)
        initial = (False, True, False, True, False)
        for parameter, fixed in zip(protected, initial):
            parameter.fixed = fixed

        env = FitEnv(
            fit=user_fit, config=EnvConfig(max_components=3, obs_length=64)
        )
        env.reset()

        assert tuple(parameter.fixed for parameter in protected) == initial
        assert {name for name, _ in env._registry}.isdisjoint(
            {"g", "l1", "l2", "dt", "rep"}
        )

    def test_rotation_components_are_structural_actions(self, decay_irf):
        from chisurf.core.fluorescence.decay_fit_model import build_lifetime_fit

        decay, irf = decay_irf
        user_fit = build_lifetime_fit(decay, bin_width=DT, irf=irf)
        user_fit.model.anisotropy.polarization_type = "vv"
        env = FitEnv(
            fit=user_fit, config=EnvConfig(max_components=3, obs_length=64)
        )
        env.reset()

        actions = env.valid_actions(env.state.structure, env.state)
        assert DiscreteAction.ADD_ROTATION_COMPONENT in actions
        state = env.apply_action(
            env.state, DiscreteAction.ADD_ROTATION_COMPONENT
        )
        assert state.structure.n_rotations == 1
        assert state.rotation_times.size == 1

    def test_apply_best_compacts_and_sorts_component_outputs(self, decay_irf):
        decay, irf = decay_irf
        env = FitEnv(
            decay=decay, irf=irf, bin_width=DT,
            config=EnvConfig(max_components=3, obs_length=64),
        )
        env.reset()
        state = _state_for(env, 2)
        env.apply_best(state)

        values = list(env.fit.model.lifetimes.lifetimes)
        assert len(values) == state.structure.n_components
        assert values == sorted(values, reverse=True)
