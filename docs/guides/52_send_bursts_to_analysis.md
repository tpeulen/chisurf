# Sending a gated burst population to FCS, TCSPC, PDA or PCH

Exploring a burst parameter space in ndX tells you *where* the populations are.
It does not, on its own, give you a shot-noise-limited distance distribution, a
multi-exponential donor decay, a diffusion time, or a molecular brightness.
Those need the population's **photons** back — a real analysis on the selected
bursts' photon stream, not a histogram of the column you gated on.

This guide covers that handoff: draw a gate, right-click, pick an analysis.

## What travels between the two

A gate in ndX is a set of selections over burst-table columns. What ChiSurf's
burst readers consume is a much simpler thing: per-file `(first_photon,
last_photon)` index intervals — the same shape a `.bst` file stores. The bridge
is that one transform plus a dispatch, so the gate you drew becomes the exact
set of photons the analysis sees.

This is why the menu needs a burst table with provenance columns. `First File`,
`First Photon` and `Last Photon` are what make a row point back at photons; a
table of derived quantities alone cannot be sent anywhere, and the menu says so
rather than failing later.

## Doing it

1. Open ndX from ChiSurf (or start it with `--chisurf-rpc host:port`). Without a
   connection there is nothing to send *to*, and the menu says exactly that.
2. Load a burst table — a `.bur` file, or bursts computed in the trace browser.
3. Draw a gate on the 2-D histogram, or add one in the selection table.
4. **Right-click** either the 2-D histogram or the selection table →
   **Send selection to** → *FCS*, *TCSPC decay*, *PDA* or *PCH*.

The status line reports how many bursts from how many files went across, and
whether the handoff was recorded.

## The menu is not a list ndX keeps

ndX does not know that a method called `pda.from_bursts` exists, and should not.
It asks ChiSurf what consumes bursts — `bursts.consumers` — and renders the
answer. Each advertised consumer carries its own label, RPC name, call shape,
default parameters, provenance vocabulary, and where needed a caveat.

That inversion is what keeps the two independent. **A new burst analysis appears
in this menu with no ndX release**, and an older ChiSurf that advertises three
analyses produces a three-entry menu rather than one with a dead fourth entry.

What ships today:

| Target | RPC | What comes back |
|---|---|---|
| FCS | `burst_fcs.correlate_file` | Correlation curves, one set per file |
| TCSPC decay | `tcspc.from_bursts` | Micro-time decay per detector group |
| PDA | `pda.from_bursts` | Experimental S1/S2 histogram, ready to fit |
| PCH | `pch.from_bursts` | Photon-counting histogram P(k) |

### Advertising another analysis

Add an entry to {src}`chisurf/server/burst_consumers.json`, or — for an analysis that
lives in a plugin — a `burst_consumers` array in that plugin's `manifest.json`,
using the same fields. A plugin entry reusing an existing `key` supersedes the
built-in one.

```json
"burst_consumers": [
  {
    "key": "my_analysis",
    "title": "My analysis",
    "summary": "One line the menu shows as a tooltip.",
    "rpc": "my_plugin.from_bursts",
    "per_file": false,
    "operation_type": "analysis",
    "product_type": "analysis_result",
    "defaults": {"some_parameter": 1.0},
    "caveat": "Shown to the user when the answer needs a qualification."
  }
]
```

`per_file: false` sends the whole `burst_slices` mapping in one call;
`per_file: true` issues one call per file with `tttr_path` and `ranges`. The
`operation_type` and `product_type` terms must exist in the mmCIF dictionary,
which is the schema authority — the store rejects anything else on write.

## PCH needs a decision the others do not

Three of the four are unambiguous. The decay of a chosen set of photons is that
set's decay; correlating them correlates them; a PDA histogram is built from
them directly. Gating does not distort any of those.

PCH is different, and the difference is easy to miss because it produces a
perfectly plausible-looking histogram either way.

PCH's usual meaning — molecular brightness ε and occupancy N from the *shape* of
P(k) — assumes the counting bins are a fair sample of the trace, **including the
empty stretches between molecules**. Bursts are by construction the bright
stretches. Bin only their interiors and you truncate the low-k side of P(k);
fit brightness to that and ε comes out too high and N too low.

So `pch.from_bursts` offers both readings and always says which one it used:

- **`span`** (the default) bins the whole trace between the first and last gated
  photon, so the inter-burst background is present and P(k) keeps its usual
  meaning. **This is the one to fit a brightness model to.**
- **`interior`** bins only inside the burst intervals. Useful for comparing the
  count statistics of two gated populations against each other, and misleading
  if read as an absolute brightness.

Every result carries `mode` and `burst_duty_cycle` — the fraction of the
analysed span the bursts actually occupy. Near 1 the two modes nearly agree;
near 0 they differ enormously, which is precisely when the distinction matters.
An `interior` result additionally carries a `selection_bias` string, so the
warning travels with the data rather than living only in this page.

## Every handoff is recorded

A gated population is a claim about a subset of the data — "these bursts are the
high-FRET species". A decay computed from it is uninterpretable without the gate
that produced it, so the two are stored together.

Each send writes an operation to MMFDB linking the input product to the output
artifact, carrying:

- the **gate** — every selection's type, name, parameter and bounds;
- the **bursts** — how many, from which files;
- the **parameters** actually used, including PCH's `mode`;
- a **summary** of the result, not the result itself. The store indexes
  provenance; it is not a results archive, and embedding a megabyte histogram
  would make every provenance query drag the data with it.

The vocabulary comes from the mmCIF dictionary, which is the schema authority:
operations are `fcs_correlation`, `tcspc_histogram_computation`,
`pda_histogram_computation` and `pch_histogram_computation`; artifacts are
`fcs_correlation`, `tcspc_decay`, `pda_histogram` and `pch_histogram`.

Recording never breaks a send. If the store is unreachable the analysis result
is still returned and the status line says the provenance is missing — losing
the record is bad, and throwing away a completed computation over a bookkeeping
failure is worse.

Provenance needs a database product to attribute the work to. Opened from a
plain file rather than from MMFDB, ndX has nothing to link to, and the status
line says `not recorded` rather than pretending.

## Headless

The same path without a GUI:

```python
from ndxplorer.analysis.burst_bridge import BurstAnalysisBridge

bridge = BurstAnalysisBridge(rpc_client, data_source, owner=window)

reply = bridge.send("tcspc", selections, channels=[[0, 8], [1, 9]])
print(reply["n_bursts"], "bursts ->", len(reply["result"]["decays"]), "decays")

# PCH, being explicit about which reading is wanted
reply = bridge.send("pch", selections, mode="span", bin_time_us=50.0)
print(reply["result"]["burst_duty_cycle"], reply["provenance"])
```

`send(..., record=False)` skips the provenance write for batch callers that
record their own operation.

## Related

- [ndX exploration workflow](46_ndxplorer.md)
- [Photon distribution analysis](../concepts/pda2c.md)
- [The metadata store](../reference/plugins/mmfdb_admin.md)
