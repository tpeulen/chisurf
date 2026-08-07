---
type: Subsystem
title: The photon container — one measurement, one file
description: How ChiSurf writes and reads .pto containers under the PTO.MFDB profile — the instrument file kept verbatim and immutable at the front, results as artifacts beside it, and every name taken from the mmCIF dictionaries.
resource: chisurf/core/fio/pto.py
tags: [data-io, pto, mfdb, provenance, container]
timestamp: '2026-08-06T00:00:00Z'
---

# Where to pick this up

1. **Stages 3 and 4 are done; three writers are left, and they are the odd
   ones.** Every burst analysis and every imaging tool writes into the
   measurement's container. What remains is
   `tttr/{tttr_time_windows,trace_browser,intensity_trace}` — browsers rather
   than analyses, whose output is a *view* of the photons (a time window, a
   binned trace) rather than a result derived from them. Decide first whether a
   saved view is an artifact at all, or a setting; the grain would be `segment`
   for a time window and `curve_point` for a trace.

   The seams are `chisurf/core/fio/fluorescence/burst_container.py`
   (`write_burst_artifact` for one measurement, `write_per_source` for a table
   covering several) and `imaging_container.py` (`write_imaging_table`,
   `write_image`). Every migrated writer is one call to those.

   **The container path is written *beside* the legacy one, never instead.**
   Switching the default over — and retiring `<source>.imaging.h5`, the `…4`
   directories and the seven scattered exports — is a separate, deliberate step,
   and the one that needs the legacy baselines below.

   **Three defects the migration itself exposed. All fixed; all worth knowing
   because the same shapes will recur:**

   * *Replacing was keyed on the run, not on the output.* `_find_run` matched on
     (operation type, artifact kind, settings hash). One run routinely writes
     several artifacts of one kind — an MLE fit writes one table per detector,
     all `fit_result`, all one settings hash — so each `put_table` found the
     previous one and overwrote it, and a three-detector analysis ended with one
     table. Silent, because replacing is the *intended* behaviour and nothing
     distinguishes it from the collision. The object's name is now part of the
     key. **A writer emitting more than one artifact per run must give them
     distinct names.**
   * *A relocated result corrupted the container.* Growing a result past its
     reserve relocates it; the freed run is one `Void`, and the next element
     written into that hole carved its front without re-heading the remainder,
     leaving the old payload's tail undeclared. Every `put_table` writes tags
     straight afterwards, so an ordinary re-run with a bigger result destroyed
     the file — and only on the *next* open, which is why tttrlib's existing
     "the space a moved object left is reused" test passed either way: it never
     reopened. Fixed in `allocate`/`allocate_aligned` (tttrlib `12a8e6ba`);
     the guard here is `test_replacing_a_result_leaves_the_container_readable`.
   * *Units matched on the whole column name matched nothing.* Every imaging
     column is suffixed with the channel it came from — `N (ch0)`,
     `Mean Micro Time (green)` — so an exact-match table silently produced a
     unitless file, "no unit" and "unknown unit" being written the same way.
     `ImagingMapViewModel.COLUMN_UNITS` matches by **prefix**; the MLE writer
     has the same rule for `Tau S0 (red)`. Found by reading the output, not by
     a test passing.

   **Four read-side gaps closed, all one shape — a writer with no reader.**
   `get_store` (a unit is an attribute of the *column*, so `get_table`'s frame
   is the one shape of a table that cannot carry one), `column_units`,
   `column_item`, `get_blob`. **When adding a writer, add its reader in the same
   change** — this kept recurring because writing is where the design attention
   goes.

   **Two traps in the seam itself:**

   * `Measurement.close()` does **not** commit. `Measurement.create(x).close()`
     writes the README and the source and then drops both, and the container
     comes back holding only what was added afterwards. Use it as a context
     manager.
   * `deinterleave_bursts` detects the `.bur` padding by looking for all-zero
     even rows, so a caller that has *tagged* the table with a constant column
     (a source filename, a BID index) has filled the padding rows too and the
     heuristic correctly concludes there is none. A caller that asked for the
     padding knows it is there and should say so rather than let it be detected
     — see `bid_to_analysis._write_container(interleaved=...)`.

2. **Capture the legacy baseline BEFORE touching each writer.** Once a writer is
   changed its output is unrecoverable and the migration cannot be reviewed by
   anyone later. The recipe is the one used for `burst_selection`: drive the
   headless API with the legacy flag, record every path with its size, sha256
   and text, plus the column inventory, and store it under
   `test/data/baselines/`. Judge parity on **columns, not bytes** — the
   container deliberately stores a table where the folder stored a padded text
   grid.
