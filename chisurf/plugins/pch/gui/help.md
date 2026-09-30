# Photon Counting Histogram (PCH) analysis

The photon counting histogram P(k) is how often a counting interval (a time bin) contains exactly k photons. Its shape carries what the mean intensity cannot: the molecular brightness ε (counts per bin per molecule) and the mean number ⟨N⟩ of molecules in the detection volume. One species broadens the histogram beyond a Poisson distribution of the same mean; a mixture broadens it further. For the theory see [Photon-counting histogram (PCH) and FIDA](docs/concepts/pch_fida.md); for a worked example and the known limits of this tool's fit see [FIDA — photon-counting histograms](docs/guides/04_fida_pch.md).

## How it works
1. Press Load TTTR and choose a photon-stream file (PTU, HT3, T2R, T3R, PTO, SPC), or drop the file on the window.
2. Set Channels to your detectors, Bin time (μs) and, if needed, the Micro time gate.
3. Press Compute PCH. The intensity trace (top) and the histogram P(k) (bottom, logarithmic) are drawn.
4. Set Components and the starting values of ε and ⟨N⟩ in the table (double click a cell to edit).
5. Drag the two vertical lines on the histogram to choose the k range of the fit, then press Fit Model.

## Settings
- Channels: comma-separated routing channels that are counted, for example 0,2. Empty counts all channels.
- Bin time: the counting interval in microseconds. It must be short compared with the diffusion time, so that a molecule does not move much during one bin.
- Micro time: the lower and upper TAC channel of the gate; photons outside it are not counted.
- Components: the number of species. Each has a brightness ε and an occupancy ⟨N⟩; the fit replaces the starting values by the fitted ones.

## Output
The results text lists ε, ⟨N⟩ and the fraction of every species and the χ² over the selected k range. Moving a line recomputes the χ² of an existing fit over the new range. Save Results writes the trace, the histogram and the fit as NPZ, the histogram and fit as CSV, and the results text as TXT, under the base name you choose.

## Command line
The same analysis runs headless: pch analyze data.ptu --components 2 --bin-time 50 computes and fits a file, and pch refit results.npz --components 3 re-fits a saved histogram. Add --json for machine-readable output.

## Before trusting a result
The fit is unweighted and the χ² is Pearson's over every bin with a positive expected count, so a tail bin with a tiny expectation can dominate it. Compare the fitted curve with the data on the log axis, not only the number.
