---
type: Guide
title: 'The PSF calculator: the focus your objective actually makes'
description: Computing the three-dimensional point-spread function of an objective (vectorial Richards–Wolf, scalar Airy or Gaussian) with the pupil polarization, reading its widths against the textbook formula, and exporting it for deconvolution or simulation.
tags: [guides, imaging, optics, resolution]
---

# The PSF calculator: the focus your objective actually makes

How wide is the focus of *this* objective, at *this* wavelength, with *this*
polarization? The PSF calculator computes the three-dimensional point-spread
function, reports its lateral and axial widths next to the 0.51 λ/NA formula
that is normally quoted, and writes the volume out for deconvolution, ISM
reassignment or simulation. It needs no data.

For the optics (the Airy pattern, the Richards–Wolf focus and what polarization
does to it), see {ref}`concept-point-spread-function`.

## Open the tool

It lives in **Main → Tools → Calculators**, as the **🔬 PSF calculator** entry
in the calculator list. It has no menu entry of its own. Like the other
calculators it opens no file and produces no dataset: it turns the optical
parameters into a volume.

```{figure} figures/psf_calculator.png
:name: fig-psf-calculator
:width: 100%

The PSF calculator at NA 1.4 in oil, 520 nm, linear x polarization, Full
quality. Left: the parameters and the **Result** panel with the measured
widths. Right: the computed volume, orbitable with the mouse. The focus is
251 nm wide along x and 510 nm along the axis. The formula gives 189 nm.
```

Every edit recomputes after a short pause, off the GUI thread, so the view
keeps up with typing. The vectorial model takes a few seconds on **Preview**.

## Set it up

**Objective**

1. **NA**: the numerical aperture engraved on the objective.
2. **n (immersion)**: 1.518 for oil, 1.33 for water, 1.0 for air. The aperture
   half-angle is arcsin(NA/n), so this sets how steeply the lens focuses. NA
   must be below n, and the vectorial model refuses otherwise.
3. **λ (nm)**: the excitation wavelength for an excitation focus, the emission
   wavelength for a detection focus.

**Model**

4. **Optical model**:
   * *Vectorial (Richards–Wolf)*: the one to use above NA ≈ 1.0, and the
     default. It includes the longitudinal field and the pupil polarization.
   * *Airy (scalar, 2-D)*: the exact scalar in-focus pattern, repeated
     unchanged in every plane. Use it for the textbook reference width. It
     has no defocus, so its axial "width" is just the height of the stack.
   * *Gaussian*: a Gaussian whose FWHM is 0.5 λ/NA, with an axial envelope.
     Use it only for its lateral profile, because its axial width is about
     four times too short (see the warning in the concept page).

**Polarization** (vectorial model only; the other two ignore it)

5. **Polarization**: the state entering the pupil. *Circular*, *Left circular*
   and *Unpolarized* give the same symmetric focus. *Linear x*, *Linear y* and
   *Linear at angle* elongate it along the polarization axis. *Radial* and
   *Azimuthal* are the cylindrical vector beams: azimuthal is a doughnut with
   a zero on the axis.
6. **Angle (°)**: the direction of *Linear at angle*, measured from x.

**Sampling**

7. **Lateral size (px)** and **Planes**: the volume is `Planes × size × size`,
   centred on focus.
8. **Pixel (nm)** and **z step (nm)**: the voxel size. The defaults (30 nm,
   100 nm) are well below the Nyquist limits at NA 1.4 (93 nm, 279 nm). Make
   sure the stack reaches beyond the focus: at the default 21 planes × 100 nm,
   ±1 µm covers the 510 nm axial FWHM with room to spare.
9. **Quality**: *Preview* evaluates the aperture integral at 60 angles and
   *Full* at 300. Full takes about five times longer. It moves the vectorial
   widths by less than 1 nm at the defaults, so switch to it once the
   parameters are settled and before exporting.

