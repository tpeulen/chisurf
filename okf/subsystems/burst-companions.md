---
type: Subsystem
title: Burst-analysis companion files
description: The one contract every burst-analysis plugin follows when writing results beside the bursts — per-measurement files in a directory ending in "4", one row per burst including the ones it skipped — so a burst folder merges into a single table without misaligning.
resource: chisurf/core/fio/fluorescence/burst_companion.py
tags: [burst, file-format, interop, ndxplorer, conventions]
timestamp: '2026-07-28T00:00:00Z'
---

# Why it exists

A burst-analysis folder is a small database keyed by *burst*. `bi4_bur/*.bur`
holds one row per burst per measurement; every analysis writes its results
*beside* it as a **companion**:

| Companion | Written by |
|---|---|
| `bv4/<stem>.bv4` | Burst Variance Analysis |
| `2c4/<stem>.2c4` | FRET-2CDE / ALEX-2CDE |
| `bg4`, `br4`, `by4` | Burst MLE, one per colour — and the segment-level fit, which adds `Tau S0`, `Tau S1`, … *columns* to the same files |
| `bh4/<stem>.bh4` | H2MM per-burst state |

Not everything a burst analysis produces is a companion. A result with a grain
other than the burst — the pooled lifetime of each H2MM state, one row per
*state* (`Info/state_lifetimes.csv`) — goes beside the analysis as a plain file
in `Info/`. Written as a companion it would be merged by position onto the burst
table and would shift every burst after the first.

A reader opens the folder by concatenating the `.bur` files and merging every
companion **column-wise, by position**, so the whole folder reads as one table
with one row per burst. ndX does exactly this, which is how a burst can be
gated on a column another plugin produced.

That merge is positional, and **nothing validates it at read time**. A companion
that gets the layout wrong does not fail — it *shifts*, and burst 900's lifetime
is reported against burst 899's efficiency. The contract is therefore
load-bearing, and it lives in one writer rather than in each plugin's head: it
stood at six independent implementations of the same format until
[`burst_companion.py`](../../chisurf/core/fio/fluorescence/burst_companion.py).

# The contract

1. **One file per measurement**, named for the `.bur` stem:
   `<ending>/<stem>.<ending>`. Not one table for the whole folder — the merge is
   per measurement. A single folder-wide table indexed by a running number
   cannot be joined at all (see *The trap*, below).
2. **The directory name ends in `4`.** That is how a reader discovers a
   companion it has never heard of. A companion named anything else is written,
   and silently never read.
3. **One row per burst of that measurement, in burst-table order** — including
   bursts the analysis could not compute. A skipped burst keeps its row with a
   sentinel; omitting it shifts every later row.
4. **Zero-interleaved**: `2N + 1` physical rows for `N` bursts, data on the odd
   rows. Historical, and load-bearing — readers drop every second row.
5. **Tab-separated, trailing tab on the header line.**
6. **Every column numeric**, and namespaced so it cannot collide with another
   companion's (`H2MM State`, `Tau (green)`). Companions merge into one frame,
   and a duplicate column name is dropped, taking its data with it.

`write_companion(analysis_dir, ending, stem, columns, rows)` enforces all six and
raises `CompanionError` rather than writing something that would misalign.
`test/plugins/burst/test_companion_contract.py` pins the contract and checks the
names every burst plugin declares.

# The trap this replaced

Two real failures, both silent:

* **H2MM** wrote one `h2mm_bursts.csv` for the whole folder, indexed by a
  *compacted* burst number — `extract_burst_photons` skips bursts below
  `min_photons`, so the index is a count of what survived, not a row into the
  burst table. One dropped burst shifts everything after it, so the table could
  not be joined back at all. Fixed by rule 1 + rule 3: per-measurement `bh4`
  files carrying every burst, with `H2MM Fitted = 0` where it was skipped.
* **A per-state MLE** first wrote `bg4_s0/`, `bg4_s1/` — which reads naturally
  and **does not end in `4`**, so a folder reader would never have merged it.
  Renaming to `s0_bg4` fixed the discovery and exposed the deeper fault: each
  folder emitted `Tau (green)`, *the same column name* the real `bg4`
  contributes. Both mergers drop a duplicate (ndX `~columns.duplicated()`, first
  wins; chisurf `if col not in df.columns`), so the per-state numbers were
  written and then silently discarded by the browser and by ndX alike — rule 6,
  learned the hard way.

  The resolution was not a better folder name. **A sub-population is a column,
  not a companion**: the split-by-state fit now writes `Tau S0 (green)` beside
  `Tau (green)` in the *existing* `bg4`, keeping one row per burst and one
  unambiguous name per quantity. The separate plugin was retired.

# Related

* [/plugins/burst.md](../plugins/burst.md) — the burst workflow and its steps.
* [/subsystems/data-io.md](data-io.md) — the wider file-reading layer.
