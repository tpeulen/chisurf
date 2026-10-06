---
type: Manual Page
title: Species-filtered FCS to recover dynamics
description: A method to recover the triplet-masked anticorrelations in the FRET-CCF is to make use of the microtimes (i.e. the fluorescence decay histograms) encoded in the data.
tags: [manual, fcs, dynamics, fret, tcspc, decay]
---

# Species-filtered FCS to recover dynamics

A method to recover the triplet-masked anticorrelations in the FRET-CCF is to make use of the microtimes (i.e. the fluorescence decay histograms) encoded in the data. Here, instead of direct photon traces, an additional weighting function is introduced based on the fluorescence decay shape of the (i) IRF, (ii) the LF state, and (iii) the HF state. The theory of the weighting functions and what the filtered curves mean is in {ref}`concept-filtered-fcs`; entries 6 and 7 of {doc}`references` are the original papers.

In this species-specific or filtered FCS approach, four different correlation pattern are generated:

Species-autocorrelation of the LF state (*sACFLF-LF*)

Species-autocorrelation of the HF state (*sACFHF-HF*)

Species-cross-correlation of the LF state to the HF state (*sCCFLF-HF*)

Species-cross-correlation of the HF state to the LF state (*sCCFHF-LF*)

Below, exemplary the work flow and input for a filteredFCS analysis of the LF(*E* = 0.2) \<-> HF(*E* = 0.7) example with additional triplet is shown.

```{image} _images/image_rId97.png
:align: center
```

```{image} _images/image_rId99.png
:align: center
```

```{image} _images/image_rId101.png
:align: center
```

*Note: Suffix "p" and "s" are used to discriminate between the parallel (p) and perpendicular (s) channel here.*

For generation of the species-filtered FCS curves, the weights determined for the LF and HF species based on the normalized intensity decays are used during the correlation.

The resulting curves are fit to standard equations with bimodal membrane diffusion and relaxation and anticorrelation terms, respectively.

```{image} _images/image_rId103.png
:align: center
```

During the fit, both diffusion times *tD1* and *tD2* as well as the relaxation times are fit jointly and the FRET-induced relaxation of the *sACFLF-LF* and *sACFHF-HF* is linked to the anticorrelation term of the *sCCFLF-HF* and *sCCFHF-LF*.

*Be aware that the number of molecules in focus, N, is only an apparent number and does no longer relate to the concentration of molecules in the experiment / simulations!*
