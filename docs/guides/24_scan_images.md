# Confocal scan images (CLSM)

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

## See also

- `tttrlib.CLSMImage`; plugins in `chisurf/plugins/microscopy/`.
