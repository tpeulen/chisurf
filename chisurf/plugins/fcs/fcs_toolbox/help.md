# FCS

Turns photon streams into correlation curves worth fitting, one step at a time,
and hosts the other FCS tools in the same window.

## The correlator workflow

1. **Channel Definitions** — pair the logical detectors of a detector setup
   (autocorrelations, cross-correlations).
2. **Files & Steps** — the photon streams to correlate (checked files are
   concatenated), and whether steps 3 and 5 run.
3. **Photon / Burst Filter** — keep only some photons: a count-rate cut against
   aggregates, bursts, or change-point detection.
4. **Correlator** — routing channels and micro-time windows of the two streams,
   multi-tau settings, and **Splits**: the number of chunks correlated
   separately. Splits are what give the merger repeats to average and reject.
5. **FCS Merger** — tick the chunks to keep; the mean and its standard error
   are saved as a `.cor` file and can be added to ChiSurf for fitting.

## Tools

2D-FLCS, Lifetime-FCS Sim, Burst-wise FCS, the diffusion/volume calculator and
the fFCS filter calculator — each has its own **?** help.

## Further reading

- [FCS toolbox: correlate, merge, convert](docs/guides/75_fcs_toolbox.md) — every
  setting, the `.cor` format, converting between file formats, and the headless
  equivalent.
- [FCS: the correlation curve and its models](docs/concepts/fcs_correlation.md) —
  what G(τ) is, and how its error bars are estimated.
- [Diffusion FCS](docs/guides/09_diffusion_fcs.md) — fitting the curve.
