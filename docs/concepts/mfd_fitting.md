# Fitting the 2D MFD histogram

The two plots that define multiparameter fluorescence detection — FRET efficiency
against donor lifetime, and anisotropy against lifetime — are usually *read*: a
static line is drawn on top, and the deviation from it is discussed. This page
describes how ChiSurf **fits** them, and why the model is built forwards rather than
by inverting each burst.

## Why per-burst inversion does not work

Both axes of an MFD plot are estimators from few photons. A burst carries 50–500
of them, so the cloud you see is dominated by shot noise, and the width of that
noise is set by the burst-size distribution — itself a product of diffusion,
brightness, and wherever the burst search drew its threshold.

The information about dynamics lives in the spread *perpendicular* to the static
line, and it is confounded with that shot-noise spread. Three problems follow, and
they all come from trying to invert:

* predicting the shot-noise contribution from first principles means a diffusion
  Monte Carlo inside every likelihood evaluation — unfittable, and it drags in
  optical nuisance parameters (focal volume, diffusion coefficient, focal depth)
  that nobody wants to fit;
* fitting each burst's decay for a lifetime is slow, and *biased* at these photon
  numbers, with a bias that moves as the parameters move;
* a per-burst maximum-likelihood lifetime has no analytic sampling distribution, so
  the model cannot say where the cloud should sit.

Forward-modelling the raw observables removes all three at once.

## The four ideas

### 1. The burst statistics come from the experiment

The nuisance measure is the **empirical** joint distribution of the burst signal
`S` and the per-channel observation spans `(t_G, t_R)` — written `D12`. This is
exactly what photon-distribution analysis does with `P(S)` per fixed time window,
except that bursts have no fixed window, so the measure is resolved by time.

Three consequences, all of them the point:

* **No brightness law.** Brightness enters only through the *measured* signal
  distribution, so the shot-noise width of the FRET axis comes out of the data
  rather than out of an assumption.
* **Selection is inherited, not modelled.** The empirical measure carries the
  burst-search threshold the same way PDA's `P(S)` carries its window criterion.
* **The spans do work a single duration cannot.** Background is Poisson with mean
  `bg_c · t_c` per channel *per burst*, and an asymmetry between the green and red
  spans additionally expresses acceptor bleaching and blinking.

`D12` holds **times, not counts**. Weighting the partition by each channel's
measured counts instead would make the FRET axis reproduce itself exactly and carry
no information at all — while still converging, which is what makes the mistake
worth naming.

### 2. The lifetime axis is the mean micro time

`⟨t⟩` is a *linear* statistic of a burst's photons, so its sampling distribution is
analytic: given `N` photons drawn from a pattern of mean `μ` and variance `v`, the
recorded `⟨t⟩` has mean `μ` and variance `v/N`. No per-burst fit, no bias.

Two subtleties that are silent if you get them wrong:

* **The convolution is circular.** The TAC window *is* the laser period, so a photon
  emitted late reappears at the start of the next period. A pattern shifted later by
  `k` channels therefore moves its mean by `k·dt − T·(mass that wrapped)`, not by
  `k·dt`. Using unwrapped moments biases every long lifetime short, and the
  histogram absorbs that into an exchange rate rather than complaining.
* **A TAC records a channel's left edge**, not the arrival inside it. Because an
  exponential is memoryless, that offset has the same distribution in every channel
  and therefore subtracts *exactly* — it is not a half-channel approximation.

### 3. Everything is fitted in raw observable space

Bins are laid on the proximity ratio `N_R/(N_G+N_R)` and the raw `⟨t⟩`. Every
correction — leakage `α`, direct excitation `δ`, `γ`, the background — lives in the
forward model.

This is what allows a correction to be a *free parameter*. On corrected axes,
changing `γ` moves the **data** histogram, and a deviance measured against a moving
target is not a fit statistic: an optimizer can lower it by reshuffling bursts
between bins instead of by explaining them. On raw axes the data histogram is built
once and never moves again.

### 4. Kinetics enters through one object

Given a state path, a burst's channel counts and micro times depend on that path
**only** through the vector of occupation-time fractions `f`. That is exact — `f`
is the path's sufficient statistic. So exchange enters as `P(f | T, K)` and nothing
else about the path matters.

It is computed deterministically, by propagating the joint distribution over
(state, occupation counts) with the exact one-slice transition matrix. Sampling
paths instead would put Monte-Carlo noise into the objective, and an optimizer
chases noise.

The discretization has to resolve the transitions *within* the burst, not the burst:
at 300 transitions per burst a 64-step grid reports a spread ~50% too wide, and that
excess reads as static heterogeneity — precisely what the kinetics is meant to be
distinguished from.

## The distance is distributed

With both dyes on flexible linkers, their positions are roughly Gaussian clouds in
three dimensions, and the *distance* between two such clouds is **not** Gaussian. It
follows the non-central chi distribution with three degrees of freedom,

$$p(R) = \frac{R}{d\,\sigma\sqrt{2\pi}}
\left[\exp\!\left(-\frac{(R-d)^2}{2\sigma^2}\right)
     -\exp\!\left(-\frac{(R+d)^2}{2\sigma^2}\right)\right],
\qquad \sigma^2 = \sigma_D^2 + \sigma_A^2 .$$

