---
type: Concept
title: 'TCSPC: fluorescence-lifetime fitting'
description: Time-correlated single-photon counting (TCSPC) measures the fluorescence lifetime — the mean time a fluorophore spends in the excited state before emitting a photon.
tags: [concepts, tcspc, lifetime, fitting, photons]
anchor: concept-tcspc-lifetime
---

(concept-tcspc-lifetime)=
# TCSPC: fluorescence-lifetime fitting

Time-correlated single-photon counting (TCSPC) measures the **fluorescence
lifetime** — the mean time a fluorophore spends in the excited state before
emitting a photon. Because the lifetime is set by the sum of all excited-state
decay rates, it reports on the fluorophore's environment (quenching, solvent,
FRET, conformation) *independently of concentration or excitation intensity*.
This page explains what the measured decay histogram is, why the model has to be
**reconvolved** with the instrument response before it can be fit, which
instrument/sample nuisances sit around the decay, and how the fitted amplitudes
and lifetimes turn into physical numbers.

For the step-by-step workflows in ChiSurf, see the guides
{doc}`/guides/10_lifetime_anisotropy_fitting`,
{doc}`/guides/21_lifetime_from_bursts` and {doc}`/guides/32_nsalex_lifetime`;
building the decay from a photon file is
{doc}`/guides/73_tttr_decay_and_correlation`; the Decay Analysis window, Lazy
Lifetime Analysis and the Synthetic Decay Generator are
{doc}`/guides/76_decay_analysis_tools`.

## The measurement

A pulsed laser excites the sample every period $T$ (typically 12.5–50 ns). For
each pulse the electronics record the arrival time of **at most one** detected
photon relative to the pulse — the *micro-time*. Over millions of pulses this
builds a histogram $y(t)$ whose shape, in the ideal limit, is the intensity
decay $I(t)$. The one-photon-per-cycle limit is also the source of the *pile-up*
artifact (below), so the detected rate is kept to a few percent of the pulse
rate.

Each channel is Poisson-distributed: its variance equals its mean. Hence the
correct least-squares weight is $\sigma_i=\sqrt{y_i}$, and at low counts the
statistically correct objective is the Poisson likelihood, not Gaussian
$\chi^2$.

(concept-tcspc-histogramming)=
## From a photon stream to a decay histogram

Time-tagging electronics store no histogram. Each photon carries a micro time
$\mu$ (an integer TAC/ADC channel, width $\Delta t$), a macro time and a routing
channel ({ref}`fundamentals-photon-counting`), and the decay is built afterwards
from the photons a selection keeps:

$$
y_k = \#\{\,j \in S : \lfloor \mu_j / b \rfloor = k \,\}, \qquad
\Delta t_b = b\,\Delta t ,
$$

with $S$ the selected photons and $b$ an integer **binning factor** (*TAC div*
in **TTTR: Generate Decay**). The histogram then has $\lceil n_\text{TAC}/b\rceil$
channels.

- **Binning keeps the statistics Poisson.** A coarse channel is a sum of Poisson
  channels, so $\sigma_k=\sqrt{y_k}$ still holds and no weighting changes.
  It costs time resolution only once $\Delta t_b$ approaches the IRF width;
  electronics with a few-ps channel width against a 100–300 ps IRF can be binned
  8–32-fold for free, and the fit gets fewer, better-filled channels.
- **The selection is part of the measurement.** Routing channels separate
  detectors, and therefore polarizations and colours. Parallel and perpendicular
  decays for anisotropy, and the prompt and delayed windows of PIE, are separate
  histograms of one file. A micro-time cut (`TAC < 3000`) drops the end of the
  converter range, where the TAC is least linear and, in reverse start-stop
  mode, where the next laser pulse arrives {cite}`wahl2015`.
- **Macro-time filters select photons by context.** Keeping only photons whose
  next photon follows within $\Delta T_\text{min}$ enriches photons from inside
  single-molecule bursts; the inverse keeps the sparse photons between bursts,
  which is a background or scatter decay taken from the same measurement.

### What distorts the histogram

The histogram is not the decay if the electronics could not record every photon
with equal probability at every micro time. Three effects are routine; ChiSurf's
fit applies the first two to the *model* (*The nuisance terms*, below, and
{ref}`fundamentals-photon-counting`):

