---
type: PRD
prd: "96"
title: "PRD-96: fpsimp is a consumer, not a second implementation — fluorescent-protein sampling into imp.bff"
description: fpsimp already drives IMP for FP sampling and carries its own copy of the FP-domain detection and FP library, which have drifted. Under the settled boundaries that work is imp.bff's; fpsimp becomes a consumer, keeping the pipeline, the web UI and the ColabFold integration that are genuinely its own.
status: draft
phase: "scoped and measured; nothing moved yet"
resource: /Users/tpeulen/dev/fpsimp
tags: [prd, scope, architecture, imp.bff, fpsimp, fluorescent-proteins, duplication]
timestamp: '2026-08-10T00:00:00Z'
---

# Where to pick this up

Nothing has moved. This is the scope and the measurement; the first stage is
small and unblocked.

The one-line summary: **`fpsim/sampling.py` already calls IMP**
(`run_imp_sampling`, 402 lines), and FP sampling takes coordinates as input, so
by the placement rule in
[references/imp-ecosystem](/references/imp-ecosystem.md) it is imp.bff's. What
fpsimp keeps is what only it does — the pipeline, the ColabFold integration, the
worker and the web UI.

# Why this is not a tidiness exercise

The two trees already hold the same code twice, and the copies have drifted.
Measured 2026-08-10:

**`segments.py` — four shared functions.** `find_fp_domains`,
`parse_plddt_from_pdb`, `segments_from_plddt` and `_align_best_window` exist in
both `imp.bff/pyext/src/cgdye/sampling/segments.py` (217 lines) and
`fpsim/segments.py` (371 lines). This is FP-domain detection from pLDDT plus a
local alignment — one algorithm, two maintained copies.

**And they have already diverged in a way that costs something.** The imp.bff
copy no longer needs Biopython: `_align_best_window` runs on an in-tree
Smith-Waterman (Gotoh, affine gaps, verified identical to `PairwiseAligner` on
40/40 randomised sequence pairs). fpsim's copy still calls Biopython — `Bio`
appears **11 times** across `fpsim/` — and will not receive that work. A fix
applied to one copy of a duplicated algorithm is a fix the other copy does not
get; that is the whole cost of duplication, made concrete.

**`fp_library.json` — drifted.** imp.bff ships 4 fluorescent proteins (eGFP,
mCherry, mScarlet, mTurquoise2); fpsim ships 5, adding **mStayGold**. The four
shared entries are byte-identical, so this is not a fork with different physics
— it is the same table, one copy of which was updated. imp.bff's is simply
stale.

**`fp_lib.py` — same data, two APIs.** No function name is shared:
imp.bff has `load_fp_library` / `get_fp_data` / `get_fp_names`, fpsim has
`get_fp_library` / `init_default_fp_library` / `load_fp_library_json`. Two
accessors over one table.

**fpsimp is already an IMP consumer**: 17 `IMP` imports and 3 `RMF` across
`fpsim/`, in `sampling.py`, `density.py` and `measure.py`. This is not a
proposal to make fpsimp depend on IMP — it already does. It is a proposal to
stop it re-implementing the parts imp.bff owns.

# Where the line falls

| stays in fpsimp | moves to imp.bff |
|---|---|
| `pipeline.py` — the orchestration | `sampling.py` — `run_imp_sampling` and the topology parsing it drives |
| `colabfold_utils.py`, `worker/`, `webui/` — structure prediction and the service around it | `segments.py` — FP-domain detection, pLDDT parsing, alignment |
| `measure.py`, `parameters.py`, `parameter_catalog.json` — the measurement/reporting layer | `fp_lib.py` + `fp_library.json` — the FP table and its accessor |
| `plddt_guard.py` if it is about accepting a prediction | `topology.py`, `density.py` — if they are structure/AV work rather than pipeline glue |

The right test for each file is the placement rule, not the filename: *what is
the input?* Coordinates → imp.bff. A prediction job, a queue, a request →
fpsimp.

# Stages

**Stage 1 — kill the `segments.py` duplication (unblocked, small).** fpsim
imports the imp.bff copy and deletes its own. This is a strict improvement the
day it lands: fpsim loses 11 Biopython call sites, and both trees get the
Smith-Waterman that was verified against Biopython rather than one tree keeping
the dependency. Check first that fpsim's 371-line copy has no behaviour the
217-line one lacks — the shared names match, but the line counts do not, and the
difference has not been read.

**Stage 2 — one FP library.** Move `mStayGold` into imp.bff's
`data/cgdye/fp_library.json`, settle on one accessor API, and have fpsim import
it. Two accessors over one table is a coin flip about which is authoritative;
today it is resolved by which repository you happen to be in.

**Stage 3 — `run_imp_sampling` moves.** The largest piece and the one that needs
a design conversation rather than a diff: it is 402 lines that read a topology
file, build an IMP system and sample it, and imp.bff already has its own
sampling under `cgdye/sampling`. Whether these merge or sit side by side is the
same question stage 3 of [PRD-93](prd-93.md) asks about the two AV
implementations, and it deserves the same answer: **measure before merging.**

**Stage 4 — fpsimp declares the dependency.** `imp.bff` in its
`environment.yml`, and its OKF records that FP sampling lives upstream.

# Decisions still open

1. **Does `topology.py` / `density.py` move?** They import IMP and look like
   structure work, but they may be pipeline glue holding a specific file format.
   Read before deciding.
2. **Does fpsimp keep its own OKF bundle?** It has one
   (`fpsimp/okf/`, with architecture, computations, subsystems, workflows).
   tttrlib's precedent says yes — a repo with a substantial domain of its own
   keeps its bundle and points cross-project findings at
   [chisurf/okf](/index.md). fpsimp's pipeline and service layer qualify.
3. **matplotlib.** fpsim imports it 5 times. If any of that is in code moving to
   imp.bff, it does not come along: plotting belongs in the application layer,
   and imp.bff's dependencies are IMP, numpy and click.

# Definition of done

* No function exists in both `fpsim/` and `imp.bff/pyext/src/`.
* One `fp_library.json`, in imp.bff, containing every FP either tree had.
* `fpsim` imports IMP.bff for FP sampling and domain detection, and declares it.
* Biopython is gone from fpsim, as it is already gone from imp.bff.

# What this does not touch

fpsimp's reason to exist — predicting structures with ColabFold, running them
through a pipeline, and serving the results — stays exactly where it is. This
PRD is about the ~800 lines in the middle that are fluorescence-structure work
imp.bff already does, not about the project around them.

# Note from imp.bff (2026-08-17, PRD-107)

`imp.bff/pyext/src/cgdye/sampling/segments.py` and `sampling/fp_lib.py` are
left as they are (used only by `dye label-fusion`), with headers pointing here:
they are fpsim copies and are not extended in imp.bff.
