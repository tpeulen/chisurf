---
type: Manual Page
title: Saving & exporting the results
description: "To save the results, select the fit window and use File ▸ Fits ▸ Current Fit (Ctrl+Alt+S) and choose a folder; File ▸ Fits ▸ All Fits saves every fit."
tags: [manual, fitting, file-formats]
---

# Saving & exporting the results

To save the results, select the fit window and use **File ▸ Fits ▸ Current Fit**
(Ctrl+Alt+S) and choose a folder; **File ▸ Fits ▸ All Fits** (and the toolbar's
*Save all fits*) saves every fit. The files of one fit share one base name, the
dataset's file name without its extension. Saving the donor-only decay of the IBH
sample (see [Overview](overview.md), Fig.1) writes:

```text
Decay_577D.fit.json
Decay_577D_00_IRF.csv
Decay_577D_00_autocorrelation.csv
Decay_577D_00_data.csv
Decay_577D_00_info.txt
Decay_577D_00_model.csv
Decay_577D_00_weighted residuals.csv
Decay_577D.docx
Decay_577D_screenshot_fit.png
Decay_577D_screenshot_model.png
```

1. A *.fit.json* holding the state of the fit, which is what ChiSurf
reads to open the analysis again (**File ▸ Fits ▸ Load Fit**).
2. One *.csv* per curve the fit produced -- the data, the IRF, the model, the
weighted residuals and their autocorrelation -- so every curve in the plots can be
re-plotted elsewhere.
3. An *_info.txt* with the fit results as plain text.
4. A *.docx* report summarising the fit results in a table (written with
python-docx, a dependency of ChiSurf).
5. Two screenshots, *_screenshot_fit.png* and *_screenshot_model.png*, of the fit
window and of the model editor.
