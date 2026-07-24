# Recurrence analysis of single particles (RASP)

:::{admonition} Theory
:class: seealso
The same-molecule recurrence probability, the conditional recurrence FRET
histogram, and how RASP separates dynamics from static heterogeneity are
explained in the concept page {ref}`concept-recurrence`.
:::

## What it does

A single burst lasts about a millisecond — too short to see slow (ms–s)
conformational kinetics. **RASP** (Hoffmann et al., *Phys. Chem. Chem. Phys.*
2011) recovers those slow timescales from freely-diffusing smFRET by exploiting
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

- `chisurf/core/fluorescence/burst/recurrence.py`
- Workflow: `Bursts.recurrence()` → a `Recurrence` result.
