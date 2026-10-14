---
type: Guide
title: 'From a selection to a fit: the ndX analysis bridges'
description: Gating a population in ndX isolates a species; a bridge then hands that species' photons to a full ChiSurf fit.
tags: [guides, fitting, ndxplorer, bridges]
---

# From a selection to a fit: the ndX analysis bridges

:::{admonition} Theory
:class: seealso
See {ref}`concept-md-bridges` for why a marginal fit is not enough and what a
bridge does; {ref}`concept-pda2c` for PDA, {ref}`concept-tcspc-lifetime` for
lifetime, {ref}`concept-filtered-fcs` for FRET-FCS.
:::

## What it does

Gating a population in {doc}`ndX <46_ndxplorer>` isolates a species; a
**bridge** then hands that species' *photons* to a full ChiSurf analysis. The
gate is resolved to per-file ``(first_photon, last_photon)`` intervals — the same
representation every ChiSurf burst reader consumes — and dispatched over the
ChiSurf RPC link to one of the analyses ChiSurf advertises as burst consumers
(`bursts.consumers`, see {doc}`52_send_bursts_to_analysis`):

| Bridge | ChiSurf RPC | Produces |
|--------|-------------|----------|
| Burst correlation (FCS) | `burst_fcs.correlate_file` | correlation curves, one call per file |
| TCSPC decay | `tcspc.from_bursts` | micro-time decay per detector group |
| PDA | `pda.from_bursts` | an S1/S2 experimental histogram, ready to fit |
| PCH | `pch.from_bursts` | photon-counting histogram P(k) |

All of them share one seam,
{py:func}`~ndxplorer.analysis.burst_bridge.selection_to_burst_slices`, so a new
target is another advertised RPC name — no new selection plumbing. Per-burst
lifetime MLE is not one of them: `burst_mle.workflow.prepare` takes a workflow
context (`.bur` files, channel settings), not burst intervals, so run it from
{doc}`21_lifetime_from_bursts`.

## Prerequisites

ndX must be linked to ChiSurf: either launched from ChiSurf (**Tools → Views → ndX** injects an in-process client exposing `pda.from_bursts`,
`tcspc.from_bursts`, `pch.from_bursts`, `burst_fcs.*`, `fit.*` and `dataset.*`),
or standalone with `--chisurf-rpc host:port` against a running ChiSurf server.
The burst table must carry `First File`, `Last File`, `First Photon` and
`Last Photon`; a Seidel-style analysis folder (**File → Import →
Analysis-Folder**, Ctrl+I) does. Without a link, a gate or those columns, the
**Send selection to** submenu is greyed out and its title names what is missing.

## The workflow

1. **Explore and gate.** Project onto E–S (or E–τ), find the population, brush a
   rectangle or draw a 2-D gate around it (see {doc}`46_ndxplorer`).
2. **Send the selection.** Right-click the 2-D histogram or the selection table
   → **Send selection to** → an analysis. The bridge resolves the active gate to
   burst intervals and calls it; the status line reports how many bursts from
   how many files went across and whether the handoff was recorded.

```{figure} figures/47_ndx_bridge_pda.png
:name: fig-47-ndx-bridge-pda
:width: 100%

ndX opened from ChiSurf on a burst folder built from `BH_SPC132.spc` (293
bursts). The gate keeps proximity ratio 0.35–1.0 (59 bursts, the FRET
population at τ ≈ 2 ns); after **Send selection to → PDA** the status line reads
*Sent 59 bursts from 1 file(s) to pda (not recorded: no database product
attached)* — the table was opened from a folder, not from MMFDB.
```

The reply is shown in a *Result from …* message and kept as `last_send` on the
ndX app. From the menu the analysis runs with the defaults ChiSurf advertises
({src}`chisurf/server/burst_consumers.json`: `channels: [[0], [1]]`, FCS pair
`chs_a: [0]` × `chs_b: [1]`); PDA reads the container type the burst analysis
recorded. Where those do not fit the measurement — other detector numbers, two
detectors per colour — use the bridge from a script, where every parameter can
be passed. The RPC client is
ndX's injected ``chisurf_rpc`` (``ndx.chisurf_rpc`` in the ChiSurf console) or an
in-process client built directly:

