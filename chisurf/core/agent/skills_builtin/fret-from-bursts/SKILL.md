---
name: fret-from-bursts
description: >-
  Analyse single-molecule FRET burst data: detect or read bursts, select a
  population by proximity ratio, build sub-ensemble TCSPC decays from the
  selected bursts, and get a distance from the donor lifetime. Use when the
  user mentions bursts, single-molecule FRET, proximity ratio, a .bur file or
  a photon stream of freely diffusing molecules.
triggers:
  - burst
  - bursts
  - smfret
  - single molecule
  - single-molecule
  - proximity ratio
  - prox ratio
  - pr histogram
  - burst selection
  - burst search
  - sub-ensemble
  - subensemble
  - setcspc
  - se-tcspc
  - mfd
  - .bur
  - bur file
  - freely diffusing
  - diffusing molecules
  - burstwise
experiments: [TCSPC, TTTR]
tools:
  - list_files
  - load_data
  - run_python
  - create_fit
  - set_irf
  - set_components
  - set_fit_range
  - run_fit
  - get_fit
  - link_parameters
  - fit_report
  - export_fit_results
---

# FRET from single-molecule bursts

A burst measurement is a photon stream from molecules diffusing one at a time
through a confocal spot. Each molecule crossing gives a **burst** of photons;
the analysis is a chain, and every link is a decision:

```
photon stream -> bursts -> per-burst proximity ratio -> select a population
             -> sub-ensemble decay of the selected bursts -> lifetime -> distance
```

Run it with `run_python`; the burst arithmetic is plain NumPy over the photon
stream, and the fitting at the end uses the ordinary fitting tools. See the
[single-molecule bursts](../../knowledge_base/concepts/single-molecule-bursts.md)
concept for what the quantities mean.

## 1. Get the bursts

A measurement usually arrives **already burst-searched**: a Seidel-style
analysis folder sits next to the photon files, holding one `.bur` table per
file with the per-burst photon indices and per-colour photon counts. Prefer it
— it is the analysis the user already trusts.

```python
import pandas as pd
from pathlib import Path

BUR = Path(WORKDIR) / "burstwise_All 0.1000#15" / "bi4_bur"
frames = []
for path in sorted(BUR.glob("*.bur")):
    table = pd.read_csv(path, sep="\t")
    table = table[table["Number of Photons"] > 0].copy()   # drop the header row
    table["file"] = path.stem + ".spc"                     # the photon file it indexes
    frames.append(table)
bursts = pd.concat(frames, ignore_index=True)
print(len(bursts), "bursts")
```

**`First Photon` and `Last Photon` are indices into the raw photon stream of
that file, and the end is exclusive** — `photons[first:last]`, ordinary Python
slicing. Verify it once on the data in front of you rather than trusting this:
summing the per-colour counts you extract must reproduce the `Number of
Photons (green)` / `(red)` columns exactly. If it does not, the indices mean
something else and everything downstream is wrong.

If there is no `.bur` analysis, run a burst search over the stream instead
(`chisurf.plugins.burst.burst_selection.api.selection.analyze_file`), and say
which parameters you used — a burst search is a threshold, not a measurement.

## 2. Proximity ratio

```python
green = bursts["Number of Photons (green)"].to_numpy(float)
red = bursts["Number of Photons (red)"].to_numpy(float)
bursts["PR"] = red / (green + red)
```

**PR is not the FRET efficiency.** It is the raw photon ratio, uncorrected for
background, spectral crosstalk, direct acceptor excitation and the detection
correction γ. Call it the proximity ratio, use it to *select* molecules, and
never report it as E. Getting E from intensities needs those corrections — see
the `accurate-fret` tooling — whereas the lifetime route below sidesteps them.

Show the user the PR histogram before selecting anything: the populations in it
are the actual result of the measurement.

## 3. Select the population — and its donor-only reference

Use exactly the window the user asked for. Then take a second population you
will need regardless:

```python
fret = (bursts.PR >= 0.5) & (bursts.PR <= 0.7)   # what the user asked for
donly = bursts.PR < 0.2                          # the donor-only reference
```

The low-PR peak is molecules whose acceptor is missing or bleached. Their
donor is unquenched, so **they are the donor reference for the same sample,
same buffer, same instrument, same day** — far better than a separate
measurement. Read the threshold off the histogram rather than assuming 0.2.

## 4. Sub-ensemble decays

The decay of a population is the micro-time histogram of its **donor-channel**
photons, over the bursts of that population only:

