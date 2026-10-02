---
type: Guide
title: The PSF measured on beads (PSF Determination)
description: Fitting three-dimensional Gaussians to the sub-resolution beads of a z-stack to measure the lateral and axial width of the point-spread function of your own objective, with the checks that tell a good measurement from a bad one.
tags: [guides, imaging, psf, calibration, beads]
---

# The PSF measured on beads (PSF Determination)

**What you get:** the lateral and axial widths (FWHM, in nanometres) of the point-spread function of *your*
objective, medium and alignment, one value per bead and the scatter over the beads, as a CSV.
The PSF *calculator* ({doc}`72_psf_calculator`) says what a perfect objective would give; this tool measures what
yours does. See {ref}`concept-point-spread-function`.

## Theory

A sub-resolution bead is a point source, so its image in a z-stack is the PSF sampled on the pixel and slice
grid. The tool models each bead as a three-dimensional Gaussian
$I = A\,e^{-\frac12\left[(x-x_0)^2/\sigma_x^2 + (y-y_0)^2/\sigma_y^2 + (z-z_0)^2/\sigma_z^2\right]} + b$,
fitted by non-linear least squares in a region of interest around the bead. With the pixel size $p$ and the z step
$\Delta z$ the physical widths are $\mathrm{FWHM} = 2\sqrt{2\ln 2}\,\sigma\,p$ (lateral) and
$2\sqrt{2\ln 2}\,\sigma_z\,\Delta z$ (axial). The ratio $\sigma_z/\sigma_{xy}$ is a property of the objective and the
medium; a value far from the expected 3 to 5 (high-NA oil) means a wrong z step or an index mismatch. The fitted
width is the convolution of the PSF with the bead, so the bead must be much smaller than the focus.

## 1. Open the tool and load a stack

*Imaging → PSF Determination*. Press **Load stack** and choose a 2-D or 3-D TIFF (or drop it on the window), or use
**MMFDB dataset** for a registered one. **Demo stack** generates a stack with five beads of known size (FWHM 424 nm
laterally, 2120 nm axially at 100 nm per pixel and 300 nm per slice) to try the tool. The z slider browses the
slices; colormap, gamma and levels change only the display; the wheel zooms and a drag pans.

```{figure} figures/psf_determination.png
:name: fig-psf-determination
:width: 100%

The demo stack after **Detect** and **Fit all**, with the bead at (x 20, y 20) selected: the stack, its
x profile with the Gaussian fit, and the fit report (FWHM 424 nm lateral, 2119 nm axial, axial ratio 5.0).
```

## 2. Calibrate and detect

Set **Pixel (nm)** and **Z step (nm)** from the acquisition: the fit only knows pixels and slices, so a wrong value
gives a confident width in the wrong units. **ROI xy** and **ROI z** are the box cut around a bead for the fit.
**Detect** finds beads with an adaptive quantile threshold (**Px/frame**), a minimum separation (**Min dist**) and a
minimum area (**Min area**: a bead covers several pixels, a single bright pixel is a hot camera pixel).

## 3. Fit and check

Click a bead in the image, or choose it with **Bead index**, and **Fit selected** (a click fits at once); **Fit all**
fits every detected bead and reports failures too. In the **x / y / z profile** tabs the white points are the data
and the red curve the fit: a flat top, a shoulder or a systematic residual means a cluster, a saturated bead or a
bead that is not sub-resolution. One bead is an anecdote: the scatter of **Fit all** is the error of the PSF
width. **Export CSV** writes one row per bead (position, sigmas, FWHM in nm, axial ratio, cost, success).

## 4. Save the settings

**Save settings** writes calibration, ROI, detection and display settings (and the stack path) to JSON; **Load
settings** restores them and reopens the stack.

## Headless and Python

```python
from chisurf.plugins.microscopy.psf_determination.gui.view_model import PsfViewModel

m = PsfViewModel(); m.load_stack("beads.tif"); m.pixel_size_nm, m.z_step_nm = 100.0, 300.0
m.detect_beads(); m.fit_all(); m.export_csv("psf_batch_results.csv")
```

## See also

- Concept: {ref}`concept-point-spread-function`; calculator: {doc}`72_psf_calculator`.
- Super-resolution and ISM reconstruction use the measured PSF: {ref}`concept-super-resolution`.