This distribution enters the model **twice, in two different ways**, and swapping
them is a real error:

* the excited-state lifetime is short compared with linker sampling, so the decay is
  a genuine *lifetime distribution* — `I(t) = ∫ dR\, p(R)\, e^{-t/\tau(R)}`;
* a burst is long compared with linker sampling, so the burst's efficiency is the
  `p(R)`-average — `E = ∫ dR\, p(R)\, E(R)`.

Averaging the efficiency first and quenching once gives the wrong decay shape;
averaging the decay to a single lifetime gives the wrong efficiency. Together they
produce the familiar linker-broadened static line — and they mean `σ` is imprinted
on the decay *shape*, which is why it must not be a free broadening parameter tacked
on afterwards.

## What the gate actually tested

The position of an MFD cloud is easy to hit; several wrong models hit it. The width
is not, and it is what matters: **any width the model fails to explain will later be
absorbed as exchange.**

So the acceptance was width, with no free broadening parameter, on a real
single-molecule DNA measurement. The donor-only population is what makes that a real
test — it has no distance, no efficiency and nothing fitted to its spread, so its
width is shot noise alone, and that width can be computed from the photons
themselves without any model:

| quantity | measured / model-free | forward model |
|---|---|---|
| donor-only proximity-ratio width | 0.0215 (binomial estimate 0.0221) | 0.0208 |
| donor-only ⟨t⟩ shot noise | 0.322 ns | 0.336 ns |
| donor-only ⟨t⟩ *observed* | 0.464 ns | — |

Three to four percent on both axes. The residual — 0.33 ns of excess on the lifetime
axis, and a FRET population 1.3× broader in `PR` than shot noise — is physical
heterogeneity, and the model is asserted to stay *below* it. A forward model that
broadened itself to match would be fitting width with something that is not width,
and every dynamics result built on it would inherit that.

## Testing it against simulated dynamics

Real measurements with an independently known exchange rate are rare, so ChiSurf
ships a generator: `chisurf.core.fluorescence.mfd.simulate` produces smFRET bursts
with exchange on a chosen timescale and writes them as a real burst-analysis folder,
which then loads through the ordinary reader like any measurement.

**It is a code test, never a physics test.** A simulator built from the same
assumptions as the model will pass whatever error the two share. What it can show is
that the implementation computes what it claims to — and it does that credibly,
because the two reach the same numbers by different routes: the simulator samples an
explicit Markov path per burst and draws each photon's micro time as an
instrument-response sample plus an exponential delay, while the model evaluates the
occupation-time law and the wrapped moments in closed form.

Regimes are named in **transitions per burst**, because a rate only means something
next to an observation window: 500 s⁻¹ is slow exchange for a 10 ms transit and fast
exchange for a 0.1 ms one. Fitting the same molecule in each
(`examples/mfd_dynamics_timescales.py`, 3000 bursts):

| regime | true rate | fitted | bursts between the states |
|---|---|---|---|
| static | 0 s⁻¹ | 0 s⁻¹ | 0.3% |
| slow | 50 s⁻¹ | 68 s⁻¹ | 3.6% |
| intermediate | 1500 s⁻¹ | 1511 s⁻¹ | 36.4% |
| fast | 60000 s⁻¹ | 43855 s⁻¹ | 79.7% |

The last column is the signal. Slow exchange leaves the gap between the two states
empty; fast exchange puts everything in it, because the states have merged into
their average; only in between does its occupancy actually report a rate.

So **the rate is accurate near one transition per burst and only an order of
magnitude away from it** — far below, almost no burst ever switches, so the
histogram barely constrains how rarely it happens; far above, every burst reports
the same average, so it barely constrains how often. That is the physics, and it is
worth knowing before quoting a rate from either extreme.

The one result that is sharp everywhere is the negative: **static data returns no
exchange.** A model that produced a finite rate there would be reporting dynamics
from static heterogeneity, which is the failure the whole design is arranged around.

## Things to know before reading a number off it

* **The donor-photon cut is not neutral between populations.** A high-FRET burst
  sends most of its photons to the acceptor, so it has fewer donor photons and is
  preferentially removed. The *fit* is unaffected — the model histogram is cut
  identically to the data one — but a model histogram is therefore **not** the
  population mixture, and amplitudes read off it directly understate every
  high-FRET species.
* **Uncertainties do not come from this fit's curvature.** The summed deviance over
  marginals is an M-estimator, not a likelihood: the same bursts appear in every
  marginal, so the score double-counts the data and its curvature reports errors
  that are too small. ChiSurf refuses to report them, and points at the burst-wise
  source or a bootstrap over bursts.
* **The instrument response taken from non-burst photons is contaminated** by
  fluorescence from molecules below the burst threshold, so a donor lifetime fitted
  against it is an *effective* number. It does not affect a width gate; it will bias
  an absolute lifetime.

## Further reading

* [FRET](fret.md) — efficiencies, distances and the correction factors.
* [Accurate FRET](accurate_fret.md) — where α, β, γ and δ come from.
* [Photon distribution analysis](pda2c.md) — the same nuisance trick, one dimension
  lower.
* [Anisotropy](anisotropy.md) — the second MFD axis.
* Guide: [Fitting an MFD burst histogram](../guides/57_mfd_fitting.md)
