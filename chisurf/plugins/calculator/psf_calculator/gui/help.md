# PSF calculator

Computes the three-dimensional point-spread function of a microscope objective
and shows it as a volume you can orbit.

## Which optical model?

**Vectorial (Richards–Wolf)** is the one to use above about NA 1.0. Strong
focusing by an aplanatic lens tips the electric field out of the transverse
plane, and the longitudinal component that creates is not small. At NA 1.4 and
520 nm the consequences are measurable:

* with **linear** illumination the focus is elongated *along the polarization
  axis* — 250 nm across x against 179 nm across y, 40% longer in one
  direction. No scalar or Gaussian model can produce that asymmetry at all.
* even with **circular** illumination the scalar answer is optimistic by about
  11%: 210 nm actual against the 189 nm that 0.51 λ/NA predicts.

**Airy (scalar)** is the exact scalar in-focus result — correct at low NA,
and the right reference when you want the textbook number. It is repeated
unchanged in every plane, so it has no axial width.

**Gaussian** is the usual approximation. It tracks the core closely but has no
wings: beyond the Airy first zero it holds 1.6% of its energy against the Airy
pattern's 16%, about ten times less. That is exactly where out-of-focus
background and crosstalk between detector elements live, so anything judged on
a Gaussian-simulated background inherits that error. Its axial envelope is
currently about four times too short (117 nm at NA 1.4, where the vectorial
focus is 510 nm), so use it for the lateral profile only.

## Polarization entering the pupil

| State | What it does to the focus |
| --- | --- |
| Linear (x, y, or at an angle) | elongates the spot along its own axis |
| Circular / left / unpolarized | radially symmetric; identical in intensity |
| Radial | a strong longitudinal lobe on axis inside a transverse ring; over the full aperture the total focus is *wider* than circular — it beats linear only with an annular aperture. The calculator currently over-weights the longitudinal field and shows it tighter (181 nm against 210 nm); a correct integral gives about 241 nm, so do not use the radial width yet |
| Azimuthal | a doughnut, with an exact zero on the optical axis |

The **Polarization vectors** toggle draws the state as strokes on a ring above
the focus, because a lateral asymmetry is hard to see in a translucent render
even though it is really there.

Polarization is ignored by the Airy and Gaussian models, and the strokes are
hidden accordingly rather than showing a state that is not in use.

## Quality

The vectorial integral is evaluated over the aperture angle: 60 points on
**Preview**, 300 on **Full**. Preview takes a few seconds for a 21 × 48 × 48
volume and is what live editing runs on; Full takes about five times longer.
At the defaults the two agree on the widths to within 1 nm; switch to Full once
the parameters are settled and before exporting.

## Reading the display

**Threshold** hides voxels below a fraction of the peak and **Gamma** shapes the
opacity ramp. Both exist because a diffraction-limited focus is mostly empty
space and renders as fog without them — they change only the picture, never the
computation.

The summary reports the lateral (along x) and axial widths measured from the
computed volume, next to the scalar prediction 0.51 λ/NA for comparison; the
number in brackets is lateral ÷ scalar.

## Exporting

**Export** on the toolbar writes the computed volume in either of two formats:

| Format | What it carries | Use it for |
| --- | --- | --- |
| `.npy` | the raw `(nz, ny, nx)` float array | deconvolution, simulation, any further NumPy work |
| `.tif` | a 32-bit ImageJ stack plus the voxel size | opening in ImageJ or Fiji already scaled in micrometres |

The TIFF records the lateral pixel size in the resolution tags and the z step as
the ImageJ `spacing`, so a line profile reads out in nanometres rather than
pixels. Both write whatever is currently computed — set **Quality** to **Full**
first if the file is going anywhere but the bin.

Headless, the same two formats come from the model directly:

```python
from chisurf.plugins.calculator.psf_calculator.core import PSFModel

model = PSFModel()
model.na, model.quality = 1.45, "full"
model.compute()
model.save(f"{model.export_basename()}.tif")
```

## Further reading

* [The point-spread function](docs/concepts/point_spread_function.md) — the
  theory: Airy pattern, Richards–Wolf focus, polarization, sampling
* [The PSF calculator guide](docs/guides/72_psf_calculator.md) — the workflow,
  each setting, export and the headless API
* [10.1098/rspa.1959.0200](https://doi.org/10.1098/rspa.1959.0200) — Richards &
  Wolf, *Proc. R. Soc. A* **253**, 358 (1959): the vectorial diffraction
  integral this implements
* The volumes come from the TTTR library's optical models
  (`tttrlib.CLSMSuperRes.psf_volume`), whose super-resolution guide covers the
  methods that consume them
* [10.1364/OPTICA.399600](https://doi.org/10.1364/OPTICA.399600) — SOFISM, one
  consumer of these PSFs
* [10.1038/s41566-025-01695-0](https://doi.org/10.1038/s41566-025-01695-0) —
  s²ISM, which needs a PSF model rather than deriving one from the data
