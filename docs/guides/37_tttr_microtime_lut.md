---
type: Guide
title: 'TAC linearization: microtime LUTs'
description: 'Some TCSPC hardware — notably Becker&Hickl SPC-130 — records photon micro-times on a TAC (time-to-amplitude converter) axis with visible differential non-linearity (DNL): the channels are not exactly equal in width.'
tags: [guides, tttr, photons, tcspc]
---

# TAC linearization: microtime LUTs

:::{admonition} Theory
:class: seealso
See {ref}`concept-tcspc-lifetime` for the micro-time axis this page linearizes —
uneven TAC channel widths bias the decay histogram that every lifetime fit,
filtered-FCS filter and PDA micro-time gate is built from.
:::

Some TCSPC hardware — notably Becker&Hickl **SPC-130** — records photon
micro-times on a TAC (time-to-amplitude converter) axis with visible
**differential non-linearity (DNL)**: the channels are not exactly equal in
width. Left uncorrected, every lifetime, FCS or PDA result built from those
micro-times is subtly distorted. ChiSurf fixes this with a per-routing-channel
**look-up table (LUT)** that you compute once from a flat-light measurement and
then apply automatically at read time.

## 1. Usage

### Compute a LUT per channel and add it to the setup

In the **Channel Definition** editor, the **LUT handling** box has a
**Configure LUTs…** button that opens **LUT Tools**. The **① Compute LUT** tab is
the tool you use; tab ② (settings.tttr.json) is optional file interchange.

Load one or more TTTR files of a **uniform-illumination** (uncorrelated-light /
scatter) measurement — light that *should* produce a flat TAC histogram. Because
TAC differential non-linearity is **per routing channel**, pick a **Routing
channel**, drag the orange region to mark the flat **linear plateau** (or
auto-detect), then press the bold **➡ Add to Detector setup**. Repeat for each
channel and close the window — that's the whole workflow. Saving a LUT file is
optional.

```{figure} figures/lut_tools_workspace.png
:name: fig-lut-tools-workspace
:width: 90%

① Compute LUT — per-channel: routing-channel selector, draggable linear region on the raw TAC histogram, corrected preview below.
```

### It lands in the detector setup

Back in the editor, the **LUT handling** box now lists the per-channel LUT you
added. Tick **Apply TAC linearization (LUT) when reading** and the correction is
applied to every read of that setup — hover a LUT to see its plot.

```{figure} figures/lut_channel_box.png
:name: fig-lut-channel-box
:width: 90%

The LUT-handling box in the channel-definition editor.
```

From then on, any reader that selects the setup linearizes photons at read time
through the single `staging.open_tttr` seam, so previews and production reads are
identical.

### Headless (CLI / API)

```bash
# ① compute a LUT from a flat-light file
chisurf lut-tools compute uniform.spc -o green.npy --routine SPC-130
# ② build a settings bundle assigning it to channel 0 (+ a 3-bin shift)
chisurf lut-tools settings --lut 0=green.npy --shift 0=3 -o settings.tttr.json
```

```python
from chisurf.plugins.tttr.tttr_lut_tools import api

tbl  = api.compute.compute_lut_from_files(["uniform.spc"], routine="SPC-130")
luts = {0: tbl["NTAC_fract"]}
# corrected micro-time histogram of channel 0
counts, axis = api.settings.corrected_histogram("data.spc", 0, luts, routine="SPC-130")
```

## 2. Concepts

A uniform-illumination measurement is the reference because it *should* be flat:
any structure in its TAC histogram is instrument DNL, not signal. The Felekyan
et al. (Rev. Sci. Instrum. 2005) construction reads the local counts as *bin
widths* — over-counted channels are "wide", under-counted ones "narrow" — and
integrates them into a cumulative table `NTAC_fract`. That table maps each raw
channel onto a corrected, equal-width axis; applying it (with stochastic
dithering, so no binning artifacts) flattens the histogram.

```{figure} figures/lut.png
:name: fig-lut
:width: 90%

DNL and its LUT correction.
```

**Left** — the same flat-light photons before (red, wavy from DNL) and after
(blue, flat) linearization. **Right** — the cumulative LUT `NTAC_fract` departs
from the linear ideal (dashed) exactly where the TAC axis is non-linear; a
perfectly linear TAC would need no correction and the two lines would coincide.

The correction is **reproducible**: ChiSurf applies the LUT with a fixed dither
seed, so reading the same file twice yields the same decay. It is also
independent of the fit-model DNL correction (`correct_dnl`): the LUT fixes the
*data*, the model correction fixes the *model* — use one or the other, not both.

## Result

A per-channel LUT that turns a DNL-distorted TAC axis into a linear one, stored
in the detector setup and applied automatically at read time for lifetime, FCS,
burst and PDA analyses.

## See also

- Plugin: `chisurf/plugins/tttr/tttr_lut_tools/` (api / cli / backend / gui).
- Reading seam: `chisurf/core/fio/staging.py::open_tttr`.
- Channel definition: `chisurf/gui/widgets/wizard/tttr_channeldefinition/`.
- Felekyan et al., *Rev. Sci. Instrum.* 76.8 (2005) 083104.
