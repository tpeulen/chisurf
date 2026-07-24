# Handling TTTR files (and Photon-HDF5)

:::{admonition} Theory
:class: seealso
The photon stream this page reads is the raw input to every method in ChiSurf:
{ref}`concept-tcspc-lifetime` explains what the micro-time axis means, and
{ref}`concept-smfret-bursts` what the macro-time axis and the routing channels
are used for.
:::

## What it does

Time-tagged time-resolved (TTTR) data records, for every photon, a **macro
time** (arrival on the experiment clock), a **micro time** (delay after the
laser pulse — the TCSPC channel) and a **routing channel** (detector). Every
single-molecule analysis in ChiSurf starts from this stream. ChiSurf reads the
common container formats through **tttrlib** — PicoQuant PTU, HydraHarp HT3,
Becker&Hickl SPC, and Photon-HDF5 — normalising them all to the same tag list, so
downstream code is format-agnostic.

## In ChiSurf

```python
import numpy as np
import tttrlib

d = tttrlib.TTTR("measurement.ptu", "PTU")      # or "HT3", "SPC-130", "PHOTON-HDF5"
macro = np.asarray(d.macro_times)               # experiment-clock ticks
micro = np.asarray(d.micro_times)               # TCSPC channel per photon
route = np.asarray(d.routing_channels)          # detector per photon

res_macro = d.header.macro_time_resolution      # seconds / tick
res_micro = d.header.micro_time_resolution       # seconds / channel

# micro-time (TCSPC) histogram of one detector
sel = d[np.where(route == 0)[0]]
hist, edges = np.histogram(sel.micro_times, bins=d.number_of_micro_time_channels)

# export to the interoperable Photon-HDF5 format
d.write("measurement.photon-hdf5")
```

TTTR utility plugins (`chisurf/plugins/tttr/`) provide GUI tools for conversion,
splitting, header editing, time-window gating and micro-time linearisation.

## Result

Micro-time (TCSPC) histograms of a green and a red detector read from a TTTR
file — the raw material for lifetime analysis, after the burst search, or for
filtered FCS.

```{figure} figures/tttr.png
:name: fig-tttr
:width: 90%

Micro-time histograms from a TTTR file.
```

## See also

- `chisurf/core/fio/fluorescence/` and the `tttrlib.TTTR` reader; plugins in `chisurf/plugins/tttr/`.
