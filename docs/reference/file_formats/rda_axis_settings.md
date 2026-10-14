---
type: File Format
title: R_DA axis settings
description: The global donor–acceptor distance axis (R_DA) of the FRET models, set in the fret section of settings_chisurf.yaml.
tags: [reference, file-formats, settings, fitting, global-analysis, fret]
---

# R_DA axis settings

The global donor–acceptor distance axis $R_{DA}$ of the FRET models is set by
the `fret` section of `settings_chisurf.yaml`:

| Key | Meaning | Shipped |
| --- | --- | --- |
| `rda_min` | lower bound of the grid, Å | 1 |
| `rda_max` | upper bound of the grid, Å | 130 |
| `rda_resolution` | number of grid points | 96 |
| `rda_scale` | `log` (`numpy.logspace`) or `lin` (`numpy.linspace`); `log` when missing | `log` |

At start-up they are read into `chisurf.core.settings.fret` and built into
`chisurf.core.fluorescence.rda_axis`.

The axis is used by:

- the PDA Gaussian-distance model (`chisurf.core.models.pda2c.pdagauss`) and its
  per-component distance curves;
- structural distance histograms that take an `rda_axis` argument and default
  to the global axis.

The TCSPC FRET models are BFF descriptions and carry their own axis as the
scalars `rda_min`, `rda_max`, `rda_resolution` and `rda_linear`.

**Settings → FRET RDA axis…** edits the four values (**R_DA min**,
**R_DA max**, **N points**, **Scale**). **Save axis** writes them to the
settings, rebuilds `chisurf.core.fluorescence.rda_axis` and updates the open
fits, so their distance distributions use the new axis.
