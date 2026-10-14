---
type: File Format
title: PCH TTTR files
description: How the PCH experiment turns a TTTR photon stream into a photon counting histogram.
tags: [reference, file-formats, tttr, photons]
---

# PCH TTTR files {#pch-tttr}

How the **PCH** experiment turns a TTTR photon stream into a photon counting
histogram (PCH). Theory: {doc}`/concepts/pch_fida`; workflow:
{doc}`/guides/04_fida_pch`.

## Supported input formats

The reader opens the file with `tttrlib.TTTR` using its reading routine
(`PTU` by default). Other formats `tttrlib` reads work too, provided they carry
macro-times, routing channels and micro-times.

## Reader setup: PCH (TTTR)

In the **Read data** dock choose **Experiment** `PCH` and **File type**
`PCH (TTTR)`, drop the file on **File** (or **Browse…**) and press **+ Data**.

The reader (`chisurf.core.experiments.pch.PCHReader`):

1. selects the photons of the chosen routing channels (*Detector*) inside the
   micro-time window **µtime min**–**µtime max** (TAC channels, default
   0–65535);
2. counts photons in bins of **Bin time [µs]** (default 100 µs);
3. histograms the counts per bin into $P(k)$ and builds a `DataCurve` with $k$
   on the x-axis. The uncertainty of each point is
   $\sqrt{n_k}/N_\mathrm{bins}$, with $n_k$ the number of bins holding $k$
   photons ($1/N_\mathrm{bins}$ where $n_k = 0$).

## Typical workflow

1. Set the detector, bin time and micro-time window.
2. Read a TTTR file recorded under stationary conditions.
3. Check that the histogram's range and shape are plausible — no saturation,
   no truncated tail.
4. Add a *PCH multi-component* or *FIDA* model.
5. Fit and inspect the residuals, the molecular brightness and the number of
   molecules.
