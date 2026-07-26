# From a selection to a fit: the ndXplorer analysis bridges

:::{admonition} Theory
:class: seealso
See {ref}`concept-md-bridges` for why a marginal fit is not enough and what a
bridge does; {ref}`concept-pda2c` for PDA, {ref}`concept-tcspc-lifetime` for
lifetime, {ref}`concept-filtered-fcs` for FRET-FCS.
:::

## What it does

Gating a population in {doc}`ndXplorer <46_ndxplorer>` isolates a species; a
**bridge** then hands that species' *photons* to a full ChiSurf fit. The gate is
resolved to per-file ``(first_photon, last_photon)`` intervals — the same
representation every ChiSurf burst reader consumes — and dispatched over the
ChiSurf RPC link to one of three analyses:

| Bridge | ChiSurf RPC | Produces |
|--------|-------------|----------|
| Burst correlation (FCS) | `burst_fcs.correlate_file` | correlation curves per file |
| PDA | `pda.from_bursts` | an S1/S2 experimental histogram, ready to fit |
| Lifetime (MLE) | `burst_mle.*` | per-burst maximum-likelihood lifetimes |

All three share one seam,
{py:func}`~ndxplorer.analysis.burst_bridge.selection_to_burst_slices`, so a new
target is just another RPC method name — no new selection plumbing.

## Prerequisites

ndXplorer must be linked to ChiSurf: either launched from ChiSurf (the in-process
client exposes `pda.from_bursts`, `burst_fcs.*`, `burst_mle.*`, `fit.*` and
`dataset.*` automatically), or standalone with `--chisurf-rpc host:port` against a
running ChiSurf server. Without a link the bridges are disabled and say so.

## The workflow

1. **Explore and gate.** Project onto E–S (or E–τ), find the population, brush a
   rectangle or draw a 2-D gate around it (see {doc}`46_ndxplorer`).
2. **Send the selection.** The bridge resolves the active gate to burst intervals
   and calls the chosen analysis; the result comes back to be overlaid or opened
   in a ChiSurf fit.

Headlessly, the bridge is a few lines. The RPC client is ndXplorer's injected
``chisurf_rpc`` (or an in-process client built directly):

```python
from ndxplorer.analysis.burst_bridge import BurstAnalysisBridge

# In-GUI you already have ndx.chisurf_rpc; here we build one explicitly:
from chisurf.plugins.ndxplorer.rpc_bridge import make_inprocess_chisurf_client
rpc = make_inprocess_chisurf_client()

bridge = BurstAnalysisBridge(rpc, ndx.data_source)   # data_source holds the burst table
sel = ndx.plot_control.get_selections()              # the active gate(s)

# 1) PDA on the gated bursts -> S1/S2 histogram, ready to fit
pda = bridge.send_to_pda(sel, channels=[[0], [1]], reading_routine="PTU",
                         maximum_number_of_photons=200)
print(pda["curves"][0]["shape"])                     # e.g. [201, 201]

# 2) Burst correlation (FCS) on the same gate
curves = bridge.send_to_correlator(sel, pairs=[{"ch1": [0], "ch2": [1]}])

# 3) Any other burst RPC (e.g. lifetime MLE) via the generic dispatch
decays = bridge.send_to("burst_mle.workflow.prepare", sel, per_file=True)
```

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
2. `bridge.send_to_pda(sel, channels=[[0], [1]], ...)` builds the S1/S2 histogram
   from exactly those bursts.
3. Fit it with a {doc}`PDA model <11_pda>` — a single static distance
   distribution should now describe the peak the Gaussian could not, and its
   residual reveals any hidden dynamics.

The no-FRET population, gated and sent the same way, gives the donor-only
reference the correction factors need.

## See also

- Theory: {ref}`concept-md-bridges`, {ref}`concept-multidimensional-exploration`.
- `ndxplorer/analysis/burst_bridge.py` (client); `chisurf/server/services/pda.py`
  (`pda.from_bursts`); the burst-FCS ({doc}`16_fret_fcs`) and burst-MLE
  ({doc}`21_lifetime_from_bursts`) analyses the other targets drive.
```
