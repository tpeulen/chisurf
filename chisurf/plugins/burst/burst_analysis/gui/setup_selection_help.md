# Setup Selection — the detector setup of the workflow

Step 0 of the Burst Analysis workflow. The page is ChiSurf's shared detector-setup
editor — the same one as *Setup: Channel Definition* — so a setup saved here is the
one every other tool lists, and the other way round.

- **Setup** chooses a saved setup; the last used one opens when the step starts.
  **Save**, **Rename** and **Delete** act on the store.
- **TTTR reading routine** sets the file type and reads the timing (macro- and
  micro-time resolution, binning) from a measurement.
- **Detectors** lists each detector's routing channels — parallel first, then
  perpendicular — its micro-time gates, G factor and the polarisation mixing
  l1 / l2. **PIE windows** names the micro-time range of each excitation.
- **LUT handling** assigns or computes per-channel linearisation tables; the
  decay preview shows the gates over a measured decay.

What the later steps take from here: the burst search reads the detectors and
windows (its per-detector burst columns are named after them), BVA, 2CDE, the MLE
fits and H2MM read the detector definition, Accurate FRET the window names.

See [Photon burst identification](docs/guides/13_burst_identification.md).
