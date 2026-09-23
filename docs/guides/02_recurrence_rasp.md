---
type: Guide
title: Recurrence analysis of single particles (RASP)
description: A single burst lasts about a millisecond — too short to see slow (ms–s) conformational kinetics.
tags: [guides, bursts, kinetics]
---

# Recurrence analysis of single particles (RASP)

:::{admonition} Theory
:class: seealso
The same-molecule recurrence probability, the conditional recurrence FRET
histogram, and how RASP separates dynamics from static heterogeneity are
explained in the concept page {ref}`concept-recurrence`.
:::

## What it does

A single burst lasts about a millisecond — too short to see slow (ms–s)
conformational kinetics. **RASP** {cite}`hoffmann2011` recovers those slow timescales from freely-diffusing smFRET by exploiting
**recurrence**: a molecule that diffuses out of the confocal spot and returns
produces a second burst, and within the *recurrence time* the recurring burst is
likely the **same** molecule.

Two quantities:

- **Same-molecule probability** $P_\text{same}(\tau) = 1 - 1/G(\tau)$, where
  $G$ is the autocorrelation of the burst arrival times. It sets the recurrence
  window in which correlations are meaningful (where $P_\text{same}$ is high).
- **Recurrence FRET histogram**: pick an initial sub-population by efficiency,
  then histogram the efficiencies of the bursts that recur within a chosen time
  window. Compared with the overall histogram, a shift reveals inter-conversion
  between states.

## In ChiSurf

Everything operates on the per-burst table (arrival time + proximity ratio) —
no photon-level access needed.

### In the GUI: the same-molecule probability

The $P_\text{same}(\tau)$ curve is drawn by **Burst Fusion** — step
**3. Burst Fusion (optional)** of **Spectroscopy → Burst Analysis**, or on its
own as *Spectroscopy:Single-Molecule:Burst Fusion*. Point **Folder** (**…**) at a
burst-analysis folder (the one Burst Selection wrote) and press ▶. The tool
estimates $P_\text{same}$ over all bursts of the folder and reads off the
longest lag at which it still meets **P(same) ≥**.

```{figure} figures/02_rasp_p_same.png
:name: fig-rasp-p-same
:width: 100%

Burst Fusion on the ten bundled SPC-132 measurements of a doubly labelled dsDNA
(`chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/`,
2980 bursts). $P_\text{same}$ stays above 0.5 out to 68.2 ms; the red
horizontal line is the threshold, the vertical one the 10 ms **Max gap**
ceiling the fusion is capped at.
```

| Control | Default | Meaning |
|---|---|---|
| **Folder** | — | Burst-analysis folder (`bi4_bur/`) to read. |
| **P(same) ≥** | 0.50 | Threshold the curve is inverted at. |
| **Max gap** | 10 ms | Longest gap ever fused, whatever $P_\text{same}$ says. |
| **Max fragments** | 0 (no limit) | Largest number of bursts merged into one. |
| **P(same molecule) estimate** | collapsed | Lag range and bin count of the $P_\text{same}$ estimate. |

The status block states the result in words
(*P(same molecule) ≥ 0.50 holds out to 68.239 ms … 2980 → 1603 bursts*) and the
table compares selected and fused bursts. The recurrence **FRET histogram**
has no GUI; it is the API below. Burst Fusion itself is covered in the
[Burst fusion](58_burst_fusion.md) guide.

### Headless

```python
from chisurf.core.fluorescence.burst import recurrence as rec

tau, p_same, _ = rec.same_molecule_probability(burst_times_s, tau_min_s=1e-3,
                                               tau_max_s=1.0, n_bins=40)

centers, rec_hist, all_hist = rec.recurrence_histogram(
    burst_times_s, efficiency,
    e_range=(0.0, 0.4),        # initial low-FRET sub-population
    dt_range_s=(1e-3, 0.05),   # recurrence-time window
)
```

Or through the guided burst workflow:

```python
r = bursts.recurrence(donor="green", acceptor="red")
r.recurrence_time(threshold=0.5)                       # usable recurrence window (s)
r.plot(e_range=(0.0, 0.4), dt_range_s=(1e-3, 0.1))
```

`bursts.recurrence()` needs a burst table with a proximity ratio or
per-detector photon counts; see *Known defects*.

## Result

Molecules that recur within ~30 ms and inter-convert between a low-FRET
(E ≈ 0.25) and a high-FRET (E ≈ 0.75) state were simulated. **Left:**
$P_\text{same}$ is high at short lags and decays — beyond ~100 ms a recurring
burst is no longer the same molecule. **Right:** the recurrence histogram for the
initial low-E population is dominated by the high-E state, directly showing the
inter-conversion the single-burst histogram cannot resolve.

```{figure} figures/rasp.png
:name: fig-rasp
:width: 90%

RASP: same-molecule probability and recurrence histogram.
```

## See also

- {src}`chisurf/core/fluorescence/burst/recurrence.py`
- Workflow: `Bursts.recurrence()` → a `Recurrence` result.
- Tool: **Burst Fusion** (`chisurf/plugins/burst/burst_fusion/`), which uses
  $P_\text{same}$ to merge fragments of one passage.

## Known defects

- **`Bursts.recurrence()` fails on bursts from `BurstWorkflow.select_bursts`.**
  `select_bursts` builds its `AnalysisRequest` without the setup's detectors,
  so the burst table has no `Number of Photons (green|red)` columns and no
  `Proximity Ratio`; `recurrence()` then raises *"no FRET efficiency /
  proximity-ratio column"* (measured on `m000`–`m002.spc`, 2026-09-23). Use
  the core functions above with an efficiency column you computed.
