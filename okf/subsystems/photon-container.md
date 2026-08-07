---
type: Subsystem
title: The photon container — one measurement, one file
description: How ChiSurf writes and reads .pto containers under the PTO.MFDB profile — the instrument file kept verbatim and immutable at the front, results as artifacts beside it, and every name taken from the mmCIF dictionaries.
resource: chisurf/core/fio/pto.py
tags: [data-io, pto, mfdb, provenance, container]
timestamp: '2026-08-06T00:00:00Z'
---

# Where to pick this up

1. **Three writers migrated, ~11 to go.** `burst_selection` (`output_formats`
   contains `"pto"`), `burst_bva` (`write_bva_container`) and `burst_fusion`
   (`write_fusion_container`). The shared seam is
   `chisurf/core/fio/fluorescence/burst_container.py` — `write_burst_artifact`
   for one measurement, `write_per_source` for a frame covering several. Every
   remaining writer is one call to those, so the work is now reading each
   plugin rather than designing anything. Next: `burst_2cde` (identical shape to
   BVA), then `burst_mle_analysis` (three colour tables plus per-state
   lifetimes), `burst_h2mm` (dwells at their own grain), `burst_fcs_correlator`,
   `bid_to_analysis` and `burst_analysis` (both duplicate `burst_selection`'s
   `bi4_bur/` writer and collapse onto `write_container`).

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
   the header's trailing tab. Both leak into the in-memory frame that
   `analyze_file` returns. `deinterleave_bursts` in the plugin's `api/io.py`
   strips them; anything else writing a burst frame into a container must do the
   same, or a placeholder row silently destroys the information that a burst was
   absent. The trap is that the frame *looks* like data.
3. **`export_seidel` is not written yet.** It is `PtoFile.disassemble()` plus
   the existing `burst_companion.write_companion` — it must go through that
   function and never hand-roll the `2n+1` interleave, which is the mistake
   four current writers make. It is **lossy by construction** for anything not
   at burst grain and must say so.
4. **`read_bur_with_companions` has no PTO branch yet.** That is the single
   seam `burst_browser` and ndX read through, so adding it there gives both
   PTO support without touching either.
5. **Embedding a multi-gigabyte file still reads it into memory** — tttrlib has
   no streaming `add_file`. The exact fix is in
   [known issues](/references/known-issues.md); the seam already prefers
   `add_file` when the library offers it, so nothing here changes when it lands.

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
