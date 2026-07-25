---
type: Parity Tracker
title: ChiMOL vs PyMOL parity
description: Measured gap between ChiMOL and PyMOL, with a prioritised route to replacing it.
resource: chisurf/plugins/chimol/
tags: [plugins, structure, viewer, pymol, parity]
timestamp: '2026-07-25T00:00:00Z'
---

# Why this file exists

The goal is for ChiMOL to **replace** PyMOL for this group's work, not merely to
resemble it. That is a programme, not a task, so it needs a tracker that survives
between sessions — otherwise each round rediscovers the same gaps and closes the
easy ones twice.

Source of truth for PyMOL's behaviour is its **source**, checked out at
`junk/pymol-open-source`. Reading it has repeatedly overturned conclusions drawn
from observation alone; see [the log](/log.md) for three cases where a measured
"constant" turned out to be a different algorithm.

# The measured gap

| | PyMOL | ChiMOL |
| --- | --- | --- |
| Code | 515 823 lines C++ + 52 154 Python | 29 442 Python |
| Commands | 303 | 81 |
| Settings | 769 | 44 registered |
| Representations | 16 | 11 |
| Selection keywords | 85 canonical | 85 canonical, 169 spellings |

ChiMOL is roughly **5 % of PyMOL by volume**. Most of that difference is not
missing features but PyMOL's own scale: shaders, pickers, movie machinery, CGO,
volume rendering, four file-format families, and twenty years of edge cases. The
useful question is not "how do we write 500 000 lines" but **which parts are load
bearing for this group's work**, and those are tiered below.

# Tier 1 — daily use, blocks replacing PyMOL

| Item | Status | Notes |
| --- | --- | --- |
| `lines` (per-bond wireframe) | **done** | `RepWireBond`; was wrongly the CA trace |
| `nonbonded` (crosses) | **done** | `RepNonbonded`; waters/ions in a wireframe |
| Cartoon pipeline | **done** | Every step of `RepCartoonGeneratePoints` |
| Camera / `zoom` / view tuple | **done** | Exact against `SceneWindowSphere` |
| Object menus A/S/H/L/C | **done** | 1:1 from `pymol/menu.py` |
| Menu bar | **done** | PyMOL's grouping |
| Selection algebra | **done** | One table from `Keyword[]`; every arity class |
| `save` (PDB/mmCIF export) | **done** | Writes what the viewer holds, not the source file |
| `label` | **done** | Expression language, not templates; `L` menu now live |
| `create` / `extract` | **done** | Child drawn in its parent's frame, true coordinates kept |
| `origin` | **missing** | Rotation about a chosen point |
| Undo / redo | **missing** | No edit history at all |

## The selection language

The vocabulary now lives in one table, `cmd/sele_keywords.py`, transcribed from
`Keyword[]` in `layer3/Selector.cpp`, and both the parser and the evaluator read
it. That structure is the point, not the coverage: the parser previously kept its
own tuple of property names which had **drifted from the evaluator**, so `resn`
was implemented, evaluated correctly and *unreachable* — `resn NAG` parsed as an
implicit `AND` of two bare identifiers and reported an empty selection rather than
a missing feature. The same stale list had been copied to three call sites in
`selection.py`, where it decided whether a leading word was a keyword or an object
name; all three now ask the table.

Arity and fixity come from the `STYP_` suffix of each `SELE_` code, which the stack
reducer at the end of `SelectorSelect` spells out. Two were wrong before:
`STYP_PRP1` reduces `LIST PRP1 PVAL`, so `around`/`expand`/`extend`/`gap` are
**postfix**; `STYP_OP22` reduces `LIST OP22 VALU VALU LIST`, so
`within`/`near_to`/`beyond` are **infix**. Both had been implemented as prefix.

Atom classes (`polymer`, `organic`, `solvent`, `inorganic`, `backbone`,
`sidechain`, `guide`, `metals`) are derived per residue from the atoms present, as
`SelectorClassifyAtoms` does, in `analysis/atom_classes.py` — not from a table of
residue names, so a modified residue or an unusual ligand lands in the right class
with nothing to maintain. `metals` is by proton count, per
`AtomInfoType::isMetal`. One deviation is documented in that module: PyMOL also
requires a peptide or phosphodiester bond before calling a residue polymer, which
needs connectivity chimol does not carry there, so an isolated free amino acid
classifies as protein.

