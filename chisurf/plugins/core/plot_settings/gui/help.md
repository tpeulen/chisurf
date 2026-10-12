# Plot Settings

How every fit plot looks: the colours and width of the curves, the fit-range
band, how the datasets of a global fit are told apart, the axes and the grid,
and the grid of the node graphs.

A change **applies at once** and is **kept for the next start** -- there is no
Apply or Save button, as in Settings ▸ Fonts. Every plot already open is
restyled at once, and plots opened later use the same settings. **Reset to defaults** puts the
shipped look back. Only what differs from the shipped look is written to
`settings_chisurf.yaml`.

## The preview

The preview is laid out like a fit window -- the autocorrelation of the
residuals on top, the weighted residuals under it, the decay below -- on a
**simulated** measurement, not your data: an instrument response convolved
with two lifetimes, a constant background and Poisson noise. The model is the
noise-free curve of a fit that is close but not exact, so data and model can be
told apart and the residuals show the structure a misfit leaves. A second,
dimmed dataset stands for the other fits of a global fit.

## Curves

The colours of the data, the model, the instrument response (IRF), the
weighted residuals and their autocorrelation. **Line width** is the width of
the model, IRF, residual and autocorrelation curves; the noisy data trace is
drawn at half of it so the model stays visible through it.

## Fit range

The band marks the channels the fit uses; you drag its edges in a fit window.
**Opacity** runs from 0 (invisible) to 255 (solid); much above 60 it reads as a
fill and hides the data under it. With the band switched off the range is still
used -- set it in the fit's own controls.

## Global fits

With several datasets in one global fit, the curves of the selected dataset
are drawn at **Selected fit** opacity and the others at **Other fits** opacity.

## Axes and grid

**Axis text** sets the point size of tick numbers, axis names and the legend;
*auto* follows the interface font. **Grid strength** is relative to the
theme's grid: 30 % draws it as the theme does, 0 % not at all, 100 % as solid lines. **Grid** turns
the grid off everywhere; the three switches beside it pick the panels.

## Node graphs

The grid under a node graph -- Global View, the light path, the provenance
inspector, the node editor -- is a background, not a workspace, so it has its
own width and opacity here, quieter than a plot grid. A width below one pixel
fades the lines instead of narrowing them, which is what keeps the grid under
the edges drawn on top of it on a HiDPI screen. A change also re-styles the
graph windows that are open; the node size is where a newly opened Global View
starts its own node-size control.

## Further reading

- [The Settings window](docs/guides/97_settings_hub.md)
- [Plot settings reference](docs/reference/plugins/plot_settings.md)
- [Settings file: `gui.plot`](docs/reference/settings.md)

Press **Guide** for the walk-through.
