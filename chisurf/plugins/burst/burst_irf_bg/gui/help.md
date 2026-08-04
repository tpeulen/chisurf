# IRF and background from the photons you already have

Most of a confocal single-molecule acquisition contains **no molecule in the
focus**. Those non-burst periods are usually thrown away. They are not waste:
they are a scatter and background measurement you already paid for.

Press **Guide** for the walk-through.

## What is in the non-burst stream

Two things, and they separate cleanly in micro-time:

**Dark counts and after-pulses** are uncorrelated with the laser, so they are
**flat** across the micro-time axis. That flat floor is the background count
rate.

**Scattered excitation light** (Rayleigh and Raman) is instantaneous, so it
produces a sharp prompt peak whose shape *is* the instrument response function.

So one pass over the non-burst photons yields, per detector, both the background
rate and an IRF — with no scatter cuvette, no buffer-only acquisition, and no
possibility of the IRF having been measured under different conditions than the
data, because it came from the same file.

## The trap this tool exists to avoid

**A baseline-subtracted non-burst histogram is not an IRF.**

The non-burst periods still contain dim and passing molecules, so the prompt
rides on a slow fluorescent tail. Subtracting a flat baseline removes the dark
counts and leaves that decay in place. Convolving a lifetime model with the
result biases the recovered lifetime roughly **two-fold short** — a genuine
2.2 ns decay came back as ~1.1 ns on real smFRET data, and the prompt's own first
moment moved several nanoseconds late.

The fix is to fit a **Gaussian** to the prompt. A Gaussian *cannot* represent a
slow tail, and that is exactly why it is the right shape: least squares locks
onto the sharp scatter prompt and leaves the fluorescent artefact behind, while
still following the measured position and width.

Two details that matter, both learned the hard way:

- The width is taken from the **rising edge only**, mirrored. The falling side is
  the fluorescence decay, not the instrument; reading a two-sided half-max opens
  a fit window wide enough for the tail to drag the Gaussian late again (2.5 ns
  against a true 1.0).
- The fit window is the **leading edge**, not a symmetric window, for the same
  reason.

Smoothing is deliberately *not* used anywhere here. The prompt is the sharpest
feature in the histogram, so any kernel wide enough to help also broadens the
width being measured.

## Per detector, always

Each detection channel has its own response. A shared IRF silently replaces
distinct detector responses, and the resulting error is a *systematic* lifetime
shift that differs between channels — indistinguishable from a real difference
between the dyes.

## Before you feed these into a fit

1. **Does the prompt look like a prompt?** One sharp peak. If it has structure or
   a shoulder, the burst mask is letting fluorescence through.
2. **Is the fitted Gaussian on the rising edge?** That is where the instrument
   is; if the fit sits late, the tail has captured it.
3. **Is the background rate plausible?** A few hundred Hz to a few kHz per
   detector. Much more is stray light, not dark counts.
4. **Does a known sample give its known lifetime?** The only end-to-end check
   that matters — and the one that caught the two-fold bias above.

## Further reading

- [TCSPC and fluorescence lifetimes](docs/concepts/tcspc_lifetime.md)
- [Background rates, step by step](docs/guides/15_background_rates.md)
- [Lifetimes from bursts](docs/guides/21_lifetime_from_bursts.md)
- [Single-molecule FRET bursts](docs/concepts/smfret_bursts.md)
