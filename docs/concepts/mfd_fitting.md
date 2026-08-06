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

They do not depend on it the *same way*, though, and the difference is easy to
miss because one half genuinely is `f`:

* **Channel counts are the `f`-weighted mixture, exactly.** A photon picks a state
  with probability `f_s` and is then detected in the acceptor channel with that
  state's probability `p_s`, so marginally it is an acceptor photon with
  probability `f·p`, *independently of every other photon*. The acceptor count is
  therefore exactly `Binomial(S, f·p)` — not approximately.
* **The micro times are not.** They are read from the donor photons alone, and
  those are a **biased sample** of the burst: a state contributes donor photons in
  proportion to `f_s (1 − p_s)`, so the mixture the mean delay is drawn from is

  ```
  g_s = f_s (1 − p_s) / Σ_j f_j (1 − p_j)
  ```

  A high-FRET state can occupy most of a burst while contributing almost none of
  the donor photons whose mean delay is plotted. For a burst split evenly between
  an `E = 0.2` and an `E = 0.8` state, **80 %** of the donor photons come from the
  low-FRET state, not half — and the predicted mean delay is 2.72 ns rather than
  2.00 ns, three to four times the width of a micro-time bin.

Weighting the micro times by `f` puts the dynamic bridge too far toward short
lifetimes, which a fit then compensates with the exchange rate. ChiSurf did this
until the green weighting was derived. Weighting by occupancy was kept as an
option long enough to be priced against ground truth and then removed: it happens
to beat the exact weighting at one exchange rate, by cancelling against a second
error, and fails badly at another.

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
ships a generator: `chisurf.core.fluorescence.burst.simulate` produces smFRET bursts
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

## Three sources, one model

The same parameters can be scored three ways, and their agreement is itself a test:

| source | what it uses | what it is for |
|---|---|---|
| **histogram** | each burst compressed to two numbers | the fast path, and the rate |
| **burst-wise** | every photon's micro time | the reference, and the only valid uncertainty |
| **pooled decay** | real decays pooled per ratio bin | the decay *shape* the mean discards |

The pooled-decay source exists for one discrimination the other two cannot make
cleanly. A burst caught mid-exchange between a close and a far state, and a burst
from a single state at the intermediate distance, can sit at the same proximity
ratio with the same mean micro time — and they do not have the same decay, because
one is a *mixture* of two lifetimes and the other is one lifetime. Pooling each
ratio bin's photons back into a real decay recovers that.

It is deliberately pooled on the **ratio only**. Pooling on a coordinate conditions
on it, and the ratio is one the model reproduces exactly; pooling on the lifetime
axis too would tilt every pooled decay in a way that reads as a lifetime shift.

Its limits are worth stating: on a two-state system its score varies by only a few
percent over a 36-fold change in exchange rate, so it is **not** the source to read
a rate from. It tells you whether the shape is a mixture. The rate comes from the
histogram or burst-wise sources.

## Two forward models

Everything above describes the **analytic** forward model: the histogram is
*computed*, cell by cell, as an expectation. Three of its steps are closed forms
standing in for something a burst actually does — a nested Poisson/binomial sum
for the channel counts, a Gaussian kernel for the mean delay, a transfer-matrix
propagator for the occupation-time law. Each is fast and each has a regime where
it frays.

ChiSurf **carried** a second, Monte-Carlo forward model for a while, transcribed
from the Sim2D program that produced published 2D-MFD analyses for years. It
approximated none of those three steps: it drew a burst's duration and photon
budget from the measured distribution, walked the kinetic scheme through it,
handed the photons out over the states by occupancy, and let every photon choose
a channel and a delay.

It was built to be measured against known ground truth, it was, and it lost —
faster where exchange is slow, both slower and more biased where it is fast — so
it is gone. What it proved is worth more than what it computed:
it carried the **same** window bias as the closed-form path, and it was the two
agreeing that showed the error lived in an assumption they *shared* rather than
in either implementation.

The general lesson is the one to keep: two implementations agreeing is not
evidence when they share an assumption. Both defects this model has had — the
donor-photon weighting and the burst-span window — were present in both scoring
sources for as long as they existed, and the sources agreed throughout.

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
  that are too small. ChiSurf refuses to report them, and both valid routes are
  available: `Mfd2DModel.burstwise_score()`, which scores every photon's micro time
  and touches each burst exactly once, and `Mfd2DModel.bootstrap()`, which resamples
  bursts — the thing that actually varies between repeats of an experiment.

  The burst-wise source is worth running even when you do not need an uncertainty.
  It shares the model with the histogram source but not the statistic, so a rate the
  two disagree on is a rate nobody should report; on simulated exchange its
  likelihood peaks exactly at the generating rate.

  **Agreement between them is weaker evidence than it looks**, though, precisely
  because they share the model. The donor-photon weighting above was wrong in both
  for as long as it existed, and the two agreed with each other throughout. What
  distinguishes a shared modelling error from a correct model is an *independent
  forward model* — see below — or known ground truth.
