---
type: File Format
title: R_DA axis settings
description: 'The global donor–acceptor distance axis (R_DA) used in FRET-related models is controlled by the entries in settings_chisurf.yaml under the fret section:'
tags: [reference, file-formats, settings]
---

# R_DA axis settings

The global donor–acceptor distance axis (R_DA) used in FRET-related models is
controlled by the entries in `settings_chisurf.yaml` under the `fret` section:

- `rda_min` – lower bound of the distance grid.
- `rda_max` – upper bound of the distance grid.
- `rda_resolution` – number of points in the grid.
- `rda_scale` – spacing of the grid, either `log` (logarithmic) or `lin`
  (linear). If missing, `log` is assumed.

At runtime these values are loaded into `chisurf.settings.fret` and used to
construct the global axis

- `chisurf.core.models.tcspc.fret.rda_axis`

If `rda_scale` is `log`, the axis is created with `numpy.logspace`; if it is
`lin`, `numpy.linspace` is used instead.

This axis is consumed by several components:

- TCSPC FRET distance models in `chisurf.core.models.tcspc.fret` (Gaussian, discrete
  and worm-like chain distance distributions).
- PDA Gaussian-distance models and their per-component distance curves in
  `chisurf.core.models.pda2c.pdagauss` and `chisurf.gui.widgets.models.pda2c.widgets`.
- Structural distance histograms that accept an `rda_axis` argument and default
  to the global R_DA axis.

The **R_DA axis (FRET distance)** widget, available from the main GUI via
**Settings → FRET R_DA axis ...**, provides a compact UI around these
settings. Changing the values and pressing **Save axis** will:

- Update `chisurf.settings.fret['rda_min']`, `['rda_max']`,
  `['rda_resolution']` and `['rda_scale']`.
- Rebuild `chisurf.core.models.tcspc.fret.rda_axis` on the fly.
- Request an update of the current fit so that FRET-related distance
  distributions use the new axis.
