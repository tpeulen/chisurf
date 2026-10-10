---
type: Subsystem
title: Burst-analysis companion files
description: The one contract every burst-analysis plugin follows when writing results beside the bursts — per-measurement files in a directory ending in "4", one row per burst including the ones it skipped — so a burst folder merges into a single table without misaligning.
resource: chisurf/core/fio/fluorescence/burst_companion.py
tags: [burst, file-format, interop, ndxplorer, conventions]
timestamp: '2026-07-28T00:00:00Z'
---

# Where to pick this up

Companions are no longer written by any burst plugin: `grep -rn "write_companion(" chisurf/plugins`
is empty. A step writes a **run into the measurement's `.pto`**, and the one place a companion
is made is
[`legacy_export.export_legacy`](../../chisurf/core/fio/fluorescence/legacy_export.py) (PTO inspector
*Export legacy…*, `csg_pto_inspect export-legacy`). Open front, in order:

1. Open: **Burst MLE and burst FCS have no run picker.** Both read loose `.bur`/`.bst` files by path
   (`burst_mle_analysis/engine.py:read_burst_analysis` and `MleSession.add_burst_files`, which derive
   the raw files from `path.parent.parent`; the correlator reads `.bst` ranges). A `.pto` input needs
   the container branch `_read_burst_analysis_from_container` that BVA, 2CDE and H2MM already take
   (`burst_h2mm/backend/services.py:run_analysis` is the pattern). Then: `class MleViewModel(RunPickerMixin)`
   with `run_picker_attr = "run_container"`, and `RUN_PICKER_SECTION` after the *Burst files*
   `data_table` of `mle_native.view.json`. Measure with `grep -n run_rows chisurf/plugins/burst/*/gui/*.json`.
2. Open: **The legacy export skips, and logs, a per-burst result of an operation that is not in
   `COMPANIONS`** (`model_fitting`: ebfret, burst_gs). Pass `operations=[...]` to make it raise instead.
   A zero in an exported companion is the sentinel for "skipped"; the container keeps the real NaN.
3. Open: **The run table's `Order` column is the write order**, because the container records no timestamp;
   if the dictionary gains one, show it instead.

Tried and reverted: coercing run `parameters` to scalars before hashing (`scalar_parameters`) — the
settings hash already takes lists, and the coercion changed the stored settings of every run, which
broke the background step's read of them. The failure that looked like a hashing error was
`df[["First File", col]]` on a `DataStore`, which needs `take_columns`.

# Why it exists

A burst-analysis folder is a small database keyed by *burst*. `bi4_bur/*.bur`
holds one row per burst per measurement; every analysis writes its results
*beside* it as a **companion**:

