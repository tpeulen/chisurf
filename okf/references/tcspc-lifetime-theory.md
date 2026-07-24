---
type: Reference
title: "TCSPC lifetime theory — reconvolution fitting of fluorescence decays"
description: The physics behind ChiSurf's time-resolved fluorescence-lifetime fitting — the TCSPC measurement, the multi-exponential decay model, the IRF and the reconvolution integral, why the fit lives in convolved space, the background/scatter/pile-up/DNL nuisances, amplitude- vs intensity-weighted average lifetimes, species vs intensity fractions, and how all of this maps to chisurf's convolution helpers, lifetime models and the fit2x Poisson-MLE path.
tags: [reference, tcspc, lifetime, reconvolution, irf, mle, pedagogy]
timestamp: '2026-07-24T00:00:00Z'
---

# TCSPC lifetime theory — reconvolution fitting of fluorescence decays

Time-correlated single-photon counting (TCSPC) measures the **fluorescence
lifetime** — the mean time a fluorophore spends in the excited state before it
emits. The lifetime is set by the sum of all excited-state depopulation rates,
so it reports directly on the fluorophore's photophysical environment (quenching,
solvent, FRET, conformational state) independently of concentration or
excitation intensity. This concept is the **science/pedagogy layer** for
chisurf's TCSPC fit-model catalogue (`chisurf/core/models/tcspc/`): what the
measured histogram is, why the model must be *reconvolved* with the instrument
response before it can be compared to data, which nuisance terms sit around the
decay, and how the fitted amplitudes and lifetimes turn into physical numbers.

It complements — does not duplicate — the engine-level subsystem concept
[/subsystems/mle-lifetime-fitting.md](/subsystems/mle-lifetime-fitting.md),
which documents the shared fit2x Poisson-MLE estimator and its input contract.
This concept explains the model those estimators (and the least-squares path)
are fitting.

The terminology and formula structure follow the standard TCSPC literature —
Lakowicz, *Principles of Fluorescence Spectroscopy* (3rd ed., 2006, chs. 4 & 5)
for reconvolution and lifetime analysis, and O'Connor & Phillips, *Time-correlated
Single Photon Counting* (Academic Press, 1984) for the measurement and its
artifacts — with pedagogy and worked exposition also drawn from QuickFit3's help
system (`junk/quickfit3/plugins/tcspcimporter/help/lifetime.html`,
`fretchen.html`) as documented prior art. All formulas are reimplemented
independently in chisurf; nothing is a verbatim copy.

## The TCSPC measurement

A pulsed source excites the sample at a fixed repetition period $T$ (typically
12.5–50 ns, i.e. 20–80 MHz). For each excitation pulse the electronics record
the arrival time of **at most one** detected photon relative to the pulse — the
*micro-time*. Accumulating micro-times over many millions of pulses builds a
histogram $y(t)$ whose shape, in the ideal limit, is the fluorescence intensity
decay $I(t)$. Because at most one photon is counted per cycle, a too-high count
rate biases the histogram toward early times — the **pile-up** artifact treated
below; the classical rule of thumb is to keep the detected rate below ~1–5 % of
the excitation rate.

