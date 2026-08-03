---
type: PRD
prd: "74"
title: "PRD-74: FCS kinetics model — full mode vs fast (eigenvalue-only bunching) mode"
description: Give the FCS kinetics model a fast path that skips the expensive spatial S1-population solve and 3D autocorrelation and computes only the eigenvalue-based photokinetic bunching factor — with the correct brightness included — trading the saturation volume expansion for near-instant evaluation.
status: done
phase: "complete"
resource: chisurf/core/models/fcs/
tags: [prd, fcs, kinetics, saturation, bunching, performance, eigenvalues]
timestamp: '2026-08-02T00:00:00Z'
---

# Summary

`FCSKineticsModel._saturated_shape` (in
`chisurf/core/models/fcs/kinetics.py`) evaluates the saturated shape through
`chisurf.core.fluorescence.fcs.saturation.saturated_curve_shape`: it solves
the steady-state S1 population **at every point of the (r, z) detection
volume** (`steady_state_population_matrix`), spatially autocorrelates that
profile (`fcs_numerical_g_diff`, the 3D-FFT-heavy step), and only then applies
the photokinetic bunching factor (`compute_bunching_factor`). The spatial
solve is what makes a cold evaluation cost ~155 ms (cached to ~0.4 ms for
N/b-only updates). That cost is only worth paying when the *spatial* signature
matters — i.e. the saturation volume expansion `V_0/V_eff` at high power.

This PRD adds a **fast mode**: skip the spatial S1-population solve and the 3D
autocorrelation entirely, and compute only the eigenvalue-based bunching factor
for the photokinetic scheme, with the **correct brightness included**. The
user-facing switch is a mode choice (full/fast) on the model; the physics is
shared with the full path so the two agree in the appropriate limit.

# Motivation

The saturation model is the expensive, high-fidelity path. But a large class of
FCS uses does not need the spatial solve:

- **Moderate-power fits**, where the volume expansion `V_0/V_eff` is still
  close to 1 and the photokinetic relaxation (triplet/bunching) is the quantity
  being fitted.
- **Screening / grid search / global fits** that iterate the model thousands of
  times — a ~155 ms cold path times thousands of evaluations is the difference
  between interactive and overnight.
- **FRET wiring** ([PRD-73](prd-73.md)) and species-mixture amplitudes
  ([PRD-75](prd-75.md)), where brightness enters through the bunching factor
  and where a fast path keeps the wiring testable.

The eigenvalue-based bunching factor already exists and already carries the
brightness correctly: `compute_bunching_factor` forms `K = K_dark +
k_exc_0*K_exc` at the **peak** excitation rate, solves its eigensystem, and
builds `X(tau) = Σ_m c_m exp(λ_m tau)` with `c_m = (q·v_m)(v_m⁻¹·(q·p_eq))` —
the brightness appears in both the `left` and `right` factors, so a species
with different `Q_i` relaxes differently. Fast mode reuses exactly that, with
`q = StateBrightness.array`, and applies the Gaussian diffusion term
unchanged. What it does **not** compute is the volume expansion — that is the
approximation being made, and it must be stated to the user.

# Design

## 1. A mode switch, not a second model

`FCSKineticsModel` gains a `saturation_mode` property (`"full"` |
`"fast"`), selectable in `kinetics.view.json` next to the power/`n_states`
controls (a `choice` binding to the new attribute, like `diffusion_mode`).
Both modes share the same parameter groups — the rate matrices, the
brightnesses, the power, the diffusion term — so switching modes never
invalidates user-entered parameters.

- **full** (default, unchanged): the current `_saturated_shape` → spatial
  solve + 3D autocorrelation + bunching, carrying `V_0/V_eff`.
- **fast** (new): the analytic `GaussDiffusion.g_diff` diffusion shape
  multiplied by `compute_bunching_factor` at the peak excitation rate, with no
  volume expansion (`V_0/V_eff := 1`).

The existing cache and re-entrancy guard apply to both; the fast path is so
cheap it may not need the shape cache at all (the cache key already captures
`power/extinction/matrices/brightness`, so it works either way).

## 2. The correct brightness is included — this is not the old "no brightness" bug

The one non-negotiable: fast mode must reproduce the full mode's brightness
dependence in the bunching factor. The implementation must therefore call the
same `compute_bunching_factor(k_exc_peak, dark_matrix, exc_matrix,
brightness, tau_s)` that the full path calls — passing
`self.saturation.brightness.array` — and must **not** drop `q` to a ones vector
(that was the historical "brightness-invisible" failure mode fixed in the
saturation model, see `okf/log.md` 2026-08-02). A guardrail test asserts that
changing `StateBrightness` values changes the fast-mode curve.

## 3. Agreement between modes

In the limit of weak saturation (power → 0, or a scheme with no power-dependent
terms), `V_0/V_eff → 1` and the bunching factor → 1, so fast and full must
converge to the same `GaussDiffusion` analytical shape. That is the contract:

- **Weak-power test**: at `P → 0` (and/or `sigma → 0`), `|g_fast - g_full|` is
  below a small relative tolerance across the lag grid.
- The fast mode at `P = 0` must equal the analytical Gaussian shape exactly
  (same as full mode's documented `P = 0` behaviour).

Where they are allowed to differ is the saturation expansion at high power —
that is the point of the mode.

## 4. Honest disclosure of the approximation

The `kinetics.view.json` info text (next to the mode switch) must state what
fast mode omits — "no detection-volume saturation expansion; photokinetic
bunching included" — so a user does not fit high-power data with fast mode and
misinterpret the amplitude. The `equation_html()` renderer reflects the active
mode, as it already does for diffusion/saturation.

# Status

**Done** (2026-08-03). Both modes implemented in `FCSKineticsModel`, and the
numerical path they share was rewritten in the same change — it had never
executed:
`chisurf/core/fluorescence/fcs/saturation.py`'s numba kernel unpacked a 2-D
array into three names, so every call to `fcs_numerical_g_diff` raised
`TypingError` and the calculator, its CLI, its RPC service and full mode all
crashed. The reciprocal-space quadrature was also wrong (an axial *real*-space
step used where the k-space step belongs), so the amplitude — i.e. the fitted
`N` — was off by orders of magnitude. Both fixed and pinned by
`test/test_fcs_saturation_physics.py`, which compares against the analytical
Gaussian curve, Parseval's theorem, the closed-form triplet-bunching expression
and the curve's own half-decay time.

The mode contract holds as specified: at `P = 0` **both** modes return the
analytical Gaussian exactly, because the fabricated fallbacks that made that
impossible (a 1 mW substitute power in the profile solve, a 1e5 Hz substitute
excitation rate in the bunching factor) are gone. `saturation.active` now means
"the excitation power is non-zero" rather than "a scheme exists" — the latter
was always true, so the analytical branch was dead code and the view text
promising it was false.

Related: [PRD-62](prd-62.md) (FCS model consolidation — `FCSKineticsModel`,
the cache, the re-entrancy guard this mode builds on),
[PRD-73](prd-73.md) (FRET wiring — brightness source feeding
`StateBrightness.array`, consumed by both modes),
[PRD-75](prd-75.md) (brightness → amplitude for species mixtures, which the
fast path helps test).
