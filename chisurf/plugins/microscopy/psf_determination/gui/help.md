# PSF determination: the focus measured on beads

A point-spread function is the image a microscope makes of a point. Sub-resolution fluorescent beads are such
points: a z-stack of beads is a direct measurement of the PSF of *this* objective, in *this* sample medium, with
*this* alignment. The tool finds the beads in the stack, fits a three-dimensional Gaussian to each and reports the
widths in nanometres.

## What you do

1. **Load stack** (a 3-D TIFF, or drop it on the window) or **Demo stack** for a generated stack with a known answer.
   Browse the slices with the z slider; the colormap, gamma and levels change only the display.
2. Set **Pixel (nm)** and **Z step (nm)** from your acquisition: they turn the fitted sigmas (in pixels and slices)
   into physical widths. A wrong z step scales the axial width by the same factor, and nothing in the fit will object.
3. **Detect** finds beads with an adaptive quantile threshold (*Px/frame*), a minimum separation (*Min dist*) and a
   minimum area (*Min area*; a single bright pixel is a hot camera pixel, not a bead). Green squares mark the beads on
   the current slice.
4. **Fit selected** fits the bead you clicked in the image (or the one chosen with *Bead index*); **Fit all** fits
   every detected bead and reports failures too; **Export CSV** writes the batch.

## What to check

* **The x, y and z profile tabs**: the data points should follow the red Gaussian. A flat top or a shoulder means a
  bead cluster, a saturated bead or a bead that is not sub-resolution.
* **The axial ratio** sigma-z over sigma-xy is a property of the objective and the medium (about 3 to 5 for a
  high-NA oil objective). A ratio far from that means a wrong z step, or a refractive-index mismatch that stretches z.
* **The spread over beads**: Fit all gives one value per bead; the scatter is the honest error of the PSF width.
  A single bead is an anecdote.
* **Bead size**: a 100 nm bead widens a 200 nm PSF noticeably; the fitted width is the convolution of both.

## Settings

The region of interest (*ROI xy*, *ROI z*) is the box cut around a bead for the fit: large enough for the tails,
small enough to exclude neighbours. **Save settings** writes calibration, ROI, detection and display settings to JSON
and **Load settings** restores them and reopens the stored stack when it still exists.

## Further reading

* [The point-spread function](docs/concepts/point_spread_function.md): the Airy pattern, the Richards-Wolf focus and what polarization does to it.
* [The PSF calculator](docs/guides/72_psf_calculator.md): the width a perfect objective would give, to compare with the measurement.