The histogram is Poisson-distributed: channel $i$ holds an integer count whose
variance equals its mean. This is why the correct weighting for least-squares
fitting is $\sigma_i=\sqrt{y_i}$ (chisurf's `counting_noise`), and why a proper
maximum-likelihood treatment uses the Poisson likelihood rather than Gaussian
$\chi^2$ (the fit2x path below).

## The multi-exponential decay model

For a population of non-interacting fluorophores, each excited-state species
depopulates exponentially with a characteristic lifetime $\tau_i$. The intensity
decay is a sum of exponentials,

$$
I(t) = \sum_{i} a_i \, e^{-t/\tau_i}, \qquad a_i \ge 0,
$$

where $a_i$ is the amplitude (pre-exponential factor, proportional to the ground-
state population of species $i$ times its radiative rate) and $\tau_i$ its
lifetime. A single fluorophore in a homogeneous environment gives one exponential;
mixtures, quenched sub-populations, and FRET give several. chisurf stores this as
an **interleaved lifetime spectrum** $[a_1,\tau_1,a_2,\tau_2,\dots]$ — the native
format of the convolution kernels and of tttrlib.

The decay is *not* observed directly. Two things stand between $I(t)$ and the
histogram: the finite instrument response, and additive nuisances.

## The instrument response function and reconvolution

No excitation pulse is a perfect delta function, and neither the detector nor the
timing electronics respond instantaneously. Their combined temporal blur is the
**instrument response function** (IRF), $\mathrm{IRF}(t)$ — measured from
scattered excitation light (a scatterer with no fluorescence) or from a reference
dye of known, very short lifetime. Because convolution with the IRF and the
excitation of the fluorophore are linear and time-invariant, the *observed*
noise-free decay is the convolution of the true decay with the IRF:

$$
M(t) \;=\; (\mathrm{IRF} \otimes I)(t)
        \;=\; \int_{0}^{t} \mathrm{IRF}(t') \, I(t - t') \, \mathrm{d}t'.
$$

Fitting therefore happens **in convolved space**: one does not deconvolve the
data (an ill-posed, noise-amplifying operation). Instead, at every optimizer step
the trial decay $I(t)$ is *reconvolved* with the measured IRF and the resulting
$M(t)$ is compared to the raw histogram. This "iterative reconvolution" is the
standard, well-conditioned way to recover lifetimes shorter than or comparable to
the IRF width (Lakowicz ch. 4; O'Connor & Phillips). It lets TCSPC resolve
lifetimes well below the ~ns instrument width because the *shape* of the tail,
not just its position, carries the lifetime information.

Two practical wrinkles:

- **Periodicity.** At high repetition rates the previous pulse's decay has not
  fully died away when the next pulse arrives, so the tail wraps around and adds
  to the early channels of the next period. The convolution must then be done
  **periodically** over the excitation period $T$, summing the wrapped tail
  contributions. chisurf uses the non-periodic kernel when the decay is short
  relative to $T$ and the periodic kernel otherwise.
- **IRF timing (colour shift).** The IRF is usually measured at the excitation
  wavelength, but the detector's transit time depends slightly on wavelength, so
  the fluorescence IRF is shifted by a fraction of a channel relative to the
  scatter measurement. A fitted sub-channel **IRF/time shift** (and, for
  reference-dye IRFs, a lamp-background subtraction) absorbs this. Getting the
  shift wrong biases short lifetimes the most.

## The nuisance terms around the decay

The count in channel $i$ is not $M_i$ alone. The full forward model chisurf
assembles (in `nusiance.Convolve` and `Generic`) layers several instrument and
sample nuisances on top of the reconvolved decay:

$$
y_i^{\text{model}} \;=\; L_i \cdot \Big[\, s\cdot \mathrm{IRF}_i
        \;+\; (\mathrm{IRF}\otimes I)_i \,\Big] \cdot P_i \;+\; b,
$$

- **Scatter ($s$).** Elastically scattered excitation light and Raman scatter
  reach the detector with the *IRF shape* (they are effectively "instantaneous"
  fluorescence). Adding a scaled IRF, $s\cdot\mathrm{IRF}$, absorbs this instead
  of letting the fit invent a spurious ultra-short lifetime.
- **Constant background ($b$).** Dark counts, afterglow and ambient light add a
  time-independent offset. It can be measured from a buffer-only run
  (`Generic.background_curve`, scaled by the ratio of acquisition times) or fitted
  as a constant.
- **Pile-up ($P_i$).** At high count rate the one-photon-per-cycle limit
  preferentially discards *late* photons (an early photon "uses up" the cycle),
  compressing the apparent decay and shortening the measured lifetime. chisurf
  applies the Coates (1968) correction as a per-channel factor on the model
  (`add_pile_up_to_model`), so the measured counting statistics — and the known
  Poisson noise — are preserved rather than reweighting the data.
- **Differential non-linearity ($L_i$, DNL).** The TCSPC time-to-amplitude
  converter has small channel-to-channel width variations that modulate a flat
  input. A **linearization table** measured from uncorrelated light (a smoothed
  ratio, `compute_linearization_table`) multiplies the model to reproduce this
  ripple without adding noise.

Modelling these as forward terms on $M(t)$ — never by pre-correcting the noisy
data — keeps the residuals Poisson and the fit statistically sound.

## Fitting: least squares vs Poisson maximum likelihood

Two objectives are in use, and the distinction matters at low counts.

- **Weighted least squares** minimizes $\chi^2 = \sum_i (y_i - y_i^{\text{model}})^2/\sigma_i^2$
  with $\sigma_i=\sqrt{y_i}$. This is the Gaussian approximation to the Poisson
  statistics and is accurate when every fitted channel has many counts (dense
  histograms from cuvette measurements). chisurf's classical lifetime models fit
  this way; the amplitude scale is recovered analytically by `rescale_w_bg`, which
  solves for the single linear scale that best matches model to data given the
  weights and background.
- **Poisson maximum likelihood (MLE).** When counts per channel are small — the
  regime of per-burst and per-pixel fits, where a whole decay may hold only tens
  to hundreds of photons — the Gaussian approximation biases the lifetime, and
  empty channels are mishandled. The correct objective is the Poisson likelihood,
  in practice the Maus-2001 $2I^*$ statistic. chisurf routes these through the
  tttrlib `Fit23`/`Fit24`/`Fit25` estimators via
  `chisurf/core/fluorescence/mle/`; see
  [/subsystems/mle-lifetime-fitting.md](/subsystems/mle-lifetime-fitting.md) for
  the estimator selection and the (nanosecond `dt`/`period`, area-normalized
  background, soft-bounded gamma) input contract.

Both fit *in convolved space*; they differ only in the statistic and in how many
parameters they can support at a given photon budget. A cuvette decay supports a
free multi-exponential spectrum; a single burst supports one lifetime plus a
background/anisotropy nuisance and little more.

## Average lifetimes: amplitude- vs intensity-weighted

A multi-exponential decay is often summarized by a single "average" lifetime, but
there are **two inequivalent averages**, and confusing them is a common error.

- **Species-averaged (amplitude-weighted) lifetime** — the number-weighted mean,
  the observable that scales with the *area* under the decay:

$$
\langle \tau \rangle_x \;=\; \frac{\sum_i a_i \tau_i}{\sum_i a_i}.
$$

  It is proportional to the steady-state intensity/quantum yield and is the
  correct quantity for FRET efficiency from donor decays,
  $E = 1 - \langle\tau\rangle_{x}^{DA}/\langle\tau\rangle_{x}^{D}$.

- **Intensity- (fluorescence-) weighted lifetime** — weights each species by the
  number of *photons* it emits, $\propto a_i\tau_i$:

$$
\langle \tau \rangle_f \;=\; \frac{\sum_i a_i \tau_i^{2}}{\sum_i a_i \tau_i}.
$$

  It is what an intensity-decay tail or a phasor/mean-arrival-time estimate
  returns, and it always satisfies $\langle\tau\rangle_f \ge \langle\tau\rangle_x$.

chisurf exposes both directly on the `Lifetime` group as read-only outputs
(`species_averaged_lifetime`, `fluorescence_averaged_lifetime`, backed by
`chisurf.core.fluorescence.general`).

### Species fractions vs intensity fractions

The same two-weighting distinction governs how a component's "fraction" is
reported.

- **Species (mole) fraction** — its share of the molecules:
  $x_i = a_i / \sum_j a_j$.
- **Intensity fraction** — its share of the *detected photons*:
  $f_i = a_i\tau_i / \sum_j a_j\tau_j$.

A dim, short-lifetime species can be a large *mole* fraction yet a small
*intensity* fraction, because it emits few photons per molecule. Always state
which fraction is meant. chisurf's `Lifetime.amplitudes` can be normalized to
sum to one (species fractions); intensity fractions follow by the $a_i\tau_i$
reweighting above.

> **Pedagogical caveat.** Multi-exponential fits are only weakly identifiable:
> lifetimes closer than ~1.5–2× are strongly correlated, and two components can
> often trade off against one continuous distribution. Adding exponentials always
> lowers $\chi^2$; it does not always add physics. Distinguishing genuine discrete
> states from a distribution needs orthogonal evidence (global fitting across
> conditions, a maximum-entropy/distribution model, anisotropy or spectral
> channels) rather than goodness-of-fit alone.

## Global and separated fitting

Because amplitudes and lifetimes appear differently across measurements, TCSPC
gains enormously from **global analysis**: fit several decays (donor-only vs
donor-acceptor, a titration, polarization channels) simultaneously with shared
("linked") lifetimes but independent amplitudes. This breaks the amplitude/
lifetime degeneracy and is how FRET distance distributions and anisotropy decays
are resolved. chisurf's linked `FittingParameter`s and `GlobalFitModel` implement
this; the amplitude block is deliberately kept rank-correct (one redundant
amplitude is held out of the optimizer, since the normalized amplitudes are
scale-invariant) to keep the Jacobian well-conditioned.

## Mapping to chisurf

- **Convolution kernels** — `chisurf/core/fluorescence/tcspc/convolve.py`:
  `convolve_lifetime_spectrum` / `_periodic` (interleaved-spectrum ⊗ IRF, numba
  and tttrlib paths), `convolve_decay_nb` (arbitrary-decay ⊗ IRF), and
  `periodic_shift` (sub-channel IRF/colour shift).
- **Nuisances** — `chisurf/core/fluorescence/tcspc/corrections.py`
  (`add_pile_up_to_model`, Coates 1968; `compute_linearization_table`, DNL) and
  the `Generic`/`Corrections`/`Convolve` groups in
  `chisurf/core/models/tcspc/nusiance.py` (scatter, constant/measured background,
  lamp background, IRF handling, `rescale_w_bg` amplitude scaling).
- **IRF helpers** — `chisurf/core/fluorescence/tcspc/irf.py` (synthetic IRF,
  rising-edge/prompt detection) and `irf_estimation.py` (Richardson–Lucy IRF
  extraction).
- **Weighting** — `counting_noise` and
  `combined_counting_noise_parallel_perpendicular` in the `tcspc` package
  (`__init__.py`); analysis-range selection via `get_analysis_range`.
- **Lifetime models** — `chisurf/core/models/tcspc/lifetime.py` (the `Lifetime`
  group and the multi-exponential model, with the two average lifetimes),
  `fret.py`, `anisotropy.py`, `maxent.py` (distribution model), `pddem.py`,
  `mix_model.py`; catalogue in `tcspc.models.json`, view specs in
  `lifetime.view.json` / `mix_model.view.json`.
- **Poisson-MLE path** — `chisurf/core/fluorescence/mle/` over tttrlib
  `Fit23/24/25`; contract in
  [/subsystems/mle-lifetime-fitting.md](/subsystems/mle-lifetime-fitting.md).

## Pointers

- User-facing rendering: `docs/concepts/tcspc_lifetime.md`.
- MLE engine & input contract: [/subsystems/mle-lifetime-fitting.md](/subsystems/mle-lifetime-fitting.md).
- Fluorescence kernel: [/subsystems/fluorescence-domain.md](/subsystems/fluorescence-domain.md).
- Least-squares engine: [/subsystems/fitting.md](/subsystems/fitting.md).
- VV/VH stacked-decay layout the anisotropy/MLE path expects:
  `okf/references/vv-vh-decay-format.md`.
- QuickFit3 help source (documented prior art):
  `junk/quickfit3/plugins/tcspcimporter/help/lifetime.html`, `fretchen.html`.
</content>
</invoke>
