---
okf_version: '0.2'
status: active
type: PRD
title: 'PRD-152: native experiment-generating self-play for residual-aware model search'
description: The model-search policy is trained on newly generated experiments, not
  only on perturbations of an already bound curve. is mined for physics and parity
  fixtures only; it is not a runtime dependency, s
tags:
- prds
timestamp: '2026-09-23T21:13:31+02:00'
---

# PRD-152: native experiment-generating self-play for residual-aware model search

## Where to pick this up

1. Measure: **Gate margin at budget 8 is one run.**
   `$E/bin/python test/mcts/bench_action_policy.py --measurements 30 --seed 91000`
   from `~/dev/imp.bff` (`$E` = arm64 env, IMP built from `../imp`, see
   [imp-local-build](../workflows/imp-local-build.md)); all games ship
   296/315/324 vs priors 277/302/319 of 330. Trap: comparing with the
   pre-2026-10-10 benchmark needs `--games` restricted to its nine games (the
   rng stream is shared across games in sorted order); there one
   `fcs_analytical` measurement at budget 8 is lost (266 vs 267) by every
   candidate tried (hidden 16/32/32-16, five seeds, temperature 3/4). The FCS
   family has the lowest held-out accuracy (0.69); more FCS episodes or an FCS
   kind-specific feature is the next lever. Retraining from saved episodes
   takes 2 min (`--episodes-file`); playing them takes 36 min, 22 of it
   `tcspc_anisotropy`.
2. Blocked: **ChiSurf's pixi env still runs the old bff** (pypi git dep, commit
   e6137af): the old 71-wide policy and no fit-settings space. Until imp.bff
   `dev` is pushed and the env rebuilt, `test_mcts_fit_settings.py` and the
   fit-settings test in `test_mcts_execution.py` skip there; they pass in the
   arm64 env. The checkbox refuses with `fit_settings_unavailable` on an old bff.
3. Open: **Three FRET families play no episodes** (`tcspc_fret_ising_chain`,
   `saw_nu`, `worm_like_chain`: 0 episodes, ising costs 380 s). Their moves
   offer no choice from the bound fixture; fix the moves or drop them from
   `_games.GAMES`.
4. Open: **from the contract:** invalid-acquisition validation before
   simulation; one photon stream reduced to several observables.

## Decision

The model-search policy is trained on newly generated experiments, not only on
perturbations of an already bound curve. `ucfret` is mined for physics and
parity fixtures only; it is not a runtime dependency, simulator, or training
surface. The production path is:

```
scenario sampler (BFF) -> photon stream (tttrlib) -> native reductions
-> BFF fit/MCTS -> residual + validity + corrective-action labels -> MlpCore
```

No Python callback may run per episode, fit, residual, or policy inference.

## Scenario contract

A versioned scenario names the acquisition, not a particular fitting family:

- detector routing and channel roles (`DD`, `DA`, `AA`, `VV`, `VH`, ...);
- excitation schedule: CW, ALEX, or PIE (including periods/windows/markers);
- per-channel IRF, micro-time resolution, detector background/scatter, dead
  time/pile-up/DNL where the associated fitting family represents them;
- molecular species: brightness per laser/channel, donor/acceptor lifetime,
  FRET efficiency or rate, quenching, rotational anisotropy, diffusion and
  state-transition matrix;
- photon budget, deterministic simulator seed and reduction recipes.

`tttrlib::SimEngine` is the simulator of record: its per-laser `q_alex`,
micro-time `SimDecay`/IRF and delay, routing channels, background decay,
anisotropy, diffusion and kinetics cover this contract. BFF owns the scenario
sampler and labels; tttrlib does not learn model-search semantics.

## Episode truth and policy targets

One episode samples a physically valid full scenario and hides one or more
mechanisms from the fitted parent. It produces:

1. photon stream plus a native provenance document containing all sampled truth;
2. model-facing reductions (decay, detector/polarization blocks, MFD/PIE burst
   summaries, correlation) with the exact masks and uncertainty model;
