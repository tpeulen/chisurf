# IRF extraction

The one place ChiSurf extracts an instrument response: from a fluorescence decay
(blind), a reference dye of known lifetime, a scatter, or the photons outside the
bursts. Burst MLE and Burst IRF & Background take their IRF from the same code;
Burst MLE's **IRF tool** button opens this window with what its IRF came from.

## Source

* **Blind** — a fluorescence decay: fit the part the IRF has stopped affecting,
  then deconvolve what is left (below).
* **Reference dye** — a dye with one lifetime (Rh110, Alexa647): each polarisation
  is the IRF convolved with (1 + 2r) e^(−t/τ) (VV) or (1 − r) e^(−t/τ) (VH); the
  IRF is recovered by Richardson–Lucy with that kernel. **Lifetime** 0 fits τ to
  the tail of VV + 2 VH (**Listed** when that fails); **ρ** 0 reads the rotation
  from VV and VH (it needs **VV | VH halves**). The exact difference used before
  took the rotation for part of the IRF.
* **Scatter** — water or Ludox: the prompt above the floor is the IRF.
* **Non-burst** — the photons between the molecules: a Gaussian or skewed Gaussian
  fitted to the prompt's rising edge leaves the fluorescent tail behind.

**Reference fit** (a view beside **Plots**): with the Reference dye source the dye's decay is fitted with
the IRF just extracted from it and the model a burst fit uses -- one amplitude, a flat background per
polarisation, the time shifts free, the lifetime fixed to the dye database's, the rotation read from
it and G, l1, l2 as the detector has them (opened from Burst MLE; G fitted otherwise). Data and model
over the weighted residuals, χ²ᵣ in the title, G and the shifts under **Est Results**. For a dye of
one lifetime it must be about 1 (a little more for a bright bulk measurement); a wave at the rise is
the IRF, VV and VH pulling apart is G or l1/l2, the first nanosecond the rotation.

The window opens **Simple** (the source and **Estimate IRF**); **Advanced** shows every setting. Opened from
Burst MLE's **IRF tool**, each estimate you make goes back to Burst MLE and is fitted there.

The rest of this help is about the blind estimate.

**It is a fallback, not a substitute for measuring the IRF.** Read the limits
section before a number from here goes anywhere near a result.

Press **Guide** for the walk-through.

The decay comes from the **Input** section, which lists the decays of the Datasets workspace: drop a
file on the ChiSurf window to add one, then pick it. **Load example** adds a seeded decay with a
known IRF to the workspace and estimates it.

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

- [Extracting the instrument response](docs/concepts/irf_extraction.md) — every
  source, the reference-dye deconvolution and its measured error.
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
