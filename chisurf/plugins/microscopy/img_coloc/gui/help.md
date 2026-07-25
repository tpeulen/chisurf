# Colocalization

Colocalization asks whether two labelled species occupy the same structures.
The tool answers it for one **pair of channels** of one image, and reports
several coefficients, because no single number answers every version of the
question.

## Workflow

1. **Pick a detector setup** (optional). Its named windows — green, red,
   yellow… — become the channels you can choose from, so you work in the same
   vocabulary as the rest of ChiSurf. Leave it empty to use the raw detector
   channels stored in the file.
2. **Load an image.** Either a TIFF stack (camera data) or a photon-stream file
   (PTU/HT3/…), which is reconstructed into a confocal-scan image. **📂** browses
   the disk, **🗄** loads a dataset registered in the database, and dropping a
   file on the window works too.
3. **Choose channel A and B.**
4. **Set background and thresholds** — see below; this is where reproducibility
   is won or lost.
5. **Run.** The coefficients appear in the *Coefficients* tab; the maps, the
   colocalized-pixel mask and the intensity scatter in their own tabs.

## Background and thresholds

Every coefficient is computed on **background-subtracted** data, and most of them
only on pixels that are **above threshold** in both channels.

* **Background** is a per-channel offset (dark counts, out-of-cell signal).
  Leaving it in inflates Manders' overlap coefficient badly and Pearson's
  coefficient mildly. *Auto background* takes the lower 5 % quantile of each
  channel; override it with a measured dark level if you have one.
* **Thresholds** decide what "present" means. Choosing them by hand is the single
  largest source of colocalization numbers that cannot be compared between
  images or between people. **Costes thresholds** derive them from the data: an
  orthogonal (total-least-squares) regression of the channel pair is walked
  downwards until the pixels *below* it are no longer positively correlated —
  everything below that point is indistinguishable from uncorrelated background.

## Which coefficient answers which question

| Coefficient | Question it answers | Range |
| --- | --- | --- |
| **Pearson PCC** | Do the two intensities *co-vary*? | −1 … +1 |
| **Manders MOC** | Do the two signals *co-occur* (no mean subtraction)? | 0 … 1 |
| **Manders M1** | What fraction of channel A's intensity sits where B is present? | 0 … 1 |
| **Manders M2** | The mirror question for channel B. | 0 … 1 |
| **Li ICQ** | Do both channels deviate from their means in the same direction? | −0.5 … +0.5 |
| **Spearman** | Is the relation monotonic (even if not linear, e.g. saturation)? | −1 … +1 |
| **Colocalized area fraction** | What share of the image is above both thresholds? | 0 … 1 |

M1 and M2 are the pair to report when the two species are present in very
different amounts — a protein can be 90 % colocalized with a marker while the
marker is only 10 % colocalized with the protein, and one Pearson number cannot
say that.

## Is it more than chance?

Two dense stainings correlate simply because both fill the cell. The **Costes
randomization test** measures that baseline: one channel is scrambled in
PSF-sized blocks (destroying the spatial relation while keeping the intensity
distribution and the local texture) many times, and the measured Pearson
coefficient is compared against the resulting null distribution.

* Report the **p-value**: the fraction of randomized images with a *lower*
  correlation than the real one. Colocalization is conventionally called
  significant at **p > 0.95**.
* Set **Block (px)** to the PSF width. Too small and the test destroys the
  image's own texture, making almost anything look significant.
* The **Seed** keeps a published number reproducible.

## Before you trust any of it: registration

The **van Steensel CCF** shifts channel B horizontally and recomputes Pearson's
coefficient at every offset.

* A peak at shift **0** — the channels are registered; the correlation is real.
* A peak **away from 0** — chromatic aberration or a misaligned detector. Fix the
  registration first; every coefficient above is meaningless until you do.
* A **flat** profile — no spatial relation at all.

## The intensity scatter and the gate

The *Intensity scatter* tab is the joint histogram: channel A horizontally,
channel B vertically, each pixel one entry. Colocalized structures form a
diagonal cloud; segregated ones sit along the axes.

Drag the blue rectangle to **gate** a population. The gated pixels light up in
the *Colocalized pixels* map and get their own Pearson/Manders values in the
table, which is how you check whether a subpopulation (say, only the brightest
puncta) behaves differently from the whole image.

## Headless use

Everything here is available without the GUI:

```
img-coloc IMAGE.ptu -a green -b red --auto-background --costes-threshold \
          --costes-test --ccf-shift 12 --json
```

See the plugin's documentation page for the full option list and the Python API.
