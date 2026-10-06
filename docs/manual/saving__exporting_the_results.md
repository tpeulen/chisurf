---
type: Manual Page
title: Saving & exporting the results
description: To save the results, click the fit window and press "Ctrl+S", or use "File" → "Save Fit-results" → "Current Fit" in the main toolbar.
tags: [manual, fitting, file-formats]
---

# Saving & exporting the results

To save the results, click the fit window and press "Ctrl+S", or use
"File" → "Save Fit-results" → "Current Fit" in the main toolbar.

```{image} _images/image_rId141.png
:align: center
```

Saving a fit writes a set of files that share one base name:

1. A *.docx* report summarising the fit results in a table.
2. A *.csv* of the fit metadata, plus one *.csv* per curve
the fit produced — the data, the model, the weighted residuals and their
autocorrelation — so every curve in the plots can be re-plotted elsewhere.
3. An *_info.txt* with the same results as plain text.
4. A *.fit.json* holding the state of the fit, which is what ChiSurf
reads to open the analysis again.
5. Two screenshots, *_screenshot_fit.png* and
*_screenshot_model.png*, of the fit window and of the model editor.
