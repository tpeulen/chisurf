---
type: Reference
title: Use case — FPS JSON Editor (labelling positions and FRET distance restraints on a structure)
description: Put dyes on a PDB structure — pick chain/residue/attachment atom per labelling site, compute the accessible volume of each dye, pair the sites into FRET distance restraints with R0 and errors, group them into scoring sets, and save the fps.json that drives FRET docking and screening.
tags: [usecase, structure, fret, fps, accessible-volume, modelling, gui]
timestamp: '2026-07-27T00:00:00Z'
---

# Use case: FPS JSON Editor — labelling positions and distance restraints

**Goal:** the step that turns a structure into a FRET model. The user takes a PDB
structure, declares where each dye is attached (chain, residue, attachment atom,
linker geometry), lets ChiSurf simulate the **accessible volume (AV)** each dye
can explore, then pairs the sites into **distance restraints** carrying a Förster
radius, a measured distance and its asymmetric errors, grouped into scoring sets.
The result is an `fps.json` — the input to FRET docking / screening, to
rigid-body and flexible fitting, and the reference against which measured
distances are scored.

This is the "Structure / modelling" coverage entry, upstream of the FRET-docking
and κ² workflows in the Structure Tools hub and downstream of
[FRET calculators](/usecases/fret-calculators.md) (which give you the `R0` you
type in here).

**Data:** `test/data/atomic_coordinates/pdb_files/148l.pdb` — **T4 Lysozyme
(PDB 148L)**, the canonical protein for rendering/structure tests. 1 385 atoms,
**chain `E`** (residues 1–162) plus a hetero/solvent chain `S`. Sites driven this
run: `E:18:CB` (TYR, buried), `E:44:CB`, `E:60:CB`, `E:134:CB` (ALA, exposed).

**Tool:** `chisurf.plugins.modelling.fps_json_editor`
(`FpsJsonEditorTool` → `FpsJsonEditor`), display name
*Structure:FRET:FPS JSON Editor*; CLI `fps-json-editor`, RPC service
`fps_json_editor.*`. Also reachable from the **Structure Tools** hub
(`modelling/structure_tools`), which bundles it with FRET Docking, Kappa2, QuEst,
HydroPro and the trajectory tools.

## Steps

1. Open the tool. It is a dock workspace with five tabs — **Positions ·
   Distances · FlexFit · JSON · 3D View** — a *File* menu and a toolbar
   (**📂 Load · 💾 Save · ♻️ Update · 🗑 Clear · ℹ Help**). The dock layout is
   persisted per user in `~/.chisurf/fps_json_editor_dock_layout.ini`, so a
   later session reopens on whichever tab (and split) was last used.
2. **Positions** tab. The table has one blank row waiting, and its own toolbar:
   **➕ Add Row · 🚀 Compute AVs · 💾 Save AV MRC**. Columns are
   *Show · Name · PDB (File/ID) · Chain · Res · Atom · Dye Preset · Dye Model ·
   Settings · Color · 🗑*.
3. Type the path of `148l.pdb` into the row's **PDB (File/ID)** cell and press
   Enter (the `…` button opens a file chooser; a four-character RCSB ID can be
   fetched instead via `fps_json_editor.pdb.fetch`). The structure loads in
   ~1.5–2 s, and the *Chain* / *Res* / *Atom* dropdowns fill from it
   (`E`, `S` / `1`…`163` / the atoms of the selected residue, with `CB`
   preselected, falling back to `CA`).
4. Pick **Chain `E`**, **Res `134`**, **Atom `CB`**. Each change re-triggers the
   AV for that row after a 400 ms debounce, on a background `AVWorker` thread.
5. Rename the row from the auto-generated label to something meaningful
   (`Acceptor_E134`) by typing in the *Name* cell — the name is the identity used
   by the Distances tab and written into `fps.json`. **Do this deliberately: the
   auto name is wrong (RF-380).**