What chimol still cannot answer it now **names**: `donors`, `acceptors`,
`delocalized` (assigned chemistry), `masked`, `protected`, `fixed`, `restrained`
(editor state), `byring`/`bycell` (ring perception), `text_type`/`numeric_type`
(force-field types), `flag`, `state`. Each raises `UnsupportedSelection` with its
reason. An unimplemented keyword must not look like an empty selection — that
confusion is exactly what hid `resn`.

## Reader differences found while closing Tier 1

* **Alternate locations.** PyMOL keeps every altloc as a separate atom (148L:
  1385 atoms, 22 A + 22 B); chimol reads through IMP's
  `NonAlternativePDBSelector` and keeps only the first (1363). Defensible for a
  viewer and it round-trips cleanly, but the atom counts will not agree with
  PyMOL's on any structure with altlocs.
* **Unit boundaries are where the bugs are.** `translate` took Angstrom and
  applied them to the renderer's scene-unit arrays, so `translate [100,0,0]`
  moved the molecule 10 Å. Invisible on screen; obvious the moment a file was
  written. The distance selection operators had the same defect from the other
  side — `within 5` measured against scene units and so meant `within 0.5`. Any
  new command or operator that takes a length must convert.
* **Ligand atom names were being lost.** IMP prefixes the type of any atom it
  cannot classify as a standard amino-acid or nucleotide position with `HET:`, so
  a ligand's `N` stringified as `"HET: N  "`. Stored verbatim in the
  five-character `atom_name` field it truncated to `HET:`, giving *every* ligand
  atom the same name. Fixed in the shared reader (`_imp_atom_name` in
  `chisurf/core/fio/structure/coordinates.py`), which benefits all of chisurf, not
  only the viewer. Two consequences worth knowing: the peptidoglycan stem peptide
  of 148L (DAL, FGA) now classifies as polymer and joins the trace, since it is a
  genuine peptide; and `name`-based selections reach ligands at all.
* **`save` wrote the wrong object.** It read the *active* object's arrays while
  masking with a selection that may have resolved against another, so
  `save out.pdb, sugars` raised a length mismatch — and would have silently
  written the wrong atoms had the two objects been the same size.

# Tier 2 — routine, works around-able

`get_area`, `get_extent`, `get_chains`, `get_title`, `get_bond`,
`iterate_state`, `alter_state`, `smooth`, `sort`, `protect`, `mask`,
`bond`/`unbond`, `h_add`/`h_fill`, `cealign`, `pair_fit`, `intra_fit`,
`matrix_copy`, `symexp`/`symmetry`, `group`/`ungroup`/`order`, scenes
(`scene`/`view`), `ramp_new`, `spectrum` by property, `cartoon_putty`,
`cartoon_dumbbell`, `cartoon_fancy_helices`, `ellipsoid`, `cell`, `slice`.

# Tier 3 — specialised or superseded here

Volume rendering, `isomesh`/`isosurface`/`map_*` (ChiSurf has its own map
plugins), sculpting, wizards, the movie/`mset` programme language, stereo modes,
CGO scripting, `fab`/`fragment` building, `alias`, `log_open`.

# Where ChiMOL is deliberately ahead

* **Ambient occlusion** in the interactive viewport, normal-aware and baked per
  rebuild. PyMOL has none.
* **Cast shadows** in the interactive viewport. PyMOL casts them only when
  raytracing.
* **Settings honesty**: every registered setting is verified to drive code that
  reads it, so `set` cannot silently do nothing.

These are the answer to "surpass on the view", and they are cheap because they
exploit the one structural advantage of a rebuild-time pipeline: work done once
per geometry change is free while the camera moves.

# Working rules

1. **Read the C++ before implementing.** Every one of `refine_tips`, the
   `weighted` extent, the orientation-blend endpoints and the view-tuple sign was
   wrong when inferred from behaviour and right when read from source.
2. **Transcribe, do not approximate.** A weighted kernel that "looks like" a box
   average converges differently and shows up on screen.
3. **Pin the transcription with a test that names the C++ function**, so a later
   change cannot quietly drift.
4. **A gap that is shown is better than a gap that is hidden** — disabled menu
   entries with reasons, unknown settings reported rather than accepted,
   unsupported selection keywords named rather than returning nothing.
5. **One table, read by everyone who needs it.** Every vocabulary duplicated
   between a parser and an evaluator, or copied to three call sites, has drifted
   here at least once. The drift is silent: the feature looks implemented and
   returns the empty answer.
