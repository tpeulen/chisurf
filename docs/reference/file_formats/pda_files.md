---
type: File Format
title: PDA TTTR files
description: How the PDA experiment builds photon-distribution histograms from TTTR files, burst tables and burst-analysis folders.
tags: [reference, file-formats, pda, tttr, photons, bursts]
---

# PDA TTTR files {#pda-tttr}

How the **PDA** experiment turns photon streams into the histograms photon
distribution analysis fits. Theory: {doc}`/concepts/pda2c` and
{doc}`/concepts/pda3c`; workflows: {doc}`/guides/11_pda2c` and
{doc}`/guides/42_pda3c`.

## Inputs

The `PTU/HT3/SPC` reader (`chisurf.core.experiments.pda2c.Pda2cReader`) takes:

- TTTR files `tttrlib` reads — PicoQuant PTU/HT3, Becker & Hickl SPC, …;
- `.bur` burst tables, which name per burst the measurement file and its first
  and last photon, so exactly those photons are used;
- burst-analysis folders; a TTTR file with a `bi4_bur` (or `bur`) folder beside
  it is read burst-wise from the tables in that folder.

Two further file types read three-colour data without a TTTR file:
`Burst table (CSV/NPZ)` and `Simulator (3-colour)`.

## Reader setup

In the **Read data** dock choose **Experiment** `PDA` and **File type**
`PTU/HT3/SPC`, add the files and press **+ Data**. Three things decide which
photons become a histogram:

- **the detector rows** — one routing-channel group per colour (defaults `0,3`
  green and `1,2` red), with a micro-time window per detector for two colours
  or per excitation period of the PIE cycle for three (**Colours**);
- **the time windows** (**TW [ms]**) — each window is read as a dataset of its
  own;
- **the inputs** above.

With two colours a burst or time window becomes a row of the S1S2 histogram
(**nPh min** / **nPh max** bound its photon number); with three it becomes a
row of a five-column photon table. The resulting `DataCurve` carries the PDA
payload; a model that cannot fit it hides itself from the model list.

## Typical workflow

1. Set the detector rows, the micro-time windows and the time windows.
2. Read the TTTR files, burst tables or folders of the sample.
3. Inspect the S1S2 histogram and its projections.
4. Choose a PDA model, e.g. *simple* or *Gaussian distance*.
5. Fit and inspect the residuals and parameters.

User-defined PDA models: {doc}`/reference/user_models`.