```python
import sys
sys.path.insert(0, "modules/ndxplorer")   # ndX ships as a ChiSurf module

from ndxplorer.io import loading
from ndxplorer.core.data_source import RectangularDataSelection
from ndxplorer.analysis.burst_bridge import BurstAnalysisBridge
from chisurf.plugins.ndxplorer.rpc_bridge import make_inprocess_chisurf_client

rpc = make_inprocess_chisurf_client()
data_source = loading.load("burstwise", kind="burst_dir")   # the analysis folder
names = data_source.parameter_names
sel = [RectangularDataSelection(parameter_idx=names.index("Proximity Ratio"),
                                lower=0.35, upper=1.0)]
# In the GUI: data_source = ndx.data_source; sel = ndx.plot_control.get_selections()

bridge = BurstAnalysisBridge(rpc, data_source)

# 1) PDA on the gated bursts -> S1/S2 histogram, ready to fit
pda = bridge.send_to_pda(sel, channels=[[0, 8], [1, 9]], reading_routine="SPC-130",
                         maximum_number_of_photons=200)
print(pda["curves"][0]["shape"])                     # [201, 201]

# 2) Burst correlation (FCS) on the same gate; a pair is chs_a x chs_b
fcs = bridge.send_to_correlator(sel, pairs=[{"name": "GxR", "chs_a": [0, 8],
                                             "chs_b": [1, 9]}],
                                settings={"fit_mode": "none"})
print(len(fcs[0]["result"]["curves"]))               # one curve per burst

# 3) Any other advertised consumer through the generic send
reply = bridge.send("tcspc", sel, channels=[[0, 8], [1, 9]])
print(reply["n_bursts"], reply["result"]["n_photons"])   # 59 7674
```

On `BH_SPC132.spc` (channels 0/8 green, 1/9 red) the gate above sends 59 of 293
bursts; the TCSPC decay then holds 7674 photons, and 3883 with the default
`[[0], [1]]`, which drops the second detector of each colour.

`selection_to_burst_slices` drops bursts that straddle two files (they have no
single TTTR source) and preserves file order; it is verified to reproduce the
`.bst` files ChiSurf's "save burst IDs" already writes, so the bridge and the
file-based path agree exactly.

## Worked example: select the FRET population, run PDA on it

Take the two-population smFRET set from {doc}`46_ndxplorer` (a no-FRET species
near $E\approx0.02$ and a FRET species near $E\approx0.50$). The E marginal fit
told you *where* the FRET peak is and roughly how wide; it could not tell you
whether that width is shot noise alone or a distance distribution. That is a PDA
question:

1. Gate the FRET cluster (rectangle on E, or a 2-D gate on E–S).
2. `bridge.send_to_pda(sel, channels=[[0, 8], [1, 9]], reading_routine=...)`
   builds the S1/S2 histogram from exactly those bursts; it comes back as
   `curves[0]["s1s2"]` with its `shape` and photon counts.
3. Fit it with a {doc}`PDA model <11_pda2c>` — a single static distance
   distribution should now describe the peak the Gaussian could not, and its
   residual reveals any hidden dynamics.

The no-FRET population, gated and sent the same way, gives the donor-only
reference the correction factors need.

## Limits

- **The menu result is a report, not a fit.** The returned histogram, decay or
  curves are summarised in a message and kept as `last_send`; they are not
  opened as a ChiSurf dataset. Use the scripted bridge above to fit them.
- **`First File` is a leaf name.** The bridge resolves it against the folder the
  table was read from (and one or two levels above, the
  `<measurement>/burstwise_*/bi4_bur` layout); a file found nowhere is passed on
  as given and the receiving service names it as missing.

## See also

- Theory: {ref}`concept-md-bridges`, {ref}`concept-multidimensional-exploration`.
- `ndxplorer/analysis/burst_bridge.py` (client); {src}`chisurf/server/services/pda.py`
  (`pda.from_bursts`); the burst-FCS ({doc}`16_fret_fcs`) and burst-MLE
  ({doc}`21_lifetime_from_bursts`) analyses.
- Tool: **ndX** (`chisurf/plugins/ndxplorer/`).