| Companion | Exported from the run of |
|---|---|
| `bv4/<stem>.bv4` | Burst Variance Analysis (`burst_variance_analysis`) |
| `2c4/<stem>.2c4` | FRET-2CDE / ALEX-2CDE (`burst_2cde`) |
| `bg4`, `br4`, `by4` | Burst MLE, one per colour (`burst_lifetime_fitting`, the detector in the artifact's name) — and the segment-level fit, which adds `Tau S0`, `Tau S1`, … *columns* to the same files |
| `bh4/<stem>.bh4` | H2MM per-burst state (`photon_hmm`) |
| `td4/<stem>.td4` | Burst FCS diffusion times (`burst_correlation`, `time_delay`) |
| `bf4/<stem>.bf4` | Burst fusion: which fused burst each source burst joined (`burst_fusion`) |

The table is `legacy_export.COMPANIONS`; it is the only place an operation is bound to an ending.

Not everything a burst analysis produces is a companion — and since the container is the primary store, a companion is only ever an export of one.

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

# The write side is one explicit export

`export_legacy(container, out_dir)` first unpacks the container's tables as
`export_tree` does (`<run>/bi4_bur/<stem>.bur`, the interleave included), then, for every
per-burst result whose operation is in `COMPANIONS`, writes one companion through
`write_companion` — never a hand-rolled interleave. The rows are placed on the burst grid of the
burst table the result belongs to (its parent, else the one in the same run, else the latest):

* a result with one row per burst is written as it is;
* a result that covers only some bursts (H2MM keeps the bursts it fitted, burst FCS those with a
  result) is placed by the `source_row_column` its artifact declares, every other burst a row of zeros;
* a result with neither a matching row count nor a key raises `CompanionError` — never a guess;
* two runs of one analysis writing the same column: the most recent wins (a duplicate column name
  would be dropped by the merging reader, taking its data with it);
* a result stored in a run of its own with no burst table (fusion's `fused/assembly`) owns its grid.

Tests: `test/fio/test_legacy_export.py` (bursts + BVA + 2CDE → export → `read_companion` equals the
run tables, directory names end in `4`, the row count is the burst count including skipped bursts,
an unregistered operation raises).

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

# The read side of rule 4

Rule 4 has a mirror image every *reader* has to honour: the zero rows are kept
in the frame, so their `First File` cell is not a measurement — it is `"0"`. A
loader that resolves the column's unique values against the data directory
therefore asks for a file named `0`, and `tttrlib` does not raise on it: it
prints a note and hands back an **empty** object whose header reports a negative
macro-time resolution. Anything reading "the first file's header" then reads the
header of nothing. `is_sentinel_file_reference` in
[`photons.py`](../../chisurf/core/fluorescence/burst/photons.py) is the single
place that recognises those cells, and `load_tttrs_for_dataframe` skips them, so
the mapping it returns holds real measurements only (RF-563).

# Table discovery and missing results

The shared BVA/2CDE legacy reader selects canonical `.bur` files and companions
whose filenames match the complete directory ending, including namespaced
`s0_bg4` and dotted `custom.4`. Binary PTO cache sidecars remain on disk and are
not decoded as tab-separated text. Table discovery does not alter deinterleaving,
row order, photon boundaries or clocks.

A skipped 2CDE score remains NaN in memory. The canonical all-numeric companion
writer serializes nonfinite values as numeric zero while retaining every
positional row; consumers must distinguish that export sentinel from a computed
zero. Actual 152-burst measurements and a missing-source fixture verify the
reader/writer behavior. Current source is verified but uncommitted; see the
[shared reader acceptance](../validation/release-readiness-w6g/bva-sidecar-owner-acceptance.json)
and [2CDE acceptance](../validation/release-readiness-w6g/two-cde-window-acceptance.json).

# `Last Photon` is inclusive

The other convention a reader has to get right, and the one that fails most
quietly: `First Photon` / `Last Photon` are photon indices into the measurement's
raw TTTR arrays, and **`Last Photon` names the burst's last photon, not one past
it** — `Number of Photons == Last Photon − First Photon + 1`. Every slice runs to
`last + 1`, and a row with `First == Last` is a one-photon burst rather than an
empty one. Three independent sources agree: the external PARIS format (all 12237
non-sentinel rows of the folder in `modules/ndxplorer/test/mfd/`), the in-tree
writer `generate_burst_dataframe`, and `tttrlib::BurstFeature::for_each_burst`,
which the compiled BVA / 2CDE engines are built on.

An exclusive `[first:last]` read does not fail — it returns a burst that is one
photon short, uniformly, for every burst in the file. The `1/N` bias lands
hardest on the shortest and dimmest bursts, which is where the gap statistics
that drive a kinetic fit live, and a `min_photons` floor applied to the short
count silently rejects bursts sitting on the threshold. `extract_burst_photons`
is the shared seam and is inclusive (RF-804, pinned by
`test/fluorescence/test_burst_photons.py`, which round-trips a table written by
the real writer). Note the repo's own `bh_spc132_sm_dna` fixture predates the
writer's fix and stores *exclusive* stops, so it agrees with a buggy reader —
a guardrail needs the PARIS folder or a freshly written table.

The live engine’s `burst_search` intervals are inclusive too, independently of
legacy table conventions. `burst_filter` converts those stops to exclusive
stops only when calling the generic half-open mask helper. The non-burst IRF/
background selection is the complement of the union of complete intervals,
including terminal photons and overlapping bursts. Actual BH174438 photons
with L60/m10/1ms produce91 intervals and remove88 leaked endpoints after overlaps;
all raw arrays and clock values remain unchanged. The verified source is
uncommitted; [owner acceptance](../validation/release-readiness-w6g/burst-mask-owner-acceptance.json)
records SDK/source hashes, physical masks and the loopback workflow test gate.

# Related

* [/plugins/burst.md](../plugins/burst.md) — the burst workflow and its steps.
* [/subsystems/data-io.md](data-io.md) — the wider file-reading layer.
