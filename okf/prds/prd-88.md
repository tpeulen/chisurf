---
type: PRD
prd: "88"
title: "PRD-88: Every provenance graph reconstructs — the source/sink matrix, and the chains between them"
description: A container's provenance is only worth having if it reaches the primary data from every artifact in it. That is a property of the whole graph, and it was being tested on one synthetic two-step chain. This defines the matrix — every photon source, every writer, and the nested chains they form — and the tests that walk it.
status: planned
phase: "audit run (6 of 26 artifacts broken, 4 fixed); harness and matrix open"
resource: test/fio/test_pto.py
tags: [prd, provenance, pto, mfdb, testing, data-io]
timestamp: '2026-08-07T00:00:00Z'
---

# Where to pick this up

1. **The audit exists and is throwaway.** The script that produced the numbers
   below lives only in a scratch directory; the first task is to make it a test.
   It drives each real writer against real data and asks, of every artifact left
   behind, whether it names its operation, its settings and its parents, and
   whether `lineage()` terminates at the primary data.

   **2026-08-10 — the audit is a test now, in two files, and widening it found
   things both times.** `test/fio/test_container_cross_writer.py` covers the
   writer this PRD did not know about (see *The 21st writer*).
   `test/fio/test_provenance_matrix.py` covers the source axis and the **nested
   chains**, which had no coverage at all — depth 4, fan-in, siblings,
   `calibrated_by` as a second relation, extend-after-reopen, re-run, and the
   no-primary case. Its `_walk_every_artifact` collects one complaint per
   artifact rather than asserting on the first, so a run says everything wrong
   with a container at once; that is the shape the remaining cells should reuse.

   **What widening found this time: the vocabulary was not being enforced on the
   compiled writer.** ChiSurf's `put_table` checks every term against the
   dictionary before writing, so a ChiSurf writer *cannot* invent one — and every
   `operation_type` in the tree is a declared term. The `tttr` CLI makes no such
   check (it is C++, does not link mmfdb, and has no mmCIF parser), and it had
   been emitting **four undeclared terms**: `bva`, `kde_cde` and
   `mle_<detector>` for operations the dictionary calls
   `burst_variance_analysis`, `burst_2cde` and `burst_lifetime_fitting`, and
   `companion_of` for a relation `_mmfdb_edge.relationship_type` does not define
   at all. Every container the CLI has written carries them.

   Fixed in tttrlib, and the check now lives on this side —
   `test_every_term_the_cli_writes_is_in_the_dictionary` — because this is the
   only side that can read the dictionary. Two smaller consequences: the
   cross-writer test's own rule-3 assertion had been *accepting* `companion_of`,
   so it passed on exactly what it existed to catch; and ndX's
   `_COMPANION_TYPES` was a list of informal spellings no writer produces, which
   is a silent fallback that would have stopped working the moment a parent edge
   went missing.

   **The pattern, third time today:** a term, a unit or a name that one side
   invents and the other side never checks. The fix is always the same shape —
   put the check on the side that owns the vocabulary, and drive the other side
   through it.
2. **Two known-incomplete cells remain** (below). Neither is a mystery; both
   need a decision rather than an investigation.
3. **Nested chains are the part with no coverage at all.** Every case tested so
   far is one or two steps. The interesting failures are at depth and at
   fan-in — see the chain table.

# Purpose

`Measurement.lineage()` reconstructs the path from any artifact back to the
primary data. Whether it *can* is a property of the graph a writer leaves
behind, and the graph is written by ~20 independent writers against a dozen
kinds of source.

Testing that on one synthetic two-step chain — which is what was there — proves
almost nothing. The audit below is why: it took an hour to write and found a
defect that had been invisible through the whole migration.

# What the audit found

26 artifacts across 11 writers, driven against real instrument files.
**6 had a broken or incomplete lineage.**

Four of the six were one root cause: `instrument_uid` was recovered on `open()`
by matching a single artifact kind, `tttr_photon_stream`. A container whose
source is *not* photons — ebFRET starts from binned traces, and `create` takes
an `artifact_kind` precisely so a `.dat` is not called a photon stream — came
back with no primary. A writer passing `derived_from=()` falls back to the
primary, so with none it recorded **no parent at all**, and everything written
after it chained to a sibling instead of to the data.