- **Differential non-linearity.** Converter channels differ in width, so a flat
  input gives a rippled histogram. It is measured with light uncorrelated with the
  laser and corrected by a per-channel table {cite}`becker2005,wahl2015`. Binning
  by $b$ averages the ripple down roughly as $1/\sqrt{b}$ when channel errors are
  independent, but a periodic pattern survives binning by its own period.
- **Pile-up.** In start-stop timing only the first photon per excitation period
  is recorded, so early photons are over-represented and the decay looks too
  short. The effect scales with the detected photons per pulse: the classical
  limit is 1 %, the lifetime shift stays near 1 % up to about 10 %, and the
  correction of {cite}`coates1968` recovers the rest
  {cite}`oconnor1984,becker2005`.
- **Dead time.** After each detection the detector and the timing channel are
  blind for a dead time $t_d$ (typically tens of ns up to ~100 ns, detector and
  electronics together). With $t_d$ longer than the laser period
  this is the same as pile-up. When $t_d$ is shorter than the period, a photon
  late in the period is lost only if a photon arrived within $t_d$ before it, so
  the loss depends on the micro time and on the previous period. That is not the
  Coates model, and at high count rates in FLIM it biases lifetimes noticeably;
  {cite}`isbaner2016` derive the distortion and a correction applied to the
  histogram. Reverse start-stop, which starts the converter on the photon rather
  than the laser, reduces converter dead time; it does not remove detector dead
  time {cite}`wahl2015`.

A histogram built from a subset of photons carries these distortions as they
were at the full count rate: selecting one detector, or only burst photons, does
not undo pile-up or dead-time losses caused by photons the selection discarded.

## The multi-exponential decay

Each excited-state species depopulates exponentially, so the decay is a sum of
exponentials,

$$
I(t) = \sum_{i} a_i \, e^{-t/\tau_i}, \qquad a_i \ge 0,
$$

with amplitude $a_i$ (proportional to the ground-state population of species $i$)
and lifetime $\tau_i$. One fluorophore in a uniform environment gives one
exponential; mixtures, quenched sub-populations and FRET give several. ChiSurf
stores this as an interleaved *lifetime spectrum* $[a_1,\tau_1,a_2,\tau_2,\dots]$.

## Reconvolution: fitting in convolved space

The excitation pulse, detector and timing electronics are not instantaneous;
their combined blur is the **instrument response function** (IRF),
$\mathrm{IRF}(t)$, measured from scattered light or a short-lifetime reference
dye. The observed noise-free decay is the *convolution* of the true decay with
the IRF:

$$
M(t) = (\mathrm{IRF} \otimes I)(t)
     = \int_{0}^{t} \mathrm{IRF}(t')\, I(t-t')\, \mathrm{d}t'.
$$

Fitting therefore happens **in convolved space**. One does *not* deconvolve the
data — that is ill-posed and amplifies noise. Instead, at every optimizer step
the trial decay is *reconvolved* with the measured IRF and the result $M(t)$ is
compared to the raw histogram (iterative reconvolution). This is what lets TCSPC
resolve lifetimes shorter than the IRF width: the *shape* of the tail, not just
its position, carries the lifetime.

Two practical points:

- **Periodicity.** At high repetition rates the previous pulse's tail has not
  decayed before the next pulse, so it wraps into the early channels of the next
  period. The convolution is then done periodically over $T$.
- **IRF shift (colour shift).** The detector transit time is slightly
  wavelength-dependent, so the fluorescence IRF is offset by a fraction of a
  channel from a scatter measurement. A fitted sub-channel time shift absorbs it;
  getting it wrong biases short lifetimes most.

## The nuisance terms

The count in channel $i$ is not $M_i$ alone. The forward model layers several
instrument/sample nuisances on the reconvolved decay:

$$
y_i^{\text{model}} = L_i \cdot \big[\, s\,\mathrm{IRF}_i
        + (\mathrm{IRF}\otimes I)_i \,\big] \cdot P_i \;+\; b,
$$

- **Scatter $s$** — elastic/Raman scatter arrives with the IRF shape; a scaled
  IRF absorbs it instead of the fit inventing a spurious ultra-short lifetime.
- **Background $b$** — dark counts and ambient light add a constant offset
  (measured from a buffer run or fitted).