6. Press **Details…** to set the dye geometry: *Linker Length (L)*, *Linker Width
   (W)*, *Radius 1–3* (R2/R3 are enabled only for the AV3 model), *Body ID*,
   *Allowed Sphere Radius*, *Grid Resolution*, *Anchor Atoms*, *Strip Mask*, and
   the advanced *Chain Weighting* / contact-volume / minimum-sphere fields.
   Defaults are L = 20 Å, W = 4.5 Å, R1 = 3.5 Å, grid 1.5 Å — an AV1 dye.
7. Repeat steps 3–6 for the second site (`E:18:CB`, named `Donor_E18`). Rows are
   colour-coded, and the *Show* checkbox and *Color* button control how the AV
   cloud is drawn in the 3D View.
8. Press **🚀 Compute AVs**. Each named row is recomputed on its own worker; the
   label under the table reports the last one to finish as
   *"AV: Calculated `<name>` (Vol: `<V>` Å³, Points: `<N>`)"*, and hovering
   **Details…** shows that row's volume, point count and mean dye position.
9. **3D View** tab — the structure with one point cloud per AV, coloured per row,
   plus a labelled line between the mean positions of every enabled distance.
10. **Distances** tab. Toolbar: **➕ Add Row** and a *Scoring group / set* combo
    with **+** / **−**. Columns are *Show · Name · Label 1 · Label 2 · Type ·
    Details · Score set · 🗑*. Pick **Label 1 = `Donor_E18`**, **Label 2 =
    `Acceptor_E134`**; the *Name* is generated as `<label1>_<label2>`.
11. Choose the restraint **Type**: `dRDA` (⟨R_DA⟩), `dRDAE` (⟨R_DA⟩_E, the
    E-averaged distance), `dRMP` (mean-position distance) or `pRDA` (a full
    distance distribution). Stored in `fps.json` as `RDAMean`, `RDAMeanE`, `Rmp`
    and `pRDA` respectively.
12. Press **Details…** on the distance row and enter *Förster Radius (R₀)*,
    *Distance (d)*, *Error Neg (err⁻)*, *Error Pos (err⁺)* — all in Å. For
    `pRDA`, load a two-column CSV (R_DA, p(R_DA)) instead.
13. Optionally create a **scoring set** with **+** and assign the restraint to it
    (each set is a separate χ² group when the model is scored).
14. **JSON** tab — review the assembled payload (`FormatVersion`, `Positions`,
    `Distances`, plus any extra sections). Hand-edit and press **♻️ Update** to
    push the text back into the visual editor.
15. **💾 Save** to `<name>.fps.json`. **💾 Save AV MRC** writes the selected (or
    all computed) AV clouds as MRC density maps for a molecular viewer.

## Expected

- Two labelling sites, each carrying an AV of a few thousand grid points
  (~8 000–14 000 Å³ for an AV1 dye with L = 20 Å on an exposed residue), named
  after the residue the user actually chose.
- One distance restraint naming both sites, with the chosen type, R₀ and errors.
- An `fps.json` that round-trips: reloading it restores both positions with their
  chain/residue/atom and the distance with its type.
- Any site that cannot carry a dye (buried attachment point, residue or atom that
  does not exist in the structure) is reported as such, not silently accepted.

## Observed (last run: 2026-07-27)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, `arm64` env,
`PYTHONPATH=modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:.`) against
`148l.pdb`; screenshots grabbed and inspected at each step.

**What works.** The whole skeleton is sound. The PDB loads and populates
chain/residue/atom in ~1.5 s; picking `E:134:CB` computes a 2 513-point,
8 481 Å³ AV in ~1.5 s on a background thread without freezing the UI; `E:44` and
`E:60` give 4 097 / 3 905 points. The Distances tab correctly derives the
restraint name from the two labels, refuses a self-pair, maps the display type to
the storage key (`dRDAE` → `RDAMeanE`) and keeps the mapping through the JSON
tab. Save → reload round-trips both positions (chain `E`, residues 134/18, atom
`CB`) and the distance with its type intact. The rows are colour-coded, the
per-row *Details…* dialog is nicely grouped (Dye Dimensions / Simulation Settings
/ Advanced Settings) and correctly greys out R2/R3 for an AV1 dye.

