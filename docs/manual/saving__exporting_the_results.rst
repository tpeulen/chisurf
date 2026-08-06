Saving & exporting the results
""""""""""""""""""""""""""""""

To save the results, click the fit window and press "Ctrl+S", or use
"File" → "Save Fit-results" → "Current Fit" in the main toolbar.

.. image:: _images/image_rId141.png
  :align: center

Saving a fit writes a set of files that share one base name:

#. A :emphasis:`.docx` report summarising the fit results in a table.

#. A :emphasis:`.csv` of the fit metadata, plus one :emphasis:`.csv` per curve
   the fit produced — the data, the model, the weighted residuals and their
   autocorrelation — so every curve in the plots can be re-plotted elsewhere.

#. An :emphasis:`_info.txt` with the same results as plain text.

#. A :emphasis:`.fit.json` holding the state of the fit, which is what ChiSurf
   reads to open the analysis again.

#. Two screenshots, :emphasis:`_screenshot_fit.png` and
   :emphasis:`_screenshot_model.png`, of the fit window and of the model editor.