3. the parent fit's concatenated signed weighted residual, block boundaries and
   modality/presence metadata;
4. a one-hot corrective action from the declared transition graph.

The policy input is not a raw curve. It is fixed-width residual profiles per
observable block, an explicit block-kind token, a valid-bin mask, log photon
budget, timing/IRF metadata and channel/excitation availability bits. Missing
blocks are zero-filled *and masked*, never indistinguishable from a flat fit.

The `NeuralNet` outputs logits in a global action vocabulary. At a state, BFF
restricts and renormalizes those logits to legal actions before PUCT.

## Invalid and unidentifiable experiments

An NN is not the numerical safety layer. Native validation rejects non-finite
or negative physical rates/counts/variances, invalid periods or bin widths,
impossible routing, inconsistent dimensions/masks, and missing required IRFs
before simulation or fitting. These are labelled `invalid_acquisition` and do
not enter a structural-policy batch.

A distinct terminal policy outcome, `request_information`, covers experiments
that are syntactically valid but cannot support the proposed model: absent AA
photons for an acceptor-excitation correction, no polarization pair for an
anisotropy action, insufficient photons, or a rank-deficient/ill-conditioned
fit. It must be surfaced to ChiSurf with the missing observable, not converted
into an arbitrary structural move.

## Curriculum and gates

1. **TCSPC:** one/two lifetime components, IRF shift, scatter, background and
   photon budget. Gate: held-out residual signature -> corrective action
   accuracy exceeds static priors, while invalid cases never select a fit.
2. **Polarized TCSPC:** VV/VH/VM joint residual blocks, `g`, rotational
   depolarization and per-channel IRFs. Gate: action labels remain invariant to
   channel ordering and refuse missing polarization metadata.
3. **smFRET/MFD:** DD/DA/AA, leakage/direct excitation/gamma/background,
   FRET/quenching and burst selection. Gate: recovered corrective action from
   held-out simulated photon streams and each reduction equals the ordinary
   analysis reduction.
4. **PIE/ALEX:** prompt/delayed micro-time or alternating macro-time windows,
   markers and per-laser brightness. Gate: swapping excitation labels fails;
   valid relabeling is invariant.
5. **Mixed curriculum:** domain-randomized all-modalities batch, held-out
   instrument profiles and photon budgets. Promote only if every earlier gate
   remains green; no aggregate metric may hide a failing modality.

## First implementation boundary

TTTRLib already installs its simulation headers flat as `tttrlib/SimEngine.h`
and exports the aggregate CMake target `tttrlib::tttrlib`. BFF's historical
dependency finder treats tttrlib as header-only, however, and therefore cannot
link `SimEngine`. The first code change is in BFF's build integration: consume
that exported target (with the simulation module enabled), then add a compact
C++ scenario/reduction adapter and multi-block policy features. Do not include
tttrlib source by relative path or invoke its Python binding from BFF.

## Implementation status (2026-09-23)