**What is wrong.** Five things, in order of how much damage they do:

1. **Every position ends up named after residue 1.** Entering the PDB path alone
   auto-fills the *Name* cell — at that moment the Res dropdown still reads its
   default (`1`), so the name becomes `E1`. Picking the residue afterwards never
   refreshes it. Driving the plain user path (PDB → chain `E` → res `134` → atom
   `CB`, no manual rename) produced a position **named `E1` pointing at residue
   134**; three sites at residues 134, 60 and 18 came out as `E1`, `E1_2`, `E1_3`
   (screenshot `v3_final.png`). Those names are the identity in the Distances tab
   and in the saved `fps.json`. **RF-380.**
2. **A wrong chain, residue or atom is silently redirected to an unrelated
   atom.** `_find_attachment_point` falls back to `atoms[resseq - 1]` — the
   `resseq`-th row of the flat atom array — whenever the (chain, residue, atom)
   lookup misses. Asking for `E:134:CG` (ALA has no CG) returns atoms[133];
   `A:18:CB` in a structure whose only chain is `E` returns atoms[17]; `E:300`
   and `E:500` in a 162-residue protein return atoms[299] / atoms[499]. No error,
   no `None`. In 148L every such case then yields a 0-point AV because
   `_strip_residue_atoms` also misses (0 of 1 385 atoms stripped), but the
   mechanism is "quietly use a different atom", which on another structure
   produces a plausible-looking and completely wrong volume. The Chain/Res/Atom
   combos are all editable, so a typo reaches this path directly. **RF-379.**
3. **A zero-volume AV is reported as a success.** `E:18:CB` (TYR 18, buried)
   returns 0 points. The status line reads *"AV: Calculated E1_3 (Vol: 0.0 Å³,
   Points: 0)"* — the same wording as a good result — the row looks identical to
   the others, and the *Details…* tooltip reports *"Mean Position (XYZ): (9.62,
   52.87, 48.96)"*, which is just the attachment point. That fictitious mean is
   what the 3D view's distance line (and anything else reading `_av_cache`) uses,
   so a restraint built on it gets a meaningless model distance with no warning.
   Because the label only ever shows the *last* worker to finish, a user
   computing several sites at once never sees the zero at all. **RF-381.**
4. **Renaming a site while its AV is computing hangs the busy indicator for the
   rest of the session.** Verified: rename mid-flight → `_active_workers` keeps
   the stale entry forever, the striped busy bar stays up and the label stays
   frozen at *"AV: Computing E1…"*; a later successful computation does not take
   it down. Visible in `v2_08_reloaded.png`, where simply loading a saved
   `fps.json` (which renames rows as it populates them) leaves the bar running.
   **RF-382.**
5. **The Dye Preset dropdown is a stub.** It offers exactly two entries —
   `a` and `Custom` — and choosing `a` changes nothing. `dye_definition.json`
   does not exist in `chisurf/core/settings/`, so the `except IOError` fallback
   plants the placeholder `{'a': 0}`, and `onDyePresetChanged` then bails on the
   falsy `0`. There is no dye catalogue behind the control that is supposed to
   supply L/W/R1–R3 for Alexa 488, Alexa 647, Cy3B … **RF-383.**

**Smaller things seen.** Typing the PDB path immediately launches a full AV for
`<first chain>:<first residue>:CB` before the user has chosen anything
(**RF-384**) — that is also what fixes the wrong name. Every **➕ Add Row** click
leaves a blank row behind, because the table already appends a trailing empty row
on its own: two positions ended up in a five-row table with three blanks
(**RF-385**). Reading the same PDB once per row floods the console with several
hundred `Could not determine CHARMM atom type` warnings per read (12 reads in one
short session). The Distances table pre-fills its placeholder row with the *same*
label in *Label 1* and *Label 2*, which the panel then refuses with a status-bar
message the user is unlikely to see.