The property that made it invisible is worth stating, because it will recur: a
writer that *creates* the container in the same call has the uid from `create`
and never asks again. It only shows on **reopen** — which is what a second
analysis on the same measurement does, and what no test did. Fixed in
`994e222f0`.

The remaining two are decisions, not bugs:

| cell | state | the decision |
|---|---|---|
| `img_tracking` | not exercised | no fixture drives it; either add one or state that the writer is unreachable from a test and say why |
| a standalone curve | no parent, no settings | a curve typed in or computed from a model genuinely has no measurement behind it, and `create_empty` makes a container with no primary. **Is a container with no primary well-formed?** If yes, the test needs to distinguish "legitimately primary" from "lost its parent" — they look identical today |

# The 21st writer — one that is not in this tree

**Found 2026-08-10.** The sink table below lists ~20 writers and every one of
them is ChiSurf. There is another: the compiled `tttr` CLI in the tttrlib
repository writes burst tables and their companions into the same containers,
through the C++ half of the same profile. It is not in the matrix, nothing
tested it, and it reproduced this PRD's own root cause independently —

> a writer that *creates* the container in the same call has the uid from
> `create` and never asks again; it only shows on **reopen**

— in its own idiom. The CLI looked its primary up **by file name**, so a
container ChiSurf had already created was extended with a *second*
`tttr_photon_stream` whenever the name did not match: two roots, with the CLI's
burst table hanging off the one nothing else references. Reading the container
looks completely intact until somebody walks the lineage of an artifact the
*other* tool wrote. The lookup is now on `_mmfdb_artifact.checksum`, so a
byte-identical file under any name resolves to the primary already there, with
the name only as a fallback for a container written before the checksum tag.

Two more, fixed in the same pass, both of which this PRD's rules would have
caught had the writer been in the matrix:

- **The container held a lossy re-encoding of the measurement.** The CLI wrote
  the *channel-filtered* stream back out as a `.sm` — other channels gone,
  vendor header gone — in the one place the profile promises is verbatim. It
  now embeds the original file unchanged with a SHA-256, verified byte for byte,
  and is smaller for it.
- **A companion's run identity did not include its parent's.** Keyed on its own
  settings alone, a BVA table computed over one burst list was silently
  overwritten by a BVA table computed over another; the row counts still line up
  whenever the two searches happen to find the same number of bursts (rule 6).

**The lesson for the rest of the matrix:** a writer outside this repository is
still a writer, and the profile is the contract, not the Python API. The same
applies to anything else that learns to write these files.

# The matrix

## Sources — what a container can be *about*

Each needs one container built from it, reopened, and walked.

| source | kind | notes |
|---|---|---|
| PTU / PHU | `tttr_photon_stream` | the common case |
| HT3 / HT2 / PT3 / PT2 / T3R | `tttr_photon_stream` | |
| SPC-130 / SPC-600 | `tttr_photon_stream` | **carries a `.set` sidecar** — the sidecar's own edge is part of the graph |
| Photon-HDF5 | `tttr_photon_stream` | |
| CZ-RAW, SM | `tttr_photon_stream` | reader exists; no fixture yet |
| binned traces (`.dat`) | `trace_data` | ebFRET; the cell that broke |
| a TIFF stack | `image_data` | FRC, drift, coloc, tracking read images directly |
| a simulated stream | `tttr_photon_stream` | `clsm_generator`, `img_flow`'s demo, `burst_fusion`'s demo — a *generated* source is still a source |
| an existing `.pto` | — | reopening must find the same primary as `create` did. **This is the case that was broken** |
| no source at all | — | `create_empty`; see the open decision above |

## Sinks — every writer, and how many artifacts each leaves

Verified `ok` unless noted. The count matters: a writer emitting several
artifacts is where the run-key collision lived, and where a chain forks.

