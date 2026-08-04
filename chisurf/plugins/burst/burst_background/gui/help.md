# Background rates — the number every corrected quantity leans on

Every corrected single-molecule quantity is a count **minus a background**. The
FRET efficiency, the stoichiometry, the burst size you cut on — all of them are
differences, and the thing being subtracted is estimated here, per detector.

Press **Guide** for the walk-through.

## How the rate is measured

Not by staring at a blank region of the trace, and not from a buffer-only
acquisition — from the measurement itself.

Build the histogram of **inter-photon times**: the gap between each photon and
the next, on one detector. Background photons arrive as a Poisson process, so
their gaps are distributed exponentially, `A·exp(−rate·t)`. Photons from a
molecule crossing the focus arrive in a tight cluster, so they pile up at *short*
gaps and leave the long-gap region alone.

That is the whole idea: **the tail of the inter-photon-time histogram is pure
background**, because a bright burst cannot produce a long gap. Fit an
exponential to the tail and its rate constant *is* the background count rate.

The approach follows Ingargiola *et al.*, PLoS ONE (2016), and the same tail fit
used in PAM's `Estimate_Background_From_Burst.m`.

## Why this beats a separate blank measurement

A buffer-only acquisition measures the background of *that* acquisition — not of
the sample sitting in the beam, not at the laser power that drifted over the next
two hours, and not including the dim, out-of-focus molecules that genuinely
contribute. Estimating from the measurement itself tracks all of it, and it
costs no extra acquisition time.

## The one setting that matters

**Where the tail starts.** Too early and burst photons are included, which biases
the rate *upward* — and a background that is too high subtracts real signal,
pushing dim bursts toward the wrong efficiency. Too late and you fit noise, and
the rate becomes unstable between files that should agree.

Look at the diagnostic plot rather than trusting a default: the fitted line
should lie on the data over the whole region it covers, and the region should
start where the curve has clearly stopped bending.

## Per detector, always

Each detection channel has its own dark-count rate and its own share of scattered
light. A single shared background is not a simplification — it moves *E* by
different amounts in the two channels, which is exactly the signature of a real
FRET difference.

## Before you use these numbers

1. **Do the rates look like a detector?** Typical dark counts are a few hundred
   Hz to a few kHz. A rate of tens of kHz is scattered light or ambient light,
   not dark counts, and is worth fixing at the microscope instead.
2. **Do repeats agree?** Files from one session should give consistent rates. A
   rate that drifts across a session is real information — about the sample or
   the laser, not about the detector.
3. **Does the fit lie on the tail?** The most common failure is a tail region
   that starts inside the burst-dominated part of the histogram.

It also runs headless: `csc burst-background --help`.

## Further reading

- [Single-molecule FRET: bursts, E, S and the corrections](docs/concepts/smfret_bursts.md)
- [Background rates, step by step](docs/guides/15_background_rates.md)
- [Finding bursts](docs/guides/13_burst_identification.md)
- [Accurate FRET — the correction factors](docs/concepts/accurate_fret.md)
