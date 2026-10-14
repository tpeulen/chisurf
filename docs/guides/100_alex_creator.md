---
type: Guide
title: Turning ALEX alternation into micro-time (ALEX Creator)
description: How the ALEX Creator folds the alternation of multiple lasers into the micro-time axis of a TTTR file, how to choose period and shift from the live histogram, and how to convert one file, many files or a merged stream, in the window, from the command line and from Python.
tags: [guides, tttr, photons, file-formats, python]
---

# Turning ALEX alternation into micro-time (ALEX Creator)

**What you get:** a TTTR file whose micro-time is the phase of the laser alternation, so that the excitation
windows of a microsecond-ALEX measurement (see {ref}`concept-us-alex`) can be gated like PIE data with the ordinary
micro-time tools.

## Theory in one paragraph

In µs-ALEX excitation lasers are switched on and off at different phases with a fixed period $T$ (in macro-time
units). A photon with macro time $t$ therefore sits at the phase $\varphi=(t-s)\bmod T$, where $s$ is a **shift** that
moves the border between excitation windows. The converter writes $\varphi$ as the photon's micro time and leaves the
macro time, the routing channel and the header alone. A histogram of $\varphi$ shows the excitation windows as
plateaus; choosing $T$ and $s$ well means the border between them contains no photons.

## 1. Load a file

Open **Tools → Photon data → TTTR Tools**, then select **ALEX Creator**. Press **Open…** and choose a TTTR file (`.sm`, `.ptu`, `.ht3`, ...), or
type or paste its path into **File** and press Enter, or drop the file on the window. The photon count appears under
the modulation fields and the folded histogram on the right; excitation regions are inferred at once (section 5).

```{figure} figures/alex_creator.png
:name: fig-alex-creator
:width: 100%

The ALEX Creator on a two-colour µs-ALEX calibration (`.sm`, 3.77 M photons) after **Detect period** set
**Period** to 8000 (contrast 155278×). Left: file row, formats, **Period**, **Shift**, **Detect period** and the batch
queue. Right: the inferred excitation regions (one *Candidate*, three *Review transition*) and the folded
micro-time histogram with the regions shaded.
```

## 2. Choose period and shift

**Period** and **Shift** are in macro-time units, not seconds. Type a value and press Enter, press the arrows at the
field's right edge, or turn the mouse wheel over the field (one notch is one step: 100 for the period, 1 for the shift).
The histogram folds again at once and the window stays usable while it does. **Input** forces the container type
(**Auto** detects it); **Output** is the container written.

**Detect period** (grey until a file is loaded) measures the period from the photons instead: the two busiest
detector groups (the **Detectors** field, or the two busiest routing channels when it is blank) alternate with the
lasers, and the sharpest line in the power spectrum of their signed difference, refined to the exact integer on all
photons, is the period. **Period** is set to it and the histogram and excitation regions fold again; the message
above the histogram gives the measured period and its alternation contrast (peak over band median). A stream whose
contrast is below 50 does not alternate (PIE / ns-ALEX data, or the wrong detectors) and is refused with that
contrast; **Period** keeps its value. **Shift** is not changed: a region that crosses phase zero is shown as one
wrapped region.

## 3. Write one file

**Save as…** (grey until a file is loaded) opens a file chooser with a suggested name; the input file is never
overwritten. The written path is shown above the histogram.

## 4. Batch: convert each or merge

1. Fill the queue with **Add files…**, **Folder…** (recursive) or **Database**, or drop several files or a folder on
   the queue. Duplicates are ignored. Select a row and press **Remove** (or Delete) to drop one, **Clear** empties it;
   the mouse wheel scrolls a long queue.
2. Choose **Convert each** (one output per input, needs an **Output folder**) or **Merge into one** (the streams are
   joined with continuing macro time before folding; the default folder is that of the first input).
3. Press **Run batch**. The written names appear above the histogram; a missing queue or folder is reported there in red.

### Convert each or merge

**Merge into one** joins the streams on a new contiguous macro-time axis with
the first input's header and folds the joined stream once, so use it only for
recordings with the same clock settings. Choose **Convert each** when each
recording should keep its own phase reference.

## 5. Excitation regions and multiple lasers

Loading a file infers excitation-phase candidates from **every routing
channel**, at the configured **Period** and **Shift**. **Re-detect** repeats the
inference after a change and replaces edited regions. There is no cap on the
number of phases: a three-colour measurement keeps all three.

The names Phase 1, Phase 2, … identify measured emission phases, not wavelength
assignments. Review the candidates before naming lasers. A real two-color
calibration can contain extra switching/heterogeneity phases; these remain
visible as **Review transition** rather than being silently discarded or called
extra lasers. Invalid detector grouping or inconclusive detection does not
disable the histogram or conversion/export controls.

**Detectors** optionally combines polarized channels into physical bands, for
example `0,8;1,9`. All observed channels must be covered exactly once. Start and
End cells are editable by double-clicking and typing; crossing phase zero is
represented by two increasing ranges. Editing resets Review confirmation.
The table and overlays are inspection aids; they do not filter photons.

Period remains an instrument setting in macro-time ticks. Region inference
works at the configured period and does not infer it; an incorrect period
smears the phases into many short "regions". Press **Detect period** to
measure it from the data first (section 2). The regions do not change what is
written: every export folds the photons the same way and keeps routing
channels, event types and header.

```python
from chisurf.plugins.tttr.ptu_alex_creator import core

tttr = core.load("measurement.ptu", "PTU")
period, shift = 8000, 0  # the measured instrument setting, in macro-time ticks
measured = core.measure_alex_period(tttr.macro_times, tttr.routing_channels)
print(measured["period"], measured["confidence"])  # what Detect period sets
phase = core.apply_alex(tttr, period, shift).micro_times
result = core.auto_excitation_regions(phase, tttr.routing_channels,
                                      alex_period=period)
for region in result["regions"]:
    print(region["ranges"], region["ambiguous"])
```

See [µs-ALEX](../concepts/us_alex.md) for the phase/clock interpretation.

## Export capacity

Folding uses `(macro_time - shift) % period` with exact integer arithmetic.
The in-memory period is limited to 1–65536 ticks. Output records may have a
narrower phase field: HydraHarp/Generic T3 supports phases 0–32767, PicoHarp T3
and most SPC formats 0–4095, SPC-600_256 0–255. Photon-HDF5 stores full uint16
phases. T2, SM and CZ store no microtime field. Both single and merge workflows
reject an output that would truncate or discard a nonzero phase; choose an
appropriate T3 or Photon-HDF5 output. A failed writer is reported as an error.

## Command line and Python

```bash
csc alex convert --help
csc alex merge --help
```

```python
from chisurf.plugins.tttr.ptu_alex_creator import core
hist = core.alex_histogram("data.ptu", 4000, 23)
core.convert_file("data.ptu", "data_alex.ptu", 4000, 23, "PTU", "Auto")
```

## See also

- [Plugin reference: ALEX Creator](../reference/plugins/ptu_alex_creator.md)
- [µs-ALEX concept](../concepts/us_alex.md)
- [Handling TTTR files](12_handling_tttr_files.md)
- Source: `chisurf/plugins/tttr/ptu_alex_creator/`