- **Pile-up $P_i$** — high count rates preferentially drop *late* photons,
  shortening the apparent lifetime; corrected per-channel on the model
  ({cite}`coates1968`) so the measured Poisson statistics are preserved. The correction divides
  by the excitation pulses that have not yet produced a detection, so it needs
  the *measurement time* (nuisance $t_{exp}$) and the *repetition rate* of the
  run: if the two imply fewer pulses than there are recorded photons the
  correction is undefined and is skipped rather than applied.
- **Differential non-linearity $L_i$** — channel-width variations of the
  time converter, flattened with a linearization table from uncorrelated light.

These are always applied to the *model*, never by pre-correcting the noisy data,
so the residuals stay Poisson.

## Least squares vs Poisson MLE

- **Weighted least squares** minimizes $\chi^2=\sum_i (y_i-y_i^{\text{model}})^2/y_i$
  — accurate when every fitted channel has many counts (cuvette decays).
- **Poisson maximum likelihood** is required when counts per channel are small —
  per-burst and per-pixel fits, where a whole decay may hold only tens to
  hundreds of photons. There the Gaussian approximation biases the lifetime.
  ChiSurf routes these through the tttrlib $\mathrm{Fit23/24/25}$ estimators (the
  $2I^*$ statistic of {cite}`maus2001`); see {doc}`/guides/21_lifetime_from_bursts`.

Both fit in convolved space; they differ in the statistic and in how many
parameters a given photon budget can support.

## Average lifetimes and fractions

A multi-exponential decay has **two inequivalent averages**. The
species-averaged (amplitude-weighted) lifetime,

$$
\langle\tau\rangle_x = \frac{\sum_i a_i\tau_i}{\sum_i a_i},
$$

scales with the area/quantum yield and is the correct quantity for FRET
efficiency, $E = 1-\langle\tau\rangle_x^{DA}/\langle\tau\rangle_x^{D}$. The
intensity- (fluorescence-) weighted lifetime,

$$
\langle\tau\rangle_f = \frac{\sum_i a_i\tau_i^{2}}{\sum_i a_i\tau_i}
\;\ge\; \langle\tau\rangle_x,
$$

weights each species by the photons it emits and is what a tail fit or a
phasor/mean-arrival-time estimate returns.

The same weighting governs component fractions: the **species (mole) fraction**
is $x_i=a_i/\sum_j a_j$, while the **intensity fraction** is
$f_i=a_i\tau_i/\sum_j a_j\tau_j$. A dim, short-lifetime species can be a large
mole fraction yet a small intensity fraction — always state which you mean.

To see how far apart the two averages can be, take equal amplitudes
($a_1=a_2$) of a 0.5 ns and a 4.0 ns species:

$$
\langle\tau\rangle_x = \frac{0.5+4.0}{2} = 2.25\;\text{ns},
\qquad
\langle\tau\rangle_f = \frac{0.5^2+4.0^2}{0.5+4.0} = \frac{16.25}{4.5}
= 3.61\;\text{ns}.
$$

Half the *molecules* are short-lived, but they contribute only
$f_1 = 0.5/4.5 = 11\%$ of the *photons*. Quoting $\langle\tau\rangle_f = 3.61$ ns
where the FRET formula needs $\langle\tau\rangle_x = 2.25$ ns would understate the
efficiency badly — with a 4.0 ns donor, $E = 1-2.25/4.0 = 0.44$ against a
spurious $E = 1-3.61/4.0 = 0.10$. This single confusion is the most common
error in reported lifetime-based FRET efficiencies.

