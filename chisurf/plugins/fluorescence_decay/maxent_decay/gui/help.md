# Maximum-entropy decay analysis — what this tool is for

A multi-exponential fit asks "which two or three lifetimes?" — which presupposes
that there are two or three. This tool asks instead **what distribution of decay
times is consistent with the data**, without assuming a shape.

If you have not run it before, press **🧭** for the guided tour.

Use it when you suspect a continuum — a dye sampling many environments, a
quencher at a range of distances, a disordered chain — or when you want to check
whether the components a discrete fit returned are real.

## Why regularization is unavoidable

Recovering a distribution from a decay is an inverse Laplace transform, and it is
ill-posed: wildly different distributions produce decays that differ by less than
the photon noise. The unregularized solution oscillates and changes when a single
count changes.

Maximum entropy picks, out of all distributions that fit, the one with the least
structure. It minimizes

    Q = χ² − ½ ν S,     S = Σ [ p − m − p ln(p/m) ]

with `m` the prior. Two consequences worth knowing: the solution can never go
negative (the logarithm forbids it), and every peak costs entropy — so a feature
appears only when the data insist on it.

## The one setting that matters: ν

**ν** is not a nuisance parameter. It is your choice about how much structure to
believe.

* Too small — the distribution oscillates and the peaks are noise.
* Too large — everything comes back as one broad hump on top of the prior.

Press **L-curve** rather than guessing. It sweeps ν and plots residual norm
against solution norm; the corner is the standard compromise, and the tool marks
it. Then do the thing the corner does not do for you: **re-run at a factor of two
either side and check your features survive.** A peak that only exists in a
narrow window of ν is a regularization artefact, not a state.

## Before you trust a result

| Check | Why |
|---|---|
| Vary **ν** around the corner | Features that move, split or vanish are not features |
| Change the **grid** range and spacing | A peak at the grid edge is mass the data cannot constrain |
| Change the **prior** | Structure following the prior is the prior showing through |
| Compare with a discrete fit | If two exponentials fit and MEM gives two narrow peaks at the same lifetimes, the discrete reading is safe |
| Count your photons | Two lifetimes closer than about a factor of two will merge at any ν — the information is not in the data |

The last row is the honest limit. Regularization cannot add information; it only
decides which of the many fitting answers you are shown.

## Lifetime mode and FRET mode

**Lifetime** recovers p(τ) on a lifetime grid. **FRET** recovers p(R) directly on
a distance grid, using the same solver with the transfer kernel substituted — the
model-free counterpart to the Gaussian and polymer distance models. It needs a
donor-only reference, which is what **Load donor** and **Load donor fit** are
for; getting that reference wrong puts the donor's own heterogeneity into your
distance distribution.

## What it does not give you

A posterior. The result is one distribution at one ν, with no error bars on the
bins, and the bins are strongly correlated. For uncertainty on a derived
quantity, use **Sample**, or fit a parametric model and sample that instead.

## Further reading

* [Lifetime distributions and maximum entropy](docs/concepts/maximum_entropy.md)
  — the entropy functional, the L-curve, and how to read a result.
* [Guide: maximum-entropy decay analysis](docs/guides/62_maxent_decay.md)
* [TCSPC: fluorescence-lifetime fitting](docs/concepts/tcspc_lifetime.md) — the
  forward model, the nuisance terms and the statistics this sits on.
* [Distance distributions from the donor decay](docs/concepts/distance_distributions.md)
  — the parametric alternative for FRET mode.
* [Photon statistics and goodness of fit](docs/fundamentals/photon_statistics.md)
