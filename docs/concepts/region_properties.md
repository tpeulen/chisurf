---
type: Concept
title: Regions and their properties
description: 'Deciding which pixels count: how regions of interest are defined, and the shape and intensity properties measured on them.'
tags: [concepts, region, properties]
anchor: concept-region-properties
---

(concept-region-properties)=
# Regions and their properties

Almost every imaging analysis begins by deciding **which pixels count**. A cell,
an illuminated patch, a bead, a single immobilised molecule, the empty field used
to measure background — each is a *region*, and ChiSurf treats them all as one
kind of object, whether the region was drawn with a mouse, thresholded, or found
by a segmentation algorithm.

A region answers two questions. *Is this point inside?* — which gates scattered
data such as bursts on an $E$–$S$ histogram. *Which pixels are inside?* — which
restricts an image analysis to part of a frame. Both follow from the same
geometry, which is why one object answers both, and why a rectangle drawn on a
parameter histogram and a rectangle drawn on a confocal image are the same
thing with different axes.

Once a region exists, a third question follows: **what is it?** How large, how
round, how elongated, how bright. Those numbers are the *region properties*, and
this page defines them.

## The measurements

Write the region as a set of pixels $R$ with $N = |R|$, and let $(r_i, c_i)$ be
the row and column of pixel $i$.

**Area** is the pixel count $N$ — not an integral of intensity. **Centroid** is
the unweighted mean position

$$
\bar r = \frac{1}{N}\sum_{i \in R} r_i, \qquad
\bar c = \frac{1}{N}\sum_{i \in R} c_i ,
$$

which is the centre of the region's *shape*. The **intensity-weighted centroid**
replaces the uniform weight with the pixel value $I_i$,

$$
\bar r_I = \frac{\sum_i I_i\, r_i}{\sum_i I_i} ,
$$

and is the centre of its *signal*. For a symmetric object the two coincide; for
a molecule whose segmentation caught an asymmetric skirt of background they do
not, and the weighted one is the better position estimate. Negative pixels — a
background-subtracted image has them — are clipped to zero first, since a
negative weight pulls the centre away from the very signal it should be
locating.

### Shape from second moments

The second central moments,

$$
\mu_{rr} = \tfrac1N\textstyle\sum_i (r_i - \bar r)^2, \quad
\mu_{cc} = \tfrac1N\textstyle\sum_i (c_i - \bar c)^2, \quad
\mu_{rc} = \tfrac1N\textstyle\sum_i (r_i - \bar r)(c_i - \bar c),
$$

define the ellipse with the same mass distribution as the region. With
$\lambda_1 \ge \lambda_2$ the eigenvalues of that covariance,

$$
\text{axis}_\text{major} = 4\sqrt{\lambda_1}, \qquad
\text{axis}_\text{minor} = 4\sqrt{\lambda_2}, \qquad
e = \sqrt{1 - \lambda_2/\lambda_1} ,
$$

and the **orientation** is the angle of the major axis,
$\theta = \tfrac12 \arctan\!\bigl(2\mu_{rc} /(\mu_{rr} - \mu_{cc})\bigr)$,
taken in $[-\pi/2, \pi/2]$. Eccentricity $e$ runs from 0 for a disc to 1 for a
line, and is the cheapest way to separate a diffraction-limited spot from a
scratch, a filament or two molecules that the segmentation failed to split.

### Boundary, and why it is not a pixel count

The **perimeter** is where a naive implementation goes wrong. Counting boundary
pixels treats a 45° edge as though it were axis-aligned and underestimates its
true length by $1 - 1/\sqrt2 \approx 29\%$. ChiSurf instead weights each border
pixel by its 4-neighbourhood configuration — 1 for a straight step, $\sqrt2$ for
a diagonal one, $(1+\sqrt2)/2$ for a corner — the estimator of Benkrid and
Crookes [1] used by scikit-image. A Crofton-formula variant is also available,
which is less biased for large convex regions and noisier for small ones.

From area and perimeter comes **circularity**,

$$
f_\text{circ} = \frac{4\pi A}{P^2} ,
$$

equal to 1 for a disc and smaller for anything less compact.

:::{admonition} Circularity on small objects
:class: warning
Discretisation biases $P$ in both directions, and $f_\text{circ}$ divides by its
square. A 7×7 pixel square measures $P = 24$ where the continuum says 28, giving
$f_\text{circ} = 1.07$ — a *square* that scores rounder than a circle. For
objects a few pixels across (single molecules, exactly) treat circularity as a
sorting key, not a measurement; eccentricity and solidity are better behaved
there.
:::

**Solidity** is the fraction of its own convex hull the region fills,
$A / A_\text{hull}$. It is near 1 for a compact blob and drops sharply for
anything with a concave outline — the standard discriminator for a region that
is really two touching objects. The hull is taken over the pixels' *corners*
rather than their centres, so a single pixel encloses an area of one instead of
zero. The **Euler number** (connected components minus holes) and the
**bounding-box fill** complete the description.

### Intensity

Given an image, each region also reports the sum, mean, minimum, maximum and
standard deviation of the pixels inside it. The mean is the natural per-pixel
brightness of an object; the sum is its integrated signal. Neither is a
photon-count fit — they are the summary statistics that decide *which* objects
are worth fitting.

## Foreground and background in single-molecule imaging

The single-molecule imaging workflow is the clearest use of all of this. An
immobilised sample is scanned, molecules are segmented, and each is fitted
individually for lifetime and anisotropy. Three regions are involved and they
are all the same kind of object:

