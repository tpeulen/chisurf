---
type: Manual Page
title: Global fit of auto- and cross-correlation curves
description: 'Before starting ChiSurf, add the cross-correlation fit model to the model catalogue as described in:'
tags: [manual, fitting, global-analysis, correlation]
---

# Global fit of auto- and cross-correlation curves

Before starting ChiSurf, add the cross-correlation fit model to the model catalogue as described in {doc}`adding_the_membranediffusion_models`:

where *aR* and *tR* describe the amplitude and relaxation time of the anticorrelation.

A more general equation – in case of more than one relaxation term – would have the following form:

where *af* describes the total amplitude of the anticorrelation (identical to *aR* in the single anticorrelation term model above) and *aRi* and *tRi* the respective relaxation times and amplitudes.

Load in total five different correlation curves into ChiSurf:

Green-prompt (autocorrelation of green signal in prompt time window)

Red-prompt (autocorrelation of the FRET-induced red signal in the prompt time window)

Red-delay (autocorrelation of the red signal (direct excitation) in the delay time window)

FRET-CCF (cross-correlation of green prompt and red-prompt signal)

PIE-CCF (cross-correlation of green-prompt with red-delay)

The two new curves (red-delay and FRET-CCF), which we have not used to far, both stem from the FRET-induced red signal now present in our data.

```{image} _images/image_rId94.png
:align: center
```

Due to the FRET-induced anticorrelated behavior of green and red signal in the prompt time window. The FRET-CCF shows a "dip" at short correlation time, coinciding with a rise in both autocorrelation curves from the prompt time window.

All five loaded curves are fit jointly with linked *tD1*, *tD2* and *tR*. The fit results are summarized in the table below. Please note that here the diffusion times can be fit jointly as the simulation software does not support the modelling of differently sized confocal detection volumes. For experimental results, this joint fitting of *tD* might not be possible, however *tR* should be linked.