| writer | artifacts | grains |
|---|---|---|
| `burst_selection` | 1 | burst |
| `burst_mle_analysis` | 2 + detectors | burst, state, curve_point |
| `burst_fcs_correlator` | 1 | burst |
| `burst_h2mm` | 2 | burst, dwell |
| `burst_gs` | 3 | state, pair, photon |
| `burst_ebfret` | 3 | state, pair, dwell |
| `burst_fusion` | 2 | burst + a row mapping, **many parents** |
| `burst_bva`, `burst_2cde` | 1 each | burst |
| `accurate_fret` | 2 | burst, species |
| `burst_background` | 1 + detectors | channel, curve_point |
| `bid_to_analysis` | 2 | burst + the `.bid` blob |
| imaging per-pixel (`nb`, `phasor`, `micro_time`, `intensity`, `mle`) | 1 each | pixel |
| `img_drift` | 2 | frame + a raster |
| `img_frc` | 1 | curve_point |
| `img_flow` | 2 | pixel + a raster |
| `img_tracking` | 2 | track, spot | **not exercised** |
| `sm_image_mle` | 1 | molecule |
| `clsm_generator` | 1 | a raster |
| a `DataCurve` | 1 | curve_point | **no parent** |

# Nested chains

The gap with no coverage. Each row is one container built by running the real
writers in sequence, then walked from the deepest artifact.

**Covered as of 2026-08-10** by `test/fio/test_provenance_matrix.py`: depth-4
(photons → bursts → per-burst fits → pooled states), fan-in through fusion *and*
something derived from the fused result, four siblings on one parent,
`calibrated_by` as a second relation type, a non-photon source, a sidecar-carrying
`.spc`, extend-after-reopen across three separate opens, a re-run that must not
orphan its children, and the duplicate-parent case. Still uncovered: the imaging
chains (a raster in the middle, crossing into the curve seam) and anything
driven through the actual analysis plugins rather than through `put_table`.

| chain | depth | what it exercises |
|---|---|---|
| photons → bursts → MLE fits → pooled state lifetimes | 4 | a fork: several detector tables share one parent, and the state table depends on all of them |
| photons → bursts → H2MM → dwells | 4 | a finer grain carrying its parent's key |
| photons → bursts ×2 → **fusion** → fused bursts → BVA | 5 | **fan-in**: two independent selections feeding one result, then something derived from *that* |
| photons → bursts → {BVA, 2CDE, FCS, MLE} | 3, ×4 | siblings on one parent; each must reach the photons independently |
| photons → background → MLE (background as a *calibration* input) | 3 | a second relation type — `calibrated_by`, not `derived_from` |
| traces → ebFRET states → {transitions, dwells} | 3 | a non-photon source with a fork |
| image → drift → corrected raster → per-pixel maps | 4 | a raster in the middle of a chain |
| photons → pixel maps → molecules → an exported curve | 4 | crossing from imaging into the curve seam |
| a `.pto` reopened, then extended twice by different tools | 3+ | **the reopen path**, which is where the found defect lived |

# Rules the tests must pin

1. **Every artifact reaches the primary data**, or is *declared* primary. The
   two are indistinguishable today and must not be.
2. **Every derived artifact names its operation and its complete settings.** A
   partial settings record is worse than none — it looks reproducible.
3. **The relation is a term**, not a UID and not empty. This was wrong for
   every artifact until 1d3e77fb0, and nothing noticed because the value was
   read back as an integer without complaint.
4. **A fan-in keeps every parent.** Fusion is the case; the arity was
   unexpressible in the format this replaces, so there is no legacy behaviour
   to fall back on.
5. **A chain survives a reopen.** Build, close, reopen, extend, walk. Most of
   the found defects are only visible across an open.
6. **A re-run does not orphan anything.** Replacing an artifact in place must
   leave the artifacts derived *from* it still pointing at it.
7. **The walk terminates.** A cycle is possible to write and would hang
   `lineage()`; the audit script does not guard it.

# Steering notes

- **Drive the real writers, not synthesised tags.** The defect found was in
  what a writer *records*, and a test that builds the graph by hand records what
  the test author believes rather than what the code does.
- **The audit is cheap and finds things.** It is ~200 lines and found a defect
  the whole migration missed. Prefer widening it over deepening any single case.
- **A missing fixture is a finding, not a skip.** `img_tracking` and the
  CZ-RAW/SM readers have no data to drive them; that is worth saying out loud in
  the test output rather than quietly passing.
