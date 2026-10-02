# Detector calibration

Choose source photon data and a detector defined in Imaging Tools. Each detector keeps its own IRF files, background estimates, shifts and microtime ranges.

Add or drop one or more IRF photon files. Files are summed using the detector's parallel and perpendicular channels. The raw histograms are cached; adjusting a shift or background does not reload photons. VV and VH IRFs have their background subtracted, are circularly shifted, clipped to nonnegative values and normalized independently to unit sum. The plot scales each normalized IRF peak to the source decay peak for a readable overlay, as in the Qt tool.

Drag the blue fit boundaries, green IRF boundaries or grey background boundaries. The grey interval estimates separate VV and VH background counts per microtime bin from the source decay. These are counts, not kHz. Enter zero to use the IRF's automatic baseline. Shift values are microtime channels and can be fractional.

Apply publishes every detector's IRF file list, fit/IRF/background ranges, shifts and background counts to Phasor and MLE. Next applies and advances the shared pipeline. Skip calibration in the pipeline to use raw data.
