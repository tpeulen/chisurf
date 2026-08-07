---
type: Subsystem
title: The photon container — one measurement, one file
description: How ChiSurf writes and reads .pto containers under the PTO.MFDB profile — the instrument file kept verbatim and immutable at the front, results as artifacts beside it, and every name taken from the mmCIF dictionaries.
resource: chisurf/core/fio/pto.py
tags: [data-io, pto, mfdb, provenance, container]
timestamp: '2026-08-06T00:00:00Z'
---

# Where to pick this up

**A container is addressed like a folder, and that is one scheme.**
`chisurf.core.fio.analysis_path` is the only place that knows the grammar
(`m000.pto/countrate_All 0.2000#60`), and it is deliberately not about bursts —
`read_tables` / `write_tables` / `list_runs` / `export_tree` are what a tool
calls instead of sniffing for a suffix. Three plugins had grown their own `.pto`
branch before it, each with its own idea of which of several analyses it meant.
A run is named inside the container exactly as the folder layout names its
directory, so the two layouts are the same thing seen from either side.

Consequences worth not re-deriving:

* **Unpacking is the whole conversion.** `extract` returns the instrument files
  byte for byte *and* one folder per analysis as CSV. `disassemble` writes only
  what the container was packed from — it had been dumping the analysis blobs
  beside the vendor file, producing a file named `bursts` that nothing opens.
* **Inside, the tables are binary columns**; text is for leaving. That is what
  makes opening a container of many analyses cheap.
* **`Measurement._resolve` accepts a bare table name.** `get_store("bursts")`
  still finds `"<run>/bursts"`, which is what keeps every caller written before
  runs existed working.
* **`disassemble` creates the directories a name implies.** tttrlib's writer
  takes an object name as a relative path but does not make its parents, so the
  first name with a slash in it fails; filed in tttrlib's `BUGS.md`.


0. **An end-to-end run on 2026-08-07 (ten `.spc` → one `.pto` → burst search →
   ndX, plus a CLSM `.ptu` → `.pto` → imaging) found four container-level
   faults. Three are fixed; the fourth is upstream.** They are listed first
   because each one is invisible from the result and each was found by *reading
   the file*, not by a test failing.

   * **A merged measurement recorded one parent.** `instrument_uid` is the
     *first* photon stream, and `write_burst_artifact` used it — so a burst
     table computed from ten streams named `m000.spc` alone and nine sources
     were unreachable from it. `Measurement.instrument_uids` (all of them) is
     the fix. Re-derive with `describe_lineage`: it printed
     `derived_from m000.spc` and now prints all ten.
   * **Tags are appended, never replaced, so parent edges accumulated.** Three
     re-runs left the same uid recorded four times, because a re-run updates
     the table *in place* and re-describes it. `_describe` dedupes against
     `parents(uid)` now. **Suspect the scalar tags too** — an object described
     three times may hold three `row_grain` values with readers taking the
     first; not yet measured.
   * **A GUI class name reached the file format.** Imaging tools without a
     `WINDOW_KIND` fell back to `type(self).__name__`, so the intensity map was
     stored as `IntensityViewModel`. `ImagingMapViewModel.artifact_name()` makes
     it `intensity`. Renaming a Python class must not rename an artifact in
     every file already written.
   * **Nothing distinguishes two runs of the same analysis to a reader.**
     Changing a setting adds an object rather than replacing one — deliberately
     — and every one of them is called `bursts`. A reader doing the obvious
     thing (read them all, concat) lines up 4621, 2318 and 1099 rows against
     each other and pads. ndX's new `.pto` reader works around it by taking the
     last object of the right `operation_type`; that leans on `objects()`
     returning write order, which the container does not promise. Filed in
     tttrlib's `BUGS.md` — a `superseded_by` edge or a `current` flag is what
     would remove the guesswork. `Measurement.metadata()` also comes back `""`
     for a container written by `create()`.

   Also confirmed clean, so it is not re-derived: **the `.pto` round-trip is
   exact for CLSM markers** — `Leica_SP5.ptu` packed and read back gives
   byte-identical event types, marker counts and `CLSMImage` geometry. The
   `no complete frames; salvaging …` warning that comes with it is a
   `CLSMImage` marker-configuration matter and the raw `.ptu` shows it too.

1. **The provenance graphs are NOT all verified — [PRD-88](/prds/prd-88.md)
   owns that.** `build_tools/dev_utils/lineage_audit.py` drives the real writers
   and reports every artifact that cannot reach the primary data. Run it before
   trusting a new writer:

   ```
   QT_QPA_PLATFORM=offscreen python -m build_tools.dev_utils.lineage_audit
   ```

   It stands at **25 artifacts, 2 incomplete** — `img_tracking` has no fixture,
   and a standalone curve legitimately has no measurement behind it. **Nested
   chains have no coverage at all**; the chain table in the PRD is the worklist.

   The defect it found is the shape to expect: `instrument_uid` was recovered on
   reopen by matching a single artifact kind, so a container whose source is not
   photons had no primary, and writers falling back to it recorded no parent.
   **Invisible except across an open** — a writer that creates the container in
   the same call never asks again.

2. **Derivatives go into the measurement's `.pto`, and the provenance has to
   reconstruct the path back to the primary data.** Stated as an objective:
   "when there is a .pto file the derivatives must end up in the .pto (with
   according provenance data, for reconstruction of the path). the provenance
   must contain all settings how the derived data relates to the primary data."

   Every writer goes through `container_for` / `open_measurement`, so an
   existing container is always the target. What each writes is checked by
   `test_every_derived_object_in_a_real_container_can_be_traced`.


