# Confocal scan images (CLSM)

:::{admonition} Theory
:class: seealso
How CLSM images are reconstructed from a TTTR stream, per-pixel lifetime maps,
and the phasor approach to fit-free FLIM (the universal semicircle, the lever
rule) are explained in the concept page {ref}`concept-imaging-flim-phasor`.
:::

## What it does

A laser-scanning confocal microscope builds an **image** by rastering the focus
across the sample while recording TTTR photons tagged with frame/line/pixel
markers. From that stream ChiSurf reconstructs per-pixel data and computes
pixel-wise observables: intensity, **fluorescence lifetime** (FLIM), FRET,
phasors, and — for immobilised single molecules — per-pixel maximum-likelihood
lifetime fits. This is the imaging counterpart of the burst analyses.

## In ChiSurf

The engine is `tttrlib.CLSMImage`; the `microscopy/` plugin group provides the
tools:

```python
import tttrlib

img = tttrlib.CLSMImage(tttr, channels=[0])     # reconstruct from frame/line/pixel markers
img.fill(tttr)
stack = img.intensity                            # frames × lines × pixels
decays = img.get_pixel_decays()                  # per-pixel micro-time histograms
```

Pixel-wise analyses: `img_pixel_mle` (per-pixel `2I*` lifetime, same harness as
[burst MLE](21_lifetime_from_bursts.md)), `img_pixel_phasor`, `img_pixel_intensity`,
`sm_image_mle` (single-molecule image MLE), plus `psf_determination` and
`img_calibration`.

## Result

The same photon stream yields two co-registered images: an intensity map and a
lifetime map. The lifetime map is the one that reports on environment and FRET —
here a quenched (FRET) region is indistinguishable from a dim one by intensity
alone, but separates cleanly by lifetime.

```{figure} figures/clsm.png
:name: fig-clsm
:width: 100%

Simulated confocal scan. **Left:** photons per pixel. **Middle:** the per-pixel
lifetime; photon-starved pixels are masked (dark). **Right:** the micro-time
decays of the two regions — 3.2 ns unquenched versus 1.6 ns under FRET.
```

Per-pixel lifetime precision is photon-limited ($\sigma_\tau \approx
\tau/\sqrt{N}$), which is why FLIM images need far more photons per pixel than
intensity images and why dim pixels are masked rather than fitted.

## See also

- `tttrlib.CLSMImage`; plugins in `chisurf/plugins/microscopy/`.
- Fit-free lifetime imaging via phasors and the same MLE estimator per burst:
  {ref}`concept-imaging-flim-phasor`, [lifetime from bursts](21_lifetime_from_bursts.md).