3. **The interleave is a file-format artifact and must not travel.** A `.bur`
   holds `2N+1` rows — a zero row, a burst, a zero row — because companions are
   merged by *counting*, and it carries a nameless trailing column to produce
   the header's trailing tab. Both leak into the in-memory frames the analyses
   pass around. `deinterleave_bursts` in `burst_container.py` strips them and
   `write_burst_artifact` calls it, so a writer that goes through the seam is
   safe; one that reaches past it is not, and a placeholder row silently
   destroys the information that a burst was absent. The trap is that the frame
   *looks* like data.
4. **`export_seidel` is not written yet.** It is `PtoFile.disassemble()` plus
   the existing `burst_companion.write_companion` — it must go through that
   function and never hand-roll the `2n+1` interleave, which is the mistake
   four current writers make. It is **lossy by construction** for anything not
   at burst grain and must say so.
5. **`read_bur_with_companions` has no PTO branch yet.** That is the single
   seam `burst_browser` and ndX read through, so adding it there gives both
   PTO support without touching either.
6. **Streaming landed in the library** (tttrlib PRD-020): `add_file`,
   ranged reads, row windows and cues. The seam already prefers `add_file`, so
   embedding no longer holds a file in memory — the known-issues note for it is
   closed.

# What it is

`chisurf/core/fio/pto.py` is the only code that writes or reads a photon
container. A plugin never touches `tttrlib.PtoFile`, so no writer has to
remember the conventions and there is one place to change them.

The normative rules are the [PTO.MFDB profile](/specs/pto-mfdb.md). The
container beneath it is PTO, specified in tttrlib and **frozen** — nothing here
adds an element or changes framing.

| Concern | Where |
| --- | --- |
| The profile | [`okf/specs/pto-mfdb.md`](/specs/pto-mfdb.md), generated to `modules/tttrlib/doc/formats/pto-mfdb.rst` |
| The container | `modules/tttrlib/doc/formats/pto.rst` |
| The vocabulary | `mmfdb_flr_ext.dic`, plus `mmfdb_workflow_ext.dic` for the serialisation-only container terms |
| The seam | `chisurf/core/fio/pto.py` |
| The reading seam | `chisurf/core/fio/staging.py::open_tttr` |
| Tests | `test/fio/test_pto.py` |

# Three things that decide the design

**The instrument file is the truth.** It is embedded verbatim as the *first*
object and never rewritten, so its offset is stable for the life of the file and
no recomputation can move it. It is not decoded into a second copy beside
itself — `tttrlib.TTTR` reads it in place — so a container is the size of the
raw data plus the results, not twice the raw data. `extract()` puts it back
byte-for-byte and verifies the recorded SHA-256 while doing it; a mismatch
raises rather than returning a plausible file.

**Nothing is joined by position.** Every table declares
`_mmfdb_artifact.row_grain` — what one row *is* — and a relation names its key
columns. This is what the `…4` companion format could never express, and both
of its known failures are the two directions of that hole: an H2MM dwell is
*finer* than a burst (so its results ended up in five files outside the
companion system), and a fused burst is *coarser* and has several parents (so
burst fusion writes `fg4/` back into the source analysis's directory). Neither
is reproduced here. A skipped row is **absent**, not a sentinel.

**Re-running replaces.** The identity of a run is
`_mmfdb_operation.settings_hash`. The same settings rewrite the artifact in
place — which is what PTO's in-place update is for — and different settings
produce a new one. Without this a container accumulates one object per run,
which is the directory sprawl it replaces, moved inside a single file.

# The vocabulary is not ours

Tag names **are** mmCIF item names, and every controlled value is an
enumeration term. A term that is not in the dictionary is refused at write time
rather than producing an unqueryable file, and
`test_every_written_term_resolves_in_the_dictionary` walks a produced container
back against the dictionaries so the profile cannot drift into a private
namespace. Anything ChiSurf needs a word for gets one added to
[MMFDB](/architecture/mmfdb.md) first.

Every container records the four versions that can drift independently — the
container format, the profile, the dictionary (version *and* content hash), and
the writing application — so a later disagreement can be diagnosed instead of
silently mis-binding a renamed item.

# What it replaces

Three rival containers, none of which covered everything: the positional `…4`
companion directories, `<source>.imaging.h5` (one pixel table per source file,
unable to hold a curve, a field, a stack or a non-pixel table), and `.csp`,
which imaging never touched. `.csp` stays as the project archive and
*references* containers; `.imaging.h5` is retired.

See also [burst companions](/subsystems/burst-companions.md) for the legacy
layout that remains readable, [data IO](/subsystems/data-io.md), and the
[columnar store](/subsystems/columnar-store.md) that carries every tabular
payload.