* an optional **analysis region**, drawn or loaded, confining the search to one
  cell or one illuminated patch. It is applied *before* thresholding, so an
  automatic (Otsu) threshold is computed from that region's own pixels — the
  point of restricting the analysis is that the rest of the frame should not set
  its threshold;
* the **foreground**, the union of the segmented molecules;
* the **background**, which is *not* simply the complement of the foreground.
  The pixels immediately around a molecule still carry the tail of its
  point-spread function; including them biases the background rate upward and
  makes every molecule look dimmer than it is. The foreground is therefore
  dilated by a margin before being subtracted, leaving a clean background from
  which a mean photon rate per pixel can be read.

Each segmented molecule is a region in its own right, so a molecule's properties
— its area, its circularity, its weighted centre, its brightness — sit in the
result table beside its fitted lifetime, and the same region can be handed to
another tool, combined with another region, or stored with the project.

## The same region, different axes

A region carries no axes of its own, which is what lets one object do jobs that
look unrelated:

* **on a frame** — the pixels a decay is built from, a cell to restrict an
  analysis to, the patch a drift estimate is measured in;
* **on a scatter plane** — a gate on the joint histogram of two channels, where
  the "coordinates" are the two intensities rather than positions. Gating a
  rectangle there is the standard way to ask *do the bright pixels colocalize
  even though the dim ones do not?*, and because the gate is a region it need
  not be a rectangle: an ellipse around a population, or a polygon around a
  diagonal cloud, works with no new machinery;
* **as a segmentation** — each label of a watershed or an imported Cellpose
  result is a region, so the objects a segmentation found can be gated,
  measured and stored like a hand-drawn one.

A **painted** gate works on either kind of axis too. Paint on an image and the
brush strokes are pixels; paint on a 2-D histogram and they are *bins*, so the
region carries the bin edges and tests values instead of indices. That is what
lets a population be selected as the cloud it actually is — a phasor cluster, a
diagonal band in an intensity scatter — rather than as the box or ellipse that
approximates it.

Regions save as JSON — geometry, name, and nested boolean combinations — which
survives a project save, an RPC hop or another tool; a mask image is the export
for programs that read nothing else.

## Interoperability

The property names, definitions and algorithms follow
``skimage.measure.regionprops`` [2] exactly — the border-weighted perimeter, the
half-pixel-offset convex hull, the inertia-tensor axes, the sign convention of
the orientation, the Euler coefficients. ChiSurf's implementation is checked
against scikit-image property by property, so a number reported here is directly
comparable to one computed in any other image-analysis pipeline, and code
written for one transfers to the other.

The compatible surface is the whole of it: every property scikit-image defines,
`regionprops_table` with the same `centroid-0`/`centroid-1` splitting,
`extra_properties`, item access, `spacing=`, `offset=`, and the 61 historical
property names (`Area`, `max_intensity`, `major_axis_length`, …) that older code
still asks for. One behaviour differs on purpose: a **negative label** is
refused here, where scikit-image accepts it and then silently drops that region
from the results — losing an object without a word is worse than refusing the
input.

**Anisotropic pixels.** A confocal voxel is rarely square, and a scan is often
sampled differently along the two axes. Pass `spacing=` — a scalar, or one value
per axis — and every length, area, centroid and moment is reported in those
units rather than in pixels; `num_pixels` stays a count. Two corners, both shared
with scikit-image: the perimeter estimators weight pixel-border configurations
under an assumption of square pixels, so an *anisotropic* spacing is refused
rather than approximated; and the orientation of a rotationally symmetric region
is undefined, so it is a convention there and the two libraries may differ by
$\pi/4$ (the axis lengths, which such a region does determine, agree).

Two things go beyond it. A drawn region or a bare mask is measured exactly like
a segmentation label, so a hand-drawn selection and a watershed output are
comparable; and a measured region converts back into a region of interest, which
closes the loop between measuring and selecting.

## See also

- How to do it: {doc}`the regions guide </guides/48_regions>` — where regions
  appear in each tool, the single-molecule foreground/background workflow, the
  headless `--roi` option and the Python API.
- Object-based colocalization, which counts and compares segmented objects:
  {ref}`concept-colocalization`.
- Confocal images and per-pixel lifetime analysis:
  {doc}`the scan-image guide </guides/24_scan_images>`.
- Restricting a drift estimate to a structured patch:
  {ref}`concept-drift-correction`.

# Citations

[1] K. Benkrid, D. Crookes, A. Benkrid, *Design and FPGA implementation of a
perimeter estimator*, Proceedings of the Irish Machine Vision and Image
Processing Conference, 2000, 51–57.

[2] S. van der Walt, J. L. Schönberger, J. Nunez-Iglesias, F. Boulogne, J. D.
Warner, N. Yager, E. Gouillart, T. Yu, *scikit-image: image processing in
Python*, PeerJ 2:e453, 2014.

[3] M. K. Hu, *Visual pattern recognition by moment invariants*, IRE
Transactions on Information Theory 8(2):179–187, 1962.

[4] F. Bolte, F. P. Cordelières, *A guided tour into subcellular colocalization
analysis in light microscopy*, Journal of Microscopy 224(3):213–232, 2006.
- Tools in ChiSurf: **Region MLE** (`chisurf/plugins/microscopy/region_mle/`) fits each segmented region, and **Image Tools** (`chisurf/plugins/microscopy/imaging_tools/`) draws and stores the regions.