```python
import numpy as np, tttrlib

N_BINS, GREEN = 4096, [0, 8]        # donor routing channels of this setup
decays = {name: np.zeros(N_BINS, np.int64) for name in ("donly", "fret")}
for name in sorted(bursts["file"].unique()):
    tttr = tttrlib.TTTR(str(Path(WORKDIR) / name), "SPC-130")
    routing, micro = np.asarray(tttr.routing_channels), np.asarray(tttr.micro_times)
    for label, mask in (("donly", donly), ("fret", fret)):
        part = bursts[mask & (bursts["file"] == name)]
        for a, b in zip(part["First Photon"].astype(int), part["Last Photon"].astype(int)):
            photons = micro[a:b][np.isin(routing[a:b], GREEN)]
            decays[label] += np.bincount(photons, minlength=N_BINS)[:N_BINS]
```

The donor channels depend on the instrument — confirm them, do not copy the
numbers above. A cross-check that costs nothing: the photons you collect per
colour must match the `.bur` counts.

**Count the photons you ended up with.** A few thousand in the donor channel is
enough for one lifetime, not for two; a narrow selection window can leave too
few, and the honest response is to say so rather than to fit noise.

## 5. The instrument response

A decay fitted without an IRF is systematically wrong, and burst measurements
rarely ship one. Take it from the **non-burst photons of the same measurement**
— the scatter and dark counts between molecules:

```python
from chisurf.core.fluorescence.burst.irf_bg import extract_irf_background

estimate = extract_irf_background(tttr, {"green": {"chs": GREEN, "micro_time_ranges": []}})["green"]
irf, axis, background_khz = estimate.irf, estimate.time_ns, estimate.background_khz
```

This IRF is **contaminated**: molecules too dim to trigger a burst still
fluoresce into it, so it is broader than the true instrument response and the
lifetimes it yields are biased. That is tolerable here for one reason only —
**both decays are fitted against the same IRF, so the bias largely cancels in
their ratio**, and the ratio is what the distance is made of. Never quote an
absolute lifetime from such a fit without saying where the IRF came from.

Write the two decays and the IRF on one shared time axis, then load them with
`load_data(experiment="TCSPC")`:

```python
for label, counts in decays.items():
    np.savetxt(Path(WORKDIR) / f"{label}.dat", np.column_stack([axis, counts]), fmt="%.6f\t%d")
np.savetxt(Path(WORKDIR) / "irf.dat",
           np.column_stack([axis, np.round(irf / irf.sum() * 1e6)]), fmt="%.6f\t%d")
```

## 6. Fit both decays the same way

Same model, same components, same IRF, same fit range — a difference in
treatment becomes a difference in lifetime and then a false distance. Use
`create_fit` with `Lifetime (new)`, `set_irf` on both, `set_components`, then
`run_fit`, and check each fit as the `fit-decay` skill describes.

From the fitted amplitudes and lifetimes take the **species-weighted** average
`<tau>x = sum(x_i tau_i) / sum(x_i)` for the efficiency; the
intensity-weighted `<tau>f = sum(x_i tau_i^2) / sum(x_i tau_i)` is what a
steady-state anisotropy or an intensity measurement sees, and mixing the two up
is a common and silent error.

## 7. Distance, and the check that makes it trustworthy

```
E = 1 - <tau>x(DA) / <tau>x(D0)
R = R0 * (1/E - 1)^(1/6)
```

**R0 must come from the user** — it depends on the dye pair, the refractive
index and κ². Do not invent one; ask, and state the value you used.

Then run the consistency check, which is the whole reason this workflow is
worth doing:

> the efficiency from the donor lifetime should agree with the proximity ratio
> of the population you selected.

On a clean measurement it does — a window of PR 0.5–0.7 gives E ≈ 0.53 from
the lifetime. They come from independent observables (photon ratio versus
donor decay), so agreement is real evidence and disagreement is a finding:
a lifetime-E far *below* PR usually means acceptor-channel background or
crosstalk inflating PR; far *above* usually means donor quenching that is not
FRET, which no distance can be extracted from.

## What to report

The number of bursts and donor photons in each population, the selection window,
where the IRF and the donor reference came from, both lifetimes with their
reduced chi-squares, E, R0 and R — and the PR-versus-lifetime agreement. A
distance without the selection that produced it is not a result anyone can
reproduce.

A sub-ensemble decay is an **average over the selected molecules**. If the
population is heterogeneous the fit returns a mixture, and one distance may not
describe it: say that rather than reporting a mean of two states as if it were
one.