```{figure} figures/lifetime_averages.png
:name: fig-lifetime-averages
:width: 100%

**Two averages of one decay.** *Left:* equal amplitudes of a 0.5 ns and a 4.0 ns species, reconvolved with a 90 ps IRF by {src}`chisurf/core/fluorescence/tcspc/convolve.py#convolve_lifetime_spectrum`, with the two averages marked. *Right:* the same two species weighted the two ways — half the *molecules* are short-lived, but they contribute 11 % of the *photons*. Quoting $\langle\tau\rangle_f$ where the FRET formula wants $\langle\tau\rangle_x$ turns $E = 0.44$ into $E = 0.10$.
```

```{note}
Multi-exponential fits are only weakly identifiable: lifetimes closer than
~2× are strongly correlated, and discrete components can trade off against a
continuous distribution. Adding exponentials always lowers $\chi^2$ without
necessarily adding physics. Distinguish real states from a distribution with
orthogonal evidence — global fitting, a maximum-entropy model, or anisotropy/
spectral channels — not goodness-of-fit alone.
```

(concept-tcspc-model-selection)=
## How many components?

Models with $n$ and $n+1$ exponentials are **nested**: setting one amplitude to
zero turns the larger into the smaller, so its minimum $\chi^2$ can only be
lower. Whether the drop is more than noise is a test, not a reading of
$\chi^2_r$. With $\nu_n = N - p_n$ degrees of freedom and $\Delta p = p_{n+1}-p_n$
(two per exponential), the **extra-sum-of-squares F-test** is

$$
F = \frac{(\chi^2_n - \chi^2_{n+1})/\Delta p}{\chi^2_{n+1}/\nu_{n+1}}
\;\sim\; F(\Delta p,\, \nu_{n+1}),
$$

exact for linear models and approximate for a non-linear fit
{cite}`motulsky1987`. Written in the ratio of reduced chi-squares that lifetime
software usually reports, $R = \chi^2_{r,n}/\chi^2_{r,n+1} = (\nu_{n+1}+\Delta p\,F)/\nu_n
\approx 1 + \Delta p\,(F-1)/\nu$. The threshold a given ratio must beat depends
strongly on which distribution it is referred to. For $\nu = 3500$ channels and
$\Delta p = 2$:

| Rule | Referred to | $R$ needed at 68 % | at 95 % |
|---|---|---|---|
| extra-sum-of-squares | $F(\Delta p, \nu_{n+1})$ | 1.0001 | 1.0011 |
| ratio of reduced $\chi^2$ (the **F-Test** tool) | $F(\nu_n, \nu_{n+1})$ | 1.016 | 1.057 |
| ratio against $F(2, \nu_{n+1})$ (**Lazy Lifetime Analysis**) | — | 1.14 | 3.0 |

The first is the textbook test; the second treats the two $\chi^2$ as
independent, which they are not, and is correspondingly conservative; the third
is what {doc}`/guides/76_decay_analysis_tools` measures and flags as a defect.

Three cautions apply whichever rule is used.

- **Significance is not physics.** At $10^6$ photons the extra-sum test accepts
  a component that lowers $\chi^2_r$ by 0.1 %. An IRF that is slightly wrong in
  shape or position produces exactly such residual structure, and an extra
  exponential absorbs it. A component is established when it survives a change of
  IRF, of fit range and of starting values, and when a distribution model
  ({ref}`concept-maximum-entropy`) or a global fit finds it too.
- **Close lifetimes are poorly separable.** Exponentials are far from
  orthogonal: two lifetimes within a factor of about two are strongly correlated
  with each other and with their amplitudes, and the separation that a given
  photon budget allows falls off steeply with their ratio
  {cite}`grinvald1974,istratov1999`.
- **The test assumes both fits reached their minimum.** A multi-exponential fit
  started from poor values can end *above* the fit with one component fewer; a
  selection rule applied to such a sequence counts optimizer failures, not
  components. Start the $n+1$ fit from the $n$ solution plus one new component,
  and check that $\chi^2$ is monotone in $n$ before testing anything.

Information criteria make the same trade without a threshold. For a
least-squares fit with Gaussian errors, up to a constant,
$\mathrm{AIC} = \chi^2 + 2p$ {cite}`akaike1974` and
$\mathrm{BIC} = \chi^2 + p\ln N$ {cite}`schwarz1978`; the model with the smaller
value wins. Adding an exponential costs 4 in AIC and $2\ln N$ in BIC (16 at
3500 channels), so on well-filled decays AIC accepts components BIC rejects
{cite}`burnham2004`.

(concept-tcspc-synthetic-decays)=
## Synthetic decays

A decay generated from known parameters is the only data on which a fitted
lifetime can be called right or wrong. ChiSurf builds one as the measurement
does: the ideal decay on the channel grid, convolved with a normalized IRF, then
sampled,

$$
p_k = \frac{(\mathrm{IRF}\otimes I)_k}{\sum_j (\mathrm{IRF}\otimes I)_j},\qquad
y_k \sim \mathrm{Poisson}(N\,p_k).
$$

Independent Poisson channels are a multinomial draw of $N'$ photons with
$N' \sim \mathrm{Poisson}(N)$, so the total itself scatters: a request for
$10^4$ photons returned 9883 for one seed. Without the sampling step the result
is the exact expectation $N p_k$ — the right input for checking that code
reproduces a function, and the wrong one for anything about uncertainty, since
$\chi^2$ against noise-free data has no distribution.

The photon budget sets a floor on the precision of any lifetime estimate,
$\sigma_\tau/\tau = F/\sqrt{N}$, with $F = 1$ for a single exponential recorded
without IRF blur, background or truncation, and $F > 1$ once any of those enter
{cite}`kollner1992`. 400 generated 4 ns decays of $10^4$ photons in a 65 ns
window, estimated by their mean arrival time, gave $F = 1.03$. A window shorter
than a few times the longest lifetime truncates the tail that carries the
evidence for it, and $F$ grows accordingly.

Two generator options model effects a real instrument has and the simple
recipe above omits: a finite laser **period**, which wraps the unrelaxed tail of
earlier pulses into the window through the periodic kernel (*Reconvolution*,
above), and a sub-channel **time shift** of the IRF. Both are arguments of
{src}`chisurf/core/fluorescence/decay.py#synthetic_decay`, not of the GUI.

