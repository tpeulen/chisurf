---
type: Manual Page
title: Loading the Alexa488 data into the anisotropy plugin
description: 'The anisotropy wizard is opened from the ribbon (Tools → Calculators → Wizards, then Anisotropy) and walks from the VV/VH files to the fit windows.'
tags: [manual, anisotropy, plugins]
---

# Loading the Alexa488 data into the anisotropy plugin

The anisotropy wizard is opened from the ribbon: **Tools → Calculators → Wizards**, then the
**Anisotropy** entry of the hub. (The wizard reads the files with its own reader settings, set in its
*Data* step.)

```{image} figures/anisotropy_ribbon_tools.png
:align: center
```

The *Tools* tab of the ribbon; **Wizards** is in the *Calculators* group.

```{image} figures/anisotropy_wizards_hub.png
:align: center
```

The wizards hub with **Anisotropy** selected: the wizard's steps on the left, the current step on the
right, **Back** / **Next** at the bottom.

Load the data in the *Data* step: type the paths, use **Browse**, or drop the files on the window. For
a file that holds both polarisations (VV followed by VH), tick *Two stacked VV/VH files* -- one IRF file
and one data file are then enough (see {doc}`vv_vh_format`); for separate files see
{doc}`two_single_files`.

```{image} figures/anisotropy_wizard_stacked.png
:align: center
```

Click **Next** (or *Normalize IRF* in the list) to proceed, and **Load / reload data** to read the
files. Here the IRF background region is defined: drag the edges of the green box in the plot, or type
*Background from* and *Background to*. A region typed the wrong way round is swapped, not ignored.

```{image} figures/anisotropy_wizard_normalize_irf.png
:align: center
```

Click **Next** to proceed. Here the *g-factor*, *l1* and *l2* can be given (if known) or estimates
entered.

```{image} figures/anisotropy_wizard_corrections.png
:align: center
```

Click **Next** to continue. In this step the fluorescence lifetimes and rotational correlation times
are added. The spectra can be saved and loaded (**Save spectra** / **Load spectra**), e.g. if many
similar cells need to be analysed (see also below).

```{image} figures/anisotropy_wizard_components.png
:align: center
```

To add a fluorescence lifetime or a rotational component, set *Amplitude* and the *Lifetime (ns)* or
*Correlation time (ns)* below the table and press **Add component**.

Components are removed by selecting the row and pressing **Remove selected** (or Delete); a cell is
edited by double-clicking it.

Please note that the amplitude sum of the fluorescence lifetime components is normalized to 1, while
for the anisotropy components the sum is the fundamental anisotropy r0 (at most 0.4; 0.38 for most
fluorophores).

In the *Finish* step press **Create fits** to generate the joint fits in the main ChiSurf window, and
**Tile Windows** (*Main* tab of the ribbon) to distribute the windows.

```{image} figures/anisotropy_fit_windows.png
:align: center
```

In total, three fit windows are now open: "Global anisotropy" holds the two polarised fits and
minimises them together, "Lifetime - Anisotropy VV" and "Lifetime - Anisotropy VH" are the individual
fits.

Next, switch to the **Analysis** dock and inspect what it shows for the three windows:

1. Global-fit: In the top-part the fits, which are to be minimized jointly are listed, the bottom part could be used to manually link variables across different datasets listed above (not used here).
2. Lifetime - _vh and Lifetime - _vv: Each of them have four different sections:
3. Convolve (top left to bottom right):
4. Datapath to the IRF
5. Convolution algorithm: e.g. exponential or periodic (selected here)
6. dt: size of a time bin in nanosecond
7. n0: total number of photons in the decay
8. start / stop: start and stop of time range
9. lb: offset of the IRF, must be zero or another small number as we background was already subtracted when setting up the experiment
10. ts: time shift between IRF and decay
11. IRFw/IRFk: In case an IRF cannot be measured/is missing, these parameters can be used to generate a synthetic Gaussian-shaped IRF with width IRFw and skewness IRFk. This option is not when (i) an IRF is loaded and (ii) the parameter are fixed (1st of the three boxes selected)
12. Generic:
13. Sc: fraction of scatter-based fluorescence, should be low in all experiments except signle-molecule
14. Bg: background/offset of the data
15. tBG/tMeas: to be filled when fitting single-molecule in "Burst-Integrated Fluorescence Lifetime" mode
16. Corrections: Ticking this box reveals option to perform a deadtime correction (pulse pile-up at high count rates) or to correct for differential non-linearities of the counting electronics (white light reference measurement required)
17. Lifetime:
18. xL,\[x\] are the amplitudes of the fluorescence lifetimes, normalized to a sum of 1 if the "Norm." box is ticked. Amplitudes can also get negative (e.g. for FRET-sensitized acceptor emission data), then the box next to "Abs." must be unticked.
19. τL,\[x\] are the respective fluorescence lifetime.
20. Rotational times
21. VM - VV - VH: designate the polarization of the dataset
22. r0: fundamental anisotropy of the used fluorophore
23. g: g-factor
24. l1, l2: polarization correction factors
25. b\[x\]: amplitudes of the rotational correlation times, normalized to r0

```{image} _images/image_rId127.png
:align: center
```

```{image} figures/anisotropy_analysis_vh.png
:align: center
```

```{image} figures/anisotropy_analysis_vv.png
:align: center
```

The **Analysis** dock for the VH and the VV fit: the *Fit* bar (**Fit**, dataset, fit range *First* /
*Last*), then the *Convolution*, *Generic*, *Corrections*, *Lifetimes* and *Anisotropy* sections.

Each numeric parameter is a row of a table:

1. *Fixed* keeps the parameter constant; it is not fit.
2. *Lo*, *Hi* and *Bounds* define the range the parameter may take, e.g. a fluorescence lifetime
   should not become negative.
3. A parameter linked to one of another fit follows it; the fit's *Info* page marks it with an arrow
   (e.g. `→g`). The wizard links the VH fit's amplitudes, lifetimes, rotations and corrections to the
   VV fit.
