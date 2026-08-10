---
type: PRD
prd: "97"
title: "PRD-97: FRET docking is imp.bff's — the engine, the AV backend and the one fps.json"
description: ChiSurf's FRET plugin holds 4,014 lines of docking algorithm that import IMP and nothing of ChiSurf, plus the most elaborate of three fps.json readers. The algorithms move to imp.bff and ChiSurf calls them; imp.bff becomes the home for the data schemas -- legacy C# FPS, both fps.json dialects and what supersedes them -- authored once and derived, the way mmfdb derives its schema from the flrCIF dictionary.
status: draft
phase: "scoped and measured; nothing moved yet"
resource: chisurf/plugins/modelling/fret/core
tags: [prd, scope, architecture, imp.bff, fret, docking, fps-json, schema, flrcif, mmfdb]
timestamp: '2026-08-10T00:00:00Z'
---

# Where to pick this up

Nothing has moved. This is the scope and the measurement.

The headline is that the cut is unusually clean: **`imp_engine.py` (1391 lines)
and `av.py` (742) import IMP twelve and six times respectively, and ChiSurf zero
times.** They are already independent of the application they live in. Under the
placement rule in [references/imp-ecosystem](/references/imp-ecosystem.md) —
coordinates in, structure scored — they are imp.bff's, and moving them is a
relocation rather than a disentangling.

# There are three fps.json readers

| where | size | what it does |
|---|---|---|
| imp.bff, C++ `AVNetworkRestraint` | — | parses fps.json to build the AV network it scores |
| imp.bff, `pyext/src/fps.py` | 74 lines, 2 functions | reads fps.json |
| ChiSurf, `fret/core/io.py` | 539 lines, 11 functions | reads **and writes** fps.json, plus evaluators JSON, PDB/RMF output, RMSD, and the legacy Olga `lps.txt` / `distances.txt` formats |

The ChiSurf one is the elaborate one, and it is the only one that round-trips.
A format with three readers has no owner: the C++ one decides what a restraint
sees, the Python one decides what a script sees, and the ChiSurf one decides
what a user can save. They agree today by coincidence and review, not by
construction.

**fps.json is imp.bff's format** — it describes labelling positions and
distance measurements on a structure, which is precisely what imp.bff exists to
score. One reader, in imp.bff, used by all three call sites.

# What moves, measured

Classified by what each file imports, not by what it is called:

**Moves — imports IMP, imports no ChiSurf (2,133 lines)**

* `imp_engine.py` (1391) — the docking engine itself: AV network restraints,
  rigid-body setup, the sampling macro, error estimation.
* `av.py` (742) — the accessible-volume backend, including the LabelLib/IMP
  backend selection.

**Moves — the format and its I/O (539 lines)**

* `io.py` — fps.json read/write, evaluators JSON, structure output, RMSD, and
  the legacy readers. One tie to cut: a lazy `StructureRmfWriter` import inside
  `write_rmf`, which IMP.rmf can do directly.

**Moves — docking algorithms that import nothing either way (1,342 lines)**

* `olga_greedy.py` (436) — Olga-style greedy informative pair selection.
* `distance.py` (411) — model distance calculation.
* `engine.py` (179) — rigid-body data structures (marked legacy; check whether
  it is dead before moving it).
* `uncertainty.py` (121) — FPS-style positional uncertainty from repeated docking.
* `stat.py` (110) — reads PMI `stat.*.out` for docking progress and score curves.
* `distributions.py` (85) — FPS-style P(R_DA) for a structure.

**Stays — tied to the application (1,742 lines)**

`trajectory.py` (522), `pair_selection.py` (301), `results.py` (287),
`screening.py` (269), `evaluate.py` (247), `av_viewer_3d.py` (116). These import
ChiSurf: the session, the fitting parameters, the plots, the 3D view. They are
the workflow around the algorithm, which is what an application is for.

**Total: 4,014 lines move, 1,742 stay.**

# Why this is worth doing

Not tidiness. Three things follow from the algorithm living in the application:

1. **The docking engine cannot be used without ChiSurf.** A structural
   modeller with IMP installed cannot run FRET docking, because the engine is
   inside a fluorescence GUI application. That is backwards: imp.bff ships
   through conda-forge as part of IMP, which is where a modeller looks.
2. **fps.json has no owner**, as above.
3. **The AV backend is duplicated in spirit.** `av.py` selects between LabelLib
   and IMP.bff's own AV; imp.bff now also holds `IMP.bff.av`
   (`BasicAV`, `ACV`) from imp-tricks and the C++ `AV`/`PathMap`. That is three
   accessible-volume paths, and the one that picks between them lives furthest
   from the other two.

# imp.bff houses the data schemas, the way mmfdb houses its own

The three readers above are a symptom. The rule underneath is that **imp.bff is
where the fluorescence-structure data schemas live** — every dialect of
fps.json, the legacy formats that preceded it, and whatever supersedes it — and
that it does so on mmfdb's model rather than by accumulating parsers.

**mmfdb's model, which is the one to copy.** The mmCIF/flrCIF dictionary is the
*single authored artifact*; the SQL schema is **derived** from it.
`mmfdb/schema/schema_from_dictionary.py` generates the DDL from `_mmfdb_schema`
bridge attributes, and `dictionary_schema_map.py` registers local entries for
fields ChiSurf stores that upstream flrCIF does not define. Nobody hand-writes a
table and hopes it matches. That is exactly the discipline three fps.json
readers lack.

