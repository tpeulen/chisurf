---
type: PRD
prd: "99"
title: "PRD-99: Calibrating the cheap model against the expensive one — linker length and rigidity as variables, AV as the thing that must reproduce them"
description: An AV is a uniform distribution over a hard-sphere-accessible volume with no energetics and an infinitely flexible linker; FPSIMP's PMI Monte Carlo is a Boltzmann ensemble with excluded volume and connectivity. Nobody has ever asked the two for the same number on the same structure. Make linker length and rigidity explicit variables of the expensive simulation, make a run cheap enough to sweep them, and fit AV's nine parameters so the cheap model reproduces the expensive one — including a map of where it provably cannot, which is the scientific result rather than a failure.
status: proposed
resource: /Users/tpeulen/dev/imp.bff
tags: [prd, imp.bff, fpsimp, av, sampling, calibration, linker, kappa2, fret]
timestamp: '2026-08-11T00:00:00Z'
---

# PRD-99: Calibrating the cheap model against the expensive one

## The claim

`IMP::bff::AV` is used because it is cheap: a grid path search produces a dye
cloud in well under a second, and every FRET screening run in the stack rests
on it. FPSIMP samples the same physical situation the expensive way — a PMI
Monte Carlo ensemble with connectivity and excluded volume, 100 000 frames of
it. **The two have never been asked for the same number on the same
structure.** Until they are, "the AV approximates the real linker" is a claim
nobody in this stack can support, and the nine AV parameters are set by
convention rather than by evidence.

This PRD makes the expensive simulation *parameterised* in the two variables
that decide whether the approximation holds — **linker length** and
**rigidity** — makes a run cheap enough to sweep them, and fits the AV to the
result.

## What exists (measured 2026-08-11)

**The AV side: nine parameters, no calibration.** `AV.h:175-183` declares
`linker_length` (default 20.0), `radius1/2/3`, `linker_width` (0.5),
`allowed_sphere_radius` (1.5), `contact_volume_thickness` (0.0),
`contact_volume_trapped_fraction` (-1) and `simulation_grid_resolution`
(1.5). Two of these — the contact-volume pair — exist precisely to
redistribute density toward the surface (the AV+/ACV correction) and are
**off by default**, so the shipped model is a plain uniform AV.

**The expensive side already measures the right observable.**
`fpsim/measure.py` walks RMF frames and computes, per frame, the
inter-site **distance and κ² from four 3D coordinates**
(`measure.py:132`, `204`), with `distance_mean`/`distance_std` over the
trajectory and `sites` a declared parameter. An expensive run therefore
already emits the `R_DA` and κ² distribution an AV pair would have to
reproduce. The comparison machinery is half-built, on the expensive side.

**Neither knob the user names is a variable.** `run_imp_sampling`
(`fpsim/sampling.py:135`) takes `steps_per_frame`, `frames`, `k_center`,
`membrane`, `membrane_weight`, `barrier_radius`, `membrane_seqs`, `seed` —
and nothing else. Linker length is whatever the AlphaFold segmentation
produced; rigidity enters only as `plddt_rigid` (70.0), a **pLDDT
threshold** deciding which residues become rigid bodies — a property of the
prediction, not a physical parameter anyone can dial. `min_linker_len` (10)
is a *detection* threshold for how long a disordered stretch must be to be
modelled as beads, not a linker's length.

**A run costs a million Monte Carlo steps.** `frames = 100 000` ×
`steps_per_frame = 10` through `IMP.pmi.macros.ReplicaExchange`
(`sampling.py:381-388`). A sweep of, say, 6 lengths × 5 rigidities × 3
attachment sites is 90 runs of that, which is why nobody has swept it.

**There is a place to declare parameters, and a test that guards it.**
`fpsim/parameter_catalog.json` holds 44 declared parameters (name, type,
default, group, help); `fpsim/parameters.py` reads it; and
`tests/test_parameter_contract.py` fails when `PipelineConfig` and the
catalog disagree. The catalog exists **because** defaults drifted once and
produced a plausible wrong run rather than an error (FPS-05:
`barrier_radius` was 800 in one place and 100 in the other). New knobs have
a defined home and a test that punishes adding them sloppily.

## The precondition nobody should skip

`AV::set_av_parameter` (`AV.cpp:203-215`) reads `radius1/2/3` from JSON into
a `Vector3D` and — in the **committed** tree — writes
`set_radius2(r[0]); set_radius3(r[0])`. Every three-radius dye loaded from
an `fps.json` therefore becomes a one-radius dye. A fix is sitting in the
working tree uncommitted (`r[1]`, `r[2]`).

This is not a side note for this PRD, it is a precondition: fitting AV radii
against expensive simulations while two of the three are silently
overwritten would not produce a bad fit — it would produce a *good-looking*
one, because the optimiser would absorb the discrepancy into
`linker_length`, and the calibration would be published as three radii that
were never independently varied. **Land the fix before any number in this
PRD is measured.**

## Requirements

