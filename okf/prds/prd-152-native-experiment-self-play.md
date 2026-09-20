---
okf_version: "0.2"
status: active
---

# PRD-152: native experiment-generating self-play for residual-aware model search

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
