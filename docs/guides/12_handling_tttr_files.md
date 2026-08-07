---
type: Guide
title: Handling TTTR files (and Photon-HDF5)
description: Time-tagged time-resolved (TTTR) data records, for every photon, a macro time (arrival on the experiment clock), a micro time (delay after the laser pulse — the TCSPC channel) and a routing channel (detector).
tags: [guides, tttr, photons, tcspc]
---

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

## One measurement, one file

**ChiSurf's own file type for photon data is `.pto`.** A vendor file is a
*recording*, in whatever your instrument's software writes; opening one in
ChiSurf produces `<name>.pto` beside it, and every result computed afterwards —
bursts, lifetimes, correlations, per-pixel maps — goes into that same file.

Three things follow, and they are the reason for the change:

- **Nothing is scattered.** A measurement used to grow a `bi4_bur/` folder, a
  `bg4/`, a `bv4/`, a `td4/`, an `.imaging.h5`, a handful of `Info/` files and
  several CSVs, all related to each other only by being named alike. Rename the
  folder and the relationship is gone. Now there is one file to copy, archive or
  send.
- **Nothing is lost.** Your original file goes in **byte-for-byte** and comes
  back identical — `Measurement.disassemble` writes it out and verifies its
  SHA-256 while doing so. The `.pto` is the size of the raw data plus the
  results, not twice the raw data, because the photons are read *in place* out
  of it rather than decoded into a second copy.
- **Your original is not touched.** It stays where it is. Deleting it is your
  decision; ChiSurf never makes it.

The vendor file still works everywhere a `.pto` does — nothing stops you opening
a `.ptu` directly. And the legacy `…4` folders are still *read*; they are now
written only when you ask for them (in Burst Selection, tick **Seidel folder**),
for the external tools that expect them.

```python
from chisurf.core.fio.staging import import_measurement, open_tttr

container = import_measurement("measurement.ptu")   # -> measurement.pto
photons = open_tttr(container)                      # the same photons

# one member of a container, by name
photons = open_tttr("measurement.pto|measurement.ptu")
```

## Converting on drop

Several tools that load a vendor file as the working measurement (Burst
Background, Burst IRF & Background, Count Rate Analysis, Burst Analysis, the
Microtime Shifter, the PCH tool, the TCSPC/PCH readers) offer to convert it
the moment you drop it: **Convert, keep original** / **Convert, delete
original** (only after the new container's checksum verifies) / **Use as
dropped**, once, with a "remember my choice" tick. An unattended/headless run
never sees the dialog and takes the safe answer — nothing is converted.

For converting outside those tools — or for turning a `.pto` back into the
vendor file it embeds — use the standalone **TTTR ⇄ .pto** tool: one drop
target, no options, works either direction depending on what you drop.

```python
from chisurf.plugins.core.tttr_to_pto import api

container = api.convert("measurement.ptu")            # pack, keep original
recovered = api.extract("measurement.pto")             # unpack, list of paths
```

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

`tttrlib.TTTR` opens a `.pto` as readily as a `.ptu` — the container names the
member it holds, so nothing above changes when the path does.

TTTR utility plugins (`chisurf/plugins/tttr/`) provide GUI tools for conversion,
splitting, header editing, time-window gating and micro-time linearisation.

For a stream you want to slice and select on, `Photons` wraps a `tttrlib.TTTR`
with the conveniences the tools use:

```python
from chisurf.core.fio.fluorescence.photons import Photons

p = Photons("measurement.ptu")        # or a list of files, read as one stream
p.mt_clk, p.dt                        # macro-time clock and TAC width, both in seconds
green = p.by_channel([0, 1])          # photons of those detectors
late = p[p.where("(ROUT == 0) & (TAC > 100)")]
green.tttr                            # the tttrlib object, for anything else
```

Correlation is `tttrlib.Correlator` — including in the **TTTR correlate** tool,
whose lag axis is in **milliseconds**, the unit ChiSurf's FCS models expect.

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

- [The photon container](../concepts/photon_container.md) — what a `.pto`
  holds, how a result says what one of its rows is, and how to take one apart.
- `chisurf/core/fio/fluorescence/` and the `tttrlib.TTTR` reader; plugins in `chisurf/plugins/tttr/`.
- Tools: the **TTTR Toolbox** (`chisurf/plugins/tttr/tttr_toolbox/`) converts, splits and edits headers; **TTTR ⇄ .pto** (`chisurf/plugins/core/tttr_to_pto/`) packs a vendor file into a `.pto` or unpacks one back out, with no prompt; **Microtime Shifter** (`chisurf/plugins/tttr/tttr_microtime_shifter/`) moves a detector's TAC axis; **ALEX Creator** (`chisurf/plugins/tttr/ptu_alex_creator/`) writes an alternating-excitation file; **Count Rate Analysis** (`chisurf/plugins/tttr/tttr_count_rate_analysis/`) compares detectors across many files; **Histogram-Microtime** (`chisurf/plugins/tttr/microtime_histogram/`) builds the decay; and **TTTR→Time-Window BIDs** (`chisurf/plugins/tttr/tttr_time_windows/`) turns fixed windows into burst ids.
