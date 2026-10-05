# FCS Correlator

Turns photon streams into correlation curves: G(τ), how much more likely a second photon is at lag τ after a first
one, normalised so that uncorrelated photons give 1. The amplitude G(0) − 1 is about one over the mean number of
molecules in the focus; the lag where the curve falls is the time a molecule needs to cross it.

## The steps

1. **Channel Definitions**: the detector setup, and which detectors are the logical channels of A and B.
2. **Files & Steps**: the TTTR files (ticked ones are correlated; a folder adds the TTTR files in it), and whether the
   photon filter (3) and the merger (5) run. **Example** adds a simulated measurement whose curve falls near 0.5 ms.
   A Burst-ID (`.bst`) file switches the filter off.
3. **Photon / Burst Filter**: keep only the photons in bursts or under a count-rate cut, so that aggregates and
   background do not dominate the curve. The plots show what is kept; drag the blue lines to set min / max dMT.
4. **Correlator**: routing channels and micro-time windows of A and B (empty = all detectors), multi-tau **Bins** and
   **Cascades**, **Splits** (the stream is cut into pieces correlated separately: their spread is the error, an odd
   one flags a bubble or bleaching), **Fine** for the micro-time-resolved grid. **Load filters...** switches to
   lifetime-filtered (FLCS) species correlation.
5. **FCS Merger**: untick the pieces that do not belong; the mean and its standard error are saved as `.cor` or added
   to ChiSurf for fitting.

## Further reading

- [FCS toolbox: correlate, merge, convert](docs/guides/75_fcs_toolbox.md)
- [FCS: the correlation curve and its models](docs/concepts/fcs_correlation.md)
- [Filtered FCS](docs/concepts/filtered_fcs.md)
