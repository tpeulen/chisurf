# Background rates

:::{admonition} Theory
:class: seealso
See {ref}`concept-smfret-bursts` for the role of background in the E/S corrections.
:::

## What it does

Every single-molecule measurement has a background — detector dark counts, buffer
Raman/scatter, and afterpulsing — that must be subtracted from burst signals for
accurate FRET, brightness and correlation. The background photon rate is read
from the **inter-photon-time distribution**: background photons arrive as a
homogeneous Poisson process, so the *tail* of the inter-photon-time histogram
(the long gaps, dominated by background) is a single exponential whose rate is
the background count rate.

## In ChiSurf

```python
from chisurf.core.fluorescence.burst import background

rate_hz = background.estimate_background_from_interphoton_times(macro_times, macro_res)
```

The `burst_background` plugin estimates a per-detector background rate; the
`burst_irf_bg` step additionally recovers a scatter-derived **IRF** from the same
non-burst photons (the photons the burst search rejects are the built-in
scatter/background), feeding both the correction factors and the MLE lifetime
fit — with no separate buffer acquisition. See
[Lifetime from photon bursts](21_lifetime_from_bursts.md).

## Result

An inter-photon-time histogram (log–log): the short-gap peak is the bright bursts;
the long-gap tail is the Poisson background, whose exponential slope gives the
background rate.

```{figure} figures/background.png
:name: fig-background
:width: 90%

Background from inter-photon times.
```

## See also

- {src}`chisurf/core/fluorescence/burst/background.py`, `.../irf_bg.py`; plugin `burst_background`.
