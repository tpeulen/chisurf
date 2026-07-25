---
type: Concept
title: FRET from lifetimes
description: >-
  How a donor-only reference and a donor-acceptor sample give an efficiency
  and a distance, and which inputs the distance is only as good as.
tags: [fret, donor, acceptor, distance, forster]
timestamp: '2026-07-25T00:00:00Z'
---

# The measurement is a comparison

Energy transfer to an acceptor gives the donor an extra way to lose its
excitation, so it decays faster. How much faster gives the efficiency:

    E = 1 - tau_DA / tau_D

which is why the analysis always needs **two** measurements — the donor-only
reference and the donor–acceptor sample, each with its own instrument
response. Fitting the quenched decay alone with a plain lifetime model yields
"lifetimes" that mix donor photophysics with transfer and mean nothing. On
the sample pair that fit reaches chi2r ≈ 45.

# From efficiency to distance

    E = 1 / (1 + (R / R0)^6)

The sixth power is what makes FRET a ruler and also what makes it unforgiving:
the useful range is roughly 0.5–1.5 R0, and outside it the efficiency barely
changes with distance.

**R0 and kappa-squared are inputs, not results.** The Förster radius depends
on the dye pair, the spectral overlap, the refractive index and the
orientation factor; the orientation factor is usually assumed to be 2/3, which
presumes both dyes rotate freely. A distance is only as good as the R0 it came
from, so quote the R0 you assumed alongside it.

# The donor-only fraction

Real samples always contain molecules with no active acceptor: incomplete
labelling, photobleached acceptors, or a fraction of the population that is
simply unlabelled. Their donors decay unquenched, and ignoring them biases the
efficiency low. The FRET models carry this as an explicit fraction — fit it
rather than assuming it is zero.

# Distributions, not a single distance

A flexible linker means the dyes sample a range of separations, so a
distribution model (a Gaussian mean and width, say) usually describes the data
better than a single distance. A width that runs to its bound is the model
telling you the data cannot resolve the distribution.

# What a good analysis looks like

Fit the donor reference first. Transfer its photophysics to the FRET model —
linked, so both datasets constrain it, or fixed when the reference is trusted.
Then fit the transfer parameters. On the sample pair this yields E ≈ 0.32 at
R ≈ 52 Å with about a third donor-only, at chi2r ≈ 1.09.
