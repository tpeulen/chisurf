# Blind IRF estimation

Recovers an instrument response from a fluorescence decay when you do not have a
measured one — by fitting the part of the decay the IRF has already stopped
affecting, then deconvolving what is left.

**It is a fallback, not a substitute for measuring the IRF.** Read the limits
section before a number from here goes anywhere near a result.

Press **Guide** for the walk-through.

## How it works

The measured decay is your molecule's decay convolved with the instrument
response. Late in the record the IRF has long since ended, so the tail is the
*pure* exponential decay — fit it there and you know the decay without ever
having seen the IRF.

Knowing the decay and the measurement, the IRF is what connects them, and
**Richardson–Lucy** deconvolution recovers it iteratively. RL is used because it
keeps the result non-negative, which an IRF must be, and because it degrades
gracefully rather than exploding when the data are noisy.

## The three settings that decide the answer

**Channel width (Δt)** must match the acquisition. Everything downstream is in
those units, and a wrong value produces a plausible IRF of the wrong width.

**RL iterations is a regularisation knob, not a convergence one.** More
iterations sharpen the estimate *and* amplify noise — Richardson–Lucy does not
converge to a sensible answer and stop; left running it converges to the noise.
Where you stop *is* the regularisation. Increase it until the IRF stops getting
narrower in a way that looks structural, and no further.

**Background must be removed first.** An offset that is not subtracted has no
exponential shape to attribute to the decay, so the deconvolution attributes it
to the *IRF* — as a long flat tail, which is exactly what an IRF cannot have and
exactly what will bias every lifetime you later fit with it.

## Before believing the result

**The circularity is the thing to watch.** An IRF estimated from a decay and then
used to fit *that same decay* will produce an excellent fit no matter what,
because the IRF absorbed whatever the model could not describe. A good χ² here
is not evidence. If you must do it, at minimum fit a *different* measurement with
the recovered IRF.

**The tail fit is an assumption, not a measurement.** The method assumes the
tail is a single clean exponential. If the sample is multi-exponential, or has a
slow component you have not accounted for, or is still rising where you started
the fit, that error is transferred wholesale into the IRF.

**Does the result look like an instrument response?** One sharp peak with a fast
rise and a short tail. A recovered "IRF" with structure, a shoulder, or a width
comparable to the lifetime you are trying to measure is a failed deconvolution
that will still convolve happily.

**Compare against a real IRF when one exists.** Even an old scatter measurement
from the same instrument tells you whether the width and position are in the
right region. A blind estimate that disagrees with the instrument's known
response by a factor of two is telling you about your tail fit.

If your lifetimes are all far longer than the pulse, consider fitting the tail
directly and skipping deconvolution altogether — a method that needs no IRF beats
one that invents one.

## Further reading

- {cite}`gomezsanchez2024` — the blind IRF identification this tool implements:
  the IRF recovered from the measured decays, without a scatter measurement.
- [TCSPC and fluorescence lifetimes](docs/concepts/tcspc_lifetime.md) — the
  convolution this inverts.
- [Lifetime and anisotropy fitting](docs/guides/10_lifetime_anisotropy_fitting.md)
- [Background rates](docs/guides/15_background_rates.md) — measuring the offset
  that must come off first.
- [IRF and background from the photons you already have](docs/concepts/smfret_bursts.md)
  — for confocal data, the non-burst periods give a *measured* IRF instead of an
  estimated one, which is always the better answer.
