"""Simulate decays and let the network learn model selection from scratch.

This is the self-play loop of the AlphaZero recipe applied to TCSPC fitting:

1. **Simulate**: draw a random ground-truth model (1–3 lifetime components
   with well-separated taus, optional IRF colour shift, prompt scatter, dark
   background) and Poisson-sample its decay — using the same canonical
   generator (:func:`~chisurf.core.fluorescence.decay.synthetic_decay` and the
   shared scatter/background patterns) the environment's forward model uses,
   so the states the network sees during training are drawn from exactly the
   distribution it will be asked to fit.
2. **Search**: run the MCTS engine on the simulated decay with the *current*
   network as prior and value guide.
3. **Learn**: train the network on the visit distributions and reward
   differences the search produced, and repeat.

Because the simulator knows the ground truth, learning is verified against
it: every ``eval_every`` games a fixed held-out set of decays is fitted with
and without the trained network, reporting the fraction of searches that
select the true component count and the reward the selected model achieves.
The curve printed at the end is the network learning to do the analysis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from chisurf.core.fluorescence.decay import (
    afterpulse_decay_pattern,
    sample_decay_shot_noise,
    scattered_light_decay_pattern,
    synthetic_decay,
)
from chisurf.core.fluorescence.tcspc.irf import synthetic_irf
from chisurf.core.fitting.mcts.environment import (
    EnvConfig,
    FitEnv,
    FitState,
    ModelStructure,
)
from chisurf.core.fitting.mcts.mcts import (
    MCTSConfig,
    MCTSFittingEngine,
)
from chisurf.core.fitting.mcts.network import TCSPCNet

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, str], None]
CancelCheck = Callable[[], bool]


@dataclass(frozen=True)
class SimulateConfig:
    """Distribution the ground-truth decays are drawn from.

    Parameters
    ----------
    n_channels, bin_width : int, float
        Micro-time axis of the simulated histograms (channels, ns/channel).
    photon_count : float
        Expected total counts per decay — the noise level the selector must
        see through.
    n_components_choices : tuple of int
        Component counts the simulator may draw.
    tau_bounds : (float, float)
        Range the true lifetimes are log-uniformly drawn from (a sub-range of
        the environment's bounds, so the tree can always reach the truth).
    min_tau_ratio : float
        Enforced spacing between true components: closer lifetimes are not
        separable at ``photon_count`` and would make "the right answer"
        ambiguous.
    scatter_fraction : (float, float)
        Prompt-scatter fraction drawn when scatter is present (0 disables it).
    background_fraction : (float, float)
        Dark-count fraction of total photons when background is present.
    shift_channels : (float, float)
        IRF colour shift drawn when a shift is present.
    irf_fwhm_bounds : (float, float)
        FWHM range of the simulated prompt, in ns.
    nuisance_probability : float
        Chance each nuisance term is present at all.
    """

    n_channels: int = 256
    bin_width: float = 0.032
    photon_count: float = 2.0e5
    n_components_choices: Tuple[int, ...] = (1, 2, 3)
    tau_bounds: Tuple[float, float] = (0.1, 20.0)
    min_tau_ratio: float = 1.8
    scatter_fraction: Tuple[float, float] = (0.005, 0.05)
    background_fraction: Tuple[float, float] = (0.005, 0.03)
    shift_channels: Tuple[float, float] = (-1.5, 1.5)
    irf_fwhm_bounds: Tuple[float, float] = (0.08, 0.25)
    nuisance_probability: float = 0.5


@dataclass(frozen=True)
class SimulatedDecay:
    """One synthetic measurement and everything known about it.

    Attributes
    ----------
    decay, irf : numpy.ndarray
        The Poisson-sampled counts and the (noise-free) instrument response,
        exactly what a :class:`FitEnv` is constructed from.
    bin_width : float
        Channel width in ns.
    structure : ModelStructure
        The generating topology (component count, which nuisances are on).
    lifetimes, fractions : numpy.ndarray
        True lifetimes (ns) and intensity fractions, sorted by lifetime.
    scatter_fraction, background_counts, irf_shift : float, float, float
        True nuisance values (fraction of total photons, counts per channel,
        channels).
    """

    decay: np.ndarray
    irf: np.ndarray
    bin_width: float
    structure: ModelStructure
    lifetimes: np.ndarray
    fractions: np.ndarray
    scatter_fraction: float = 0.0
    background_counts: float = 0.0
    irf_shift: float = 0.0

    def make_env(self, config: Optional[EnvConfig] = None) -> FitEnv:
        """Build the fitting environment of this measurement."""
        return FitEnv(self.decay, self.irf, self.bin_width, config=config)


def simulate_decay(
    rng: np.random.Generator,
    sim_config: Optional[SimulateConfig] = None,
    env_config: Optional[EnvConfig] = None,
) -> SimulatedDecay:
    """Draw one ground-truth decay and Poisson-sample its measurement.

    The expected-count model is built from unit-area species columns, the
    normalized IRF (scatter) and the constant dark-count pattern — the same
    basis the environment's NNLS step solves against, so the truth is exactly
    representable by the model class the tree searches over.
    """
    cfg = sim_config if sim_config is not None else SimulateConfig()
    env_config = env_config if env_config is not None else EnvConfig()
    n = int(cfg.n_channels)
    dt = float(cfg.bin_width)

    irf_center = float(rng.uniform(2.0, 4.0))
    fwhm = float(rng.uniform(*cfg.irf_fwhm_bounds))
    time_ns = np.arange(n, dtype=float) * dt
    irf = synthetic_irf(time_ns, irf_center, fwhm, norm=True)

    n_comp = int(rng.choice(np.asarray(cfg.n_components_choices)))
    lo, hi = cfg.tau_bounds
    taus: List[float] = []
    while len(taus) < n_comp:
        candidate = float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
        if all(candidate / t > cfg.min_tau_ratio or t / candidate > cfg.min_tau_ratio
               for t in taus):
            taus.append(candidate)
    taus = np.sort(np.asarray(taus))

    weights = rng.uniform(0.5, 1.0, size=n_comp)
    fractions = weights / weights.sum()

    with_scatter = rng.random() < cfg.nuisance_probability
    with_background = rng.random() < cfg.nuisance_probability
    with_shift = rng.random() < cfg.nuisance_probability
    scatter = float(rng.uniform(*cfg.scatter_fraction)) if with_scatter else 0.0
    bg_fraction = float(rng.uniform(*cfg.background_fraction)) if with_background else 0.0
    shift = float(rng.uniform(*cfg.shift_channels)) if with_shift else 0.0

    from chisurf.core.fluorescence.tcspc.convolve import periodic_shift

    shifted = periodic_shift(irf, shift) if shift else irf
    species = [
        synthetic_decay(n, [float(t)], bin_width=dt, irf=shifted, normalize=True)
        for t in taus
    ]
    expected = np.zeros(n, dtype=float)
    for fraction, pattern in zip(fractions, species):
        expected += (1.0 - scatter - bg_fraction) * fraction * pattern
    if scatter > 0.0:
        expected += scatter * shifted
    if bg_fraction > 0.0:
        expected += bg_fraction * afterpulse_decay_pattern(n)

    counts = sample_decay_shot_noise(expected, photon_count=cfg.photon_count, rng=rng)
    structure = ModelStructure(
        active=tuple(i < n_comp for i in range(env_config.max_components)),
        fit_irf_shift=with_shift,
        fit_scatter=with_scatter,
        fit_background=with_background,
    )
    return SimulatedDecay(
        decay=counts,
        irf=irf,
        bin_width=dt,
        structure=structure,
        lifetimes=taus,
        fractions=fractions,
        scatter_fraction=scatter,
        background_counts=bg_fraction * float(counts.sum()) / n,
        irf_shift=shift,
    )


@dataclass
class EvaluationMetric:
    """Result of one held-out evaluation round."""

    game: int
    with_net: bool
    correct_components: int
    n_eval: int
    mean_reward: float
    mean_improvement: float


@dataclass(frozen=True)
class FretSimulateConfig:
    """Distribution of the ground-truth FRET measurements.

    The donor-only reference is always generated (the linked analysis is the
    one worth learning); tau_D0 is drawn log-uniformly, the Gaussian
    distances with enforced separation so the states are resolvable at
    ``photon_count``.
    """

    n_channels: int = 128
    bin_width: float = 0.048
    photon_count: float = 3.0e5
    donor_photon_count: float = 2.0e5
    n_states_choices: Tuple[int, ...] = (1, 2, 3)
    tau_d0_bounds: Tuple[float, float] = (1.5, 5.0)
    distance_bounds: Tuple[float, float] = (25.0, 100.0)
    min_distance_separation: float = 12.0
    sigma_bounds: Tuple[float, float] = (4.0, 8.0)
    donor_only_probability: float = 0.7
    donor_only_bounds: Tuple[float, float] = (0.03, 0.2)
    irf_fwhm_bounds: Tuple[float, float] = (0.1, 0.3)
    forster_radius: float = 52.0


@dataclass(frozen=True)
class SimulatedFretDecay:
    """A synthetic FRET measurement pair with its ground truth."""

    decay: np.ndarray
    irf: np.ndarray
    bin_width: float
    donor_decay: np.ndarray
    donor_irf: np.ndarray
    structure: "ModelStructure"
    distances: np.ndarray
    fractions: np.ndarray
    tau_d0: float
    donor_only_fraction: float

    def make_env(self, config) -> "FretEnv":
        from chisurf.core.fitting.mcts.environment import FretEnv

        return FretEnv(
            self.decay, self.irf, self.bin_width,
            donor_decay=self.donor_decay, donor_irf=self.donor_irf,
            config=config,
        )


def simulate_fret_decay(
    rng: np.random.Generator,
    sim_config: Optional[FretSimulateConfig] = None,
    env_config: Optional["FretEnvConfig"] = None,
) -> SimulatedFretDecay:
    """Draw one ground-truth FRET pair (sample + donor-only reference).

    The expected FRET decay comes from the FRET model's own forward path
    (:func:`~chisurf.core.fluorescence.decay_fit_model.build_fret_fit` with
    the truth written into its parameters) -- the same model the environment
    fits, so no FRET mathematics is duplicated here. The reference is a
    single-exponential donor decay from the canonical generator.
    """
    from chisurf.core.fluorescence.decay_fit_model import build_fret_fit
    from chisurf.core.fitting.mcts.environment import FretEnvConfig, ModelStructure

    cfg = sim_config if sim_config is not None else FretSimulateConfig()
    env_config = env_config if env_config is not None else FretEnvConfig()
    n = int(cfg.n_channels)
    dt = float(cfg.bin_width)

    time_ns = np.arange(n, dtype=float) * dt
    irf = synthetic_irf(
        time_ns,
        float(rng.uniform(1.5, 3.0)),
        float(rng.uniform(*cfg.irf_fwhm_bounds)),
        norm=True,
    )

    tau_d0 = float(np.exp(rng.uniform(
        np.log(cfg.tau_d0_bounds[0]), np.log(cfg.tau_d0_bounds[1]))))
    n_states = int(rng.choice(np.asarray(cfg.n_states_choices)))
    distances: List[float] = []
    while len(distances) < n_states:
        candidate = float(rng.uniform(*cfg.distance_bounds))
        if all(abs(candidate - d) > cfg.min_distance_separation for d in distances):
            distances.append(candidate)
    distances.sort()
    sigma = float(rng.uniform(*cfg.sigma_bounds))
    weights = rng.uniform(0.5, 1.0, size=n_states)
    fractions = weights / weights.sum()
    with_donor_only = rng.random() < cfg.donor_only_probability
    x_donly = float(rng.uniform(*cfg.donor_only_bounds)) if with_donor_only else 0.0

    template = build_fret_fit(
        np.ones(n), bin_width=dt, n_states=n_states, donor_lifetime=tau_d0,
        forster_radius=cfg.forster_radius, initial_distances=distances,
        sigma=sigma, irf=irf,
    )
    template_model = template.model
    for k, x in enumerate(fractions):
        template_model.gaussians._gaussianAmplitudes[k].value = float(x)
        template_model.gaussians._gaussianSigma[k].value = sigma
    template_model.fret_parameters._xDonly.value = x_donly
    template_model.update()
    expected = np.asarray(template_model.y, dtype=float)
    expected = expected / expected.sum()
    decay = sample_decay_shot_noise(expected, photon_count=cfg.photon_count, rng=rng)

    donor_expected = synthetic_decay(
        n, [tau_d0], bin_width=dt, irf=irf, normalize=True)
    donor_decay = sample_decay_shot_noise(
        donor_expected, photon_count=cfg.donor_photon_count, rng=rng)

    structure = ModelStructure(
        active=(True,),
        fret_states=tuple(i < n_states for i in range(env_config.max_fret_states)),
        fit_donor_only=with_donor_only,
    )
    return SimulatedFretDecay(
        decay=decay, irf=irf, bin_width=dt,
        donor_decay=donor_decay, donor_irf=irf,
        structure=structure, distances=np.asarray(distances, dtype=float),
        fractions=fractions, tau_d0=tau_d0, donor_only_fraction=x_donly,
    )


@dataclass
class SelfPlayReport:
    """Training curve and held-out metrics of a self-play run.

    Attributes
    ----------
    losses : list of float
        Mean loss after each training round.
    evaluations : list of EvaluationMetric
        Held-out results with and without the network, every ``eval_every``
        games.
    n_games, n_examples : int, int
        Work done.
    """

    losses: List[float] = field(default_factory=list)
    evaluations: List[EvaluationMetric] = field(default_factory=list)
    n_games: int = 0
    n_examples: int = 0

    def summary(self) -> str:
        """Compact text report of the learning curve."""
        lines = [f"self-play: {self.n_games} games, {self.n_examples} examples"]
        if self.losses:
            lines.append(
                "loss: " + " → ".join(f"{loss:.3f}" for loss in self.losses[:3])
                + (f" → … → {self.losses[-1]:.3f}" if len(self.losses) > 3 else "")
            )
        for metric in self.evaluations:
            tag = "with net " if metric.with_net else "uniform  "
            lines.append(
                f"game {metric.game:3d} {tag}: correct n_comp "
                f"{metric.correct_components}/{metric.n_eval}, "
                f"mean reward {metric.mean_reward:.1f}, "
                f"improvement {metric.mean_improvement:+.1f}"
            )
        return "\n".join(lines)


@dataclass
class SelfPlayConfig:
    """Controls of the self-play loop.

    Parameters
    ----------
    n_games : int
        Simulated decays fitted during training.
    sims_per_game : int
        MCTS simulations per game (the per-move compute budget).
    train_every : int
        Train the network every ``train_every`` games on the accumulated
        examples.
    train_epochs, batch_size, learning_rate : int, int, float
        Passed to :meth:`TCSPCNet.train`.
    buffer_size : int
        Most recent examples trained on (0 = keep everything).
    eval_every : int
        Held-out evaluation cadence; the first and last games always evaluate.
    n_eval : int
        Decays per held-out set.
    seed : int
        Seeds the whole run (simulation draws, shuffling, network init).
    target_chi2_max : float
        Curriculum threshold: a game only contributes training examples when
        the search ended at a statistically sound model (χ²ᵣ below this).
        Learning from failed searches teaches the noise of their failure —
        measured: the untrained network beat uniform, and degraded with every
        training round fed by unsolved games.
    """

    n_games: int = 40
    sims_per_game: int = 60
    train_every: int = 4
    train_epochs: int = 2
    batch_size: int = 32
    learning_rate: float = 1e-3
    buffer_size: int = 0
    eval_every: int = 10
    n_eval: int = 6
    seed: int = 1234
    target_chi2_max: float = 3.0


def evaluate_network(
    specs: Sequence[SimulatedDecay],
    network: Optional[TCSPCNet],
    env_config: EnvConfig,
    mcts_config: MCTSConfig,
) -> Tuple[int, float, float]:
    """Fit held-out decays and score the selections against ground truth.

    Returns ``(correct_component_count, mean_reward, mean_improvement)`` over
    the ``specs``: how often the recommended model has the true number of
    components, the mean reward of the recommended model, and its mean
    improvement over each search's minimal starting model.
    """
    correct = 0
    rewards: List[float] = []
    improvements: List[float] = []
    for spec in specs:
        env = spec.make_env(env_config)
        # Evaluation is deterministic: the Dirichlet root noise that keeps
        # self-play exploring has no place in a scored search.
        engine = MCTSFittingEngine(
            env, network,
            MCTSConfig(
                n_simulations=mcts_config.n_simulations,
                c_puct=mcts_config.c_puct,
                value_scale=mcts_config.value_scale,
                dirichlet_fraction=0.0,
            ),
        )
        result = engine.search()
        best: FitState = result.best_state
        rewards.append(float(best.stats.reward))
        improvements.append(float(result.improvement))
        if (best.structure.n_components == spec.structure.n_components
                and best.structure.n_fret_states == spec.structure.n_fret_states):
            correct += 1
    return correct, float(np.mean(rewards)), float(np.mean(improvements))


def self_play_train(
    network: TCSPCNet,
    *,
    sim_config: Optional[SimulateConfig] = None,
    env_config: Optional[EnvConfig] = None,
    mcts_config: Optional[MCTSConfig] = None,
    self_play_config: Optional[SelfPlayConfig] = None,
    simulate: Optional[Callable[[np.random.Generator], Any]] = None,
    progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCheck] = None,
) -> Tuple[TCSPCNet, SelfPlayReport]:
    """Run the simulate–search–learn loop.

    Parameters
    ----------
    network : TCSPCNet
        The network to train (mutated in place and returned).
    sim_config, env_config, mcts_config, self_play_config : optional configs
        Defaults suit a laptop-sized demonstration run.

    Returns
    -------
    (network, report) : tuple
        The trained network and the :class:`SelfPlayReport`.
    """
    sim_config = sim_config if sim_config is not None else SimulateConfig()
    env_config = env_config if env_config is not None else EnvConfig(
        obs_length=network.obs_length
    )
    mcts_config = mcts_config if mcts_config is not None else MCTSConfig()
    sp = self_play_config if self_play_config is not None else SelfPlayConfig()
    if simulate is None:
        simulate = lambda r: simulate_decay(r, sim_config, env_config)  # noqa: E731

    rng = np.random.default_rng(sp.seed)
    train_rng = np.random.default_rng(sp.seed + 1)
    eval_rng = np.random.default_rng(sp.seed + 2)

    eval_specs = [simulate(eval_rng) for _ in range(int(sp.n_eval))]
    search_config = MCTSConfig(
        n_simulations=sp.sims_per_game,
        c_puct=mcts_config.c_puct,
        value_scale=mcts_config.value_scale,
        dirichlet_alpha=mcts_config.dirichlet_alpha,
        dirichlet_fraction=mcts_config.dirichlet_fraction,
    )

    report = SelfPlayReport()
    examples: List[Tuple[np.ndarray, np.ndarray, np.ndarray, float]] = []

    def _evaluate(game: int) -> None:
        correct, mean_reward, mean_improvement = evaluate_network(
            eval_specs, network, env_config, search_config
        )
        report.evaluations.append(
            EvaluationMetric(game, True, correct, len(eval_specs),
                             mean_reward, mean_improvement)
        )
        base_correct, base_reward, base_improvement = evaluate_network(
            eval_specs, None, env_config, search_config
        )
        report.evaluations.append(
            EvaluationMetric(game, False, base_correct, len(eval_specs),
                             base_reward, base_improvement)
        )

    for game in range(int(sp.n_games)):
        if should_cancel is not None and should_cancel():
            break
        spec = simulate(rng)
        env = spec.make_env(env_config)
        engine = MCTSFittingEngine(env, network, search_config)
        result = engine.search()
        # Curriculum: a solved game only. A search that ended far from a
        # statistical fit carries more noise than signal in its visit counts.
        solved = result.best_state.stats.chi2_reduced <= sp.target_chi2_max
        if solved:
            examples.extend(engine.training_examples_as_tuples())

        if (game + 1) % int(sp.train_every) == 0 and examples:
            buffer = examples if sp.buffer_size <= 0 else examples[-int(sp.buffer_size):]
            losses = network.train(
                buffer,
                epochs=sp.train_epochs,
                batch_size=sp.batch_size,
                learning_rate=sp.learning_rate,
                rng=train_rng,
            )
            report.losses.append(float(losses[-1]))

        if (game + 1) % int(sp.eval_every) == 0 or game == 0 \
                or game == int(sp.n_games) - 1:
            _evaluate(game + 1)

        if progress is not None:
            progress(game + 1, int(sp.n_games), f"self-play game {game + 1}")

    report.n_games = game + 1
    report.n_examples = len(examples)
    return network, report
