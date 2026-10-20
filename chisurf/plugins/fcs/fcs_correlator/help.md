# FCS

Turns photon streams into correlation curves: G(τ), how much more likely a second photon is at lag τ after a first
one, normalised so that uncorrelated photons give 1. The amplitude G(0) − 1 is about one over the mean number of
molecules in the focus; the lag where the curve falls is the time a molecule needs to cross it.

## The steps

1. **Channel Definitions**: the detector setup, and which detectors are the logical channels of A and B.
2. **Files & Steps**: the TTTR files (ticked ones are correlated; a folder adds the TTTR files in it), and whether the
   photon filter (3) and the merger (5) run. **Load example** adds a simulated measurement whose curve falls near 0.5 ms.
   A Burst-ID (`.bst`) file switches the filter off. With several files, **Correlate files separately** correlates
   each file on its own (Splits within each file) and the merger averages the files' pieces (`<file>-<n>`); off, the
   files' photons are stacked into one stream first.
   The file table lists every file (a folder's files under it); its **Regions** column counts each file's time
   regions. Select one file to draw its count-rate trace below. With **✏ Draw** on, drag on the trace to add a time
   region, drag an edge to move it, right-click a region to remove it; only the photons inside a file's regions are
   filtered and correlated (a file without regions is used whole). **To all files** copies the regions to the other
   files.
3. **Photon / Burst Filter**: keep only the photons in bursts or under a count-rate cut, so that aggregates and
   background do not dominate the curve. The plots show what is kept; drag the blue lines to set min / max dMT.
4. **Correlator**: routing channels and micro-time windows of A and B (empty = all detectors), multi-tau **Bins** and
   **Cascades**, **Splits** (the stream is cut into pieces correlated separately: their spread is the error, an odd
   one flags a bubble or bleaching), **Fine** for the micro-time-resolved grid. **Load filters...** switches to
   lifetime-filtered (FLCS) species correlation.
5. **FCS Merger**: untick the pieces that do not belong; the mean and its standard error are saved as `.cor` or added
   to ChiSurf for fitting. Every `.cor` gets
   a settings file beside it, `<name>.cor.json`: the raw files (with checksums), their regions, the filter and
   correlator settings and the pieces merged. `python -m chisurf.plugins.fcs.fcs_correlator.provenance <name>.cor.json`
   computes the curve again from the raw photons.

## The other FCS tools

**Filter Calc...** in the Correlator step opens the fFCS Filter Calculator in its own window with the checked files as
its mixed decay (the calculator keeps a mixed decay you loaded there yourself). 2D-FLCS, Lifetime-FCS Simulator,
Burst-wise FCS and the Diffusion/Volume Calculator are buttons of their own in **Spectroscopy › Correlation**, each with
its own **?** help and **Guide**.

## Further reading

- [FCS toolbox: correlate, merge, convert](docs/guides/75_fcs_toolbox.md)
- [FCS: the correlation curve and its models](docs/concepts/fcs_correlation.md)
- [Filtered FCS](docs/concepts/filtered_fcs.md)
