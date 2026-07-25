# Two-channel colocalization

:::{admonition} Theory
:class: seealso
What each coefficient measures, why background and thresholds dominate the
numbers, Costes' automatic thresholds and randomization test, and van Steensel's
registration check are explained in the concept page {ref}`concept-colocalization`.
:::

## What it does

The **Imaging → Colocalization** tool (`img_coloc`) takes one image with at least
two channels and reports the standard colocalization coefficient set for a chosen
channel pair — Pearson, Manders (overlap and split), Li's ICQ, Spearman — with
Costes automatic thresholds, a Costes randomization significance test, and van
Steensel's shift profile. It reads **camera image stacks (TIFF) and photon-stream
files (PTU/HT3/…) alike**.

## Workflow

### 1. Pick a detector setup (optional)

The **Setup** combo at the top lists the detector setups defined in the Detector
Def tool. Picking one makes its named windows — `green`, `red`, `yellow`, … —
the channels you choose from, so a micro-time-gated or PIE window is a "colour"
like any other. The names appear immediately, before a file is loaded.

Leave the setup empty to work with the raw detector channels stored in the file
(`ch0`, `ch1`, …).

### 2. Load an image

Use the **Image** row: **📂** browses the disk, **🗄** loads a dataset registered
in the database (the database resolves it to a local file, wherever its object
store keeps the data — local disk or an S3-compatible endpoint), and a file
dropped on the window works too. Photon streams are
reconstructed into a confocal-scan image (frame/line/pixel markers are read from
the header); TIFFs are read with the axis order the file declares — ImageJ
hyperstack and OME metadata are honoured, so a `TCYX` stack loads correctly. For
a stack whose axes are unlabelled, the **Axis order** selector decides whether the
leading axis is channels or frames.

Loading a file runs the analysis immediately.

### 3. Choose the channel pair

**Channel A** and **Channel B**. The order matters for Manders' split
coefficients: $M_1$ is "how much of A sits with B", $M_2$ the mirror.

**Frame** selects a single frame of a stack; `-1` (the default) sums every frame,
which maximises the signal-to-noise of the coefficients.

### 4. Set background and thresholds

This is where reproducibility is won or lost.

- **Auto background** subtracts the lower 5 % quantile of each channel (change
  the **Quantile**, or type a measured dark level into **Background A/B**).
- **Costes thresholds** derives both thresholds from the data. Leave it off to
  type thresholds by hand — but then say so when you report $M_1$/$M_2$.

### 5. Read the results

The **Coefficients** tab lists every value; the **Channels** tab shows both
background-subtracted maps side by side; **Colocalized pixels** is the mask of
pixels above both thresholds.

```{figure} figures/coloc_workspace.png
:name: fig-coloc-workspace
:width: 100%

The colocalization tool on a two-detector confocal image: detector setup and
channel pair on the left, coefficients on the right.
```

### 6. Check registration, then significance

Set **van Steensel shift (px)** to a dozen pixels and look at the CCF tab: the
profile must peak at 0. A peak elsewhere is a registration offset — fix it before
believing any coefficient.

Then enable the **Costes randomization test**, set **Block (px)** to the PSF
width in pixels, and read the *Costes p-value*: colocalization is conventionally
called significant at $p > 0.95$. The **Seed** keeps the reported number
reproducible.

### 7. Gate a population in the scatter

The **Intensity scatter** tab is the joint histogram (A horizontal, B vertical).
Drag the blue rectangle over a region — a dim background cloud, a bright punctate
population — and the gated pixels get their own Pearson and Manders values in the
table, while the *Colocalized pixels* map highlights them.

```{figure} figures/coloc_scatter.png
:name: fig-coloc-scatter
:width: 70%

Joint intensity histogram of the two channels with the draggable gate. The gated
pixel population gets its own coefficients.
```

Type the bounds into the **Scatter gate** panel for an exactly reproducible gate,
or press **🧹 Clear gate** to go back to all thresholded pixels.

## Headless / CLI

Everything the GUI does is available without it:

```bash
img-coloc IMAGE.ptu -a green -b red \
    --auto-background --costes-threshold \
    --costes-test --randomizations 200 --block 4 --seed 0 \
    --ccf-shift 12 --json
```

`--json` prints the full metric dictionary (`-o results.json` writes it). For a
TIFF, pass channel indices: `-a 0 -b 1`.

## Python API

The coefficients are Qt-free and reusable on their own arrays:

```python
from chisurf.core.fluorescence.imaging import (
    colocalization_metrics, costes_significance, load_image_stack, van_steensel,
)

stack = load_image_stack("cells.tif")            # (frame, channel, y, x)
a, b = stack.image("ch0"), stack.image("ch1")    # 2-D maps, summed over frames

result = colocalization_metrics(a, b, auto_threshold=True, ccf_max_shift=12)
print(result.metrics["pearson"], result.metrics["manders_m1"])

print(costes_significance(a, b, block=4, n_randomizations=200, seed=0)["p_value"])
print(van_steensel(a, b, max_shift=12)["peak_shift"])
```

`load_image_stack` is the shared image seam: the same call returns the same
`(frame, channel, y, x)` stack for a TIFF and for a photon stream, and takes
`windows={...}` to build one channel per named detector window.

## Result

For the two-detector confocal test image, green versus red gives PCC ≈ 0.99 with
the van Steensel profile peaking at shift 0 — strongly colocalized channels on a
correctly registered instrument. Report the pair $M_1$/$M_2$ alongside it, plus
the thresholds and how they were chosen; see {ref}`concept-colocalization` for
what a defensible report contains.
