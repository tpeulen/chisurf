---
type: Subsystem
title: Image I/O
description: The one seam for reading and writing image files — TIFF only, through the TTTR library's bundled libtiff — replacing three dependencies and, more importantly, three different answers to "which axis is which".
resource: chisurf/core/fio/image.py
tags: [file-format, imaging, tiff, dependencies, interop]
timestamp: '2026-08-05T00:00:00Z'
---

# Why it exists

Every image analysis in the tree — colocalization, drift, FRC, flow, tracking,
PSF determination, ROI masks, ICS carpets — starts by turning a file on disk
into a NumPy array. Each of them used to reach for whichever reader its author
knew: `tifffile`, `imageio`, `skimage.io` (which is `imageio` wearing a
different name), or Pillow, often two of them in a `try`/`except` cascade. That
is three declared dependencies and, worse, several different answers to the one
question that actually matters.

**A TIFF is a flat sequence of pages.** Six pages cannot say by themselves
whether they are six time points or two time points in three colours, and every
frame-wise analysis needs to know. Only ImageJ hyperstack metadata carries the
split. A reader that returns bare pixels leaves each caller to guess, and the
guesses disagreed.

# The seam

`chisurf.core.fio.image` is the single entry point:

| Call | Use |
|---|---|
| `imread(path)` | array in the file's own dtype |
| `imwrite(path, data, axes=…)` | write, optionally naming the axes |
| `read_labelled(path)` | `(array, axes)` when the meaning of the axes matters |
| `metadata(path)` | axes, shape, dtype, resolution, ImageJ fields — no pixels decoded |

Axis labels are `T` frames, `Z` slices, `C` channels, `I` an unlabelled page
index, `Y`/`X` the image plane. (`S`, colour samples, is still understood by the
reshaping in `image_source` but no reader produces it any more.)

Everything goes through the TTTR library's bundled, statically-linked libtiff,
which is already in every ChiSurf environment and carries no runtime dependency
of its own.

**TIFF is the only format, in both directions.** Measurement images are TIFF: it
stores the integer and floating-point pixel types instruments actually produce,
at full depth, losslessly, with the axis and voxel-size metadata that makes a
stack interpretable. The consumer formats store 8-bit colour, so writing a
16-bit photon count or a float lifetime map into one silently discards the
measurement. `imread`/`imwrite` raise `ValueError` on a non-TIFF suffix rather
than converting, and reading is refused for the same reason: a PNG in this
position means the data was flattened somewhere upstream.

Pillow is still a ChiSurf dependency, but not for data — ChiMOL's render export
writes PNG images of a scene, and the docs tooling converts figures. Neither is
a measurement.

# Rules

- **Never write PNG/JPEG for data.** The seam refuses it. If you want a picture
  of a result, that is a figure or a ChiMOL render, not an image file written
  through this module.
- **Never import `tifffile`, `imageio` or `imagecodecs`.** They were retired in
  August 2026; `test/test_no_retired_dependency_imports.py` fails on an import
  or a packaging declaration.
- **Never import `skimage.io` either.** scikit-image stays a dependency, but its
  `io` subpackage reads through an imageio plugin, so it reintroduces the
  removal without naming it. The same guardrail test covers it.
- **Label the axes when you write a stack.** `imwrite(path, stack, axes="TYX")`
  costs nothing and settles the ambiguity for every later reader. Without it a
  four-frame movie is read back as a four-channel single frame, because four or
  fewer planes look far more like a colour image — which is what
  `img_frc`'s *All planes are frames* override exists to undo.
- **A voxel size needs both halves.** ImageJ reads x/y from the TIFF resolution
  tags and z from the description, and ignores either one on its own:
  `imwrite(..., resolution=(1/px, 1/px), metadata={"spacing": dz, "unit": "um"})`.

# What "unlabelled" means

`read_labelled` reports a plain multi-page TIFF as `"IYX"`, not `"TYX"`. That is
deliberate: the file does not say what its pages are, and reporting `T` would
let a guess travel downstream as if it had been read from disk.
`chisurf.core.fluorescence.imaging.image_source` is where the guess is then
made, explicitly and overridably.

# Upstream

The ImageJ metadata support is in the TTTR library, not here — `TiffInfo`
carries the raw `ImageDescription` tag and the resolution tags, and the Python
layer parses them into an axis order. Files written this way are byte-compatible
with what ImageJ/Fiji and `tifffile` read; the round-trip is verified for `CYX`,
`TYX`, `TCYX`, `ZCYX` and `TZCYX` against both readers.

One behaviour is strictly better than the reader it replaced: `tifffile` writes
a `(4, y, x)` float array as *one page with four samples per pixel* and labels
it `"SYX"`, so a four-frame movie came back as an RGBA-like image. The bundled
writer writes four pages, unambiguously.

# See also

- [data-io](data-io.md) — the wider file-input/output picture
- [roi](roi.md) — mask and label images read through this seam
- [build-and-env](../workflows/build-and-env.md) — the dependency-closure
  measurements this removal is part of
