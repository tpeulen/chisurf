---
type: Guide
title: Selecting and comparing FRET populations
description: A single measurement usually contains several sub-populations — different FRET states, donor-only, aggregates.
tags: [guides, fret, selecting, populations]
---

# Selecting and comparing FRET populations

:::{admonition} Theory
:class: seealso
The FRET efficiency $E$ and stoichiometry $S$ that these populations are gated on,
and the corrections behind them, are covered in the concept page
{ref}`concept-smfret-bursts`.
:::

## What it does

A single measurement usually contains several sub-populations — different FRET
states, donor-only, aggregates. **Selecting** a population means gating bursts by
one or more observables: stoichiometry $S$ (to keep doubly-labelled molecules),
burst size (photon count, for signal-to-noise), and a region of interest (ROI)
on the $E$–$S$ map. Comparing the selected sub-populations — their fractions,
FRET efficiencies, burst widths — is how heterogeneity and dynamics are
quantified. A two-color (DCBS) burst search can additionally enrich the
doubly-labelled species.

## In ChiSurf

The **Burst Browser** loads a folder of per-burst `.bur` results into a sortable
table and live histogram; the **Controls** panel gates the population by
efficiency, stoichiometry and burst size before histogramming any column:

```{figure} figures/burst_browser.png
:name: fig-burst-browser
:width: 95%

The Burst Browser on a real single-molecule DNA dataset (2980 bursts). The
**Controls** panel sets the histogram column ($E$) and the `E min` / `S min` /
`Size min` gates; the **Bursts** table lists every burst; the **Histogram**
panel shows the FRET-efficiency distribution — here clearly bimodal, a donor-only
peak near $E=0$ and a FRET population around $E\approx0.4$.
```

The native browser opens at **1200 × 800** pixels on first use. After loading a
file or folder:

1. Set the **E**, **S** and burst-size gates in **Burst gates**, then choose the
   histogram column. Corrected values and the displayed gate limits can extend
   below 0 or above 1; the controls preserve those measured ranges.
2. Inspect the **Bursts** table, which shows up to **50 rows per page**. Use
   `<<` and `>>` to change pages. The horizontal scrollbar or horizontal wheel
   reaches every measurement column, including the final columns in a wide
   table. Click a header to sort the current page; numeric columns sort by their
   numeric values.
3. Click rows to toggle their selection, then enable **Use table selection for
   hist** to histogram those bursts. Selection follows the original burst
   identities through sorting and page changes. **Clear Sel** deselects all
   rows. With the checkbox off, the histogram uses all bursts passing the gates.

```{figure} figures/burst_browser_native_columns.png
:name: fig-burst-browser-native-columns
:width: 95%

The native Burst Browser on a real burst table, scrolled to its final
measurement columns. Pagination remains above the scrolling table.
```

Saved settings restore the window geometry and dock layout. Reopen the data and
set the gates again after restarting; these are not restored as an analysis
session. Table presentation does not change the measured quantities or the
scientific gating and histogram calculations.

The table is a datastore-backed column store. For Python selection, use
`numeric_column` to obtain arrays rather than assuming it is a pandas DataFrame:

```python
import numpy as np
from chisurf.core.datastore import numeric_column
from chisurf.plugins.burst.burst_browser.view_model import BurstBrowserViewModel

browser = BurstBrowserViewModel()
browser.load_bur("measurement.bur")
t = browser.table
E = numeric_column(t, "E")
S = numeric_column(t, "S")
size = numeric_column(t, "Number of Photons")
fret = (S > 0.25) & (S < 0.75) & (size > 30)
high = np.count_nonzero(fret & (E > 0.55))
low = np.count_nonzero(fret & (E < 0.45))
ratio = low / high if high else np.nan
```

Use the column names provided by your measurement; this example requires `E`,
`S` and `Number of Photons`. For interactive ROI gates and Gaussian-mixture
clustering, use **Burst Selection** ([tutorial 26](26_2d_peak_fitting.md)).

## Result

**Left:** a high-FRET region of interest drawn on the $E$–$S$ map. **Right:** the
FRET-efficiency histograms of the selected high- and low-FRET sub-populations,
ready for comparison of their fractions and positions.

```{figure} figures/population_selection.png
:name: fig-population-selection
:width: 90%

Selecting FRET populations.
```

## See also

- `chisurf/plugins/burst/burst_selection/`; the full workflow: [tutorial 27](27_alex_smfret_workflow.md).