1. **Linker length and rigidity become declared parameters of a run.** Added
   to `parameter_catalog.json` with `PipelineConfig` agreement (so the
   contract test covers them):
   - `linker_length` — the number of residues in the modelled linker,
     overriding what segmentation inferred.
   - `linker_rigidity` — how the linker's flexibility is realised. Not a
     free-floating float: it must map onto something PMI can build, which
     means either bead resolution plus an angular/`ConnectivityRestraint`
     stiffness term, or a persistence length realised as harmonic angle
     restraints along the bead chain. Whichever is chosen, the parameter's
     `help` text states the physical quantity and its units, because a
     dimensionless "stiffness 0…1" is how a calibration becomes
     unreproducible.
2. **A cheap mode: the label subsystem, not the whole fusion.** The
   calibration system is one rigid body, one linker and one label —
   the protein interior is irrelevant to where the dye can reach. A run
   restricted to that subsystem, with the rigid body frozen, is orders of
   magnitude cheaper than the full multimer pipeline and is the *same*
   physical question. This is what "make FPSIMP cheap" means here; the
   production pipeline is not touched.
3. **Stop on convergence, not on a frame count.** `frames = 100 000` is a
   guess that is simultaneously too many for a short flexible linker and
   possibly too few for a stiff one. The sweep runs until the observable
   stops moving — the mean position and covariance of the label cloud (see
   requirement 4) are a natural convergence monitor because they are the
   very quantities being compared. Report the frames actually used; a
   sweep cell that failed to converge is reported as such, never averaged
   in silently.
4. **Compare at two levels, cheap first.** The label cloud's **mean and
   covariance** are the low-order comparison: an AV that gets the centre and
   the spread wrong cannot get a distance distribution right, and this test
   costs nothing. It requires [PRD-94](prd-94.md) — an `AV` that actually
   calls `set_gaussian()` — which is why these two PRDs are worth doing in
   order. The full comparison is the `R_DA` distribution (and κ², which
   `measure.py` already produces) for a labelled pair, compared as
   distributions: mean, width, and a distributional distance, not means
   alone. Two clouds can share a mean and disagree everywhere.
5. **Fit the AV, and say what was fitted.** For each (length, rigidity)
   cell, fit the AV parameters that are physically free — `linker_length`,
   `linker_width`, `allowed_sphere_radius`, and the contact-volume pair —
   to reproduce the expensive ensemble. The dye radii are *not* free
   parameters in this fit: they describe the fluorophore, which the sweep
   holds fixed. The deliverable is a **table**: physical linker → AV
   parameters, with residuals.
6. **A map of where the approximation holds, and where it cannot.** This is
   the honest core of the PRD. An AV's linker is infinitely flexible by
   construction — it is a path of a given length through free space, with
   no energy — so:
   - In the **flexible** limit, an AV with the right length should match
     well, and the fitted `linker_length` should track the physical one.
   - In the **stiff** limit (persistence length approaching or exceeding the
     linker length), the ensemble samples a *shell*, not a ball. No choice
     of AV parameters produces a shell from a uniform accessible volume.
     The result there is a documented **boundary**, not a fudged fit.
   - Where the expensive ensemble shows **surface enrichment**, the
     contact-volume parameters are the intended absorber, and this is the
     first evidence-based setting of `contact_volume_trapped_fraction` in
     the stack — a parameter currently shipped as `-1`.
   A fit reported without its residual, or a cell where the best fit is
   still poor reported as a success, defeats the entire exercise.

## Acceptance criteria

1. A run is reproducible from its declared parameters alone: same catalog
   values plus `seed` gives the same ensemble statistics, and the contract
   test passes with the new parameters declared in both places.
2. The cheap mode reproduces the full pipeline's label-cloud mean and
   covariance for at least one real construct, within the converged
   ensemble's own uncertainty — otherwise "cheap" has changed the physics
   rather than the cost. Report the speed-up measured, not estimated.
3. The sweep completes over at least 5 linker lengths × 4 rigidities for
   one construct, with per-cell convergence reported.
4. For every cell, the fitted AV's mean position and covariance are compared
   with the expensive ensemble's, and the `R_DA` distributions are compared
   as distributions.
5. The flexible-limit claim is quantitative: fitted `linker_length` versus
   physical linker length, with a stated agreement.
6. The stiff-limit boundary is stated as a number — the rigidity beyond
   which no AV parameter set reproduces the ensemble within a stated
   tolerance — rather than as prose.
7. The resulting parameter table is committed as data, not prose, so an
   `fps.json` author can look up a linker and get AV parameters with a
   provenance.

## Non-goals

- **Changing the AV algorithm.** This PRD measures and calibrates the model
  that exists. If the map in requirement 6 shows a whole regime the AV
  cannot represent, *that finding* motivates a future model — it is not
  this PRD's job to invent one.
- **The production FPSIMP pipeline.** ColabFold, the worker, the web UI and
  the multimer path are untouched; the cheap mode is an addition beside
  them.
- **Re-deriving κ².** `measure.py` computes it and imp.bff owns the
  functions; this PRD consumes both.

## Placement

Per [PRD-93](prd-93.md)'s rule — coordinates in, so imp.bff — the AV side,
the comparison statistics and the fitted table belong to **imp.bff**. The
sampling knobs and the cheap runner belong to **fpsimp**, consistent with
[PRD-96](prd-96.md)'s line: a prediction job or a queue stays in fpsimp,
while what owns coordinates moves up. This document lives in the shared
bundle because it spans two repositories, as `imp.bff/AGENTS.md` requires.