## Global fitting

Fitting several decays together — donor-only vs donor-acceptor, a titration, or
parallel/perpendicular polarization channels — with **shared (linked) lifetimes**
but independent amplitudes breaks the amplitude/lifetime degeneracy. This is how
FRET distance distributions and anisotropy decays are resolved; see
{doc}`/guides/10_lifetime_anisotropy_fitting` and
{doc}`/guides/32_nsalex_lifetime`.

## See also

- Fundamentals: {ref}`fundamentals-photon-counting` (the measurement and its
  limits) · {ref}`fundamentals-photon-statistics` (weighting, $\chi^2_r$,
  residuals) · {ref}`fundamentals-lifetime-quantum-yield` (the rate picture and
  the two averages).
- Guides: {doc}`/guides/10_lifetime_anisotropy_fitting` ·
  {doc}`/guides/21_lifetime_from_bursts` · {doc}`/guides/32_nsalex_lifetime` ·
  {doc}`/guides/73_tttr_decay_and_correlation` (histogramming a photon file) ·
  {doc}`/guides/76_decay_analysis_tools` (Decay Analysis, Lazy Lifetime
  Analysis, Synthetic Decay Generator).
- Implementation: convolution kernels
  {src}`chisurf/core/fluorescence/tcspc/convolve.py`; nuisances (pile-up, DNL)
  {src}`chisurf/core/fluorescence/tcspc/corrections.py`; IRF helpers
  {src}`chisurf/core/fluorescence/tcspc/irf.py`; lifetime model view
  {src}`chisurf/core/models/views/tcspc_lifetime.view.json`; Poisson-MLE facade
  {src}`chisurf/core/fluorescence/mle/__init__.py`.
- Key literature: {cite}`oconnor1984` is the standard treatment of reconvolution
  and the nuisance terms; {cite}`becker2005` the instrumentation, pile-up and
  differential non-linearity; {cite}`lakowicz2006` (lifetime chapters) the two
  averages and their correct use; {cite}`coates1968` the pile-up correction
  applied above; {cite}`maus2001` the $2I^*$ statistic used for burst- and
  pixel-wise fits; {cite}`wahl2015` the timing electronics and acquisition
  modes; {cite}`isbaner2016` dead-time distortion and its correction.
- Tools in ChiSurf: **Decay Analysis** (`chisurf/plugins/fluorescence_decay/lifetime_analysis/`) collects the decay tools — IRF estimation, **MaxEnt MEM** (`chisurf/plugins/fluorescence_decay/maxent_decay/`) for a lifetime *distribution*, **Lazy Lifetime Analysis** (`chisurf/plugins/fluorescence_decay/lltf/`) for an automated discrete-exponential fit of one decay file, and the **Synthetic Decay Generator** (`chisurf/plugins/fluorescence_decay/synthetic_decay/`) for a decay whose answer you know.