## The instrument response, and why a Gaussian is the right shape

The response comes from the measurement's own **non-burst** photons — so no
separate scatter acquisition is needed. "Non-burst" means the exact complement of
*this folder's* burst table, taken from its `First Photon`/`Last Photon` columns.
Separating molecules from the empty acquisition is what the burst cut was for, so
running a second search at its own thresholds answers a different question: at
other thresholds, bursts the analysis kept land back on the instrument's side of
the line and their fluorescence is read as response. There is nothing to
configure here, and that is the point.
Those photons are not, however, only scatter and dark counts: most of a confocal
acquisition holds molecules too dim to cross the burst threshold, and their
fluorescence is in that stream too. Subtracting a flat baseline removes the dark
counts and leaves the *decay*, so the "response" comes out with a slow tail and a
first moment nanoseconds late.

That error lands on the lifetime axis, and the parameter degenerate with it — the
donor lifetime — absorbs it. On a real BH SPC-132 DNA measurement the least-squares
optimum for `tau_d0` was **1.57 ns**, about half of anything a dye on DNA has.

The fix is to fit a **Gaussian** to the prompt. A Gaussian cannot represent a slow
tail, which is exactly the property wanted: least squares locks it onto the sharp
scatter peak and leaves the fluorescence behind, while still following the measured
position and width. Two details matter:

* the width is taken from the **rising** edge only, mirrored. The falling side of a
  non-burst histogram is the decay, not the instrument, so a two-sided half-max
  reads the decay's width;
* the fit window is the leading edge, not a symmetric interval — anything right of
  the peak is prompt *plus* decay;
* the half-max walk tolerates a short dip rather than stopping at the first one,
  because a sparse non-burst stream has Poisson dips inside the rise. Smoothing
  would also fix that and must not be used: the prompt is the sharpest feature in
  the histogram, so any kernel wide enough to bridge a dip flattens the very peak
  being measured.

Re-deriving that real measurement's optimum under the corrected response moves
`tau_d0` to **2.72 ns** and leaves the distance, donor-only fraction and leakage
within a percent: the signature of a genuine degeneracy being broken rather than a
refit. The same estimator serves the burst-MLE lifetime fit, where it removed a
comparable factor-of-two bias.

On simulated photons with a declared 1.0 ns response, the estimate is recovered to
better than 0.2 ns, and the fitted exchange rate's bias falls from what the
contaminated response caused to what the forward model itself carries.

## Photons do not sample a burst uniformly in time

A burst's duration is not the window over which its conformational state
averaged. A molecule is brightest at the centre of its transit, so its photons
over-sample whichever state it held then, and they carry information about a
shorter stretch of the trajectory than the first-to-last-photon span covers.

Taking the span as the averaging window makes the model predict a *more* averaged
histogram than the data shows at the true rate, and a fit answers that by
lowering the rate — by 20% at 1 kHz and 33% at 5 kHz on known ground truth. The
direction matters: a model that under-reports exchange reports a molecule as more
static than it is.

The correction needs no approximation. The two-state indicator is a telegraph
process with covariance `π₀π₁ e^{−k|Δt|}`, and a photon-weighted fraction is a
plain average over the photons, so

```
Var(f) = π₀ π₁ · (1/N²) · Σᵢ Σⱼ exp(−k |tᵢ − tⱼ|)
```

holds whatever the arrival pattern. Inverting it gives the window a burst's
photons behave like, which is always shorter than the span and shortens further
as the rate rises. Recovery improves to −7% and −3%, and the fit gets *faster*
because a shorter window needs fewer transfer-matrix slices.

This was shared by chisurf's closed-form path and by a transcribed Sim2D Monte
Carlo built to check it — the reason those two agreed with each other while both
were wrong. That Monte Carlo, and two other alternatives that were measured and
lost, are recorded in the project's design notes.

## Further reading

* [FRET](fret.md) — efficiencies, distances and the correction factors.
* [Accurate FRET](accurate_fret.md) — where α, β, γ and δ come from.
* [Photon distribution analysis](pda2c.md) — the same nuisance trick, one dimension
  lower.
* [Anisotropy](anisotropy.md) — the second MFD axis.
* Guide: [Fitting an MFD burst histogram](../guides/57_mfd_fitting.md)
