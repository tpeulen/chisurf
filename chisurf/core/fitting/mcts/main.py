"""Execution script: synthetic 2-component decay → MCTS search → report.

Run as a module from the repository root::

    python -m chisurf.core.fitting.mcts.main [--sims 250] [--seed 7]

Without ``--train-games`` the search runs with uniform priors (reward-guided
exploration — the network-free fallback). With ``--train-games 30`` the
TCSPCNet is first trained by self-play on simulated decays (see
:mod:`chisurf.core.fitting.mcts.training`), and the final search uses it as
the policy/value guide; the report then shows the network's held-out learning
curve and its effect on the target decay.
"""

from __future__ import annotations

import argparse
import logging
from typing import Optional

import numpy as np

from chisurf.core.fitting.mcts.environment import EnvConfig, FitEnv, ModelStructure
from chisurf.core.fitting.mcts.mcts import MCTSConfig, MCTSFittingEngine
from chisurf.core.fitting.mcts.network import TCSPCNet
from chisurf.core.fitting.mcts.training import (
    SelfPlayConfig,
    SimulateConfig,
    self_play_train,
)

logger = logging.getLogger(__name__)


def make_synthetic_measurement(seed: int = 7) -> "tuple":
    """A 2-component TCSPC decay with scatter, background and an IRF shift.

    Ground truth: τ = (1.1, 3.9) ns, intensity fractions (0.35, 0.65),
    3 % prompt scatter, ~2 % dark background, +0.6 channel colour shift,
    2·10⁵ photons, 256 channels at 0.032 ns — the canonical "textbook decay"
    a model selector must decompose without being told how many components
    there are.
    """
    from chisurf.core.fluorescence.tcspc.convolve import periodic_shift
    from chisurf.core.fluorescence.tcspc.irf import synthetic_irf
    from chisurf.core.fluorescence.decay import (
        afterpulse_decay_pattern,
        sample_decay_shot_noise,
        synthetic_decay,
    )

    rng = np.random.default_rng(seed)
    n_channels, dt = 256, 0.032
    time_ns = np.arange(n_channels) * dt
    irf = synthetic_irf(time_ns, center_ns=3.0, fwhm_ns=0.15, norm=True)

    true_taus = np.array([1.1, 3.9])
    true_fractions = np.array([0.35, 0.65])
    scatter = 0.03
    bg_fraction = 0.02
    shift = 0.6  # channels

    shifted = periodic_shift(irf, shift)
    species = [
        synthetic_decay(n_channels, [float(t)], bin_width=dt, irf=shifted, normalize=True)
        for t in true_taus
    ]
    expected = np.zeros(n_channels)
    for f, pattern in zip(true_fractions, species):
        expected += (1.0 - scatter - bg_fraction) * f * pattern
    expected += scatter * shifted
    expected += bg_fraction * afterpulse_decay_pattern(n_channels)

    decay = sample_decay_shot_noise(expected, photon_count=2.0e5, rng=rng)
    return decay, irf, dt, true_taus, true_fractions, scatter, bg_fraction, shift


def run(
    sims: int = 250,
    seed: int = 7,
    train_games: int = 0,
    obs_length: int = 128,
    max_components: int = 4,
    backend: str = "numpy",
    device: str = "cpu",
    load_net: Optional[str] = None,
    save_net: Optional[str] = None,
) -> dict:
    """Generate the synthetic decay, search the model space, print the result.

    Returns a summary dict (structure, parameters, statistics, and — after
    self-play — the training report) for programmatic use by tests and the
    GUI demo path.
    """
    decay, irf, dt, true_taus, true_fractions, scatter, bg_fraction, shift = \
        make_synthetic_measurement(seed)

    env_config = EnvConfig(max_components=max_components, obs_length=obs_length)
    mcts_config = MCTSConfig(n_simulations=sims)

    network: Optional[TCSPCNet] = None
    report_text = None
    if load_net is not None:
        network = TCSPCNet.load(load_net)
        print(f"loaded network weights from {load_net}")
    if train_games > 0:
        if backend == "torch":
            from chisurf.core.fitting.mcts.torch_backend import TCSPCNetTorch

            train_net = TCSPCNetTorch(
                obs_length=obs_length, seed=seed, device=device
            )
        else:
            train_net = TCSPCNet(obs_length=obs_length, seed=seed)
        train_net, report = self_play_train(
            train_net,
            sim_config=SimulateConfig(n_channels=256, bin_width=dt),
            env_config=env_config,
            mcts_config=mcts_config,
            self_play_config=SelfPlayConfig(
                n_games=train_games, sims_per_game=max(30, sims // 4), seed=seed
            ),
        )
        report_text = report.summary()
        weights_path = save_net or "tcspcnet_trained.npz"
        train_net.save(weights_path)
        print(f"saved network weights to {weights_path}")
        if backend == "torch":
            # Inference stays on the dependency-free NumPy net; the trained
            # weights cross over through the shared npz format.
            network = TCSPCNet.load(weights_path)
        else:
            network = train_net

    env = FitEnv(decay, irf, dt, config=env_config)
    engine = MCTSFittingEngine(
        env, network,
        MCTSConfig(n_simulations=sims, dirichlet_fraction=0.0),
    )
    result = engine.search()
    best = result.best_state

    print("=" * 72)
    print("MCTS model selection on a synthetic 2-component TCSPC decay")
    print("=" * 72)
    if report_text:
        print(report_text)
        print("-" * 72)
    print(f"search: {result.n_simulations} simulations, "
          f"{result.n_states_evaluated} states optimised, "
          f"reward improvement {result.improvement:+.1f}")
    print(f"action path: {' -> '.join(str(a) for a in result.best_path) or '(root is best)'}")
    print("-" * 72)
    print(best.describe())
    print("-" * 72)
    print(f"ground truth: taus {true_taus} ns, fractions {true_fractions}, "
          f"scatter {scatter:.1%}, background {bg_fraction:.1%}, "
          f"shift {shift:+.1f} ch")

    return {
        "result": result,
        "state": best,
        "structure": best.structure,
        "lifetimes": best.lifetimes.copy(),
        "fractions": best.intensity_fractions.copy(),
        "stats": best.stats,
        "true_taus": true_taus,
        "training_report": report_text,
    }


def main(argv: Optional[list] = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--sims", type=int, default=250,
                        help="MCTS simulations for the final search (default 250)")
    parser.add_argument("--seed", type=int, default=7,
                        help="seed of the synthetic measurement (default 7)")
    parser.add_argument("--train-games", type=int, default=0,
                        help="self-play training games before the search (default 0)")
    parser.add_argument("--obs-length", type=int, default=128,
                        help="network observation length (default 128)")
    parser.add_argument("--max-components", type=int, default=4,
                        help="largest component count the search may add (default 4)")
    parser.add_argument("--backend", choices=("numpy", "torch"), default="numpy",
                        help="self-play training backend (default numpy; torch for a GPU node)")
    parser.add_argument("--device", default="cpu",
                        help="torch device for training (default cpu; e.g. cuda)")
    parser.add_argument("--load-net", default=None,
                        help="network weights (.npz) to load for search guidance")
    parser.add_argument("--save-net", default=None,
                        help="where to save the trained network weights (.npz)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run(
        sims=args.sims,
        seed=args.seed,
        train_games=args.train_games,
        obs_length=args.obs_length,
        max_components=args.max_components,
        backend=getattr(args, "backend", "numpy"),
        device=getattr(args, "device", "cpu"),
        load_net=getattr(args, "load_net", None),
        save_net=getattr(args, "save_net", None),
    )


if __name__ == "__main__":
    main()
