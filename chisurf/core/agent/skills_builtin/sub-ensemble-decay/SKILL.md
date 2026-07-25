---
name: sub-ensemble-decay
description: >-
  Build a fittable TCSPC decay from a selected set of bursts, with an
  instrument response taken from the same measurement. Use when the user wants
  a decay, a lifetime or sub-ensemble TCSPC out of single-molecule data.
triggers:
  - sub-ensemble
  - subensemble
  - setcspc
  - se-tcspc
  - decay from bursts
  - burst decay
  - lifetime of the population
  - microtime histogram
  - micro-time histogram
experiments: [TCSPC, TTTR]
uses:
  - burst-selection
tools:
  - run_python
  - load_data
---

# A decay from selected bursts

One burst has too few photons to fit. Pool the photons of a whole selected
population and there are enough — that is sub-ensemble TCSPC. It is an
**average over the selected molecules**, which is why the selection
(`burst-selection`) is part of the result.

## Build the histogram

The decay of a population is the micro-time histogram of its
**donor-channel** photons, over that population's bursts only:

```python
import numpy as np, tttrlib
from pathlib import Path

N_BINS, GREEN = 4096, [0, 8]          # verified in burst-search, not assumed
decays = {name: np.zeros(N_BINS, np.int64) for name in populations}
for name in sorted(bursts["file"].unique()):
    stream = tttrlib.TTTR(str(Path(WORKDIR) / name), "SPC-130")
    routing, micro = np.asarray(stream.routing_channels), np.asarray(stream.micro_times)
    for label, mask in populations.items():
        part = bursts[mask & (bursts["file"] == name)]
        for a, b in zip(part["First Photon"].astype(int), part["Last Photon"].astype(int)):
            photons = micro[a:b][np.isin(routing[a:b], GREEN)]
            decays[label] += np.bincount(photons, minlength=N_BINS)[:N_BINS]
```

Build **every** population you will compare in the same pass, on the same
axis. A decay built differently from the one it is compared against produces a
difference that is procedural, not physical.

**Count the photons.** Roughly:

| donor photons | what it supports |
| --- | --- |
| < 1000 | nothing — say so |
| a few thousand | one lifetime |
| > 10 000 | two lifetimes, cautiously |

On the bundled sample, narrowing from ten photon files to three took the FRET
population from ~10 000 photons to ~2600; the two-component fit stopped being
determined (reduced chi-square 0.43) and the efficiency moved from 0.53 to
0.14. Too few photons does not announce itself as an error.

## The instrument response

A decay fitted without an IRF is systematically wrong, and burst measurements
rarely ship one. Take it from the **non-burst photons of the same
measurement** — the scatter and dark counts between molecules:

```python
from chisurf.core.fluorescence.burst.irf_bg import extract_irf_background

estimate = extract_irf_background(stream, {"green": {"chs": GREEN, "micro_time_ranges": []}})["green"]
irf, axis, background_khz = estimate.irf, estimate.time_ns, estimate.background_khz
```

Sum the IRF over the same files the decays came from.

This IRF is **contaminated**: molecules too dim to trigger a burst still
fluoresce into it, so it is broader than the true instrument response and
biases the lifetimes it yields. It is usable for one reason only — **every
decay is fitted against the same IRF, so the bias largely cancels in ratios of
lifetimes**, and ratios are what efficiencies are made of. Never quote an
absolute lifetime from such a fit without saying where the IRF came from.

Watch the burst-search parameters here: too permissive a definition leaves no
non-burst photons at all (with a 15 ms window the bundled sample kept *one*),
and the estimate silently becomes meaningless. Check
`estimate.n_background_photons` is large.

## Hand it to the fitting tools

Write every decay and the IRF on the shared axis, then load them as ordinary
TCSPC data:

```python
for label, counts in decays.items():
    np.savetxt(Path(WORKDIR) / f"{label}.dat", np.column_stack([axis, counts]), fmt="%.6f\t%d")
np.savetxt(Path(WORKDIR) / "irf.dat",
           np.column_stack([axis, np.round(irf / irf.sum() * 1e6)]), fmt="%.6f\t%d")
```

From here it is a normal decay analysis — `load_data(experiment="TCSPC")`,
`create_fit`, `set_irf`, `set_components`, `run_fit` — and the `fit-decay`
skill applies unchanged. Fit every population **the same way**: same model,
same components, same IRF, same fit range.
