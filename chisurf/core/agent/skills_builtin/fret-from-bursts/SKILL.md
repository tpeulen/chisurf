---
name: fret-from-bursts
description: >-
  Get a FRET efficiency and a distance from single-molecule burst data by way
  of the donor lifetime. Use when the user wants a distance, an efficiency or
  a structural number out of an smFRET measurement of freely diffusing
  molecules.
triggers:
  - smfret
  - single molecule fret
  - single-molecule fret
  - distance from bursts
  - burst fret
  - fret from bursts
  - mfd
  - multiparameter
  - sub-ensemble fret
  - determine the distance
  - distance by tcspc
  - distance from the lifetime
  - fret efficiency
  - inter-dye distance
experiments: [TCSPC, TTTR]
uses:
  - burst-search
  - burst-selection
  - sub-ensemble-decay
  - fret-from-decays
tools:
  - run_python
  - load_data
  - create_fit
  - set_irf
  - set_components
  - run_fit
  - get_fit
  - fit_report
---

# A distance from single-molecule bursts

This procedure composes four others. Each step is described where it belongs;
what follows is only how they fit together and what makes the answer
trustworthy.

```
burst-search        photon stream -> bursts, detector roles verified
burst-selection     -> proximity ratio -> the population, and its donor-only reference
sub-ensemble-decay  -> one donor decay per population, one shared IRF
fret-from-decays    -> lifetimes -> efficiency -> distance
```

## Why the donor-only population is not optional

The requested population gives τ_D(A). A lifetime alone is not an efficiency:
it means nothing without the **unquenched** donor lifetime τ_D(0) of the same
dye in the same buffer on the same instrument. `burst-selection` keeps the
low-PR population for exactly this, so take it even when the user asked only
about the FRET window, and say that you did.

## From lifetimes to a distance

Fit both decays identically, then use the **species-weighted** average
`<tau>x = sum(x_i tau_i) / sum(x_i)`:

```
E = 1 - <tau>x(DA) / <tau>x(D0)
R = R0 * (1/E - 1)^(1/6)
```

The intensity-weighted `<tau>f = sum(x_i tau_i^2) / sum(x_i tau_i)` is a
different quantity — what a steady-state measurement sees — and swapping them
is a silent error that biases every distance in the same direction.

**R0 must come from the user.** It depends on the dye pair, the refractive
index and κ². Ask, and state the value you used with the answer.

## Never constrain the answer you are measuring

**The FRET population's lifetime is the measurement. Do not fix it, link it,
or seed it from the donor-only value.** τ_D(A) has to come out of its own
data, freely.

A real model, given this procedure, fitted the donor-only decay to 1.85 ns and
then called `set_parameter` to **fix** the FRET population's `t0` at 1.85 ns
before fitting it. The fit was excellent (reduced chi-square 0.93) and the
conclusion was that the donor is unquenched, E ≈ 0 and the distance is
infinite. Every number was consistent and the answer was manufactured: freed,
that same decay fits to 0.86 ns and gives E = 0.53. Fixing a parameter to the
reference value guarantees the reference value.

The donor-only fit contributes exactly one thing to the FRET fit: **nothing**.
It contributes to the *arithmetic afterwards*. The only quantities the two
fits may share are ones that belong to the instrument rather than to the
molecule — the IRF, and the fit range.

Two more traps seen in the same run:

* If a fit needs an extra component, add it and let both lifetimes float; a
  second component is not an excuse to pin the first.
* Stay in the decay models (`Lifetime`). Photon-distribution (PDA) and
  correlation models answer different questions and do not take a
  sub-ensemble decay as input.

## The check that makes it a result rather than a number

> the efficiency from the donor lifetime should agree with the proximity ratio
> of the population you selected.

These are independent observables — an intensity ratio and a decay shape — so
agreement is real evidence that the burst indices, detector roles, decay
construction and shared IRF are all right. On the bundled sample a window of
PR 0.5–0.7 gives τ_D(0) = 1.82 ns, τ_D(A) = 0.86 ns, **E = 0.53**, and
R = 51 Å at R0 = 52 Å.

Before treating a disagreement as a finding, check that you did not cause it:
if τ_D(A) came back equal to τ_D(0), the usual reason is that it was fixed or
seeded there, not that the sample lacks FRET.

Disagreement is a finding, not noise:

* **lifetime-E well below PR** — acceptor-channel background or donor
  crosstalk is inflating PR; the lifetime is the more trustworthy of the two.
* **lifetime-E well above PR** — the donor is quenched by something that is
  not FRET (a nearby tryptophan, a bad label, aggregation). No distance can be
  extracted; say that.

## What to report

The number of bursts and donor photons per population, the selection window,
where the IRF and the donor reference came from, both lifetimes with their
reduced chi-squares, E, R0 and R, and the PR-versus-lifetime agreement.

A sub-ensemble decay averages over the selected molecules. If the population
is heterogeneous the fit returns a mixture and one distance may not describe
it — a two-component donor decay in the FRET population usually means two
conformations, not two dyes, and reporting their mean as "the distance" hides
the very thing single-molecule measurement was done to see.
