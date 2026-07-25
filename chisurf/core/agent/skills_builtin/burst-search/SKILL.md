---
name: burst-search
description: >-
  Turn a single-molecule photon stream into bursts, or read the bursts of an
  existing analysis, and establish which detector is which. Use when the user
  has a photon stream of freely diffusing molecules, a .bur analysis folder,
  or asks how many molecules were detected.
triggers:
  - burst search
  - burst detection
  - find bursts
  - detect bursts
  - .bur
  - bur file
  - burstwise
  - photon stream
  - freely diffusing
  - diffusing molecules
  - how many bursts
experiments: [TCSPC, TTTR]
tools:
  - list_files
  - run_python
---

# Getting bursts out of a photon stream

A burst is one molecule's crossing of the confocal spot. Everything
single-molecule is built on this step, and two things have to be settled here
or every later number is wrong: **which photons belong to which burst**, and
**which detector is which colour**.

## Prefer the burst search that already ran

Most measurements arrive with a Seidel-style analysis folder beside the photon
files — one `.bur` table per file, rows are bursts:

```python
import pandas as pd
from pathlib import Path

BUR = Path(WORKDIR) / "burstwise_All 0.1000#15" / "bi4_bur"
frames = []
for path in sorted(BUR.glob("*.bur")):
    table = pd.read_csv(path, sep="\t")
    table = table[table["Number of Photons"] > 0].copy()   # first row is a zero header
    table["file"] = path.stem + ".spc"                     # the stream it indexes
    frames.append(table)
bursts = pd.concat(frames, ignore_index=True)
```

Use it rather than re-searching: it is the analysis the user already works
with, and a second burst search with different thresholds silently produces a
different set of molecules.

If there is genuinely no analysis, run one over the stream
(`chisurf.plugins.burst.burst_selection.api.selection.analyze_file`) and
**state the parameters you used** — minimum photons, photon window, time
window. A burst search is a threshold, not a measurement, and the thresholds
are part of any result that follows.

## The two facts to verify before trusting anything

**1. The photon indices.** `First Photon` and `Last Photon` index the raw
photon stream of that file, and the end is **exclusive** — `photons[a:b]`,
ordinary Python slicing.

**2. The detector roles.** Routing channels carry no colour; the mapping is
the instrument's. On the bundled Becker & Hickl setup the donor is `[0, 8]`
and the acceptor `[1, 9]`, but never copy that into another measurement.

Both are checked by one cross-check, which costs nothing and catches an
off-by-one *and* a swapped detector at once — the counts you extract must
reproduce the counts the analysis recorded:

```python
import numpy as np, tttrlib

GREEN, RED = [0, 8], [1, 9]
green = red = 0
for name in sorted(bursts["file"].unique()):
    routing = np.asarray(tttrlib.TTTR(str(Path(WORKDIR) / name), "SPC-130").routing_channels)
    part = bursts[bursts["file"] == name]
    for a, b in zip(part["First Photon"].astype(int), part["Last Photon"].astype(int)):
        green += int(np.isin(routing[a:b], GREEN).sum())
        red += int(np.isin(routing[a:b], RED).sum())
assert green == int(bursts["Number of Photons (green)"].sum())
assert red == int(bursts["Number of Photons (red)"].sum())
```

If it does not match, stop and say so. Do not adjust the slice until the
numbers agree — that is fitting the bookkeeping to the answer. Something about
the file layout is different from what you assumed, and every burst-wise
quantity computed from it would be wrong in a way no later fit reveals.

## What to report

How many bursts, over how many files, and their typical photon count. A
measurement with a few hundred bursts supports a population; one with a few
dozen does not support anything.