3. **`.pto` is now the default, and that is a user objective rather than a
   preference** — "in the end .pto (mfdb) should be the main filetype for tttr
   data in chisurf (this is objective)". A vendor file is an *import source*:
   `staging.import_measurement` turns one into its container, leaving the
   original untouched, and `AnalysisSettings.output_formats` defaults to
   `["pto"]`.

   **Opening a file creates nothing.** `onLoadSample` calls
   `import_measurement(create=False)`: it prefers an existing container and
   otherwise reads the vendor file where it lies. Importing on *open* wrote a
   `.pto` into the repo's own test-data directory, and handed the reader the
   caller's `file_type="bh132"` — which no longer described the path. Someone
   browsing a colleague's folder has not asked for a file to appear in it. The
   container is created when there is a **result** to put in it, which is where
   every writer already does it.

   **What the flip broke, and it is the shape to expect again:** three callers
   *consume* a `.bur` they had been getting for free — `burst_fusion`'s demo
   (the tool reads a `bi4_bur/` folder; that is what it is *for*),
   `burst_analysis`'s workflow API (hands back `roles["bur"]`), and the tests
   that exercise the legacy reader. Each now asks for `["pto", "bur"]`
   explicitly, which is the honest statement. Before flipping any other
   default, grep for who reads the legacy artifact rather than who writes it.

   **The file dialogs were the invisible half.** Every one of them listed the
   vendor formats and not `.pto`, so the format ChiSurf produced was the one
   format its own Open dialogs hid. `staging.TTTR_FILE_FILTER` is now the single
   definition and `test/test_pto_is_the_default.py` fails on any dialog that
   names a vendor photon format without the container. The guard was worth
   writing: it found **eight** more dialogs after the ones found by hand.

4. **Provenance has to reconstruct the path, and a writer that records partial
   settings breaks that silently.** Every derived object carries three tags:
   `_mmfdb_edge.source_node_id` (one per parent), `relationship_type` (a term,
   plus the join columns when grains differ), and `operation_type` with the
   **complete** `settings_json`. `Measurement.lineage()` walks to the instrument
   file; `describe_lineage()` renders it.

   **The trap that produced this:** `source_node_id` exists in the database
   schema and was never declared in the dictionary, so the writer put the parent
   UID under `relationship_type` — and the relation was never recorded at all,
   while `tag(uid, relationship_type)` returned an integer. Fixed in
   `mmfdb_flr_ext.dic` 1.7; `parents()` reads both spellings so older containers
   still resolve. **When a tag's value looks like the wrong type, check the
   dictionary before the writer.**

   A partial settings record is worse than none — it looks reproducible. The
   test walks a *real* container, not a synthesised one, so a writer that
   forgets fails there.

5. **Formats are consolidated by *direction*, and that is the rule to keep.**
   Readers are free — an instrument writes one format and a collaborator's
   software another, and ChiSurf reads about a dozen curve formats, six of which
   cannot write at all. Writers are **one per kind of thing**: a measurement is
   a `.pto`, a curve is a `curve_point` artifact, a table is an artifact at its
   grain, a raster is a TIFF carried inside, a project is a `.csp`, deposition
   metadata is mmCIF. Everything else is an import source or an export the user
   asks for by name.

   `Measurement.put_curve`/`get_curve` is the curve seam, and `DataCurve.save`/
   `load` route through it. `test/test_formats_are_consolidated.py` holds a
   **shrinking** allow-list of modules still permitted to write a curve their
   own way — and pins that the *reader* count must not shrink, so the guard can
   never be satisfied by deleting import paths.

   **What is left here:** `save_xy`, `write_vv_vh` and the three FCS writers are
   still on that allow-list. They are exports rather than defaults now, and each
   can come off once its callers ask for the export explicitly. Check the
   callers before removing one: `write_vv_vh` in particular is read by tools
   outside ChiSurf.

6. **Stages 3 and 4 are done; three writers are left, and they are the odd
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
   `get_store` (a unit is an attribute of the *column*, and a frame has nowhere
   to keep one — which is why `get_table` was retired with PRD-82 rather than
   kept as a convenience), `column_units`,
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

7. **Capture the legacy baseline BEFORE touching each writer.** Once a writer is
   changed its output is unrecoverable and the migration cannot be reviewed by
   anyone later. The recipe is the one used for `burst_selection`: drive the
   headless API with the legacy flag, record every path with its size, sha256
   and text, plus the column inventory, and store it under
   `test/data/baselines/`. Judge parity on **columns, not bytes** — the
   container deliberately stores a table where the folder stored a padded text
   grid.
8. **The interleave is a file-format artifact and must not travel.** A `.bur`
   holds `2N+1` rows — a zero row, a burst, a zero row — because companions are
   merged by *counting*, and it carries a nameless trailing column to produce
   the header's trailing tab. Both leak into the in-memory frames the analyses
   pass around. `deinterleave_bursts` in `burst_container.py` strips them and
   `write_burst_artifact` calls it, so a writer that goes through the seam is
   safe; one that reaches past it is not, and a placeholder row silently
   destroys the information that a burst was absent. The trap is that the frame
   *looks* like data.
9. **`export_seidel` is not written yet.** It is `PtoFile.disassemble()` plus
   the existing `burst_companion.write_companion` — it must go through that
   function and never hand-roll the `2n+1` interleave, which is the mistake
   four current writers make. It is **lossy by construction** for anything not
   at burst grain and must say so.
10. **`read_bur_with_companions` has no PTO branch yet.** That is the single
   seam `burst_browser` and ndX read through, so adding it there gives both
   PTO support without touching either.
11. **Streaming landed in the library** (tttrlib PRD-020): `add_file`,
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