**Display**: **Threshold** hides voxels below a fraction of the peak,
**Gamma** (shown as Γ) shapes the opacity ramp, **Colormap** colours the
volume, and **Polarization vectors** draws the pupil state as strokes on a
ring above the focus. None of these enter the computation.

## Read the result

The **Result** panel gives the volume size, the **lateral FWHM** (along x,
through the focus), the **axial FWHM** (along the optical axis) and the scalar
prediction 0.51 λ/NA for comparison. The number in brackets is lateral ÷ scalar.
The widths are interpolated at the half-maximum crossings, so they do not
snap to the pixel size.

At the defaults (NA 1.4, oil, 520 nm, circular) it reads **211 nm** lateral
and **512 nm** axial, against 189 nm from the formula, which is 12 % wider.
Things to check:

* **Linear polarization.** The panel reports the x width only. With *Linear x*
  that is the long axis (250 nm). The y width is 179 nm, and you only see it by
  switching to *Linear y*. A single "resolution" hides a 40 % difference
  between the two axes.
* **Radial** currently reports a focus *tighter* than circular (181 nm). That
  number comes from a known error in the underlying library (the longitudinal
  field is over-weighted). A correct integral gives about 241 nm, wider than
  circular. Do not use the radial width yet.
* **Azimuthal** has a zero on axis, so its "lateral FWHM" is the outer width
  of the ring, not a resolution.
* An **axial FWHM equal to the stack height**, or `nan`, means the profile
  never fell to half inside the stack (Airy), or fell faster than one z step
  (Gaussian). Add planes or refine the z step.

## Export

**💾 Export** on the toolbar writes the volume currently computed:

| Format | Contents | For |
| --- | --- | --- |
| NumPy (`.npy`) | the `(nz, ny, nx)` float64 array, peak = 1 | deconvolution, simulation, further NumPy work |
| ImageJ TIFF (`.tif`) | a 32-bit `ZYX` stack; pixel size in the resolution tags, z step as ImageJ `spacing`, unit µm | opening in ImageJ/Fiji already scaled |

A bare filename gets the extension of the chosen format. Set **Quality** to
*Full* first, because the file holds whatever was last computed.

## Headless

`PSFModel` is the whole computation without the window. Its attributes are the
parameters above:

```python
from chisurf.plugins.calculator.psf_calculator.core import PSFModel

model = PSFModel()
model.na, model.n_immersion, model.wavelength_nm = 1.4, 1.518, 520.0
model.model, model.polarization = "vectorial", "x"
model.nxy, model.nz = 64, 31
model.pixel_size_nm, model.z_step_nm = 25.0, 50.0
model.quality = "full"

volume = model.compute()            # (nz, ny, nx), peak-normalized
print(model.summary_text())         # the Result panel, as markdown
model.save(f"{model.export_basename()}.tif")   # or .npy
```

`export_basename()` encodes the optics in the name
(`psf_vectorial_NA1.4_n1.518_520nm_x`), so exports of different settings do
not overwrite each other. `compute()` calls the TTTR library's
`CLSMSuperRes.psf_volume`, which can also be called directly with the same
arguments.

## Using it well

**Compute the focus you mean.** An excitation focus uses the laser wavelength
and a detection focus the emission wavelength. A confocal PSF is their product
and is narrower than either one.

**Expect the measured bead to be wider.** The calculator assumes an aberration-free
aplanatic lens, a matched immersion medium and a point emitter. Refractive-index
mismatch, bead size and the pinhole all widen a measured PSF. Bead widths of
230–245 nm at NA 1.4 are typical.

**Quote the polarization with the width.** At high NA it changes the answer
by tens of per cent.

## See also

- Concept: {ref}`concept-point-spread-function`. Resolution of a real image:
  {doc}`51_frc_resolution`.
- Tool: **PSF calculator** (`chisurf/plugins/calculator/psf_calculator/`),
  reached through the Calculators hub. Press **Guide** on its toolbar for
  a walk-through.
