---
type: Guide
title: Turning ALEX alternation into micro-time (ALEX Creator)
description: How the ALEX Creator folds the alternation of two lasers into the micro-time axis of a TTTR file, how to choose period and shift from the live histogram, and how to convert one file, many files or a merged stream, in the window, from the command line and from Python.
tags: [guides, tttr, alex, converter, tools]
---

# Turning ALEX alternation into micro-time (ALEX Creator)

**What you get:** a TTTR file whose micro-time is the phase of the laser alternation, so that the two excitation
windows of a microsecond-ALEX measurement (see {ref}`concept-us-alex`) can be gated like PIE data with the ordinary
micro-time tools.

## Theory in one paragraph

In µs-ALEX the donor and the acceptor laser are switched on and off out of phase with a fixed period $T$ (in macro-time
units). A photon with macro time $t$ therefore sits at the phase $\varphi=(t+s)\bmod T$, where $s$ is a **shift** that
moves the border between the two windows. The converter writes $\varphi$ as the photon's micro time and leaves the
macro time, the routing channel and the header alone. A histogram of $\varphi$ shows the two excitation windows as two
plateaus; choosing $T$ and $s$ well means the border between them contains no photons.

## 1. Load a file

Open **Tools → Converter → ALEX Creator**. Press **Open…** and choose a TTTR file (`.sm`, `.ptu`, `.ht3`, ...), or
type or paste its path into **File** and press Enter, or drop the file on the window. The photon count appears under
the modulation fields and the folded histogram on the right.

```{figure} figures/alex_creator.png
:name: fig-alex-creator
:width: 100%

The ALEX Creator with a loaded file and a two-file batch queue. Left: file row, formats, the **Period** and **Shift**
spin fields and the batch queue. Right: the micro-time histogram of the loaded file.
```

## 2. Choose period and shift

**Period** and **Shift** are in macro-time units, not seconds. Type a value and press Enter, press the arrows at the
field's right edge, or turn the mouse wheel over the field (one notch is one step: 100 for the period, 1 for the shift).
The histogram folds again at once and the window stays usable while it does. **Input** forces the container type
(**Auto** detects it); **Output** is the container written.

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