**Headless limitation.** The 3D View is a `QOpenGLWidget`; under the offscreen
platform it cannot create a GL context (*"QOpenGLWidget: Failed to create
context"*) and renders blank, so the AV clouds, the distance line and its
`<d> Å` label were verified from `_av_cache` / `_measurements` rather than from
pixels.

## UX / UI suggestions

- **Show the AV result in the table, not only in a tooltip and a transient status
  line.** A *Volume (Å³)* / *Points* column would make a zero-volume or
  suspiciously small AV impossible to miss, and would let a user compare sites at
  a glance. Colour the row red when an AV comes back empty.
- **Show the model distance next to the target distance.** The distance between
  the two AV mean positions is already computed — but only as a floating label in
  the 3D view. Put it in the Distances table beside the user-entered *d*, with the
  deviation, so the panel answers "does my structure agree with my measurement?"
  without opening the 3D view. Note it is currently ⟨R_mp⟩ regardless of the
  restraint type, which is only correct for `dRMP`.
- **Put the restraint numbers in the table.** *R₀*, *d*, *err⁻*, *err⁺* are the
  content of a restraint set and they all hide behind **Details…**. A user
  cannot review or compare a dozen restraints without opening a dozen dialogs.
- **Label residues by type.** The *Res* dropdown lists bare numbers `1…163`;
  `18 (TYR)` / `134 (ALA)` would let a user sanity-check the site they picked —
  and a *Res* cell reading `134 ALA` would make the `E1` naming bug obvious.
  Similarly, mark the solvent/hetero chain (`S`) as not a labelling chain.
- **Do not offer a dye preset list that contains one placeholder.** Until a dye
  catalogue exists, hide the column, or feed it from the fluorophore data already
  curated in the MMFDB admin plugin.
- **Give the *Details…* fields tooltips and units.** Fourteen spin boxes carry no
  tooltip and no `Å` suffix; *Body ID*, *Allowed Sphere Radius*, *Strip Mask*,
  *Chain Weighting*, *Contact Vol Trapped Frac* and *Min Sphere Vol Frac* are
  unguessable. The project rule is that every control carries a `description`.
- **Explain the four restraint types where they are chosen.** `dRDA` / `dRDAE` /
  `dRMP` / `pRDA` appear as bare abbreviations in a combo, and the saved file uses
  a second vocabulary (`RDAMean` / `RDAMeanE` / `Rmp`). One tooltip per entry, and
  showing the type in the Details dialog, would remove the guesswork.
- **Make "Add Row" and the auto trailing row one behaviour.** Either drop the
  button (the trailing row already invites a new entry) or have the button reuse
  the existing blank row.
- **Restrict the editable Chain/Res/Atom combos to what the structure contains**,
  or validate on commit — with the attachment-point fallback fixed, a typo should
  say "chain A is not in this structure", not compute something.
- **Spell it Förster** in the distance Details dialog (*"Forster Radius (R₀)"*).

## Bugs filed

- **RF-379** — `_find_attachment_point` silently substitutes `atoms[resseq-1]`
  when the chain / residue / atom lookup misses, so a typo or an out-of-range
  residue relocates the dye to an unrelated atom instead of erroring.
- **RF-380** — the auto label name is fixed from the chain-only state, so every
  position is named after residue 1 (`E1`, `E1_2`, `E1_3`) whatever residue the
  user picks.
- **RF-381** — a zero-point AV is reported as *"AV: Calculated … (Vol: 0.0 Å³,
  Points: 0)"* and still yields a mean position (the attachment point) that the
  3D distance line consumes.
- **RF-382** — renaming a labelling site while its AV worker is in flight leaks
  the worker entry and leaves the busy indicator running for the rest of the
  session.
- **RF-383** — the Dye Preset dropdown offers a single placeholder entry named
  `a` that does nothing; `chisurf/core/settings/dye_definition.json` is missing.
- **RF-384** — entering the PDB path launches a full AV computation for
  `<first chain>:<first residue>:CB` before the user has chosen anything.
- **RF-385** — **➕ Add Row** plus the automatic trailing empty row leave one
  blank row per click.
