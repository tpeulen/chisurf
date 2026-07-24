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
{doc}`/guides/21_lifetime_from_bursts` and {doc}`/guides/32_nsalex_lifetime`.

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
  shortening the apparent lifetime; corrected per-channel on the model (Coates
  1968) so the measured Poisson statistics are preserved.
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
  Maus-2001 $2I^*$ statistic); see {doc}`/guides/21_lifetime_from_bursts`.

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

```{note}
Multi-exponential fits are only weakly identifiable: lifetimes closer than
~2× are strongly correlated, and discrete components can trade off against a
continuous distribution. Adding exponentials always lowers $\chi^2$ without
necessarily adding physics. Distinguish real states from a distribution with
orthogonal evidence — global fitting, a maximum-entropy model, or anisotropy/
spectral channels — not goodness-of-fit alone.
```

## Global fitting

Fitting several decays together — donor-only vs donor-acceptor, a titration, or
parallel/perpendicular polarization channels — with **shared (linked) lifetimes**
but independent amplitudes breaks the amplitude/lifetime degeneracy. This is how
FRET distance distributions and anisotropy decays are resolved; see
{doc}`/guides/10_lifetime_anisotropy_fitting` and
{doc}`/guides/32_nsalex_lifetime`.

## See also

- Guides: {doc}`/guides/10_lifetime_anisotropy_fitting` ·
  {doc}`/guides/21_lifetime_from_bursts` · {doc}`/guides/32_nsalex_lifetime`.
- Implementation: convolution kernels
  `chisurf/core/fluorescence/tcspc/convolve.py`; nuisances (pile-up, DNL)
  `chisurf/core/fluorescence/tcspc/corrections.py`; IRF helpers
  `chisurf/core/fluorescence/tcspc/irf.py`; lifetime models
  `chisurf/core/models/tcspc/`; Poisson-MLE facade
  `chisurf/core/fluorescence/mle/`.
</content>
