---
type: PRD
prd: "94"
title: "PRD-94: An AV is a Gaussian that means it — mean and covariance from the path-map density"
description: imp.bff's AV decorator derives from IMP::core::Gaussian but never sets the Gaussian — every accessible volume claims an identity covariance whatever its shape. Compute the density-weighted first and second moments of the path-map cloud on every resample and write them through set_gaussian(), fixing the biased mean along the way.
status: proposed
resource: /Users/tpeulen/dev/imp.bff
tags: [prd, imp.bff, av, pathmap, gaussian, accessible-volume]
timestamp: '2026-08-10T00:00:00Z'
---

# PRD-94: An AV is a Gaussian that means it

## The assertion

An accessible volume computed by a path map **is also a Gaussian in IMP**: the
particle must carry the mean position *and* the covariance matrix of the dye
cloud, not just claim the type. Today the claim is made and the content is
missing.

## What the code does today

- `AV` derives from `IMP::core::Gaussian` (`imp.bff/include/AV.h:111`), and
  `do_setup_particle` calls `IMP::core::Gaussian::setup_particle(m, pi)` with
  **no `Gaussian3D` argument** (`AV.h:216-218`) — a default Gaussian.
- Nothing in the repository ever calls `set_gaussian()`. Grepping
  `src/AV.cpp` and `src/PathMap.cpp` for `Gaussian|covar|variance` returns
  nothing. So every AV particle reports an identity-shaped Gaussian regardless
  of the linker length, the label site, or the obstacles around it.
- The mean *does* reach the particle, but only as XYZ: `resample()` ends with
  `set_coordinates(get_mean_position())` (`src/AV.cpp:199`). The covariance
  never exists anywhere.
- The cloud the moments must summarize is already exposed:
  `PathMap::get_xyz_density()` returns `Vector4D` rows `(x, y, z, w)` with the
  tile density as weight (`include/PathMap.h:320`), and contact-volume
  reweighting is already folded into those densities before the mean is taken.

## A defect the moment computation must fix

`AV::get_mean_position(include_source)` (`src/AV.cpp:115-131`) seeds
`sum = 1.0` **unconditionally**. With `include_source=false` the weighted mean
is divided by `1 + Σw` instead of `Σw`, biasing it toward the origin. With
`include_source=true` the source enters the numerator with weight 1 but the
denominator gains 2. Either way the "mean position" is not the mean of
anything. The replacement is the plain density-weighted first moment; whether
the source point belongs in it at all is answered below (no).

## Requirement

After every `resample()`, the particle's Gaussian is the density-weighted
first and second central moments of the path-map cloud:

- μ = Σ wᵢ xᵢ / Σ wᵢ over all tiles with wᵢ > 0
- Σ = Σ wᵢ (xᵢ − μ)(xᵢ − μ)ᵀ / Σ wᵢ

written through the existing IMP machinery — no new math in imp.bff:
`IMP::algebra::get_gaussian_from_covariance(cov, μ)`
(`algebra/Gaussian3D.h:58`) does the eigendecomposition into a reference
frame + three variances, and `IMP::core::Gaussian::set_gaussian(g)`
(`core/Gaussian.h:109`) stores it. `IMP::algebra::get_covariance(g)` is the
exact round-trip for tests.

Rules:

1. **The Gaussian describes the dye cloud, not the attachment atom.** The
   source coordinate does not enter the moments. `get_mean_position()`'s
   `include_source` default was a hack around the bias bug and both are
   retired together; `get_mean_position()` becomes a thin call to the same
   moment pass, and XYZ, the Gaussian mean, and `get_mean_position()` are the
   same number by construction.
2. **One pass, one place.** The moments are computed where
   `set_coordinates(get_mean_position())` sits today — at the end of
   `resample()`, after the contact-volume density edit — so a moved label
   site invalidates mean and covariance atomically. No caching beyond what
   the particle attributes already are.
3. **Double accumulators, two-pass or shifted.** Tile coordinates are floats
   on a grid far from the origin; a naive single-pass E[x²]−E[x]² loses the
   small variances. Accumulate in double, centered on the first accepted
   tile or two-pass.

## Why (the consumers)

- **Overlap scoring against EM/GMM densities**: a populated
  `core::Gaussian` is what `IMP.em` GMM utilities and bayesianem-style
  restraints consume. An AV that is a real Gaussian participates without a
  bridge.
- **Moment-based distance approximations**: mean and covariance per AV give
  closed-form first approximations of inter-dye distance moments — a cheap
  screen before the sampled `DYE_PAIR_DISTANCE` paths (`AV.h:51`), and honest
  error bars on `R_mp` vs `R_DA`.
- **Visualization**: an AV exports to RMF/ChimeraX as an ellipsoid without
  dumping the grid — the shape of the volume at a glance.
- **Placement** ([prd-93](prd-93.md)): input is coordinates, so this is
  imp.bff code entirely — committed in `../imp.bff`, never the IMP checkout
  (golden rule in [references/imp-ecosystem](../references/imp-ecosystem.md)).

## Out of scope

- Replacing the grid: the Gaussian is a *summary*. Sampled distance
  distributions, `AVNetworkRestraint`, and the path-map machinery keep using
  the cloud.
- Multi-component GMM fits for L-shaped or split AVs. A single Gaussian is
  deliberately crude; if a consumer needs better, a k-component fit over the
  same `get_xyz_density()` rows is a follow-up PRD, not this one.
- tttrlib: no photons are involved.

## Acceptance criteria

1. After `resample()`, `get_covariance(av.get_gaussian())` equals the numpy
   covariance of `get_xyz_density()` (weights included, source excluded) to
   float precision, on a real PDB test case in `imp.bff/test/`.
2. A free-dye AV (no obstacles, radii 0) matches the analytic uniform-ball
   moments: μ at the source, Σ ≈ (L²/5)·I for linker length L, within grid
   tolerance.
3. XYZ coordinates == Gaussian mean == `get_mean_position()` after every
   resample; moving the source and resampling updates all three.
4. The `include_source`/`sum=1.0` bias is gone; the numeric change to
   existing results is documented in the imp.bff changelog (means shift by
   O(1/Σw) — small for real maps, but nonzero).
5. An RMF export of a decorated AV shows a finite ellipsoid, not a unit
   sphere.