**There are already two fps.json dialects, and they differ.** Measured:

| | ChiSurf `hiv_rt.fps.json` | imp.bff `template_av_position.fps.json` |
|---|---|---|
| shape | `Positions` (11) + `Distances` (20) | flat, one position |
| per-position keys | `linker_length`, `linker_width`, `radius1/2/3`, `simulation_grid_resolution`, … | the same **plus** `allowed_sphere_radius`, `anchor_atoms`, `chain_weighting`, `contact_volume_thickness`, `contact_volume_trapped_fraction`, `min_sphere_volume_fraction`, `simulation_type`, `strip_mask` |

The imp.bff template carries accessible **contact** volume parameters the
ChiSurf example has no field for. So a file written by one is not fully
readable by the other, and neither is wrong — there is simply no definition
saying which fields exist.

## What imp.bff has to house

1. **The legacy C# FPS formats.** `read_old_lps_txt` and
   `read_old_distances_txt` in ChiSurf's `io.py` read labelling positions and
   experimental distances from the original C# FPS `.txt` files. These come
   along: a format nobody can still read is data that has been lost, and these
   are the files a decade of measurements live in. Read support only — nothing
   should write them again.
2. **fps.json as it is**, both dialects, with the union of their fields defined
   rather than discovered.
3. **The advanced `.fps.json` that supersedes it.** Design it as a schema first,
   not as a parser: the fields the AV and contact-volume machinery actually
   take, the distance types and their error model, and the provenance of a
   measurement — which is where it meets mmfdb.

## The alignment with mmfdb, concretely

fps.json describes labelling positions and distance measurements on a
structure. mmfdb already models exactly that, in flrCIF terms, because
[PRD-02c](prd-02c.md) mapped ChiSurf's parameter short names onto canonical
flrCIF dictionary items. So:

* **Where flrCIF defines an item, the schema uses that name.** A labelling
  position and a FRET distance are dictionary concepts, not imp.bff inventions.
* **Where it does not, imp.bff authors the definition** and it is registered the
  way mmfdb registers its local entries — visible, in one file, rather than
  implied by a reader.
* **Readers and writers are checked against the definition**, so a new dialect
  is a change to one artifact rather than a change to three parsers that then
  have to be reconciled by review.

The payoff is the same one mmfdb already gets: an fps.json can round-trip
through the metadata store and come back as the same measurement, because both
sides name the same things. Today that mapping is done by whichever code path
happens to be reading.

## Not in scope here

This does not make imp.bff depend on mmfdb, and it does not move mmfdb.
mmfdb is ChiSurf's metadata store and stays there; what is shared is the
*vocabulary*, which is flrCIF's and is upstream of both.

# Stages

**Stage 0 — write the schema down.** Before any parser moves: one definition
covering the union of both dialects, with flrCIF item names where flrCIF has
them and authored entries where it does not. Everything after this is checked
against it.

**Stage 1 — one fps.json reader, plus the legacy formats.** Move `io.py`'s
fps.json read/write and the two C# FPS `.txt` readers into imp.bff, delete
`pyext/src/fps.py`'s duplicate, and have the C++ and Python readers agree by
construction — ideally the C++ one being the only parser. Verify against the
schema and on the fps.json files already in the tree before deleting anything.

**Stage 2 — the engine and the AV backend.** `imp_engine.py` and `av.py` move
as they are; ChiSurf imports them. No behaviour change, and the FRET suite is
the acceptance test: it must stay at its current count, with the six
`test_examples.py` failures still the only ones (they want a `../olga` checkout
that is not on this machine).

**Stage 3 — the algorithm files.** The six that import nothing either way.
Check `engine.py` for deadness first; it is marked legacy.

**Stage 4 — resolve the three AV paths.** With `av.py`, `IMP.bff.av` and the
C++ `AV`/`PathMap` all in one repository, the comparison PRD-93 stage 3 asks for
becomes possible: measure them against each other and decide which survives.
Not before.

# Decisions still open

1. **Does the C++ fps.json parser become the only one?** It is the most
   constrained and the hardest to keep in sync from outside. If Python parses
   through it, the format has one definition; if not, two remain.
2. **What happens to `screening.py` and `pair_selection.py`?** They read as
   workflow, and they import ChiSurf, so they stay by the rule — but
   `olga_greedy.py` is the algorithm underneath `pair_selection.py`, and
   splitting a pair like that is worth a second look.
3. **Does ChiSurf keep thin forwarders?** κ² kept them (PRD-93) so call sites
   did not change. Four thousand lines is a different scale, and a forwarding
   module that large is its own maintenance burden.

# Definition of done

* One fps.json reader in the stack, in imp.bff, checked against one written
  schema.
* The legacy C# FPS `.txt` formats still readable, from imp.bff.
* Every field either carries a flrCIF item name or an authored definition; none
  is implied only by a parser.
* `chisurf/plugins/modelling/fret/core` contains no file that imports IMP.
* FRET docking runs from IMP alone, with no ChiSurf installed.
* The ChiSurf FRET suite is unchanged: same pass count, same six `../olga`
  failures.
