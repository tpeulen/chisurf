---
name: fret-from-decays
description: >-
  Measure FRET from time-resolved decays: fit the donor-only reference, then
  fit the donor-acceptor sample against it to get the efficiency and the
  inter-dye distance. Use when the user mentions FRET, donor-only, D0/DA, a
  labelled pair, or asks for a distance from lifetimes.
triggers:
  - fret
  - donor
  - acceptor
  - donor-only
  - donly
  - d0
  - da
  - efficiency
  - distance
  - forster
  - förster
  - quenching
  - labelled pair
experiments: [TCSPC]
tools:
  - load_data
  - create_fit
  - set_irf
  - set_components
  - set_parameter
  - link_parameters
  - run_fit
  - fit_report
  - plot_fit
---

# FRET from time-resolved decays

The measurement is a comparison: the donor decays faster when an acceptor is
present, and how much faster gives the efficiency and, through the Förster
radius, the distance. So the analysis always needs **two measurements** — the
donor-only reference (often named `D0`, `Donly`) and the donor-acceptor
sample (`DA`) — each with its own instrument response.

Fitting the DA decay on its own with a plain lifetime model is a mistake: it
yields "lifetimes" that are a mixture of donor photophysics and FRET, and
nothing physical. On the sample data that fit reaches a reduced chi-square of
about 45.

## The procedure

1. **Fit the donor-only decay first**, with its IRF, as an ordinary decay
   (see the `fit-decay` skill). Usually two lifetimes. This is the *donor
   reference*: what the dye does with no acceptor present.
2. **Create a FRET fit on the DA decay** with one of the `FRET: FD (...)`
   models. `FRET: FD (Gaussian)` describes the inter-dye distance as a
   Gaussian distribution, which is the usual choice for a flexible linker;
   `FRET: FD (Discrete)` fits discrete distances.
3. **Attach the DA measurement's own IRF.**
4. **Give the FRET model the same number of donor components** as the
   reference fit: `set_components` with `component="donor"`.
5. **Transfer the donor reference.** Either link the donor lifetimes to the
   donor-only fit (`link_parameters`, which lets both datasets constrain
   them), or fix them at the reference values (`set_parameter` with
   `fixed=true`) when you trust the reference and want it held. Either way
   the donor photophysics must come from the reference, not be re-fitted
   against the quenched decay.
6. **Run the fit**, then read the result.

## What the model reports

* `E_FRET` — the FRET efficiency.
* `R(G,1)`, `s(G,1)` — the mean and width of the distance distribution, in
  ångström.
* `xDOnly` — the fraction of molecules with no active acceptor. This is
  always present in real samples (incomplete labelling, bleached acceptors),
  and ignoring it biases the efficiency low.
* `R0`, `k2` — the Förster radius and the orientation factor. These are
  *inputs*, not results: check they match the dye pair before believing any
  distance. A distance is only as good as the R0 it came from.

On the sample donor/acceptor pair this yields E ≈ 0.37, R ≈ 55 Å with about
17 % donor-only.

## Judging and reporting

Report the efficiency **and** the distance, with the R0 you assumed, the
donor-only fraction, and the reduced chi-square. State whether the donor
reference was linked or fixed.

If the DA fit stays poor with the donor reference in place, the usual causes
are: the reference does not describe this donor (different buffer, different
labelling), the acceptor is partly bleached (let `xDOnly` float), or the
distance is genuinely distributed more widely than the model allows (free
`s(G,1)` or move to a distribution model). Adding donor lifetimes to force
chi-square down is not one of the options — it changes the reference and
makes the result meaningless.