Landed in bff (see `imp.bff/okf/validation/model-search-strategy.md`, "One
action policy for every game"):

- The first boundary above is done: bff's optional `dependency/tttrlib`
  links `tttrlib::tttrlib`, and `IMP.bff.PhotonExperiment` runs `SimEngine`
  scenarios in native memory (`simulate`, `record_pattern`).
- Self-play, labels and training are native (`ModelSearchSelfPlay`,
  `ModelSearchPolicyData`, `train_action_policy`); the network is bff's own
  `MlpCore`, no longer a vendored tttrlib copy (`bff.neural_net` documents).
- **Deviation: no global action vocabulary.** The network scores each
  (state, move) pair from family-agnostic features and multiplies the declared
  prior; one network therefore serves every family, including ones added
  later, with no vocabulary to extend. Legal-move restriction is structural.
- Curriculum coverage today: TCSPC lifetime, polarised and VV/VH/VM
  anisotropy, FRET distance families, FCS, generic equations, and a global
  kinetic scheme over FCS + TCSPC (`kinetic_fcs_tcspc`). Count data are
  recorded as photons per curve; smFRET/MFD bursts and PIE/ALEX are not yet
  games.
- Gate: `test/mcts/bench_action_policy.py`, strict (never fewer right than
  the declared priors at any budget). Candidates 1-5 failed it. **Candidate 6
  passed and ships** (imp.bff 08742ec9, `data/model_search/policy/`): on 270
  fresh runs per budget it matches or beats the priors at budgets 2, 4 and 8
  with 11-23% fewer structures evaluated, at temperature 3, which the document
  carries. ChiSurf's default `action_policy="shipped"` now runs it.
- Block-aware state features (the worst member block of a joint residual) are
  in the shipped policy.

## Closing the open items and a second action space (spec, 2026-10-10)

Status: **done 2026-10-10** (imp.bff b7a7049c1, policy 13a19829d; chisurf
commit in `okf/log.md`). Each item names where it landed in bff and how it is
proven.

1. **Modality token.** `ModelSearchBlockKind` (`generic, tcspc, polarized,
   fcs, burst_mfd, pie_alex`). A description declares
   `"dataset_kinds": {<dataset>: <kind>}`; `ModelSearchSpec::build` reads the
   kind of every joint member's bound dataset, in block order, into
   `FittingModelSearchProblem::set_structure_block_kinds`. The policy state
   gains a one-hot of the worst block's kind and log of the number of distinct
   kinds (state width 71 -> 78). Every shipped family declares its kinds. The
   width change invalidates the shipped network; it ships again only after a
   retrain passes the bench gate.
2. **`request_information`.** A move may say `"requires": [<dataset>]`. When
   one is unbound the move is not offered but recorded
   (`add_withheld_action`). `ModelSearchResult::get_outcome()` is
   `selected | request_information | cancelled`: `request_information` when
   the best state is not an acceptable fit (`acceptable_above`) and a move out
   of it was withheld; `get_missing_observables()` names the datasets. ChiSurf
   warns with the missing observable and keeps the user's model.
3. **smFRET/MFD and PIE/ALEX games.** `smfret_mfd` (DD, DA; AA optional) and
   `pie_alex` (prompt DD/DA, delayed AA): FRET species share quenched donor
   lifetimes across channels; an acceptor term adds the acceptor lifetime to
   DA. In `smfret_mfd` that move requires `decay_aa`. A stage present only when
   a dataset is bound is written `"when_bound"` (nodes, joint members, free
   entries), so every topology is scored on the same data. Both are self-play
   games: the generating structure's curves are recorded as photons through
   TTTRLib, so each episode's answer is known.
4. **Fit-settings action space.** `ModelSearchFitSettings` (algorithm,
   ftol/xtol/gtol, maxfev, step factor, start `declared|primary|parent`,
   bounds on/off). `set_action_space(ACTION_SPACE_FIT_SETTINGS)`: a state is
   a structure fitted with one candidate; structural moves keep the
   candidate, settings moves refit the same structure with another one
   (declared prior share 0.25). Scored by the same reward and read by the same
   residual features. The tree tells states apart by
   `ModelSearchState::get_search_key()` (`<structure>|<settings>`); the
   structure key stays the structure. Default candidates keep bounds on.
   ChiSurf: `prepare_model_search(fit, search_fit_settings=...)`, one
   checkbox in the fit controls.
5. **Retrain + gate.** `train_action_policy.py` over all games including the
   two new ones; `bench_action_policy.py` must match or beat the priors at
   every budget and the previously shipped benchmark's `right` counts.

Closed 2026-10-10 (section above): the modality token, `request_information`,
the smFRET/MFD and PIE/ALEX games and the retrained policy. Still open:
invalid-acquisition validation before simulation, and one full photon stream
reduced to several observables (the MFD/PIE games simulate each channel's
curve separately).
