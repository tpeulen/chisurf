---
type: Manual Page
title: Saving & exporting the results
description: To save the results, select the fit window and use File ▸ Fits ▸ Current Fit (Ctrl+Alt+S) and choose a folder; File ▸ Fits ▸ All Fits saves every fit.
tags: [manual, fitting, file-formats]
---

# Saving & exporting the results

To save the results, select the fit window and use **File ▸ Fits ▸ Current Fit**
(Ctrl+Alt+S) and choose a folder; **File ▸ Fits ▸ All Fits** (and the toolbar's
*Save all fits*) saves every fit. The files of one fit share one base name, the
dataset's file name without its extension. Saving the donor-only decay of the IBH
sample (see [Overview](overview.md), Fig.1) writes:

```text
Decay_577D.fit.cs.pto
Decay_577D_00_IRF.csv
Decay_577D_00_autocorrelation.csv
Decay_577D_00_data.csv
Decay_577D_00_info.txt
Decay_577D_00_model.csv
Decay_577D_00_weighted residuals.csv
Decay_577D.docx
```

1. A *.fit.cs.pto* holding the fit and its data -- the same container a project is
saved in, holding one fit. **File ▸ Fits ▸ Load Fit** adds it to the open session
beside the fits already there (a fit that is already open is not loaded twice).
2. One *.csv* per curve the fit produced -- the data, the IRF, the model, the
weighted residuals and their autocorrelation -- so every curve in the plots can be
re-plotted elsewhere.
3. An *_info.txt* with the fit results as plain text.
4. A *.docx* report: a picture of the fit window and one of the model editor for
every member of the fit, and a table of every parameter (fitted ones in bold,
linked ones in italics) with χ²ᵣ. The pictures are drawn by ChiSurf itself, not
taken from the screen, so the report looks the same whichever window saved it.

**All Fits** writes one folder per fit, named like the files above, and stacks the
reports into *all_fits.docx*. Global fits are left out; their members are fits of
their own. When some of the folders are there already, you are asked once whether
to overwrite or skip them.

Saved with ChiSurf before 2026-10, a fit was a *.fit.json* with two screenshots
beside it; that file cannot be loaded (save the project instead, or save the fit
again).
