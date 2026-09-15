# Synthetic decay generator

Builds a TCSPC decay histogram from a lifetime spectrum you specify — optionally
convolved with an IRF and given Poisson shot noise.

Its use is that **you know the answer**. A fitting routine, a starting-value
strategy or a model comparison can be checked against data whose parameters you
set, which is the only place a recovered lifetime can be called right or wrong.

Press **Guide** for the walk-through.

## What is generated

The decay is the amplitude-weighted sum of exponentials

**f(t) = Σᵢ aᵢ · exp(−t/τᵢ)**

sampled on `Bins` channels of width `Δt`, convolved with an IRF if one is given,
and then — if shot noise is on — drawn as Poisson counts scaled to the requested
photon budget.

## The aᵢ are amplitudes, not brightnesses

This trips people up constantly, so it is worth being explicit. The `a` column
holds **pre-exponential amplitudes**: they are proportional to the *number of
molecules* in each state, not to the light each contributes.

A long-lived species emits for longer, so its share of the photons is weighted by
its lifetime. The **intensity fraction** is

**fᵢ = aᵢτᵢ / Σⱼ aⱼτⱼ**

so an amplitude-equal mixture of 1 ns and 4 ns components is **20 % / 80 %** in
photons. The species-averaged lifetime ⟨τ⟩ = Σaᵢτᵢ/Σaᵢ and the
intensity-averaged ⟨τ⟩_f = Σaᵢτᵢ²/Σaᵢτᵢ differ for the same reason, and mixing
them up is one of the more common ways a published lifetime is wrong.

## The window is Bins × Δt, and it must fit the decay

The default 256 bins at 0.032 ns spans **8.2 ns**. A decay whose longest
component is 4 ns is barely two lifetimes long in that window — the tail is cut
off before it has decayed, and a fit to it will report a **shorter** long
lifetime than you asked for, because the evidence for the slow component is the
part that was truncated.

The rule of thumb is a window of at least 3–5 times the longest lifetime, and
more if the slow component is a small amplitude fraction. Widen it with either
`Bins` or `Δt`; they trade time resolution against range, and `Δt` also has to
stay well below the shortest lifetime you intend to resolve.

`Start` shifts where the decay begins in the window, which is what you want when
mimicking a real measurement whose prompt does not sit in channel 0.

## Noise, and what it is for

**Photons** sets the total budget; Poisson noise then gives each channel a
standard deviation of √(counts in that channel). What decides whether a fit can
resolve two components is the **peak** channel count, not the total: at a peak of
10 000 the relative error there is 1 %, and in the tail — where the long lifetime
lives — it is far worse.

**Turning shot noise off** gives an exact model curve. That is the right setting
for checking that an implementation reproduces a known function, and the wrong
one for anything about uncertainty: a fit to noiseless data has a χ² with no
meaning, and error estimates derived from it are fiction.

**Seed** makes a noisy dataset reproducible. Change it to draw an independent
realisation — which is how you find out whether a result depends on one lucky
noise pattern, and it usually takes only a handful of seeds to find out.

## The IRF

Without one, the generated decay starts instantaneously — a mathematical
convenience no instrument produces. With one, the rise is smeared by the
instrument's response, and **components shorter than the IRF width stop being
recoverable**: below roughly a nanosecond most of the shape is the IRF, not the
sample.

If the point of the exercise is to test a fitting routine that deconvolves, it
must be given data that were convolved. Testing a deconvolving fit on
IRF-free data proves it can do the easy case.

## Anisotropy: VM vs VV/VH

The **Mode** choice picks the measurement. **VM (magic angle)** generates the
ordinary polarisation-free decay above — it carries no anisotropy. **VV/VH
(polarized)** generates the parallel and perpendicular pair the way the
instrument would see it:

**f_VV(t) = f_VM(t) · (1 + (2 − 3·l₁)·r(t))**
**f_VH(t) = f_VM(t) · (1 − (1 − 3·l₂)·r(t)) / g**

The corrections are the ones the fit stack uses: **g** is the
parallel/perpendicular detection sensitivity ratio (the perpendicular channel
records 1/g of what an equally sensitive one would), and **l₁**, **l₂** are the
polarization mixing factors of the two channels.

**r(t)** comes from the rotation-spectrum table — one row per correlation
component, `b` amplitudes summing to the fundamental anisotropy r₀:

**r(t) = Σᵢ bᵢ · exp(−t/ρᵢ)**

The anisotropy is plotted in its own panel, in both modes (in VM mode the decay
carries no anisotropy, but the sample's r(t) is still the sample's). With shot
noise on, the Poisson budget is shared between the channels proportionally, so
the *pair* is a realistic observation — including the cross-talk between the
channels' noise.

**Save** in VV/VH mode writes a VV/VH file whose footer carries g, l₁, l₂ and
the mode, so reading it back through the VV/VH reader restores the corrections
the data were generated with. **Fit group** skips the file entirely: it adds
the generated curves as a dataset and creates a fit group with the Lifetime
model exactly as a VV/VH data load does — VV and VH become group members with
`vv`/`vh` polarisations, g/l₁/l₂ are carried into the model parameters, and the
bin width comes in through the time axis.

## Before trusting a conclusion drawn here

- **Does the window hold the decay?** See above; a truncated tail biases every
  long lifetime downward.
- **Are you comparing amplitudes with amplitudes?** Not amplitudes with intensity
  fractions.
- **Did you vary the seed?** One realisation is one realisation.
- **Is the photon budget realistic?** A routine that works at 10⁶ photons and
  fails at 10⁴ has not been shown to work on your data.
- **Was the IRF part of the test, or only of the generation?**

## Further reading

- [TCSPC and fluorescence lifetimes](docs/concepts/tcspc_lifetime.md) — the model,
  the convolution and the averaged lifetimes.
- [Lifetime and anisotropy fitting](docs/guides/10_lifetime_anisotropy_fitting.md)
- [Simulating TTTR data](docs/guides/18_tttr_simulation.md) — the photon-level
  simulator, when a histogram is not enough.
- [Parameter uncertainty](docs/guides/39_parameter_uncertainty.md) — what to do
  with the several realisations the seed lets you draw.
