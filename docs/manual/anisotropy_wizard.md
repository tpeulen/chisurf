---
type: Manual Page
title: Anisotropy Wizard
description: The Anisotropy Wizard in ChiSurf is a guided tool designed to facilitate the setup and analysis of time-resolved fluorescence anisotropy data.
tags: [manual, anisotropy, wizard]
---

# Anisotropy Wizard

The Anisotropy Wizard in ChiSurf is a guided tool designed to facilitate the setup and analysis of time-resolved fluorescence anisotropy data. It ensures that relevant parameters are correctly configured and linked for accurate analysis. Before importing data, configure the reading parameters to ensure correct interpretation of the input files. Verify data reading settings before importing files to avoid misinterpretation of the dataset.

This wizard helps in setting up analysis by linking relevant anisotropy parameters, correcting for sensitivity differences, and ensuring proper handling of mixing effects. The g-factor (g) is an essential correction parameter that accounts for differences in sensitivity between the VV and VH detection channels. Another crucial aspect is the mixing of anisotropy when using a high numerical aperture (NA) objective, which can introduce distortions in the measurement. Proper calibration and correction are necessary to ensure accurate anisotropy calculations. A detailed tutorial on how mixing factors and g-factors can be determined by reference measurements can be found in the Tutorial section of this manual.

The wizard is the **Anisotropy** entry of the wizards hub, **Tools → Calculators → Wizards**. Its
six steps are listed on the left with a check mark once complete; **Back** and **Next** walk them,
**Guide** starts a guided tour and **Help** opens the background text.

```{image} figures/anisotropy_wizard_data_empty.png
:align: center
```

**Fig.26 Data step of the Anisotropy wizard.** One path field per curve -- *IRF VV*, *IRF VH*,
*Data VV*, *Data VH* -- typed, chosen with **Browse**, or dropped on the window (a dropped file fills
the next empty field); "missing" turns to "found" once the file exists. The reader settings below
(*Two stacked VV/VH files*, *First column is time*, *Use file header*, *Bin width*, *Repetition rate*,
*Header rows*) say how the text files are read.

The first step in the analysis is reading data, which includes IRF and measurement data. The
instrument response function (IRF) must be provided for the VV and VH channels independently; both
IRFs are used to correct the time-resolved signals.

```{image} figures/anisotropy_wizard_normalize_irf.png
:align: center
```

**Fig.26 IRF background correction (Normalize IRF step).** **Load / reload data** reads the files.
The green box marks the background region (drag its edges in the plot, or type *Background from* /
*Background to*); its mean is subtracted from both IRFs, which are then scaled to the same intensity.
Raw IRFs are drawn faint, corrected ones solid. **Export corrected IRFs** writes them to a file.

After reading the files, the IRF is prepared for convolution: constant background is subtracted from
the recorded IRFs and the parallel (VV) and perpendicular (VH) IRFs are normalized.

Next, the stored defaults of the g-factor and of the anisotropy mixing are read from the user folder
and shown in the *Corrections* step.

```{image} figures/anisotropy_wizard_corrections.png
:align: center
```

**Fig.26 Corrections step.** *g-factor* corrects the different sensitivity of the VV and VH
detection; *l1* and *l2* the polarization mixing of a high-aperture objective (zero on a low-NA
set-up). The values are kept for the next session.

```{image} figures/anisotropy_wizard_components.png
:align: center
```

**Fig.26 Components step: fluorescence lifetimes and rotational correlation times.** The lifetime
spectrum (amplitude, lifetime) and the rotation spectrum (amplitude, correlation time) are shared by
the VV and VH fits. Double-click a cell to edit it; **Add component** appends the pair typed below a
table, **Remove selected** (or Delete) drops a row; **Save spectra** / **Load spectra** keep them in
a `.spk.json` file.

After defining the lifetime and anisotropy spectra, **Create fits** in the *Finish* step adds a VV fit,
a VH fit and a global fit to ChiSurf, with amplitudes, lifetimes, rotations and corrections linked.

```{image} figures/anisotropy_fit_windows.png
:align: center
```

**Fig.26 Created fit windows** (after **Tile Windows**): the VH fit, the VV fit and the global fit
that minimises both together, before fitting.
