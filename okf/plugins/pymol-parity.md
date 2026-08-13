---
type: Parity Tracker
title: ChiMOL vs PyMOL parity
description: Measured gap between ChiMOL and PyMOL, with a prioritised route to replacing it.
resource: chisurf/plugins/chimol/
tags: [plugins, structure, viewer, pymol, parity]
timestamp: '2026-07-25T00:00:00Z'
---

# Why this file exists

The **target** — a PyMOL clone that is command-compatible with PyMOL and better
than it — is stated in [specs/chimol](/specs/chimol.md). This file is the
*measured gap* against that target: the tier list, what is done, and the findings
from closing each item. It needs to survive between sessions, or each round
rediscovers the same gaps and closes the easy ones twice.

Two sources are read, and they answer different questions.
**PyMOL** (`junk/pymol-open-source`) is the authority on *behaviour*: what a
command does and what its defaults are. **ChimeraX** (`junk/ChimeraX`) is the
reference for *how to do it well* — rendering above all — and is explicitly not
the compatibility authority.

A third, a WebGL viewer, was consulted for shader technique, **read out, and its
checkout removed** on 2026-08-05 — see *the WebGL viewer is read out* for what it
gave and how to fetch it again. Anything it offered beyond shaders duplicates
PyMOL or ChimeraX under names chimol must match anyway.

Reading them has repeatedly overturned conclusions drawn from observation alone;
see [the log](/log.md) for cases where a measured "constant" turned out to be a
different algorithm, and for one where the data was blamed before the rule was.

# The measured gap

| | PyMOL | ChiMOL |
| --- | --- | --- |
| Code | 515 823 lines C++ + 52 154 Python | 29 442 Python |
| Commands | 303 | 119 |
| Settings | 790 | 74 registered |
| Representations | 16 | 11 |
| Selection keywords | 85 canonical | 85 canonical, 169 spellings |

ChiMOL is roughly **5 % of PyMOL by volume**. Most of that difference is not
missing features but PyMOL's own scale: shaders, pickers, movie machinery, CGO,
volume rendering, four file-format families, and twenty years of edge cases. The
useful question is not "how do we write 500 000 lines" but **which parts are load
bearing for this group's work**, and those are tiered below.

# Where to pick this up

The findings below are what has been *closed*. This section is the open front,
kept at the top so a new session does not have to reconstruct it. Ordered by
what a user actually hits.

**0-ante-ante. Density contouring is fast now (landed 2026-08-11); what is
left of it.** The user-reported "make density plots more performant" is
closed by taking the map-contour habits from the ChimeraX checkout
(`_map/contour.cpp`, `map_data/src/arrays.py` — both carry `CHISURF-*`
headers): the marching cubes reads the grid in its own precision with `uint8`
corner cases, normals are symmetric differences sampled only at surface
vertices, and `VolumeGrid` memoises range/histogram/default-levels/strided
copy plus the last 4 contours (`values` is immutable by contract — nothing in
the tree writes it in place, and the memo depends on that). A level drag now
live-previews under a 2 M-voxel budget (`_VOLUME_PREVIEW_LIMIT_M`, view.py)
with one full contour on release, and `set_volume_levels` swaps only that
object's `volume_*` scene objects via `_refresh_volume_objects` instead of a
full `_update_view`. Measured in `docs/development/benchmarks.md` ("ChiMOL
density-map contouring", script `test/benchmarks/benchmark_map_contour.py`):
180³ cold contour 500–770 ms → ~100 ms, unchanged-level re-ask ~3 µs,
histogram per panel paint 92 ms → 0.4 µs. Re-derive with the benchmark
script; the trap in measuring is that the *second* ask is served from the
memo, so time a **fresh** grid for the cold number. Left open, in order of
what it blocks:

* **the format is one format, and chimol reads it (2026-08-13, user round):**
  chimol builds painted forms from ChiSurf `view.json` specs
  (`renderer/ui/view_spec.py` + `renderer/form_window.py`, opened with `form`).
  It is an **adapter, not a second renderer**: a spec becomes `Setting` rows
  over the settings editor that already existed. The trap it walked into first
  is the one worth carrying -- the draft invented `{"type": "float", "min": 0}`
  where the dialect is `{"type": "value", "kind": "float", "minimum": 0}`, read
  fine here and was valid nowhere else. The scheme
  ([PRD-103](/prds/prd-103.md)) now asserts chimol's own specs alongside every
  other plugin's, and `SettingsProxy` exposes the registered settings as
  attributes so a spec can be written against them.
* **four user-reported defects, 2026-08-13.** (1) The tour bubble covered the
  control it was pointing at -- fatally for the command prompt, which spans the
  width, so the step saying *type this at the prompt* hid the prompt.
  `_tour_bubble_at` now tries all four sides and only accepts a placement that
  clears the target. (2) `fetch emdb-3061` fell through to RCSB and reported
  "no entry emdb-3061", naming the wrong database: the pattern matched `emd`
  and not `emdb`. (3) **Typing was US-only on the desktop** -- glfw's key event
  carries *its own keycode*, a US-QWERTY position, and chimol used it as the
  character with a US shift table on top; the layout-aware `char` event was
  going unread. Text now comes from `char` where a backend has one (glfw, qt,
  wx -- asserted against those backends' own source), and `key_down` supplies
  only the keys that act. The Qt and browser hosts were already correct and are
  now pinned too. (4) `ihm-12` routed to PDB-IHM and then asked for
  `ihm-12.cif`, which is a 404 -- the accession is zero-padded behind
  `pdbdev_`.
* **AlphaFold, and the pLDDT that was being thrown away (2026-08-13):**
  `fetch AF-P69905-F1` works, with the **version asked for rather than
  assumed** -- the entry's own API reports the current `cifUrl`, and the v4 URL
  that would have been hard-coded is already a 404 because the database is on
  v6. It exposed a real defect one level down: the mmCIF reader never passed
  `biso`, so **every `.cif` loaded with a column of zeros** while the same file
  read through the core reader had it. Invisible until something asks --
  `spectrum b` painted one flat colour and putty drew a constant tube -- and
  worst for a predicted model, where that column is the confidence.
* **the reference viewer's presets (2026-08-13):** ten, under their own
  **Preset** menu and `preset_cx` command, kept separate from PyMOL's fifteen
  because they answer a different question -- PyMOL's choose *what to show*
  (ligands, sites, interfaces), these choose *how what is shown should look*
  (ribbon geometry, surface transparency, the three lighting states a figure
  passes through). Transcribed from documented behaviour, never from the
  source. The tenth is `alphafold`: colour by pLDDT, low warm and high cool,
  because reading a prediction without its confidence is the mistake that
  database invites.
* **guided tours in the viewport (2026-08-13):** a demo runs itself and shows
  a finished result, which teaches nothing about *where the controls are*.
  `chimol/tour.py` + `_paint_tour` ring one real control at a time and **wait
  for the user to use it** -- the same contract as ChiSurf's `guide.json`
  tours, transposed onto a painted chrome. The transposition is the
  interesting part: a ChiSurf step locates a `QWidget` and waits for its
  signal; there are no widgets here, so a step locates a **painted rectangle**
  by name and waits for the **command** it asks for, observed at the one funnel
  every route ends in (`BaseCmd._do_one` -> `_notify_command`). A step is then
  satisfied whether the user typed it, used the menu or pressed the toolbar.
  Two ship, both on real data with right answers to check against:
  `fit_in_map` (EMD-3061 + PDB 5A63, one experiment) and `superpose`
  (1DG3/1F5N, one protein in two states). **Real-data measurement worth
  keeping:** `fitmap` at 5A63's *deposited* position moves it 0.03 A and 0.1
  deg -- it agrees the deposit is the answer -- and from 10.31 A out returns to
  0.044 A of it. Map correlation is **0.49**, not 1.0, because an experimental
  map carries solvent and noise a model does not account for; the tour says so,
  since a user expecting 1.0 reads a good fit as a failure. The walkthrough
  test caught a real defect in the tour's own text (`hide_dust dens, 30` names
  the contour object where the command wants the map), which is the failure
  mode a tour has: the instruction on screen tells the user to do something
  that does not work, and nothing raises.
* **`molmap` and `fitmap` (2026-08-12, ChimeraX round):** the biggest
  scientific gap in the earlier census is closed. `analysis/molmap.py`
  simulates a density from atoms -- one Gaussian each, width
  `resolution / (pi*sqrt2)` and **not** the resolution (a 3 A map splatted with
  3 A blobs is markedly blurrier than the real thing), step `resolution/3`, pad
  `3*resolution` so the tails are not clipped flat by the box faces, evaluated
  to 5 sigma per atom so the cost is `n_atoms * (cutoff/step)^3` rather than
  `n_atoms * n_voxels`. `on_grid=` samples onto an experimental map's own
  lattice, which is the only way two maps can be compared.
  `analysis/mapfit.py` fits rigidly by steepest ascent on the map value at the
  atoms, using the density gradient and the torque about the model's centre;
  both motions are scaled so the largest *atom* displacement is one step, or a
  large complex spins while a small one barely turns.
  **The measurement:** 148L displaced 5.9 A RMSD (10 deg + 5.4 A) is recovered
  to **0.014 A** in 13 steps, through the command layer. Re-derive with
  `chimol/test/test_molmap_fitmap.py`.
  **Two traps, both pinned by tests.** (1) The obvious fit score -- correlate
  each atom's weight against the map value under it -- **prefers the wrong
  answer**: on 148L at 6 A it is -0.030 at the true position and -0.014 four
  angstrom away. Density at map resolution is smooth and heavy atoms are not
  under denser voxels. The number to quote is `map_correlation`, model density
  simulated `on_grid` and compared voxel-wise: 1.000 at the answer, 0.62
  displaced. With uniform weights the per-atom form returns `nan`, never 0.0,
  because 0.0 reads as total failure for a perfect fit. (2) The basin is much
  wider than expected -- 45 deg and a half-extent shift both recover fully --
  but **90 deg does not** (17.2 A out, settles 12.8 A out) and still reports an
  ordinary score. A model entirely off the map does not move, correctly.
  Open: a global search (many starts) on top of this, `volume zone`, and a
  difference map.
* **secondary structure knew nothing about chains (2026-08-12, ChimeraX
  round):** `analysis/ss.py` built one flat `(n, 4, 3)` backbone from *every*
  residue in the structure and ran DSSP down it as one polypeptide. Three
  silent consequences: the last residues of one chain were read as turning
  into the first of the next (helix patterns are sequence *offsets* — an i+4
  can be in another molecule); **proline donated** hydrogen bonds, though its
  nitrogen is in the ring and carries no H, which is exactly the bond that
  makes a helix; and a residue missing a backbone atom was dropped from the
  *middle* while the codes were padded at the *end*, shifting every later
  residue by one. Now `_backbone_record` carries slots, a donor mask and
  covalently continuous segments (chain label **and** a C–N bond under
  `PEPTIDE_BOND_MAX = 2.5 Å`, so a disordered loop breaks a segment too).
  **The trap that cost a rewrite:** the obvious fix — run DSSP per chain —
  is wrong. A β bridge is a *spatial* pairing and inter-chain sheets are
  ordinary; segmenting the hydrogen-bond map dropped **40 of 1DG3's 68**
  strand residues with nothing in the output to say so. The split that is
  correct is **helices per segment, bridges across the whole map**, masking
  only the three-residue windows that straddle a break
  (`_helix_from_hbmap` / `_strand_from_hbmap`). Re-derive with
  `_backbone_record(...).segments` and by comparing a chain's codes alone
  against the same chain with another laid after it — and note that laying a
  helix against *a copy of itself* does not discriminate (the fused thing is
  still a helix); 148L 93–106 followed by 38–50 does. Pinned by
  `chimol/test/test_ss_chains.py`, three of whose tests fail on the old code;
* **`align`/`super`/`rms` paired residues by position (2026-08-12, ChimeraX
  round):** `_align_or_super` truncated both selections to `min(len, len)`
  and paired them by index — its own comment admitted it. Any insertion,
  deletion, missing loop or different first residue number superposed
  **mismatched residues** and returned a confident meaningless RMSD. A
  131-residue fragment cut from 148L itself scored **15.964 Å** against its
  own parent, where the answer is zero. Now `_pair_residues` tries chain +
  residue number, then residue number, then Needleman–Wunsch on the
  one-letter sequences (the aligner in `analysis/sequence.py` already
  existed and *nothing called it*); falling back to position is deliberately
  **not** a rule, because refusing to pair beats a wrong number. `rms` held a
  **second copy** of the same bug, found only by the test — and its default
  is all-atom, so it additionally pairs atoms **by name within each paired
  residue** (`_paired_atom_coords`): two structures need not carry the same
  atoms per residue, and lining up two flat atom lists is the same mistake
  one level down. All four commands now report 0.000 on that fragment;
* **sticky windows + chrome file dialogs (2026-08-12, fourth user round):**
  windows stick to *each other* — a title-drag within 8 px snaps flush and
  aligns the near-perpendicular edge; the stuck group is geometric
  (`_frames_touch`/`_stuck_group`, read at drag start, nothing linked
  explicitly) and rides along at fixed offsets; **shift-drag detaches**;
  partners get the accent border mid-drag. The viewport menu bar now honours
  `MenuEntry.file_prompt` via `InternalGui.on_file_prompt` (the app opens the
  QFileDialog; unset, e.g. the browser, falls back to the CLI placeholder) —
  the Qt bar had the dialogs but is hidden, so Save/Export never showed one.
  `chimol/test/conftest.py` pins every test to a throwaway
  `CHISURF_SETTINGS_DIR` after the user's live session closed the density
  window in real prefs and seven fixture tests read it and failed. Trap worth
  keeping: a fixture callback with the wrong arity dies *inside* the
  producer's `try/except` — the hierarchy guard test was green-by-accident
  until run against the two-argument `on_change`. Open: stuck groups do not
  resize together, and a group dragged against a viewport edge anchors only
  the lead window;
* **polish round (2026-08-12, third user round):** window bounds stop at
  the prompt/status band; the mouse block left PyMOL's palette for
  chimol's own; chrome-wide hover tooltips (`GuiWindow.on_tooltip` is the
  seam for panel bodies; `MODE_ACTION_WORDS` decodes binding cells); the
  hierarchy-disable bug was an object-identity mismatch (tree from one
  object, hiding applied to the active one — carried the id through);
  the object list grew an eye and names run `activate` (new command);
  density panel compact by default with the palette clamped into the body;
  `load_map` fetches EMDB deposited contour levels. Lesson worth keeping:
  a panel that *shows* one object's data while *acting* on "the active
  object" will eventually act on the wrong one — carry the identity with
  the data;
* **six-ask sweep (2026-08-12, second user round):** menu saves via real
  file dialogs (`MenuEntry.file_prompt`), the Qt status bar replaced by the
  chrome's own line (`status_text`, obeys `show_status`), chrome fully
  strippable via `show_menubar`/`show_toolbar`/`show_command_line`/
  `show_status` (bare viewer for embedding), the Atoms-level `sele`
  widening bug fixed at `_selected_residues_atom_mask`, Save Molecule As…
  surfaced, and the **Build menu un-omitted** — bond/unbond/remove/alter/
  pseudoatom/h_add/mutagenesis existed, tested, and were invisible; the
  OMITTED_MENUS reason "no structure editing" had silently gone stale.
  **Open:** structural undo beyond PyMOL's coordinate scope (topology
  snapshots so `remove`/`bond`/`unbond` can be undone) — the ring in
  `renderer/undo.py` is the seam, and its docstring explains why the
  current scope is deliberate; extend, don't replace;
* **scene model export (2026-08-12):** `save x.glb/.stl/.wrl` writes the
  drawn scene as a 3-D model (`io/mesh_export.py`, wholly new); glb is the
  PowerPoint format and is labelled so in the menu, the prompt and the save
  message. Spheres/sticks re-tessellate from the primitives templates; the
  export deliberately skips lines, labels and the solid fog. PyMOL parity
  note: PyMOL's `save` also does `.wrl`/`.stl`/`.obj`/`.dae` — `.obj` and
  `.dae` remain open, same writer pattern if wanted;
* **the chrome is windows (2026-08-12):** Object List and Mouse are
  `GuiWindow`s (content painters untouched; the windows position
  `_panel`/`_block` and dispatch their sub-hits so z-order wins), snapping
  with corner anchors in `renderer/window_state.py`, persistence to
  `chimol_windows.json` **opt-in from the shipped app only** (a bare panel
  in a test must never touch real preferences — enforced by a test).
  Docked-column mode survives behind `gui.docked = True`. Traps worth
  keeping: the chrome atlas has no `×` — a missing glyph draws as
  *nothing*, so use ASCII in chrome text; and hit-testing must follow
  window z-order, not a flat rect list, once panels can overlap. Open:
  the density/hierarchy/settings windows do not auto-anchor on first start
  (only objects/mouse do), and `test_a_middle_drag_moves_the_molecule` is
  failing 2× independent of this change (see the log entry);
* **map tools and a Tools menu (2026-08-12):** Hide Dust
  (`geometry/dust.py`, the reference's `size` metric = largest bbox extent;
  a display setting on the map, applied pre-refinement, preview-exempt) and
  the Gaussian filter (`volume.py::gaussian_filtered`, FFT, **new map
  object** — never rewrite samples the contour memo caches). The Tools menu
  (Map / Measure / Panels) is a declared extra (`EXTRA_MENUS`) so the
  PyMOL-order test tolerates it; board ticket T-20260811-12 (menu-test
  drift) closed in the same change. Candidates for the next tool round, in
  the reference's volume-filter family: median filter, binning, Laplacian,
  flatten/subtract for background — all the same shape as the Gaussian
  (new-map-from-old);
* **map surfaces have quality presets (2026-08-12):** the reference's
  rendering options ported into `chimol/geometry/refine.py` (its `smooth.cpp`
  and `subdivide.cpp`, NumPy) and named — coarse / normal / smooth / fine —
  in `_VOLUME_QUALITY_PRESETS` (view.py), a panel row, and `volume_quality`.
  The trap if reordered: the refinement pipeline must run subdivide →
  square-mesh mask → smooth, because smoothing destroys the exact coordinate
  identity the mask tests — masking after smoothing silently turns mesh mode
  back into the full-wireframe scribble. Left open: quality presets act on
  contours only (solid mode has its own budget), and the molecular Gaussian
  surface's separate quality system (`surface_quality.py`, another session's
  in-flight work) is untouched — the two "quality" vocabularies could
  eventually meet;
* **the mesh style works now, and the defect was an engine seam worth
  remembering (2026-08-12):** `kind="line"` geometry **ignored its
  `indices`** — `interleave_lines` packed positions raw and the draw counted
  vertices, so the map wireframe (the only *indexed* line geometry in the
  tree) drew chords between array-adjacent welded vertices. Every other line
  builder pre-pairs vertices, which is exactly why the seam stayed invisible;
  an attribute a pipeline silently drops is a bug that waits for its first
  real user. Fixed in the packer; pinned by a unit test. The mesh then got
  the reference's two defaults: square mesh (`_square_mesh_edges`, exact
  coordinate equality, falls back to full wireframe on rotated grids) and
  baked mesh lighting (line pipeline stays unlit by design);
* **`solid` is direct volume rendering now (2026-08-12):** the box-per-voxel
  `voxel` style (user: "make no sense") is replaced by the reference's
  image mode — markers as a colour/opacity transfer function, composited as
  three axis-aligned unlit plane stacks (`_volume_solid_object`, view.py;
  `meta["unlit"]` rides the spare `gauss.w` uniform to an early-out in
  `shading.wgsl`). Known cosmetic: mild banding edge-on to a stack (the
  reference's axis-aligned mode has the same; its fix is view-aligned
  planes off a 3-D texture, which this engine does not have). Two traps if
  retuned: per-plane alpha is sub-1% *by design* — an 8-bit cull erases the
  fog (cull at 1/1024); and the single-marker ramp needs the reference's
  wide foot (transparent at the densest-10% value), not a start at the
  marker, or almost nothing is coloured. The ray tracer still draws solid
  maps as lit geometry — unlit is a raster-shader flag only;
* **the controls themselves are Chimera's now (2026-08-12):** a persistent
  *selected* threshold (gold handle) that the colour well, alpha slider and
  level readout act on; the well opens a palette drawn in the panel (an HSV
  grid, not a system dialog — the panel also runs in the browser); markers
  drag off the histogram to delete (never the last — an empty level list
  falls back to the opening contour and the map would reappear). This
  replaced two defects, both worth remembering as a pattern: the old well
  cycled presets indexed by **marker number** (pressing it repeatedly did
  nothing), and the colour/alpha controls bound to "held, else first" (a
  second contour could never be recoloured after release). If a control acts
  on "the active X", the selection must **survive the mouse release**;
* **the mid-drag→release "pop"** on noisy maps: the preview is a stride-2/3
  *sample*, so it crosses fewer noise voxels than the full-resolution release
  and the surface visibly roughens on release near the noise floor (seen in
  the QA screenshots). ChimeraX's answer is smoothing-free too, so this is
  cosmetic, not a defect — but if it is ever worked, it belongs in the
  preview path, not in a filter applied to the data;
* **the histogram's paint loop** (`density_window._draw_histogram`) still
  issues one `fill_rect` per column (~300/frame). The data behind it is now
  free; the loop is the remaining cost and it is chrome-wide, not
  map-specific;
* **the GPU marching-cubes route** (`compute.marching_cubes_active`) was left
  untouched; it predates this work and its host fallback now outruns small
  grids. Worth re-measuring its decline thresholds (`_declines`) against the
  new host numbers before trusting them;
* tried and *kept out*: ChimeraX's fine-bins-then-rebin histogram (10 000
  bins rebinned to display width) — memoising `np.histogram` per requested
  width has the same cost profile at the panel's one or two widths and stays
  bit-identical to what the tests pin; and a flying-edges port — its win is
  cache locality in compiled row loops, which array-at-a-time NumPy cannot
  express.

**0-ante. `C ▸ by element` is wired to the wrong mechanism, and it is 1 entry
where PyMOL has 49 (filed 2026-08-11, user-reported).** This is not a refusal —
the menu answers, and does the wrong thing: `color byelement, {sele}` sets an
**object-wide colour mode**, so it repaints the whole molecule regardless of the
selection, clears any per-atom overrides on the way, and on a cartoon varies
over CA elements (all carbon) so nothing turns CPK at all. The per-atom
implementation is already in the tree and unused by the menu —
`cmd/presets.py:252` `_color_by_element`, which even takes the `carbon`
argument PyMOL's variants need. Missing entries: `util.cnc` (**CNOS** — colour
H/N/O/S, leave carbon), 8 `util.cba` carbon colours, and sets 2–6
(`junk/pymol-open-source/modules/pymol/menu.py:339-425`). Full diagnosis:
[known-issues](../references/known-issues.md). **Do not** fix it by masking
atoms inside `_apply_color_mode` — `by_residue`/`by_ss`/`by_chain` share that
path and are legitimately per object.

**0-ante-0. Landed 2026-08-11, and what is left of each.** The **measurement
wizard** (Wizard ▸ Measurement) and the **selection levels**
(`mouse_selection_mode`, cycled from the block's Selecting row) both shipped
with tests. Left open on them: the wizard measures within the **active object**
only, because the pick index is into that object's atom table — measuring
between two molecules still needs `distance` with selections; and the levels
omit PyMOL's *Segments* (no segi is parsed — that is the same gap the Label
menu refuses on) and *Molecules*. Two defects found underneath and fixed:
`distance` reported **scene units** (258.450 for 25.845 Å) and drew its dashes
in the wrong place, and residue ids are **not unique across chains**, which the
selection had been matching on alone. Both in
[known-issues](../references/known-issues.md), both with guardrails.

**0-ante-bis. The mutagenesis wizard leaves a stale `mutation` row in the
Sequence strip (filed 2026-08-11, user-reported, screenshot).** The preview
object is correct and PyMOL-faithful; the refresh order is not. `_wizard_finish`
refreshes the sequence view *inside* `_wizard_commit` — while the preview still
exists — then deletes it and never refreshes again. Check first why the *object
panel* is clean in the same screenshot; that asymmetry is the part the
hypothesis does not explain. Details in
[known-issues](../references/known-issues.md).

**0. The refusals are the worklist — six were stale in one day (2026-08-07).**
Start here, because it is the cheapest parity there is: chimol repeatedly has
the capability and still tells the user it does not. Six found in one sweep —
`origin`, `cell` (which was also *broken*, resolving symmetry differently from
`symexp`), `generate ▸ symmetry mates`, `A ▸ hydrogens ▸ add`,
`donors`/`acceptors`, `byring` — every one refusing on behalf of a command,
keyword or analysis that already existed. **Capability and surface land
separately and nothing pairs them up again.**

Two lists hold the remaining refusals and both are worth re-reading whenever
that area is touched:

* `DISABLED_ENTRIES` in `test/test_menu_coverage.py` — 21 menu leaves. The test
  fails both ways, so one that gains a command has to be struck;
* `_UNSUPPORTED_FLAGS` in `cmd/sele_parser.py` — the selector's equivalent.
  What is left there is genuine: `delocalized`, `flag`, `text_type`, the
  sculpting flags, the picking mask, and the `center`/`origin` pseudo-atoms.

**0-bis. Valence display: half done, and the half that is left is the wiring.**
`S/H ▸ valence` needs bond orders. Two of the three pieces landed on
2026-08-07 and are tested on their own; **nothing is user-visible yet**, which
is the state to pick up from:

* **done** — `analysis/bond_orders.py`, the bond-order half of
  `assign_pdb_known_residue` transcribed (C=O for any protein residue, ARG
  CZ=NH1 with CZ-NH2 forced back to single, the carboxylates, both histidine
  tautomers by residue name, the Kekulé rings, the nucleobases, P=O1P).
  `assign_bond_orders(atoms, bond_pairs)` gives **258 doubles of 1384 bonds on
  148L in 4 ms**, 3564 of 18434 on 1RTD in 50 ms;
* **done** — `geometry/wireframe.py`: `valence_offsets()` and an `orders=`
  argument on `bond_line_segments`, which appends a second line *beside* each
  double bond, offset towards the rest of the molecule so it falls **inside** a
  ring (PyMOL's `valence_mode 1`). Verified inward on a benzene; a bond whose
  atoms have no other neighbour falls back to any perpendicular rather than
  drawing on top of itself. 13 tests in `test/test_bond_orders.py`;
* **open** — the wiring, in this order:
  1. compute the orders where bonds are inferred (`MolView._infer_bonds`, and
     the payload path for files that carry bonds) and keep them on the object
     state beside `bond_pairs`, or the renderer recomputes per frame;
  2. a `valence` setting (bool) plus `valence_size` (0.06) in `_DISPLAY_CONFIG`,
     reachable as `set valence, on`. PyMOL's own menu uses **`set_bond`**, a
     per-bond setting chimol has no equivalent of — a global/per-object setting
     is the chimol spelling and should be said so in the docs;
  3. `_update_lines` passes `orders=` when the setting is on;
  4. **sticks too, or say why not.** PyMOL draws valence in both
     (`stick_valence_scale`); shipping lines only is a half-answer and the menu
     entry would be lying about sticks;
  5. strike `S > valence` and `H > valence` from `DISABLED_ENTRIES`, and
     screenshot a tyrosine and a guanine before accepting — this is exactly the
     kind of change that looks right in a mesh count and wrong in a picture.

**0a. Anything a user types into needs a test that types into it.** Not a task
— a standing correction, and it belongs first because it is what let two total
failures sit behind a green suite. Every test of the command layer drove
`_run_object_menu_command`, the menu path; the **console** was untested, and
every no-argument command in it was unreachable (see the 2026-08-06 log entry).
Likewise the shift+wheel test built its own `QWheelEvent` with a `y` delta and
passed, on a platform that only ever delivers `x`. Both were reported by the
user against a build whose suite was green. `test/console/test_command_dispatch_rule.py`
is the pattern: construct the real window, `setText` into the real input line,
submit, assert on the resulting objects. Where a platform transforms an event —
macOS shift+scroll, trackpad sub-notch deltas — the test has to carry the
platform's shape, not the API's.

**0b. Run the tests that cover the file you edited — and read the picture, not
the mesh count.** Also a standing correction rather than a task, and the third
in a row that a green suite did not catch. On 2026-08-06 a rung-drawing block
landed in the wrong cartoon function and `NameError`-ed every protein cartoon
with secondary structure; `test_cartoon_geometry.py` already covered it in six
tests and was simply not run before the commit. The nucleic tests stayed green
because the nucleic builder calls the protein one with `ss_codes=None`, which
returns early two lines above the fault — **a test that reaches a function
through a different door is not coverage of that door.**

The picture half is separate and cost as much. `show cartoon, <sele>` reported
success, produced a plausible triangle count and rendered the *whole structure*;
it was visible only in the PNG, and only because the render was taken for an
unrelated reason. When judging a representation, count the entities the mask
names (`state.cartoon_mask.sum()` against the residues the selection should
cover) — a mesh count cannot distinguish "the selection" from "everything", and
a mask is where the two differ.

**0a-bis. The PyMOL source is now a ranked worklist, so "what next" is a
command.** Every file in the reading preset (480) carries a
`CHISURF-VALUE: <rank> <facets> -- …` header; 25 are read, the rest are
triaged. `python -m build_tools.dev_utils.reference_coverage
junk/pymol-open-source --rank A` prints the 36 that matter, and the report
prints A and B with the coverage table. The A-list clusters, and the clusters
are the shape of the remaining work:

* **the overlay GUI chimol hand-rolled**: `layer0/Block.{cpp,h}` (the widget
  base class every panel derives from), `layer1/Ortho.cpp` (the block stack,
  who gets a click, the command line), `layer1/Seq.cpp` +
  `layer3/Seeker.cpp` (the sequence viewer, drawn and driven),
  `layer1/Control.cpp` (the transport and the idle policy),
  `layer1/ButMode.cpp`, `layer3/SpecRec.h` (a panel row as a data type);
* **the UX chimol has none of**: `modules/pymol/_gui.py` — the entire desktop
  menu bar *as data*, which is how the object menus were generated and how the
  menu bar should be — plus `keyboard.py`, `shortcut_manager.py`,
  `completing.py` (tab completion), and `pmg_qt/keymapping.py` +
  `pymol_gl_widget.py`, which carry the two platform traps already hit once
  each (Meta-is-Ctrl on macOS, shift+wheel arriving as `angleDelta().x()`);
* **representations**: `RepCartoon.cpp` (4.3k lines, 67 settings),
  `RepLabel.cpp` (the whole disabled L menu), `RepSphere.cpp` (`sphere_mode`),
  `layer1/Extrude.cpp` (where the cartoon's shape comes from),
  `ObjectVolume.cpp`;
* **data**: `CifMoleculeReader.cpp` + `CifBondDict.h`, which together unblock
  `valence`; `AtomInfo.cpp`; `ObjectMolecule.cpp`;
* ~~**one small file that closes three menu entries**: `layer3/Interactions.h`~~
  — done 2026-08-07, see *the three disabled `find` entries are closed* below.

**0b-bis. A unit test that calls the widget's handler directly cannot see a
dead event path.** Standing correction, from 2026-08-06 and the same family as
0a. `InternalGui.mouse_move` was covered and correct, and *nothing called it*:
the GL widget had no `setMouseTracking(True)`, so Qt delivered a move only while
a button was down and every hover behaviour of the in-viewport panel was dead in
the app while green in the suite. Where a behaviour depends on Qt choosing to
deliver an event — mouse tracking, focus policy, wheel phase, drag thresholds —
the test has to **send the event to the widget**, as
`test_mouse_selection.py`'s viewport tests do, not call the handler. Two of the
three box-select faults found the same day were of this shape.

**0c. `ray` framed the widget, not the viewport — fixed 2026-08-07.** The
symptom was "`orient` then `ray` puts the molecule off-centre and small", and
it was neither the camera nor the tracer: `ray` with no size defaulted to the
**whole GL widget**, while the viewport draws the scene into what is left after
the panel's column and the sequence viewer's band. So the trace covered a wider
field than the screen, and centred the molecule in it, while the viewport
centres it in the narrower column. Measured on a 998x583 widget: the molecule
filled **59 %** of the traced width against **70 %** on screen, and sat right of
where the user saw it.

PyMOL says the default is taken "from the current viewpoint", which is that same
rectangle, and adds a second rule chimol also had wrong: given one dimension the
other "is scaled so as to preserve the current aspect ratio" — chimol used a
fixed 4:3. `MolView.scene_pixel_size()` now answers the question in device
pixels (so a default trace and a screenshot match on a retina display) and
`ray` uses it for both. After: the molecule's bounding box agrees with the
viewport's to **0.003 of the frame** in every direction; the residual coverage
difference (0.110 vs 0.088) is shading and anti-aliasing, not framing. Two tests
in `test_ray_command.py`.

A measurement trap worth keeping: judging this needs the colour mask, not a
brightness threshold. The viewport grab contains the panel's chrome, which is
bright and reaches the edges, so a `> 25` mask reports the molecule's bounding
box as the whole image and both framings look identical.

**0d. "It got dark" is a camera report, and "it is slow" is rarely arithmetic.**
Two standing corrections from the mutagenesis wizard, both of which cost an hour
of looking in the wrong place. A screenshot that goes dark after an interaction
reads as a lighting or occlusion regression, so that is what was instrumented —
and the instrumentation proved the scene data identical across steps
(`n_objects 7 {'mesh': (3, 0.398), 'points': (1, 0.6), 'line': (3, 0.47)}` before
and after). The molecule was **receding**: adding an object moves the scene
centre and a state change re-derives the radius, so the camera drifts and the
frame dims because the subject is leaving. Check the view state before the
renderer. Second: the response to a slow interaction was "use numba", and the
arithmetic was 125 ms of a 2.2 s step — the rest was rebuilding and re-baking
occlusion for atoms that had not moved. **Time the parts before choosing a
faster language for one of them**; here the fix was PyMOL's data model (states),
which took the step to 32 ms with the same Python.

**0. A trajectory that is a simulation — landed, with one thing left.** See
*[A frame carries more than coordinates](#a-frame-carries-more-than-coordinates)*
below. What is **open**: the depiction is spheres only, so the buried strata are
visible from outside a mound but not through it. PyMOL's answer is `clip slab`,
which chimol has; a cut-away demo beat was left out because a demo script runs to
completion before `mplay` returns, so it would have to come *before* playback or
be a second entry. Also unmeasured: whether the per-frame read is affordable on a
model the size of the pore — it is `O(frames x particles)` Python calls, and the
only reason it is cheap today is that a static file has one frame. If a large
multi-frame RMF appears, measure before assuming.

**1. Settings — the standout gap, and it has a measured worklist.** 790 in
PyMOL, 55 registered here. The raw remainder (735) is misleading: most of it is
sculpting, roving, stereo, movie, shader and session bookkeeping that does not
apply. What matters is the **228 that PyMOL's own Python layer references**,
which is the closest available proxy for real-world use. Re-derive it with:

* parse `layer1/SettingInfo.h` for `REC_<x>(idx, name, level, default)` — **strip
  `/* … */` comments first**, or ~20 records with trailing comments are silently
  missed and the total reads 770 instead of 790; `REC__` is a retired slot;
* count each name's occurrences under `modules/pymol/` and `modules/pmg_tk/`;
* subtract `chimol.settings.setting_names()`.

The appearance-bearing names at the top of that ranking, which is where to
start: `transparency`, `surface_color`, `surface_type`, `two_sided_lighting`,
`stick_color`, `ribbon_color`, `stick_ball`, `sphere_mode`, `valence`,
`light`, and the `util.py` lighting family (`specular_intensity`,
`spec_direct`, `spec_count`, `reflect`, `power`, `ray_shadow_decay_factor`).
`cartoon_highlight_color` and `cartoon_fancy_helices` are the two the `pretty`
and `publication` presets still report as skipped. The `dash_*` family and the
six `h_bond_*` came off this list with the polar-contact finder, and
`transparency` / `two_sided_lighting` with the surface work -- which leaves
`surface_color`, `surface_type`, `stick_color`, `ribbon_color`, `stick_ball`,
`sphere_mode`, `valence` and the `util.py` lighting family at the top.

**The first three of that ranking have landed** -- `stick_color`,
`cartoon_color` and `surface_color`, which are one mechanism under three names:
PyMOL implements each with the same line in its own representation,
`c != cColorDefault ? c : ai->color`, where the sentinel is the integer -1.
chimol stores the absence of an override as `None` (a negative number is not a
colour and a config full of -1 says nothing to whoever reads it) and accepts
`-1`, `default`, `none` and `atom` to clear it. Two things the implementation
turned on:

* the override is read **where the representation assembles its colours**, not
  folded into the shared per-residue array -- that array feeds the cartoon *and*
  the trace, so one fold would colour both;
* the colour *parser* had to move. It lived in the command layer, and the
  renderer cannot call that, so `colors.as_rgba` is the shared reader now --
  names, hex and sequences. The command layer keeps the part that is session
  state (colours defined with `set_color`).

`ribbon_color` is **deliberately not registered**. chimol has no separate ribbon
representation -- `show ribbon` already aliases the cartoon -- so the name would
colour something other than what a PyMOL user means by it. Decide that
deliberately rather than by accident.

`surface_quality` **is fixed** -- it was three defects wearing one name, and the
finding generalises: a registered setting with a live config path and a passing
test still had no effect at all. Before registering more names, **count what the
setting produces**, not whether it stores.

**`valence` is blocked, and on data rather than on drawing.** It is high on the
ranking and the algorithm is straightforward -- `RepValence` in
`layer2/RepWireBond.cpp` builds a local frame from the bond direction and a
*prioritized third atom* for planarity, then draws the centre line plus one
inset parallel line (`valence_mode 1`, "fancy"), or two symmetric lines when
that mode is off; a triple doubles the offset and keeps the centre. All
transcribable. What stops it is that **chimol has no bond orders**:
`MolView.bond_order` returns 1 for everything except a bond made by hand with
the `bond` command, because bonds are inferred from distance and a distance
carries no order. So `set valence, on` would leave every deposited structure
looking exactly as it does now, which is the "accepted and inert" failure this
table exists to prevent.

Unblocking it means reading orders from somewhere: mmCIF's `chem_comp_bond` has
them for ligands (which is where a double bond is actually wanted), a PDB's
`CONECT` does not, and perception from geometry is the third option. That is a
reader change, not a settings change -- do it first, then `valence` is small.

**Register a name only if code reads it** — a setting that reads nothing is what
the settings table exists to prevent, and it is why the three cartoon settings
above are absent rather than accepted-and-ignored.

**1a. DONE — the two-stores blocker is cleared, and it was three.** This was
the thing that would have made the next twenty registrations silently useless,
so it came first. All three are closed:

* `silhouette` / `silhouette_thickness` / `depth_jump` lived on the renderer's
  `_post` object **and** in `_DISPLAY_CONFIG["silhouette"]`, which was read only
  in `QtGLRenderer.__init__`. `PostProcess` reads the section through properties
  now — one store, read where it is used — so `lighting silhouette=on` and
  `set silhouette, on` are the same write, and an already-open viewer sees it.
  The four names are registered.
* `depth_cue` / `fog` / `fog_start` were registered against `ray.*` while
  driving **both** renderers. They are `depth_cue.enabled` / `.intensity` /
  `.start` now. The move needed the loader extension this predicted:
  `DISPLAY_CONFIG_MIGRATIONS` can only change a *value*, so
  `DISPLAY_CONFIG_KEY_MOVES` was added beside it. Its rule is the **mirror
  image** of a value migration and worth stating: a value migration moves what
  the user did *not* choose (it still equals the old default), a key move
  carries across what they *did*, and drops the old key either way so the
  section it left keeps no stale twin.
* the third was found by walking into it: **`bg_color` versus `ray`**, described
  below. `bg_color` writes to the renderer and `ray` read the configuration, so
  every traced figure came out on the background the session *started* with.

**The pattern to reuse** is `_fog_planes`: read the configuration where the
value is *used*, never at construction. Everything that failed here failed by
caching it somewhere a later `set` could not reach.

**2. Rendering.** One measured defect left in the ray tracer.

*Meshes are double-shaded* — occlusion and cast shadow are baked into the vertex
colours and then shaded again, costing 44 % of the colour. Described under
*`ray` renders the scene, not the molecule*. **This is the last known wrong thing
in the traced picture**: speed, transparency, the depth cue, and mesh shadows are
all closed, so the tracer's remaining gap is one of shading rather than of
capability.

*Nothing but a sphere casts a shadow.* **Done** — see *a cartoon casts a shadow
now* below. So is the darkness: `ray` was missing PyMOL's `direct` headlight term
entirely and came out 30 % below the viewport; it is now within 2 %.

*Does `ray` frame the molecule as the viewport does?* **Open, and unmeasured** —
this is where to start, because it is the one thing a user would still see. It
came up while checking the brightness fix: the traced molecule looked smaller in
the frame than the viewport's. **Both attempts to measure it were wrong**, and
the way they were wrong is the useful part. A whole-frame correlation said
"no difference" (0.93 as-is against 0.20 flipped) — worthless, because ~90 % of
both images is black background and the agreement is background-on-background. A
brightness-threshold bounding box then said the viewport's molecule spans the
entire frame — also worthless, because the object panel and the mouse-mode text
are drawn *inside* the GL widget and the threshold counts them as molecule. Redo
it masked to the scene column, on silhouette bounding boxes, with the chrome
hidden rather than cropped around.

**Transparency is done** — see *the tracer walks through a surface* below — and
so is **speed**: `ray` was 143–651× slower than it needed to be.

**3. Tier 2 leftovers**, in rough order of use: `matrix_copy`, `ramp_new`,
`cartoon_dumbbell`, `ellipsoid`, `slice`. **`cell` is done** -- and drawing the
box is what exposed that `symexp` had never worked: see *the mates were all in
the same place* below.

# What has been mined, and how to tell

**The question this answers:** ChiMOL is built by reading PyMOL's source and
transcribing it, so the useful thing to know is *which parts have already been
read* -- otherwise the same file is re-read by the next session and "is the
source exhausted?" has no answer. As of 2026-08-06 it is **14 files of 461**
(3.0 %) across the layers that matter. Nowhere near exhausted.

**Editing the reference checkouts is sanctioned, for the header only** -- and
this is a **general rule for everything in `junk/`**, not a chimol one: see
[reference checkouts](../workflows/reference-checkouts.md), which owns the
format, and `CLAUDE.md`. A marker goes at the top of each file that has been
read, so it is found by whoever opens the file rather than by whoever thinks to
search here:

```c
/*
 * CHISURF-REVIEWED: 2026-08-06
 * CHISURF-TAKEN: cSetting_stick_color -> renderer/view.py::_representation_color
 * CHISURF-SKIPPED: cSetting_valence -- chimol has no bond orders
 * CHISURF-RECORD: okf/plugins/pymol-parity.md
 * Header added by ChiSurf; the code below is untouched.
 */
```

The same applies to the ChimeraX checkout. **Never touch the code** -- only the
header -- so that `git diff` inside the checkout stays readable (it should show
insertions and *zero deletions*) and the file keeps saying what the reference
does.

**`SKIPPED` matters as much as `TAKEN`.** "Read and deliberately not taken, for
this reason" is the expensive knowledge: without it the next session re-reads
the file, reaches the same conclusion, and pays again -- which is exactly what
happened with `valence`.

**This concept is the record; the markers are an index.** `junk/` is gitignored
and re-clonable, so a re-clone loses every marker and loses nothing else. That
is why each marker points back here, and why the coverage tool reports a fresh
checkout as 0 % -- which is the honest reading of "nobody has looked at this
one".

Measure it with:

```bash
python -m build_tools.dev_utils.reference_coverage --all
python -m build_tools.dev_utils.reference_coverage junk/pymol-open-source
python -m build_tools.dev_utils.reference_coverage junk/pymol-open-source --unreviewed layer2
python -m build_tools.dev_utils.reference_coverage junk/ChimeraX
```

The denominator is the directories the parity work actually reads (`layer0`-`layer5`,
`modules/pymol`) rather than the whole tree: PyMOL is ~3000 files, most of them
build glue and bundled dependencies, and counting those would hold coverage near
zero for ever and tell nobody anything.

## Which reference answers which question

**PyMOL is the authority on the GUI and the UX; ChimeraX is the authority on
functionality.** (User instruction, 2026-08-06; it supersedes the earlier
"ChimeraX for rendering only".) The reason is what each does well: PyMOL's
interface is the one structural biologists have in their fingers, so matching it
is what makes ChiMOL usable without being learned — while ChimeraX has the
larger *capability* surface, and is where to look for what a viewer should be
able to **do**.

### ChimeraX for functionality — the measured gap

`src/bundles/std_commands/src` holds **71** commands. **36** are covered by a
ChiMOL command already (under PyMOL's spelling: `cofr` is `origin`, `zonesel` is
`select … within`, `sym` is `symexp`, `coordset` is `mset`/`mplay`). **35 are
not**, and they group into five kinds:

| Gap | Commands | Worth |
| --- | --- | --- |
| **Measurement** | ~~`measure_buriedarea`~~ ~~`measure_center`~~ ~~`measure_inertia`~~ ~~`measure_weight`~~ · `measure_convexity` `measure_correlation` `measure_rotation` `measure_symmetry` | **Four landed** (2026-08-06); four left. The mass table that blocked `measure_weight` is transcribed, so `measure_inertia` is mass-weighted as ChimeraX's is. `measure_correlation` needs the map reader wired to the atom set and is the next worth doing. |
| **Colour and attributes** | `palette` `colorname` `rainbow` `defattr` `setattr` | `defattr` — assign a per-atom attribute *from a file* and colour by it — is the one that unlocks the rest, and is close to `alter` plus `spectrum b`. |
| **Appearance** | `material` `size` `style` `tile` `axis` `windowsize` | `tile` (lay every open structure out on a grid) is the cheapest big win for comparing models, which is what ChiSurf produces. |
| **Movie** | `crossfade` `perframe` `fly` `roll` `wobble` `time` `wait` | ChiMOL has `mplay`/`mset`/`mview`. `perframe` (run a command each frame) is the general one and would subsume several. |
| **Session/env** | `alias` `runscript` `altlocs` `cd` `pwd` `version` `move_cofr` | `alias` and `altlocs` are the two with real content. |

Re-derive with `analysis/reference_coverage.py` plus the command scan in
`test/test_reference_coverage.py`.

### PyMOL for the GUI and the UX — what its Qt front end has

`modules/pmg_qt` is **6812 lines** across a dozen widgets, and it is the right
reference because it is the Qt interface, not the retired Tk one. Read as a
survey; nothing here is transcribed yet:

| File | Lines | What it is | ChiMOL |
| --- | --- | --- | --- |
| `builder.py` | 1579 | molecular builder: fragments, valence editing | absent, and out of scope for now |
| `pymol_qt_gui.py` | 1267 | the main window, menu bar, the command line's history | ChiMOL's is closer to this than to the Tk one |
| `volume.py` | 877 | the volume-ramp editor: drag colour/alpha stops over a histogram | absent — ChiMOL contours by level only |
| `file_dialogs.py` | 855 | format-aware open/save | partly |
| `shortcut_menu_gui.py` | 415 | **editable keyboard shortcuts**, presented as a menu | absent |
| `properties_dialog.py` | 415 | per-atom property inspector | absent |
| `scene_bin_gui.py` | 397 | scene thumbnails as a strip | ChiMOL stores scenes, shows no bin |
| `advanced_settings_gui.py` | 92 | **every setting in one filterable table** | absent — and this is the standout |

**The standout is the settings table**, and the reason is arithmetic: ChiMOL has
**79 registered settings** and the only way to reach any of them is to know its
name and type `set`. PyMOL's answer is 92 lines — a filter box over a
two-column table, booleans as check boxes, everything else editable in place,
the description as the tooltip. Everything it needs, ChiMOL already has:
`iter_settings()` yields the name, the value, the type and a one-line doc.

**A note for whoever needs PyMOL's source:** `junk/pymol-open-source` is the
authority on behaviour and **is present**. A 2026-08-06 session briefly found it
missing and recorded that it had been deleted -- it had not; the directory was
unreadable for a few minutes, most likely while another instance re-cloned it,
and `clone.sh` skips what is already there. `junk/clone.sh` restores it if it
ever really goes. Nothing here should be transcribed from memory; the entries
that were, were wrong.

**4. The other `distance` modes.** 0–4 are done; 5–7 (π–π, π–cation), 9
(halogen bonds) and 10 (salt bridges) are not, and the **A ▸ find** submenu
shows each disabled with that reason. They are separate detectors, not
variations on the hydrogen-bond test: PyMOL keeps 5–7 in its incentive build and
implements 9/10 in `layer3/Interactions.cpp`, which is the file to read. The
plumbing they would need — a multi-segment dashed measurement, the combined
atom table, the settings — is now in place, so each is its own small predicate
rather than a new subsystem.

**Two smaller things the polar-contact work left measured but not done.** The
contact object is not a real *object*: it does not appear in the panel, cannot
be enabled/disabled or deleted by name, and `hide everything` does not touch it
(PyMOL's `dist` creates an `ObjectDist` that the panel lists). And with
`label=1` the numbers overlap badly on anything denser than a few contacts —
PyMOL has the same problem and answers it by having every preset pass
`label=0`, which is what chimol does too.

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
| Selection *scope* | **done** | Every object, as PyMOL's one atom table; groups included |
| `save` (PDB/mmCIF export) | **done** | Writes what the viewer holds, not the source file |
| `label` | **done** | Expression language, not templates; `L` menu now live |
| `create` / `extract` | **done** | Child drawn in its parent's frame, true coordinates kept |
| `origin` | **done** | Needed the two-point camera the view tuple defines |
| Undo / redo | **done** | PyMOL's scope: coordinates, per object, ring of 16 |
| Sessions (`save`/`load` a whole state) | **done** | Own zip format, not PyMOL's pickled `.pse` |

**Tier 1 is closed.** Everything a day's work touches is present. What follows is
Tier 2, which is real but has workarounds.

## The menus were never tested, and five were broken

The A/S/H/L/C menus are how most people drive the viewer, and nothing tested them:
the *command* layer was covered, the menus were not. Firing all 138 entries through
`MolViewPluginWindow._run_object_menu_command` — the path a click takes — found five
broken at once:

| Entry | What happened |
| --- | --- |
| A: remove waters | **crashed** on any structure that had waters |
| A: delete object | reading state from the emptied viewer raised, so the next repaint died |
| A: copy to object | template arguments reversed: it copied *from* the name typed |
| C: by element / by chain | menu writes `byelement`; `color` only knew `by_element` |
| C: tints > yellowtint | not a PyMOL colour at all — the menu invented it |

All five fixed, and the sweep is now a test: 157 cases, every entry plus a check
that each disabled entry explains itself.

A sixth was found later, and only by clicking in the *viewport* panel: an entry
needing a typed value (`rename object`, `copy to object`, `align to ...`) was
**skipped there** — `_emit` dropped any template carrying `{text}`, on the
grounds that there is nowhere in the viewport to type. That is a menu entry that
does nothing when clicked, in the panel that is now the primary one. Those
entries write themselves into the command line instead, with the placeholder
selected so the next keystroke replaces it; the command line is one row below
the panel. The sweep test could not have caught it, because it drives the
*docked* panel's path.

The sweep also turned out to be **passing two entries that did nothing**, and
only the new unknown-name error exposed it: it filled every `{text}` with the
literal `copied`, which is right for `copy to object` (a name for something the
command creates) and wrong for `align to ...` / `super to ...`, where the slot
is a *target selection that must already exist*. A made-up name resolved to an
empty mask, so both commands returned quietly and the assertion held. The filler
now picks a value that suits the slot. The lesson is the file's recurring one:
**a fixture is an assertion too, and nothing checks it.**

**Why they survived.** Every structure in the test data was a protein with no
waters and no ions, so nothing could exercise the entries that act on them. Added
`solvated_fragment.pdb` — six residues, a zinc, eight waters — small enough that
150 window loads run in 23 seconds.

## One missing line made every passive gesture dead

Reported against the viewport panel as "submenus overlap and never collapse".
Three faults, and the root of two of them was that **the GL widget never called
`setMouseTracking(True)`**. Qt delivers a mouse move to a widget without
tracking *only while a button is down*, so nothing the panel does on hover ran:
no row or menu-entry highlight, and no hover-open of a submenu. A submenu could
therefore only be opened by clicking it — and, since nothing ever told the panel
the cursor had moved on, it then stayed open until a command closed the menu.
The pile of overlapping boxes in the report is that: several submenus opened by
click, none of them closed. **A handler that is written and never invoked looks
exactly like a handler that is wrong**; the panel's `mouse_move` was correct and
untested through the widget, because the unit tests call it directly.

The other two are transcribed from `layer4/PopUp.cpp` and `layer1/Pop.cpp`:

* **placement.** PyMOL's `PopPlaceChild` tries the preferred side, and if the
  child had to be *shoved back on screen* to fit there, flips to the other side
  and tries again; the side it settled on (`PlacementAffinity`) is inherited by
  its own children so a chain that went left keeps going left. Ours clamped the
  child into the window instead of flipping — and the panel is docked against
  the right edge, so a submenu opened rightward never fits and was clamped
  straight on top of the parent it came from. The child's first *entry*, not its
  title, lines up with the row it hangs off, which is PyMOL's `target_y`
  correction.
* **collapse.** PyMOL's `CPopUp::drag` frees the child as soon as the cursor is
  on a different row of the parent, and walks back up to the parent when the
  cursor re-enters it. One deliberate difference: PyMOL delays that by
  `cChildDelay` (0.25 s) so sloppy diagonal mousing does not lose the submenu,
  and chimol closes immediately, as Qt menus do. It is affordable here because
  the child is placed *adjacent* to the row, so the diagonal is a few pixels;
  add the delay if that changes.

A submenu is now identified by the parent **entry** it hangs off, held by
identity, rather than by its label: `by element` opens a menu whose only entry
is also `by element`, and the label match kept the wrong one open.

**And a long menu scrolls; it does not wrap into columns.** Reported next, as
"the arrangement of the menu does not make sense": on a small window the Action
menu broke into two columns, and a column break lands wherever the window
height happens to put it — so `zoom orient center origin | copy to object
group delete object` read as one list snapped in an arbitrary place. The
separators were dropped on top of that, to keep the two columns aligned, which
removed the grouping that is most of what a menu's order says. PyMOL never
wraps: `CPopUp::release` takes the scroll buttons and `Block::translate`s the
pop-up, one column always. Ours does the same, with two deliberate
improvements over it: the wheel moves by a **row** rather than PyMOL's ten
pixels (ten is not a multiple of the row height, so every notch sliced the
rows at both edges), snapping to the nearest entry boundary because a
five-pixel separator puts the entries below it off the row grid; and the title
row carries `▴▾` when there is more in that direction, since a menu silently
cut off at the window edge is the fault the column-wrapping was trying to
answer. A scrolled-out row keeps its rectangle — it is the same list the
painter walks — so hit-testing tests visibility too, or the menu would take
clicks through its own title.

**The panel is also drawn from startup now**, `all` and `sele` in it and nothing
loaded, as PyMOL's is. Two things kept it away: the overlay pass was gated on the
panel having *rows*, while `scene_width` gives the column away to a merely
*visible* panel — so an empty window had a black stripe down its right-hand side
rather than a saved column — and `sync_internal_gui` was called only when an
object arrived, so the panel had not been handed its `run_command` either.

## Rectangle selection: three ways to not work

Same report, same session. The box select worked in the tests and not in the
app, three times over:

* **the release only ever ended a box for the left button.** `-Box` is
  shift-*middle* in every three-button mode and shift-*right* in the two-button
  ones, so that drag never completed: nothing was subtracted, the band stayed on
  the glass and `_drag_selecting` stayed set — which swallowed every later drag
  of the session into a box that could not be finished either. One stuck flag,
  and from the user's side *every* mouse gesture stops working. The press now
  records which button started the box and the matching release ends it, and the
  right button consults the mode table before its dolly-vs-menu deferral.
* **the selection was applied and never drawn.** `handle_mouse_click` called
  `_update_view()` after merging; `handle_rect_selection` did not. The sequence
  strip is repainted every frame so it showed the new selection, and the
  molecule — where the rings are — did not, until something unrelated rebuilt
  the scene. The redraw now lives in `_apply_selection_indices`, the one place
  the selection changes, and only when it actually changed.
* **the band was a `QRubberBand` child of the GL widget**, which `grab()` cannot
  see, so no screenshot of a box select ever contained a box. It is drawn in the
  overlay painter now, beside the panel and the labels.

`box` — Maestro's plain-left cell — was also the one box action the press did
not recognise, so the block on screen named a gesture the widget did not start.

## Networks, clashes and mutation: what PyMOL half-answers

Three requests in one, and each is a different relationship to PyMOL.

**Hydrogen-bond networks are not PyMOL's at all.** It finds polar contacts
(`distance ..., mode=2`, already transcribed) and draws them as one
undifferentiated bundle; which of them belong together is left to the eye, and
the eye is exactly what misses a four-bond water-mediated path. So the contacts
are unchanged and the grouping is new: connected components over "these two
bonds share an atom", each drawn in its own colour, each described by what it
spans — bonds, residues, waters, and whether it crosses chains, which is what
makes an interface network worth a second look. Three water policies, because
either default is misleading: a water may **bridge** two halves, be **excluded**
(the protein's own network), or be all there is (**only**, the wire). ChimeraX
does not name a network either; its `hbonds` returns a list.

**The three disabled `find` entries are closed — 2026-08-07.** Halogen bonds,
salt bridges and pi interactions were the *"one small file that closes three
menu entries"* on the A-list, and `layer3/Interactions.{h,cpp}` is indeed the
whole of it: the criteria are literals and the algorithms are a page each. They
are reached exactly as PyMOL reaches them — `distance ... mode=9` / `mode=10` /
`mode=5,6,7`, plus the `pi_interactions` command its own menu calls — so the
menu entries carry PyMOL's command strings unchanged.

The load-bearing part is not any of the three finders: it is **formal charge**.
A salt bridge is *"two heavy atoms of opposite formal charge within 5 Å"* and a
pi-cation needs *"formal charge above zero"*, and a PDB file carries neither.
PyMOL fills it in from nomenclature while it connects the molecule
(`assign_pdb_known_residue`), and that table is transcribed rather than
re-derived because its asymmetries are the correctness:

* **one** oxygen of a carboxylate (`OD2`, `OE2`) and **one** nitrogen of a
  guanidinium (`NH1`, with `NH2` pinned to zero — PyMOL's own PYMOL-5019 fix).
  Charging both halves is the obvious improvement and it double-counts every
  bridge;
* **a plain `HIS` is neutral.** Only `HIP`/`HISP`/`HISH` carry the charge, so a
  HIS–ASP pair is not reported. That is a protonation-state decision PyMOL
  declines to make, and inheriting the refusal is the right call;
* nucleotide `OP2`/`O2P`, which is what makes DNA phosphate contacts findable.

Measured: 148L gives **10 salt bridges** (2.8–4.8 Å) and 1RTD **129**, with 71
pi interactions of which 17 are face-to-face — consecutive and cross-strand DNA
bases at 3.5–4.2 Å, which is base stacking and is the check that the pi arm
works. 148L has **no** pi-pi at all: its closest aromatic pair is 5.9 Å apart,
past the 5.5 Å bound, so zero is the right answer and a finder that reported
something there would be wrong.

Two things worth keeping:

* **the vector conventions are a silent trap.** `TestHalogenBondDonor` takes
  X→A and X→D, both pointing *away* from the atom whose angle is measured.
  Reversing either measures 180 minus the angle meant, which passes a bent
  geometry and rejects a straight one — and it reads perfectly plausibly. It
  was caught only because the test built its geometry from the angle it wanted;
* **a ring is planar because a template says so, or because its hydrogens make
  it measurable.** A two-neighbour carbon carries no angle that separates sp2
  from sp3, so a ligand ring in a hydrogen-less PDB is missed. The first reading
  of this recorded it as a chimol gap against PyMOL — **it is not**. Checked
  against the source afterwards: `ObjectMoleculeGetAtomGeometry` returns
  *unknown* for two neighbours in PyMOL too (only `nn == 3` runs the cross
  products, `nn == 2` detects linear and nothing else), and
  `InferChemFromBonds` has no bond orders to consume for a PDB ligand either.
  Measured on built geometry: two stacked benzenes give **0 planar atoms and no
  stacking without hydrogens, 12 planar atoms and a face-to-face pair with
  them**. So the answer for a user is to load the hydrogenated structure, not to
  wait for bond orders — and the *real* open item is `h_add`, which chimol does
  not have (A ▸ hydrogens ▸ add is one of the 22 disabled entries).

22 tests in `test_interaction_finders.py`. The angle criteria are tested on
built geometry rather than on a structure: 148L has no halogen at all, and a
bound that is two-sided (the 90–170° acceptor angle) cannot be shown to have
both halves by a structure that happens to pass.

**Three more `find`/`A` entries, and one that was lying — 2026-08-07.**
`interchain_distances` (PyMOL's `util.interchain_distances`) runs a distance
search over every pair of chains and collects them under one name; on 1RTD's
eight chains that is 28 pairs, 141 contacts at 4 Å or 190 polar ones. It needed
`_distance_set` split into `_distance_segments`, because PyMOL accumulates into
a named distance object across calls and chimol's named measurements *replace*
— so the accumulation has to happen before the drawing. Typing the molecule
once for the polar mode rather than once per pair took it from **5.4 s to 2.4
s**; the per-call `type_atoms` was 28 passes over 17784 atoms for an answer that
cannot change between them.

`disulfides` is PyMOL's own selection expression verbatim — `byres` over the
`SG` atoms that are `bound_to` another `SG`, narrowed to `CA+CB+SG` — which
chimol's selector already answers. The `bound_to` is the whole of it: without
it the entry shows every cysteine.

And **`origin` was disabled with a reason that had stopped being true.** The
command has existed in `rendering.py` for some time; the menu said "chimol
rotates about the scene centre, a per-object origin is not implemented". That
is the same failure as a wrong tooltip — it tells the user a capability is
missing — and it is worth a sweep rather than a fix: a disabled entry is only
honest while its reason still holds, and nothing re-checks them.

**The disabled entries are now an inventory, because three of them were
lying.** A greyed-out entry with a reason is the honest way to show a gap — but
it is honest only while the reason still holds, and **nothing re-checks them**.
Sweeping the 26 disabled leaves on 2026-08-07 found three that had had working
commands for some time: `origin` ("chimol rotates about the scene centre"),
`generate ▸ symmetry mates` ("chimol cannot generate symmetry mates", while
`symexp` sat in `cmd/symmetry.py` under 53 tests) and `S/H ▸ cell` ("chimol does
not read crystal cells"). To a user those read exactly like missing features.

The `cell` one was worse than stale: the command existed and **did not work**.
It tested `state.symmetry` directly instead of going through `_symmetry_for`,
which is the resolver that falls back to the file's `CRYST1` record and then to
the space-group table — so `cell` only ever drew after an explicit
`set_symmetry` while `symexp`, on the same object, expanded straight from the
file. Two paths to one answer, and the wrong one reported the record as missing
while it sat in the file on screen. Fixed by resolving and writing the result
back, since the renderer reads `state.symmetry` too.

`DISABLED_ENTRIES` in `test_menu_coverage.py` now pins the set: 22 leaves, each
with its reason, and the test fails both ways — a new disabled entry has to be
added deliberately, and one that gains a command has to be struck. Like the
other trackers here it is meant to **shrink**.

**Three keywords and a menu entry that were waiting on work already done.**
Continuing the sweep, in the same shape as the `origin`/`cell`/`symexp` finds:

* `A ▸ hydrogens ▸ add` was disabled as "no structure editing" while **`h_add`
  sat in `cmd/editing.py`**; it places 1325 hydrogens on 148L in 0.6 s and
  reports the six ligands it has no template for. Both PyMOL entries are wired
  now, *add* and *add polar*;
* `donors` / `acceptors` (`don.`/`acc.`) were refused as "needing assigned
  chemistry" — chemistry `analysis.hbonds.type_atoms` **was already assigning**
  for every polar-contact search. Only the keyword was missing, and its absence
  is what blocked *add polar*, whose command is
  `h_add (sele) and (donors or acceptors)`. 278 donors and 261 acceptors on
  148L, cached per object like the atom classes;
* `byring` was refused for want of a ring finder, which the pi-interaction work
  wrote the same day. It uses **every** ring rather than the planar ones — a
  proline is as much a ring as a phenylalanine, and the planar filter belongs to
  the pi finder's question, not this one. One trap from the source: PyMOL
  *clears* the mask before its ring finder runs (`std::fill_n(...)` in
  `SELE_RING`), so an atom in no ring is **dropped** — `byring (name CA)`
  answers "the prolines" (15 atoms), not "every CA plus the prolines" (177).

The pattern in all six is one thing: **capability and surface land separately,
and nothing pairs them up again.** The command, the keyword or the analysis
arrives; the menu entry or the parser branch keeps its refusal, and the refusal
is what the user sees. Worth re-reading every "chimol cannot" string whenever
that area is touched — `DISABLED_ENTRIES` now pins the menu half, and
`_UNSUPPORTED_FLAGS` in `cmd/sele_parser.py` is the same list for the selector.

**The clash check is PyMOL's, and it is not a command there.** It is the bump
check inside the mutagenesis wizard: sculpting's van der Waals term, one
iteration, with `sculpt_vdw_vis_mode` on. Transcribed from `Sculpt.cpp`, and
three details are what separate it from a naive vdW test:

* a **hydrogen bond is not a clash** — the pair cutoff drops by
  `sculpt_hb_overlap` (1.0 Å) for the hydrogen and `sculpt_hb_overlap_base`
  (0.35 Å) for the heavy atoms;
* **1-2 and 1-3 pairs are excluded**, and a **1-4 pair is scored but never
  drawn**. That asymmetry is deliberate in PyMOL: `SculptCGOBump` is called only
  in the `ex == 10` arm. Drawing 1-4 pairs buries the real clashes in
  intra-residue haze;
* the radii are **PyMOL's `ElementTable`**, not the force-field radii chimol's
  reader stores. Measured on 148L: with the reader's radii, 862 pairs report as
  deep overlaps; with PyMOL's, 15 do. That was the first measurement this work
  took and it decided the whole design — a clash check calibrated against the
  wrong radii is worse than none.

**Mutation is PyMOL's loop with PyMOL's data.** `do_library`: fragment onto the
backbone, one state per rotamer, bump-check each, start on the least strained.
The data is generated from the reference checkout rather than re-derived —
`analysis/make_residue_library.py` reads `data/chempy/fragments/*.pkl` and
`sc_bb_ind.pkl` and writes a plain-Python module, the same pattern the 547
space groups use. Three things decide whether the result is usable:

* the **backbone is not moved**. The fragment is fitted on N/CA/C and then the
  target's own backbone is kept; the fit residual is absorbed as a *translation
  onto CA*, which puts it in the N-CA-CB angle instead of stretching the CA-CB
  bond (1.58 Å before that, 1.55 after, against an ideal 1.53);
* **which atoms a chi rotation moves** is read from the fragment's own bond
  graph, not from a per-residue table that goes wrong on the one residue nobody
  checked;
* the side chain is scored **with its own bonds**, or every bond in it counts as
  two atoms deep inside their radii and a tryptophan reports strain 60 before
  it has touched anything (measured: 64.7 → 29.4 when the bonds went in).

Validation is the identity rebuild: mutate every residue of 148L into itself and
ask how close the library's best rotamer lands to the deposited side chain.
**0.50 Å mean, 31 of 33 within 1 Å** — which is the resolution of a rotamer
library (a set of cluster means), not an error in the build. The *choice* is a
separate matter: the least-strained rotamer is often not the crystallographic
one, which is precisely why PyMOL's wizard shows the list and so does `mutate`.

**The wizard panel is PyMOL's simplest GUI, and it is now chimol's.**
`Wizard.get_panel()` returns rows of `[code, label, action]` — 1 a banner, 2 a
button whose action is a command, 3 a pop-up whose action names a menu the
wizard supplies — and the viewport draws them under the object list, with
`get_prompt()` in the top-left of the scene. Three codes, and every wizard
PyMOL ships is built from them; that vocabulary is transcribed as
`WizardRow(kind, label, action)`, and the mutagenesis wizard is its first user,
because choosing a rotamer means *looking* at each one and a command cannot
offer that.

**The preview is a states object, and that is not a detail of taste — it is the
performance.** The wizard first previewed **in place**: rebuild the residue in
the source object on each step, keeping a copy of the original rows so `Clear`
could restore them. It was correct and it was unusable — **2.2 s per step** on a
1363-atom protein, because rebuilding the residue runs `set_structure` over the
whole molecule and re-bakes ambient occlusion for 1349 atoms that did not move.
The instinct at that point ("use numba") aims at the wrong thing: building all
81 rotamers of the largest residue costs **28 ms** and scoring them **97 ms**,
so the arithmetic was never the cost. PyMOL's own design removes it — a separate
object named `mutation`, `cmd.create(obj, frag, 1, state)` per rotamer, and
stepping is a state change. Measured after the port: build a target **320 ms**
(was 2881), step a rotamer **32 ms** (was 2172). No numba, no approximation, and
`Clear`/`Done` become a delete rather than a restore because the source was
never touched.

Three things had to be right for a separate object to work here, none of them
obvious from PyMOL, whose scene model differs:

* **it must live in the source object's frame.** An object added on its own is
  centred on its own centroid, so a 14-atom residue previews at the middle of
  the scene rather than where it belongs (`set_frames(..., share_frame_with=)`);
* **its states are its own.** chimol's timeline is global and drives trajectory
  playback for every object; asking the whole scene for state 7 to step a
  9-state rotamer re-derives the scene bounds from the 14-atom object and the
  protein shrinks to a speck. Stepping the preview's own state via
  `_select_state_frame` renders correctly. The cost is cosmetic — the movie
  transport keeps showing the trajectory's state, not the rotamer's — and that
  is the right trade;
* **the camera is held across every wizard action.** PyMOL needs only
  `auto_zoom 0`; chimol loses the framing two further ways (adding an object
  moves the scene centre, a state change re-derives the radius). The symptom was
  read wrong for an hour: successive screenshots looked *dark*, which reads as a
  lighting or occlusion regression, and instrumenting proved the scene data
  identical across steps. It was the camera receding. `get_view_state` /
  `set_view_state` around the build and the step, with a test that asserts it.

Two deliberate differences from PyMOL's wizard remain, both simplifications: the
caps (`N-Cap`, `C-Cap`) and the `dep`/`rep` rows are absent — chimol mutates
inside a chain and has no terminus chemistry, has one rotamer library, and its
representations are the object menu's business.

**A bump is drawn between the surfaces, not between the atoms.** The first
drawing ran a line from atom centre to atom centre, which is what "clash line"
suggests and is wrong: in a crowded site the lines cross the whole residue and
the picture is a scribble. `SculptCGOBump` (mode 1) draws a short segment about
the **contact point** — the position dividing the pair in proportion to their
radii — extending a `delta` fraction either side, with the *radius* carrying the
depth of the overlap. Transcribed as `clashes.bump_geometry`; the visual
difference is the whole reason the feature is legible.

The prompt goes **below the sequence strip**, not at the window's top edge —
the strip owns a band up there and a prompt drawn at `y = margin` lands on the
residue numbers. Found by looking at the screenshot, which is the only way that
class of fault is ever found.

Open here: the **backbone-dependent** library (`sc_bb_dep.pkl`, 3569 phi/psi
bins) is PyMOL's own default and is not shipped — the reader is written
(`--dependent`) and 1.4 MB of generated module was not worth it before anyone
asked to be phi/psi-aware. And the wizard is the *only* one: PyMOL's
measurement, appearance, density and sculpting wizards have no chimol
equivalent, which is why the Wizard menu lists one entry rather than listing
five and disabling four — a wizard is a **mode**, and offering to enter one
that does not exist is worse than not offering it.

**A test trap worth knowing.** A `MolViewPluginWindow` built inside a pytest
fixture aborts the interpreter — SIGABRT, taking the whole run with it —
*unless the `QApplication` is created by a fixture of its own that the window
fixture depends on*. Creating it inline at the top of the same fixture is not
enough. `test_interactions.py`'s `qapp` fixture is the pattern; the abort is
silent about its cause and costs an hour to find twice.

## The element field was one character wide

Found in the same pass. `ZN` was stored as `Z`, `CL` as `C`. Everything keyed on
the element inherited it: `metals` matched nothing on any structure ever, `elem ZN`
matched nothing, bond inference saw the wrong element, and a chlorine coloured as a
carbon. One character in `keys_formats`, in the reader shared by all of chisurf.

## Sweep the surface before extending it

Closing Tier 1 turned up four "implemented but silent" defects in a row, so before
starting Tier 2 the whole registered command surface was run against a real
structure and the *data* checked rather than the message. Six more commands were
answering cheerfully while doing nothing or crashing:

| Command | What it did | Cause |
| --- | --- | --- |
| `alter` | reported "Altered 1299 atoms", wrote none | own property map naming `chain_id`, `b_factor`, `occupancy` — no such fields |
| `alter` | shrank the molecule 10× on every call | assigned raw Angstrom into the render-space array |
| `spectrum` | ignored expression, palette **and** selection | body was `self.color("spectrum")` |
| `pseudoatom` | crashed, leaving a broken active object | invented a fifth atom dtype |
| `copy` | `NameError`, then a broken fallback object | called an undefined `_copy_state`, and `entry.id` |
| `as` | rejected `as cartoon, polymer` | no selection parameter |

All six are fixed, with `iterate_state`/`alter_state` and a persistent `stored`
namespace added alongside — without somewhere to put results, `iterate` can only
print.

### The test double was causing the bugs

`copy_object` used `copied.id` because `MockEntry` had `.id` while the real entry
has `.object_id`; the `alter` fixture declared `chain_id`/`b_factor` because
`alter` looked for those names. **Both halves were wrong together, so the tests
passed and the application was broken.** The double now matches the real viewer's
shape — `object_id`, an entry returned from `_create_object`, the `chain` field,
`set_atom_color_override` — and that is the standing rule: a divergence in the
double is a bug waiting to be written, not a convenience.

Two counts of the same lesson as the `resn` bug, which makes it the dominant
failure mode in this codebase: **a second copy of a table always drifts, and the
drift is silent because the feature keeps answering.**

## Undo is narrower than the word

PyMOL's `undo` is not a command history and matching that scope mattered more than
extending it: it stores *coordinate* snapshots, per object, in a ring of sixteen
(`cUndoMask = 0xF`), and refuses to restore one once the atom count has changed. It
does not undo a colour, a representation, a deletion or a load. Promising more would
be the wrong parity — a user expecting `undo` to bring back a deleted object is
better served by being told no.

The walk in `ObjectMoleculeUndo` is not the obvious pair of stacks: it writes the
present state into the ring *before* stepping, which is why one ring serves both
directions. A two-stack implementation passes a single undo and then drifts, so the
tests pin the reversibility rather than just the first step. chimol's snapshot has
to carry every array derived from the same edit — the trace, the render-space
positions, the atom array's Angstrom coordinates — or an undo would move the picture
back while leaving what `save` writes stale.

## The camera carries two points, not one

`origin` looked like a one-line command and was actually a camera-model gap. PyMOL's
view tuple defines **two** points — slots 12-14 the pivot in world space, slots 9-11
a camera-space offset applied after the rotation — and chimol had collapsed them
into a single orbit target. They agree until something separates them, and `origin`
is the only thing that does: `ExecutiveOrigin` always passes `preserve=1`, so moving
the pivot must leave the picture exactly where it was. The compensation is
`SceneOriginSet`'s, transcribed: the model-space difference rotated into camera
space, added to the view offset.

The property worth pinning is the invisible one. A wrong implementation looks
correct until someone rotates, so the tests assert both halves: that the
projection matrix is unchanged by `origin`, and that after it a chosen atom holds
its screen position through a 40° turn while the control case swings away.

Adding a non-zero slot 9 broke the loader's layout discriminator, which keyed on
"slot 9 is zero" to tell a PyMOL tuple from chimol's two older ones — a saved view
with an offset would have been read as a completely different camera, silently. One
corner is genuinely ambiguous (an identity rotation with a negative slot 11 could be
either format) and is resolved in PyMOL's favour, which the tests document.

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

**Done:** `get_area`, `get_extent`, `get_chains`, `get_title`, `iterate_state`,
`alter_state`, `spectrum` by property, `scene`, `pair_fit`, `cartoon_putty`,
`group`/`ungroup`/`order`, `bond`/`unbond`/`get_bonds`, `h_add`/`h_fill`, `smooth`,
`protect`/`deprotect`, `sort`, `mask`/`unmask`,
`symexp`/`get_symmetry`/`set_symmetry`, `distance` modes 0-4 (polar contacts).

**Remaining:** `cealign` (skipped by request), `matrix_copy`, `ramp_new`,
`cartoon_dumbbell`, `cartoon_fancy_helices`, `ellipsoid`, `cell`, `slice`.
`set_bond`/`get_bond` (per-*bond* settings, not the bond list) need a per-bond
settings store and are deliberately not started — which is also why
`preset ball_and_stick` reports that it could not colour its sticks white.
(`cartoon_putty` was listed in both columns; it is done.)

## Symmetry: hand-entered data, machine-checked

`symexp`, `get_symmetry`, `set_symmetry`. The generation follows
`ExecutiveSymExp`: transform in **fractional** space, shift the copy so it lands
beside the original rather than an arbitrary number of cells away, convert back,
and keep it only if some atom comes within the cutoff.

**The operators are PyMOL's own**, transcribed out of `modules/pymol/xray.py`
(`sym_base` + `space_group_map`) into `analysis/space_groups.py` by a generator
checked in beside the data: **547 names over 528 distinct operator sets**, up to
192 operators each. No crystallography library is a dependency — no `gemmi`,
`spglib` or `cctbx` — and none is wanted: sharing PyMOL's table is what makes a
mate here *the same mate* PyMOL would build, rather than approximately the same.

An earlier revision of this section described a 27-group table entered by hand.
That was replaced: a hand table covers the common cases and diverges from PyMOL
everywhere else, which is the wrong trade for a parity project.

Operators are looked up in order of trust: supplied explicitly or read from the
file (exact, whatever the group), then PyMOL's table, then **nothing** — in which
case the space group is named and the command declines. A mate built from guessed
operators looks entirely plausible and would be believed.

**Reading them out of an mmCIF is parsing, not line-shaping.** The file source
outranks the verified table, so a misread there beats everything the table
guarantees. The first version took the whole `_symmetry_equiv` loop row as the
operator; a PDBx loop carries `_symmetry_equiv.id` beside `pos_as_xyz`, so
`3 x+1/2,y+1/2,z` became a rotation with **determinant 3** — a threefold
*scaling*, moving that mate by up to 19.6 Å — and the quoted form RCSB writes
raised out of `symexp`. So the loop *header* is parsed, the column of
`pos_as_xyz` is taken (either tag order, either tag spelling), quotes are honoured
per field, and the non-loop `tag value` form is read too. All four layouts are
pinned, twice: same operators out of each, and every operator an isometry — the
check the det-3 row failed.

**A transcription can fail silently, so the whole table is verified
mathematically.** All 547 groups are closed under composition modulo lattice
translations, every rotation is an isometry (determinant exactly ±1 — 4355 proper
and 3303 improper, since the table covers all 230 groups and the centrosymmetric
ones contain inversions), every group has exactly one identity, and none lists an
operator twice. **7658 operators verified.** The chiral groups proteins
crystallise in are checked separately for determinant +1 only, where an improper
rotation would be an extraction error rather than a legitimate mirror. A size
guard sits alongside, because a *truncated* extraction would pass every
mathematical check — whatever survived would still be self-consistent.

Two other checks worth keeping: a mate must be a **rigid** copy (symmetry is an
isometry, so internal distances cannot change), and a pure lattice translation
must offset the molecule by exactly one cell edge — which is the strongest test of
the fractional-to-Cartesian transform.

**Performance.** The first version rebuilt the neighbour tree per candidate: 107
tree builds over every atom, and on HIV-RT's 17 784 atoms that dominated
everything. Hoisting the tree and rejecting candidates by bounding box first
brings the whole expansion to **0.26 s**.

## `sort`: the ordering was the easy half

The priority table is transcribed from `AtomInfoAssignParameters`. Two of its
properties are counter-intuitive, and both were got wrong by guessing before the
source was read:

* **priority depends only on the Greek letter, not the branch number.** `CG2` and
  `OG1` both score 5, and the *name* comparison settles them — giving `CG2` first,
  which is what deposited files contain. Folding the branch digit into the
  priority put `OG1` first and disagreed with **both** real structures checked
  (148L and hGBP1), at 10% and 2% of atoms. Reading the C++ turned a
  "the files are non-canonical" conclusion into "the rule was wrong";
* **a one-character `C` or `O` scores 997/998**, so the canonical order is
  `N, CA, CB, ..., C, O, OXT` — side chain *before* the carbonyl. That is not PDB
  write order, so sorting a freshly loaded file genuinely reorders it (74% of
  atoms move), and matching PyMOL means accepting that.

**The consequence, not the ordering, is the dangerous part.** A reorder
invalidates every array indexed by atom and every bond index. The atom-indexed
fields are written out rather than detected by shape — a residue-length array can
coincidentally match the atom count, and being wrong there pairs colours with the
wrong coordinates — and a **guardrail test** walks the state dataclass and fails
on any array field that is neither listed as atom-indexed nor listed as exempt.
It found three unclassified fields on its first run.

Mutation testing was informative beyond confirming the tests bite:

| broken deliberately | caught? |
| --- | --- |
| per-atom colour array not permuted | yes, 2 failures |
| manual `bond_edits` keys not remapped | yes |
| `bond_pairs` indices not remapped | **no** |

The last one is not a gap in the tests but a fact about the code: `sort` rebuilds
afterwards, which re-infers bonds from coordinates and overwrites whatever the
remap set. So that line is belt-and-braces for a direct API caller, and the
`bond_edits` remap is the part that has to be right — it is replayed on top of
each fresh inference. Said so in the code rather than leaving a line that looks
tested and is not.

`mask`/`unmask` are threaded into the pick site, because a flag nothing reads is
decoration. Kept separate from `protect`: one is about the mouse, the other about
transforms, and conflating them would mean hiding an atom from selection also
froze it.

## `smooth` is four decisions, none of them in the help text

Transcribed from `layer3/Executive.cpp::ExecutiveSmooth`. The command's own
documentation describes a window average; the behaviour depends on four things it
does not mention, and each changes the numbers:

* the half-windows are `window / 2` in **integer** arithmetic, taken
  independently as `backward` and `forward`, so an even window spans an odd
  number of states — `window=4` averages five;
* `ends` is a **four-way choice**, not a boolean: `0` skips one state at each
  end, `1` skips none, `2` skips a whole half-window, `3` wraps the trajectory;
* the average divides by the number of states actually **found**, not by the
  window width. Dividing by the width pulls states near an unskipped end towards
  the origin, which reads as the trajectory collapsing at its ends;
* `cutoff` stops the window extending across a jump and pads with the last good
  position, which is what keeps an atom that crosses a periodic boundary from
  being averaged with its own image.

Two mathematical properties are asserted alongside the transcription, because
they hold for *any* correct running mean and catch what a transcription test
cannot: a constant trajectory is unchanged, and a linear ramp is preserved away
from the ends. Both mutations tried against the suite — dividing by the window
width, and misreading the halves as asymmetric — are caught (5 and 1 failures).

## `protect` needed something to honour it

A flag nothing reads is decoration, so `protect`/`deprotect` are tested through
`translate` and `rotate` rather than by reading the mask back: protected atoms
move 0.000 Å while the rest move exactly the requested distance.

The transform seam moves every array at once, which is right for an unprotected
object and wrong as soon as `protect` has been used. Rather than teach
`apply_transform_to_object` which of its arrays are atom-indexed and which are
derived, the protected atoms are snapshotted, the transform runs, and their rows
are written back before the derived arrays are rebuilt — keeping the knowledge of
what is derived in the one place that already has it. With nothing protected the
helper returns `None`, so the common path is untouched.

## Polar contacts: one finder unblocked three visible things

`distance ... mode=2`. Before it, `preset technical` and `preset ligands` both
reported drawing no polar contacts and the object menu's **A ▸ find** submenu was
disabled outright — one missing piece behind three symptoms, which is what made
it the item to do next rather than the biggest one.

The algorithm is transcribed from `ObjectMoleculeTestHBond`,
`ObjectMoleculeFindBestDonorH`, `ObjectMoleculeGetCheckHBond`,
`ObjectMoleculeGetAvgHBondVector` and `CoordSetFindOpenValenceVector`. Three
details are invisible to a reader who does not open the C++ and each changes
the answer:

* **the cutoff is a curve, not a number.** The donor–acceptor limit slides with
  the A–D–H angle from `h_bond_cutoff_center` (3.6 Å, head-on) to
  `h_bond_cutoff_edge` (3.2 Å, at `h_bond_max_angle` = 63°). The names read
  backwards from what they do — *center* is the angle-zero end;
* **the virtual hydrogen sits 1.0 Å out**, not at the real X–H bond length:
  `FindBestDonorH` adds a *unit* open-valence vector. Only the direction is
  used, but "fixing" the length moves the angle and with it the cutoff;
* **an atom with no neighbours aims its hydrogen straight at the acceptor**
  (`copy3f(seek, v)` with the *unnormalised* seek vector), so the angle is zero
  and the test collapses to "within 3.6 Å". That is not a bug — it is how PyMOL
  finds water-mediated contacts in a hydrogen-less PDB, and it is reproduced.

### Donors and acceptors without bond orders

PyMOL derives them from bond orders, which a PDB does not carry, and fills the
gap twice: a hard-coded table of double bonds for standard residues applied while
connecting (`assign_pdb_known_residue`), and valence arithmetic for the rest.
chimol already holds the equivalent of the first — the `h_add` residue template,
which knows each named atom's hydrogen count and whether its centre is planar.
So a templated atom is typed from the template (which is what makes a backbone
carbonyl oxygen an acceptor and *not* a donor), an untemplated one from the
element's expected valence with the geometry read off its bond angles
(`ObjectMoleculeGetAtomGeometry`), and explicit hydrogens beat both.

Following PyMOL's own logic reproduces its ligand behaviour by construction: an
untemplated carbonyl oxygen reads as a donor in both, because a single bond and a
free valence slot look the same. **One deviation is deliberate**: PyMOL reads a
proline nitrogen's three single bonds as a tertiary amine, marks it a donor and
invents an amide hydrogen the residue does not have. The template says zero.

### The measurement that says the invented hydrogens are right

`hGBP1_closed.pdb` carries its hydrogens, so the same question can be asked
twice. With them: **735** contacts. With them stripped, so every hydrogen used is
a placed one: **803**, of which **729 are the same pairs — 99.2 % recall**. The
9 % extra are rotatable donors (hydroxyls, ammonium groups) whose real hydrogen
points elsewhere while a placed one is free to aim at the acceptor, plus a few
3₁₀-like i→i+3 backbone pairs. That is the direction the error should go.

On 148L the finder returns 234 contacts in 0.02 s, over 40 of them the i→i−4
backbone bonds that *define* an α-helix — the check that a unit test choosing its
own geometry cannot make.

### What came with it

`distance` grew PyMOL's full signature (`[name,] s1, s2 [, cutoff [, mode]]`,
plus `label`/`quiet`/`reset`) and modes 0–4; measurements became multi-segment
and **dashed**, through `dash_length`/`dash_gap`/`dash_width`/`dash_color`; the
**A ▸ find ▸ polar contacts** submenu is transcribed from `menu.py::polar`, with
halogen/salt-bridge/π left visible-and-disabled rather than dropped. Thirteen
settings moved from the missing list to the registered one (55 → 68), all of
them read by code.

## `transparency` runs the other way, and the setting says so

`transparency` and `two_sided_lighting`: first and fourth on the settings
worklist, and the two `preset ligand_sites` had been reporting as skipped.

**PyMOL counts transparency; chimol stores alpha; they run opposite ways.**
`transparency 0` is fully opaque and `alpha 1` is. Storing both is two numbers
that must agree and eventually will not, so `SettingSpec` gained `stored`/`shown`
transforms and the complement is declared once in the table: `set transparency,
0.4` echoes 0.4 and stores 0.6, `get` answers 0.4. A guardrail asserts that any
spec converting on the way in converts back on the way out -- a one-way
transform would compound the error on every subsequent `set`.

`unset transparency` restores **chimol's** 0.15, not PyMOL's opaque 0. `unset`
restores *the default*, and the default has to be the one this program ships;
changing that is a config-version migration, not something a settings entry may
do quietly.

### The picture caught what the tests could not

Wiring `two_sided_lighting` to the existing `twoSided` uniform *worked* by every
test -- and drew the wrong thing. That uniform flips the normal toward the
**light**, which is a different effect, written for flat nucleic base plates.
PyMOL's two-sided lighting flips a back face toward the **viewer**
(`gl_FrontFacing`); the old rule darkens a front face lit only by the fill
light, by flipping its normal away from that fill light. Fixed, with the
honest caveat that on a closed surface the two criteria mostly coincide, so the
measured difference in that scene is negligible (-8.09 vs -8.17): it is a
correctness fix justified by the failure mode it removes, not by a number.

**And the first metric was wrong.** Mean brightness over lit pixels *fell* 7.6 %
when two-sided lighting was turned on, which read as a bug. It is not: the newly
lit back faces are mid-grey and veil brighter cartoon pixels behind them. Only
the side-by-side images settled it -- off leaves the far half of the shell dark
and patchy, on gives a coherent closed envelope. A scalar over the whole frame
cannot tell "back faces now lit" from "bright cartoon now obscured", and
choosing one before looking is how a correct change gets reverted.

`preset ligand_sites` sets both for real now. Its fourth PyMOL step,
`surface_quality 0`, is deliberately **not** passed through: PyMOL's is a level
(0-4, coarse to fine) and chimol's is a grid *spacing* in Angstrom, where 0 is
not "coarse" but "infinitely fine". It would hang rather than approximate, so it
is named in the skipped list -- a real parity wart, written down instead of
guessed at.

## The tracer walks through a surface, and the twin that hid a bug is gone

`ray` took the nearest hit along each ray and sliced the colour to RGB, so a
surface at `transparency 0.6` traced solid: the viewport showed a glass shell
with the cartoon inside, `ray` an opaque grey blob. Now each ray composites
front to back -- every hit contributes its alpha, the remainder passes on, and
what is still transmitted at the end is background.

**It costs nothing when it is not used.** Measured on 148L at 300x220: opaque
renders in 3.60 s with four layers allowed against 3.83 s with one, because the
walk ends at the first solid hit. Translucent is 9.06 s -- 2.4x, not 4x, since
the walk also stops once the remaining transmittance cannot change a byte.

**The NumPy twin is deleted, and it had already rotted.** `trace()` kept a
pure-NumPy implementation of the same tracer behind `if _HAVE_NUMBA` *and* an
`except Exception` fallback. Nothing ran it while numba was installed -- so when
transparency was added to both, the NumPy one went in wrong (it referenced
`max_layers` without taking the parameter) and every test still passed. A
fallback nobody runs is not a safety net; it is an untested branch that fails
the day you need it. `_trace_numpy` and its three helpers are gone, numba is a
hard import, and the file is ~380 lines lighter.

Two process notes from doing it:

* **a bulk deletion by regex overreached** -- "from this `def` to the next" also
  swallowed `_LINE_SIDES` and `TRACEABLE_KINDS`, which sat between two
  functions. Diffing the *set of top-level names* against `HEAD` is what proved
  the repair complete; reading the diff would not have.
* **the first test asserted the wrong thing.** Colouring the molecule red and
  comparing "redness" fails because `color red` reddens the *surface* too, so
  the opaque case scores redder than the translucent one. The premise was wrong,
  not the code. It is now two spheres driven through `trace()` directly, where
  red can only reach the centre pixel by passing through the shell -- plus the
  converse, that an opaque shell must not leak it.

## `surface_quality` was three defects wearing one name

Flagged as a units wart -- PyMOL takes a level, chimol a grid spacing -- and each
measurement found something worse underneath.

**It is not a different quantity.** `RepSurfaceSetSettings` shows the level is a
*selector* for a point separation in Angstrom, which is exactly what chimol
stores. Eight levels over four base separations (`surface_best`,
`surface_normal`, `surface_poor`, `surface_miserable`), all transcribed, and the
four bases registered because the table reads them.

**Then the level did nothing.** Levels -3 to 1 moved 148L from 26 286 to 27 238
vertices -- 3.6 % across an eightfold request. `max_dim` caps the grid at 96
samples per axis and **rescales the spacing to fit**, so every fine level
collapsed onto the same grid.

**Then the reason turned out to be worse.** `_all_atom_coords` is in *scene*
units -- Angstrom x `_scale_factor` (10) -- and the configured spacing was passed
through as though it were scene units too. `0.8` asked for **0.08 A**, and the
cap clamped it straight back. The spacing had never had a measurable effect in
this path; `max_dim` was making the whole decision. `add_volume` already does the
conversion, so the bug is one path forgetting what its neighbour remembers.

With the conversion right and the cap following the request (ceiling 320
samples/axis, measured at 0.66 s for the finest realistic level on 1300 atoms):
2 446 / 13 654 / 25 876 / 105 922 vertices at levels -3 / -1 / 0 / 1. A 43x range,
monotone, and visibly different -- level -3 is a smooth blob and level 1 resolves
individual atoms.

**The default changed number without changing picture.** An honest 0.8 A would
have made every existing surface *coarser* than what users see (13 654 against
27 114). 0.5 A is PyMOL's own `surface_normal`, is `surface_quality 0`, and
reproduces today's appearance at 25 876 -- so that is the shipped value, moved by
a config-version migration (7 -> 8) that only touches copies still holding the
old default.

### And a fourth, found by pulling the same thread

`solvent_radius` was registered **twice**, onto two different config keys:
`surface.probe_radius`, which the surface mesh reads, and
`surface.solvent_radius`, which `get_area` reads. The later entry silently
shadows the earlier in the name table, so `set solvent_radius, 2.5` moved the
number the *area calculation* used and left the surface on screen untouched. One
physical quantity, two storages, disagreeing quietly -- which is exactly what the
`transparency` transform two hundred lines above it exists to prevent.

Both entries had plausible docstrings, the name resolved, nothing failed. Only
instrumenting the live path -- watching the config value stay at 1.4 while `set`
reported success -- showed it. Collapsed onto one key; `solvent_radius` now moves
the surface (34 770 / 30 744 / 25 260 vertices at probes 1.0 / 1.4 / 2.5 A, the
right direction: a bigger probe bridges more crevices). Two guardrails added --
no name registered twice, and no one name writing several config entries. The
reverse stays legal: `cartoon_side_chain_helper` and `ribbon_side_chain_helper`
are deliberately one setting here.

**Worth carrying: "the setting is registered" and "the setting works" are
different claims.** Four defects sat behind one flagged wart -- wrong type, no
effect, 10x units, two homes -- and every one of them had a live config path, a
passing test and a correct-looking name. Only measuring the *output* caught
them.

## The camera stayed where the user put it, once the aspect was fixed

Every scene rebuild refitted the camera, and a rebuild is what colouring, a
representation change, a label, a bond edit and **every** `set` all trigger.
Measured on 148L: `zoom resi 20-26` frames at distance 357, and **12 of 12**
ordinary commands put it straight back to 1730. Framing a site is the first half
of almost every task in a viewer and the second half undid it.

**This had been attempted and reverted, and the recorded reason was a symptom
seen through another defect.** The note said flipping the default was not
sufficient because `ray` then traced an empty image for every representation —
so the load-time fit looked as though it had nothing to measure. It measured
fine. The empty images were the aspect defect below: a never-shown window has no
viewport, so the camera went thirty times too far away, and refitting on every
rebuild hid it because the last rebuild landed after the widget had a size. With
`_aspect()` fixed, the same flip passes `test_ray_command.py` untouched.

Two things it needed on top, both found by measuring rather than reasoning:

* `_rebuild_after_coordinate_change` reuses `set_structure` — the *load* path —
  to re-derive after an edit, so `h_add` on a zoomed-in residue still jumped
  out. `set_structure`/`set_coordinates` grew a `fit_camera` argument; loading
  frames, re-deriving does not;
* nothing re-derived the distance on a **resize**, which refit-on-every-rebuild
  had been covering by accident. `resizeGL` now re-frames when the viewport's
  *shape* changes — distance only, since the clips carry a user's `clip`
  adjustments and a resize is not a request to discard them.

The resize correction **scales** the distance rather than recomputing it, which
is the other thing only a measurement finds: the scroll wheel moves the camera
without touching what was framed, so recomputing would snap a hand-zoomed view
back to the last `zoom`. `portrait_factor` is now one function in
`view_state.py` read by both the framing and the resize, rather than the rule
written twice.

0 of 12 after. The seven call sites that had been patched to `fit_camera=False`
one at a time are gone with the default; the only places that ask to frame are
now the three load paths. `test_camera_persistence.py` pins both halves: what
must not move the camera, and what must — with the trap that `orient resi 20-26` after
`zoom resi 20-26` correctly leaves the distance alone, so a "camera commands
still work" test has to start from a different framing than it asks for.

**Worth carrying: when an attempt fails, record what was measured, not what was
concluded.** "Reverted because `ray` broke" was true and sent the next session
to the wrong subsystem; "reverted because `ray` traced empty images, cause
unknown" would have cost one afternoon less.

## The portrait correction ran on a window that did not exist

Five tests in `test_camera_framing.py` were red, every one by a factor of
**exactly 30**, and the round number pointed at the wrong thing: chimol scales
coordinates by `_scale_factor` (default 10), which is close enough to feel
related. It is not. `scene_width()` subtracts the internal panel's 220-pixel
column and clamps what is left to **1**, so a `MolView` that has never been laid
out (100×30) reported an aspect of 1/30 — and PyMOL's portrait framing
correction, told the window was thirty times taller than wide, put the camera
thirty times too far away.

`_aspect()` now returns 1.0 below a 16-pixel viewport: an aspect measured off a
one-pixel column is not a measurement, and there is nothing to correct until
there is a window. Two guardrail tests, one per direction — the unlaid-out case
frames square, a genuine 400×900 portrait still corrects.

The lesson is the misdirection. A factor that matches a constant you already
know is not evidence; printing the actual `scene_width()` and `_aspect()` took a
minute and named it outright.

## Hydrogens need a template, and the reason is measurable

`h_add`/`h_fill`. The geometry is a transcription of
`layer2/HydrogenAdder.cpp::ObjectMoleculeSetMissingNeighborCoords`, where the
trap is the control flow rather than the constants: the `switch (n_system)`
**falls through**, so one existing neighbour on a tetrahedral centre yields the
second, third *and* fourth directions, each built from the ones before. Read as
an if/elif it produces one hydrogen where three are wanted.

**The count cannot be derived from valences without bond orders.** PyMOL works
from valences and warns in `h_add`'s own help that PDB files lack them for
ligands. Measured here on `hGBP1_closed.pdb` (4671 deposited hydrogens),
`valence(element) - heavy neighbours` is wrong for **41.6% of atoms** — it adds a
hydrogen to every carbonyl carbon, every carboxyl oxygen and every aromatic
carbon. So standard residues use a template of "how many hydrogens, and what
geometry", which is exact for proteins.

Validated against that protein by stripping its hydrogens and putting them back:

| | |
| --- | --- |
| counts correct | **99.78%** (4634 / 4644) |
| median position error | **0.10 Å** |
| within 1.0 Å | 97.8% |
| clashes introduced | none below 0.8 Å |

The 2.8% beyond 1 Å are **all** rotatable terminal groups — SER/THR/TYR
hydroxyls, CYS thiols, and the amide and guanidinium NH₂ groups — whose torsion
the geometry does not determine and which PyMOL also places arbitrarily. A test
asserts that set, so a *backbone* atom appearing there would fail rather than be
absorbed into the tolerance.

Two corrections a per-residue template cannot express, both found by that
comparison and both the *only* disagreements in 4644 atoms:

* **the N-terminus is an ammonium, not an amide** — three hydrogens on a
  tetrahedral centre. Detected from the bond graph (a backbone nitrogen with no
  preceding carbonyl), so it needs no separate residue name;
* **histidine's tautomer is a property of the structure, not the residue.**
  ND1-protonated is assumed unless the file already carries a hydrogen on NE2.
  Without hydrogens to read, the two are indistinguishable — so it is stated
  rather than implied.

A residue with no template is **named and skipped**, not approximated. An
approximate hydrogen is worse than a missing one, because it looks like data.

## Sessions carry everything, and the field list is derived

`session_save` / `session_load` / `session_info`, with `save x.pse` and
`load x.pse` routed by extension because that is what a PyMOL user types. A
reloaded session renders **pixel-for-pixel identically** to the one saved --
verified by comparing two real GL framebuffers, which is the only check that
covers the whole path.

**The object field list is derived from the state dataclass, not written out.**
That dataclass has 53 fields; a hand-kept list drifts the first time one is
added, and the drift is silent -- the session saves, reloads, and quietly lacks
whatever was new. A test guards it by round-tripping `bond_edits`, a field added
by separate work and named nowhere in the session code.

Three things that were bugs first:

* **JSON objects only have string keys, and some of ours are tuples.** The
  bond-edit map is keyed by an `(i, j)` atom pair. Skipping non-string keys
  dropped every recorded bond *order* while keeping the bonds, so a reloaded
  session had single bonds where doubles had been set. Non-string-keyed dicts are
  now stored as key/value pairs.
* **The camera has to be restored after the GUI refresh.** Rebuilding the object
  panel re-zooms, replacing the saved distance (slot 11) and clip planes (15, 16)
  with ones computed from the bounding sphere. Rotation and pivot survived, so
  the view looked restored while the framing was wrong -- three numbers out of
  eighteen, invisible unless compared element by element. `load_session` returns
  the view so whoever touches the camera last is the one restoring it.
* **`get_view` is a command; the viewer's accessor is `get_view_state`.** Reaching
  for the command name stored a null view behind an `except` clause.

**Deliberately not PyMOL-compatible.** A `.pse` is a pickle of PyMOL's C
structures. chimol writes a zip of `manifest.json` plus `arrays.npz`: readable
without chimol, and loading one cannot execute code (`allow_pickle=False`). A
format people exchange should not be a code-execution path. Saving to `.pse` says
so, and a real PyMOL session handed to `session_load` is named as such rather
than reported as corrupt -- that is the mistake a PyMOL user will actually make.

Anything a session cannot carry -- an opaque RMF hierarchy handle, say -- is
**named in the message** rather than dropped, and a field from a newer session is
reported instead of crashing the load.

## Editing bonds, and the fixture that could not test it

`bond`, `unbond` and `get_bonds`, transcribed from `editing.py` and
`querying.py`. Three details that are not guessable:

* `bond` requires **exactly one atom** from each selection and both in the same
  object, because a bond lives inside one object's connectivity table. Repeating
  it on an already-bonded pair sets the *order* — that is how a single bond is
  promoted, not an error.
* `unbond` takes selections of any size and removes **every** bond between them.
  Not the cross product: only bonds that actually run from one selection to the
  other, or it would try to remove bonds that were never there.
* `get_bonds` indices are **0-based positions within the selection**, not the
  `index` property. PyMOL warns about this in capitals. They coincide for `all`,
  so a test that checks only `all` cannot tell the difference.

Bonds are re-inferred whenever coordinates change, so a manual bond kept only in
`bond_pairs` vanishes the next time an atom moves. Edits are stored as **deltas**
(`added` orders, `removed` pairs) and replayed over each fresh inference. The
direction matters: the edits are the source of truth and `bond_pairs` is derived,
so the two cannot drift. Orders live in that delta map rather than as a third
column of `bond_pairs`, because several consumers flatten that array to ask
"which atoms have a bond" and an order column reads as an atom index.

### The fixture was geometrically impossible

`solvated_fragment.pdb` — added earlier in this effort as the first fixture with
waters, an ion and a two-letter element — placed its six alanines along a helical
path *without constructing the backbone*. `C(i)-N(i+1)` came out at 4.4–5.2 Å
against a peptide bond's 1.33 Å, so the file had **no peptide bonds at all**, and
residues 4 and 5 interpenetrated (`O4-CB5 = 0.63 Å`, which is not a chemical
distance). Bond inference on it produced 40 bonds where 29 are correct: 11
spurious contacts and 4 of 5 peptide bonds missing.

Rebuilt by NeRF placement from ideal internal coordinates — the way a peptide is
actually constructed, each atom from the previous three by a length, an angle and
a torsion. The generator lives beside the file as
`make_solvated_fragment.py` and self-checks what matters: all five
`C(i)-N(i+1)` at 1.329 Å, closest contact 1.231 Å (the C=O bond), CA-CA at 3.8 Å
as an α-helix requires.

The lesson is about fixtures rather than about bonds: **a fixture is an
assertion too, and nothing checks it.** Every test built on this one was
green while the molecule it described could not exist.

## Groups are a display hierarchy, and membership belongs to the member

All eleven of PyMOL's group actions (`creating.py::group_action_dict`) plus
`ungroup` and `order`. Three decisions worth recording, each of which the
obvious alternative gets wrong:

**Membership is stored on the member, not as a list on the group.** A list plus
a back-pointer is two places that say where an object sits, and they drift the
first time an object is deleted — the failure this codebase keeps finding in its
own colour, keyword and representation state. A group therefore has no existence
apart from its members: `group_names()` is derived, and deleting the last member
removes the group, which is what PyMOL needs `ExecutiveGroupPurge` for.

**The second argument means either members or an action.** `group kinases, close`
is how PyMOL's own menu writes it, and every example in the command's help text
uses that form. Reading the word as an object name instead makes the documented
examples all report a missing object.

**Members must be drawn contiguously, and the registry does not keep them
adjacent.** Grouping the first and third objects leaves the registry order
`lig, pep, nag`, so walking it directly drew `nag` under whichever header came
last — visibly the wrong group. The display order is computed separately
(`_grouped_display_order`): a group's block goes where its first member sits, and
nothing in the viewer is reordered, so `order` still means what it says.

Two smaller ones, both found by a test rather than by reading:

* `order lig nag` has to keep the order **given**, not panel order. The shared
  name resolver sorted into panel order, which made `order` a silent no-op
  whenever the names were already in panel order — most of the time.
* A group used as a menu target expands to one command per member, which is
  PyMOL's documented "the command should be applied to all members". The
  expansion happens where the target is known (the row), because the selection
  resolver answers for one object at a time.

A group name inside an *atom selection* — `show cartoon, ligands` — is handled
by the multi-object resolver described in the next section. It was the last
place a group was not a first-class name.

## One atom table, not one object

PyMOL's selector runs over **one global atom table spanning every loaded
object** (`layer3/Selector.cpp`). chimol evaluated per object and against the
*active* one, and three consequences followed, each of them silent:

* a **group name** selected nothing — `count_atoms ligands` said `0`, and every
  representation, colour and camera command aimed at a group did nothing at all.
  The object panel's group rows emit exactly those commands, so a whole row of
  A/S/H/L/C buttons was inert;
* a plain `chain A` meant chain A **in the active object**, so `count_atoms all`
  under-counted by every other molecule on screen;
* a name that resolved to nothing **answered `0`** instead of erroring, which
  made a typo indistinguishable from an empty selection.

`_resolve_selection_to_atom_masks` returns `(object_id, name, mask)` per object;
the union is assembled in the command layer rather than inside the evaluator,
which stays per-object. The singular `_resolve_selection_to_atom_mask` remains
for the commands that genuinely want one object (`get_area`, `symexp`,
`pair_fit`) and **prefers the active object** among the hits, so those keep
answering about the molecule in front of the user.

Rules transcribed from `SelectorSelect0`, in its order: object, stored
selection, group, then `Invalid selection name "x"` — with a leading `?` as the
"undefined is allowed here" escape (`?sele`), which needed a tokenizer change or
the one spelling that suppresses the error would have raised it.

Framing had to follow: `MolView.zoom`/`center`/`orient` take a `selections`
list, because measuring one member of a group and reporting success is exactly
the failure that looks like it worked.

Migrated to the plural resolver: `show`/`hide`/`as`, `color`, `spectrum` — one
ramp over the whole selection, or a group restarts the palette at each member —
`zoom`/`center`/`orient`/`origin`, `count_atoms`, `select`, `label`, `remove`,
`alter`/`iterate`/`*_state`, and `mask`/`protect`. The last pair matters more
than it looks: their default is `all` and their purpose is one molecule sitting
in front of another, so reaching only the active object left exactly the
molecule you were trying to stop clicking through. `alter`/`iterate` share one
`stored` namespace across the objects, which is what makes accumulating over a
group work. Deliberately still single-object: `get_area` (its occlusion model is
per object), `save`, `symexp`, `pair_fit`, `intra_rms`, and bond editing.

**Three defects fell out of using it**, all pre-existing and invisible until a
command reached a second object:

* `color` refused every object `create` had made — it required a residue table
  that a copied ligand does not have, and blamed *atom coordinates that were
  right there*;
* an object without a residue table is drawn by the point-sphere path, which
  read `colors_per_ca` and never the per-atom override — so `color` wrote a
  value nothing looked at, and the molecule stayed its default colour while the
  command reported success. **The state and the scene disagreed**, which is why
  a state assertion would have passed; it took a screenshot;
* `hide everything` with no selection only reached the *active* object, because
  nine of the ten representation setters write the active object's state and
  only `spheres` had a spanning `_all` variant.

## The presets wore PyMOL's labels and made a different picture

A preset is the one-click path from "loaded" to "looks like a figure", and the
busiest entry in PyMOL's object menu. Ours were **four hand-rolled lines** —
`hide everything, {sele}; show cartoon, {sele}` — under the labels *simple*,
*ball and stick*, *ligand sites* and *technical*. Same words, different picture,
which is worse than not having them: the label is a promise about what you will
get.

All fifteen are transcribed from `modules/pymol/preset.py` now
(`cmd/presets.py`), with PyMOL's names, reachable as a `preset` command and from
the menu — whose shape follows `menu.presets`, including the *ligand sites*
submenu of surface variants. What chimol cannot do, it **names**: `technical`
and `ligands` report that they drew no polar contacts (that needs a
hydrogen-bond finder, not `distance`, which measures between two picked atoms);
`pretty` reports the three cartoon settings chimol's cartoon does not implement;
the surface variants that differ only by `surface_type`/transparency are shown
disabled with the reason. A preset that quietly does less than PyMOL's is the
failure the module exists to avoid.

Two divergences apply throughout and are stated once rather than left to be
discovered: PyMOL scopes a setting to a selection and chimol's settings are one
global config, and PyMOL's `ribbon` is thinner than its cartoon while chimol
draws one cartoon for both.

**The chain colour cycle had to come first.** `util.cbc` is what `simple`,
`technical`, `ligands` and `interface` colour with, and it walks PyMOL's
40-entry `_color_cycle` in `get_chains` order. chimol had **eight invented
colours assigned in first-seen order** — so every multi-chain figure came out
differently from PyMOL, and differently again depending on how the file was
written. Transcribed as `colors.CHAIN_COLOR_CYCLE`; chain A is the carbon green,
B cyan, C light magenta.

## Side chains that grow out of the ribbon

`cartoon_side_chain_helper`, transcribed from `SideChainHelper.cpp` into
`analysis/side_chain_helper.py`. PyMOL's `pretty` and `ligand_cartoon` presets
set it, and it is why they look the way they do: a cartoon with sticks on a few
residues is a mess otherwise, because each stick residue also draws its backbone
N, C and O inside the ribbon.

The thing to get right is that it is a **bond filter, not an atom filter** — the
atoms stay in the model and stay pickable, and it is the bonds *between* them
that are dropped where a cartoon already covers them. Suppressed: `CA-C`,
`N-CA`, `N-C`, `C-O`/`C-OXT`, and every hydrogen on CA and N. Kept: `CA-CB`,
which is what the side chain hangs from. Two exceptions carry the meaning —
**proline** keeps its `N-CA` because its ring needs it, and `marked` atoms (a
cartoon here, none on the bonded neighbour) keep their backbone bonds so sticks
at the end of a segment still reach the ribbon. Measured on 148L residues 20–26:
62 stick bonds become 35, and the 27 dropped are exactly 7 `N-CA`, 7 `CA-C`,
7 `C-O` and 6 `C-N`.

PyMOL's nucleic branch (`na_mode`, the `C[45][*']` bonds) is not transcribed, so
the helper only ever hides protein backbone bonds.

**Vectorised, because it runs on every scene rebuild.** The first cut was a
per-bond Python loop: 4 ms on 1 000 bonds is invisible, but **1.3 s on 500 000**,
and this repository's demos reach that. Every test in the rule is on the two
endpoints, so it rewrites as gathered boolean arrays with the same result —
**332 ms at 500 000 bonds, 4× faster**, identical hidden counts at every size.
It is left there rather than tuned further because the filter runs *after* the
sticks mask, so its input is the scoped bond list: a binding site is ~60 bonds,
and reaching 500 000 means sticks on everything, which is a heavy scene already.

## Two coordinate arrays, and they had drifted apart

The worst defect found so far, because it made commands disagree about where the
molecule *is*. chimol keeps coordinates twice — `atoms["xyz"]` in Angstrom, and
the renderer's arrays in scene units — and `_apply_rigid_transform` **skipped
structured arrays on purpose**. So `translate` and `rotate` moved the render
arrays and left the atom array behind.

Everything that reads the atom array was then working from pre-transform
coordinates: `align`, `super`, `get_area`, `get_extent`, `alter_state`, and every
distance selection. On a displaced copy, `rms` (render arrays) reported 281 Å
while `align` (atom array) saw nothing to do, announced an RMSD of 0.000, and
moved nothing.

Both halves are fixed: the transform now reaches the atom array — through the
scale, since the translation arrives in scene units and the atom array is in
Angstrom — and `rms` converts its result out of scene units, having previously
printed a length ten times too large with an Angstrom sign on it.

One test had encoded the desynchronisation (it asserted that `save` and the atom
array *disagreed* by exactly the translation) and now asserts they agree.

**Sampling is orientation-dependent.** Fixed dot directions mean a rotated
molecule samples its own surface slightly differently — a few percent at the
default density. Pure translation is exact. Documented in the concept page; worth
knowing before comparing two structures' areas.

## `pair_fit`

`align` finds its own correspondence; `pair_fit` takes one you state, matching
atoms in order within each pair. That is what you need when the two structures are
not the same sequence, or when only a domain or a ligand should drive the fit.
Several pairs feed **one** least-squares fit, so a superposition one stretch would
leave ambiguous can be pinned down by adding another.

`intra_fit` and `intra_rms` fit the *states* of one object to each other; chimol
holds a single coordinate set per object, so they have nothing to work on and are
deliberately absent rather than stubbed.

## Bonds were inferred from one distance

chimol used a single 1.9 Å cutoff for every pair of atoms. A single cutoff has to
be wide enough for the longest real bond, which makes it wide enough for a mere
*contact* between heavier atoms — and too narrow for the longest. Both errors were
live:

* **every disulfide was missed.** S–S is 2.05 Å, past the cutoff, so no structure
  ever showed one;
* on a model *with* hydrogens the old rule produced 2278 bonds the new one does
  not, of which **2138 are hydrogen-to-hydrogen** — pairs that are never bonded —
  and most of the rest are hydrogen bonds at ~1.65 Å drawn as covalent.

Every bond-based feature inherited those: sticks and lines drew them, and `bymol`,
`bound_to` and `extend` walked across them.

Now transcribed from `is_distance_bonded` (`layer2/ObjectMolecule2.cpp`):
`|v1−v2| − (vdw1+vdw2)/2 ≤ connect_cutoff + adjustment`, with 0.35 as the cutoff,
+0.2 for sulfur, −0.2 for hydrogen, never between two hydrogens, and a coincident
guard at `R_SMALL4` — which the first transcription omitted, so duplicate atom
records bonded to themselves.

The radii come from the atom array, so this needed no new data.

## Putty

A tube whose thickness carries a number — one of the few representations that
shows a quantity rather than a shape, and for this group the quantity is rarely a
b-factor: an accessibility from `get_area`, a fitted lifetime, a per-residue
efficiency, written in with `alter` and drawn.

Scale factors transcribed from `ExtrudeComputeScaleFactors` (`layer1/Extrude.cpp`)
— all nine transforms. Two details change the picture and are pinned by tests: the
clamp is applied **after** the power, and the factors are smoothed along the chain
with a running window that leaves the ends alone (without it, one outlying residue
beads the tube instead of bulging it).

The extrusion already accepted a per-point `vert_scale`; only the scale factors and
the wiring were missing.

**Verified geometrically rather than visually**, since the ray tracer cannot draw a
cartoon: the tube's actual ring radii are measured back out of the mesh. A uniform
tube is constant at 5.0; a putty tube over a monotone property ranges 2.4–10.2,
monotone, with its thinnest point at exactly `radius x scale_min`. That pins two
settings and the transform at once, and is a stronger check than looking at a
picture.

## Scenes

`scene` stores the camera, object activity, representations and colours, with
PyMOL's per-aspect flags so a scene can carry only a viewpoint or only a
colouring. Two things are chimol-specific, both from the camera being stored
*relative to the scene centre*, which moves when what is drawn changes:

* the view is restored **last**, after the representations — restoring it first
  lets the rebuild undo it;
* `view=0` actively holds the camera across the rebuild, since otherwise "leave
  the view alone" still moves the picture.

## `get_area` is the one with physics in it

Solvent accessibility decides where a dye can be attached and how freely it moves,
so this is one of the few numbers the viewer computes that feeds back into
experiment design. Transcribed from `RepDotDoNew` in `cRepDotAreaType` mode, with
two details that a generic Shrake–Rupley gets wrong:

* the points are an **icosahedral geodesic** (12/42/162/642/2562 for `dot_density`
  0–4), reproduced exactly — dot counts verified against `Sphere_nDot`;
* each point carries **its own** solid angle, from the spherical excess of its
  incident triangles, not `4π/N`. On a geodesic sphere the twelve original
  icosahedron vertices have five neighbours where every later vertex has six, so a
  uniform weight is wrong by a few percent, worst at low density (min/max weight
  ratio is 0.74 at the default level).

Validated three ways: the weights sum to 4π to 1e-9 at every level; an isolated
sphere and two overlapping spheres match closed-form areas, converging 6.3 % →
1.5 % → 0.2 % across densities 0/2/4; and a random cluster agrees to within 1 %
with an independently written Shrake–Rupley using a *golden-spiral* sphere and
uniform weights, so a shared mistake in the tessellation cannot hide. T4 lysozyme
gives 8 200 Å² accessible against 17 700 Å² van der Waals — the factor of two that
makes labelling the surface without saying which one nearly meaningless.

Every atom occludes even when only a selection is reported, which is the whole
point: the area of a residue *in* a protein is not its area in isolation.

# Documentation

**Closed.** Theory in `docs/concepts/molecular_surfaces.md`, application in
`docs/guides/44_molecular_viewer.md`, each registered in its index and
cross-linked. Both figures regenerate from `docs/guides/make_screenshots.py`
(`_grab_chimol_viewer`), and every command and Python snippet in both pages was
executed to confirm it runs — 43 of 44 command lines pass, the exception being
`png`, which the guide itself documents as needing a display.

# `ray` renders the scene, not the molecule

Found while making the guide's figure: `ray` traced **every atom in every state**.
`hide everything` and `show spheres, resn NAG` produced the identical picture of
the whole molecule, because it called `get_atom_sphere_data`, whose contract is
explicitly "all atoms regardless of representation".

Now filtered by `sphere_visible_mask`. The rule that matters: the per-atom mask is
the authority where one exists and the boolean flag is only the whole-object
fallback — `show spheres, resn NAG` sets `_ball_mask` and leaves `_show_atoms`
alone, so reading the flag alone sees nothing.

## The refusal outlived the limitation

"The tracer draws spheres only and cannot render a cartoon" was true when it was
written and stopped being true when `render_scene` learned triangle meshes — the
cartoon *is* a triangle mesh, and so are sticks, surface and metaballs. What kept
it true in practice was the **guard**: `ray` decided what to do from the count of
visible *spheres*, which a cartoon-only display (PyMOL's default, and chimol's)
leaves at zero, so it returned early with the message and never reached the scene
path sitting fifty lines below that could have drawn it. A capability nobody
could invoke, behind an error message asserting it did not exist.

The lesson generalises: **a stated limitation is a claim with a shelf life.** It
was re-read as documentation by everyone who came after, including the guide and
this tracker, and the one test covering it asserted the *refusal* — so the suite
defended the bug. When a limitation is lifted somewhere else in the tree, the
sentence stating it is a call site that needs updating.

`ray` now asks the scene what it holds. Also from that work:

* **`line` geometry is traced**, as PyMOL does it: a segment becomes a *sausage*
  (`ray->sausage3fv`, `layer1/CGO.cpp` `CGO_LINE`), split at the midpoint into
  two capped cylinders so each half keeps its own atom's colour
  (`CGO_SPLITLINE`). The tracer has no cylinder primitive, so the shaft is
  tessellated and the caps stay spheres — which it intersects exactly. Width
  follows PyMOL's `line_radius`-else-`PixelRadius * line_width / 2`, so a line is
  *n pixels* wide at any output resolution.
* **`text` is the one kind that cannot be traced**, and is named in a message
  rather than dropped.
* **The fallback could contradict the viewport.** With the scene empty after
  `hide everything`, `ray` fell through to `get_atom_sphere_data`, which still
  offered 32 ligand atoms — and drew a molecule that was not on screen. A viewer
  that produced a scene has already said everything it draws; the atom path is
  now only for a viewer that has no scene at all.

Still open: transparency (a `render_mode="transparent"` surface traces opaque),
and the baked-occlusion interaction below.

## A mesh that is really spheres should say so

Routing `ray` through the scene made `as spheres` **380× slower** before anyone
noticed the picture was the same: the viewport draws space-filling spheres as one
merged mesh, so 1363 atoms of 148L arrived as 210 240 triangles — **113.9 s**,
against **0.3 s** for the 1363 spheres the tracer intersects exactly and without
facets. The ball mesh now carries the centres and radii it was built from in
`Geometry.meta["spheres"]` and `render_scene` prefers them: 113.9 s → 0.3 s.

The record is kept **at the builder**, not rebuilt in the tracer from
`get_atom_sphere_data`, for the same reason the sphere fallback had to go: a
second source for "which atoms are drawn" is a second answer.

And the builder existed **twice** — the shared `_build_balls_mesh` and an inline
copy of it in the scene builder, sixty lines of the same tessellation plus a
duplicated nested guard with identical conditions. They had already diverged
(only the inline one baked occlusion), and the `meta["spheres"]` record landed in
the copy nobody was calling, which is how the duplication surfaced. **A duplicated
builder does not merely drift: it cannot *receive* what the other learns** — the
same shape as the RMF reader's private route into the viewer. 83 lines deleted;
`_build_balls_mesh` takes the bake as an argument and is the one builder.

## `ray` came out far darker than the viewport, and it was a missing term

Reported as "way too dark, and the lighting does not correspond to the live
view" — which turned out to be one fault, not two.

PyMOL's traced brightness has **two** diffuse terms (`layer1/Ray.cpp`):

```
bright = ambient
       + ((1-direct_shade) + direct_shade*lit) * direct * direct_cmp
       + lreflect * reflect_cmp
```

`direct_cmp` is `pow(surfnormal[2], power)` — the normal's z in *camera* space —
so `direct` is a **headlight**: a surface facing the viewer is lit whatever the
lamps are doing. `reflect` is the lamp-driven term, and `lreflect` carries
`reflect_scale`, which the source comments as "divide up the reflected light
component over all lights" — so chimol's averaging over lights was already right.

chimol had only the lamp term: `bright = ambient + diffuse * reflect_norm`. Its
ceiling was **0.14 + 0.45 = 0.59**, and only where a lamp faced the surface
squarely, against PyMOL's 0.14 + 0.45 + 0.45 clamped to 1. The missing 0.45 was
the whole complaint.

Measured on 148L's cartoon, mean brightness of lit pixels, against the GL
viewport rendering the same scene from the same camera:

| | mean lit | p95 |
| --- | --- | --- |
| `ray` before | 35.5 | 97 |
| `ray` after | **50.3** | 144 |
| viewport (GL) | 51.1 | 134 |

Within 2 % of the viewport, from 30 % below it. `direct` (0.45) and `power`
(1.0) are registered under PyMOL's own names and defaults (`SettingInfo.h` 8
and 11); they are new config keys, so a merge adds them and no migration is
needed.

**Not established, and worth a fresh look:** whether `ray` and the viewport also
disagree about *framing*. A first comparison suggested the traced molecule sits
smaller in the frame, but the viewport capture includes the panel and mouse-mode
text drawn inside the GL widget, and a brightness threshold picks those up as
"molecule" — so the measurement was measuring chrome. Redo it by masking to the
scene column and comparing silhouette bounding boxes, not by eye and not on a
whole-frame statistic.

## `ray` looked slow, and it was compiling, not tracing

Reported as "1f5n takes more than 10 s". The trace is **0.4–0.6 s** for that
structure at 638×291 with 2×2 samples; end to end through the command, thread
and PNG write it is 0.46 s in a fresh process.

The 10–33 s is **numba compiling the tracer kernel**. It is cached under
`~/.chisurf/cache/<module>_<contenthash>/`, and the hash is over the source — so
*every* change to `raytracer.py` or `bvh.py` throws the cache away and the next
`ray` anyone runs pays a full recompile. Measured directly: 33.5 s immediately
after a kernel signature changed, 0.46 s in the next fresh process. It also
means a **fresh install** pays it once.

Nothing said, that reads as "ray is slow", and the number a user reports is the
compile. So `ray` now says which it is spending time on — it announces the
compile when `_jit_trace` has no signatures yet, and reports elapsed time in the
"wrote" message either way. A report of slow that carries no number cannot be
acted on; it cost a session of measuring to establish that a render called slow
was under a second.

## A cartoon casts a shadow now, and the second tree is gone

`ray_shadow` did nothing on the display chimol and PyMOL both start with. The
shadow query walked a **sphere-only** tree, so a cartoon — zero spheres —
returned "fully lit" for every point, and a helix lying across another did not
darken it. PyMOL shadows every primitive.

The second tree existed as an optimisation and had stopped being one. It was
built when a shadow ray cost a sweep of the whole scene, where excluding the
triangles was the difference between usable and not; with the BVH it is one more
descent of a tree that already exists. **So the fix deletes code rather than
adding it** — one tree, walked by both the primary and the shadow rays, and the
`skip` argument becomes the hit primitive's own unified index, which is finally
correct for a triangle as well as a sphere.

Measured on 148L at 320×240 2×2, before and after switching mesh shadows on:
cartoon 0.05 → 0.07 s, sticks 0.04 → 0.08 s, surface 0.07 → 0.12 s. Between
40 % and 70 % more for a shadow ray that now tests the whole scene, against a
starting point 100× faster than it was this morning.

**Checked for the failure mode this class of change has**, which is self-shadow
acne — a surface shading itself dark where adjacent triangles occlude at grazing
angles. None on the cartoon or the surface; the difference against the old
picture sits in the crevices between surface lobes and under the ribbons, which
is where a cast shadow belongs. The `skip` index plus the existing
`shadow_fudge` offset is enough because the tracer intersects the primitive
exactly rather than sampling a depth map.

## Every ray tested every primitive

The sphere-mesh finding above is the same bug seen through a keyhole. Trading
210 240 triangles for 1363 spheres bought a 380× speedup because the tracer's
cost was **linear in the primitive count per ray** — so the fix that worked for
one representation could not work for any of the others, whose triangles are not
secretly spheres. A cartoon is 39 252 triangles and a solvent surface 51 748, and
each of them was intersected by every sample, for every transparency layer.

Measured on 148L at 320×240 with 2×2 samples, before and after a BVH:

| Representation | Geometry | Before | After | |
| --- | --- | --- | --- | --- |
| cartoon | 39 252 triangles | 19.12 s | 0.126 s | **151×** |
| sticks | 33 216 triangles | 8.96 s | 0.062 s | **144×** |
| surface | 51 748 triangles | 35.00 s | 0.198 s | **177×** |
| lines | 5 536 caps + shafts | 51.11 s | 0.152 s | **337×** |
| spheres | 1 314 spheres | 0.32 s | 0.058 s | 5.6× |

A publication-sized cartoon — 1024×768, 2×2 samples — went from **195 s to
0.30 s (651×)**. The win grows with resolution because the one linear cost left
is building the tree, which is paid once per render rather than once per ray.

`spheres` gains least because it was already the cheap case: it is the one
representation whose primitive count the earlier fix had brought down to 1314.
That is the tell that the sphere-mesh work had treated a symptom.

**The picture is unchanged, and that was checked rather than assumed.** Rendering
each representation through both tracers and differencing the images: cartoon,
sticks and surface are **bit-identical**, every pixel. The tree changes which
primitives a ray tests, never what a hit is.

`spheres` and `lines` do differ, in 3.6 % and 0.03 % of pixels, and the cause is
a defect the tree exposed rather than caused: the shadow query returned
**whichever occluder came first in the array**, so how soft a contact shadow came
out depended on the order the scene happened to be built in. PyMOL takes the
nearest one, and takes it precisely when the decay is on —
`nearest_shadow = (shadow_decay != _0)` in `layer1/Ray.cpp` — because the decay
is a function of how far the occluder is, so any other occluder answers a
different question. Every one of the 2 788 changed pixels is **brighter, none
darker**, which is what the nearest occluder implies under
`occlusion = 1 − exp(−(t − decay_range) · decay)` and is how the change was
confirmed to be that one change and nothing else.

A second defect fell out of the same place: the hit primitive was passed to the
shadow query as the sphere to skip, **without checking it was a sphere**, so a
triangle hit excluded the sphere sharing its index from casting. Invisible on a
pure cartoon (no spheres) and on pure spheres (indices agree); it needed a mixed
scene, which is exactly what a wireframe is.

**What made this survivable for so long** is that the tracer was correct. There
was no wrong picture to notice, only a slow one, and slow reads as "ray tracing
is expensive" — a statement about the technique rather than about this
implementation. The 380× sphere-mesh finding should have been the alarm: a
speedup that large is rarely a property of the geometry, it is usually the
complexity class.

The tree is a binned-SAH BVH in
[`renderer/bvh.py`](/chisurf/plugins/chimol/chimol/renderer/bvh.py); spheres and
triangles share one index space so a mixed scene is one tree and one descent.
The guardrails are in `test/test_bvh.py`, and the one that matters is the last:
every correctness test there passes just as well against an exhaustive search,
so cost is asserted separately, or removing the tree would leave a green suite.

Two traps found building it, both of which draw a plausible wrong picture rather
than failing:

* **A cartoon is full of exactly axis-aligned triangles**, whose bounding box is
  exactly flat in one dimension. A ray travelling in that plane computes
  `0 × inf`, and the NaN loses every comparison — so the triangle silently
  leaves the image. The bounds are padded at build time.
* **A traversal stack that overflows drops geometry**, so the build caps depth
  and forces a leaf rather than letting a pathological split sequence outgrow
  the stack. An over-full leaf is merely slow, which is the right way for this
  to fail.

## The depth cue was normalised against the wrong range

Measured while checking that the traced cartoon looked right — it came out dark,
and the cause was not the cartoon. The fog fraction was `best_t / far_clip`:
distance from the **camera**, over a far plane fitted to nothing. On 148L the
camera sits 1730 units out with a far plane at 2442, so the whole molecule
occupied 0.58–0.83 of the range and every pixel of it was fogged 24–69 %. No
pixel anywhere in the image was unfogged, which is a dimmer, not a depth cue.

PyMOL normalises over its front-to-back **clipping** range —
`ffact = (front - dist) * invFrontMinusBack` (`layer1/Ray.cpp`) — and those planes
are fitted around the object, so its fog spans the molecule exactly. `trace` now
takes `fog_front`/`fog_back`, and `render_scene` derives them from the scene's own
bounding sphere. Measured on the 148L cartoon: mean lit pixel 21.9 → 33.3,
p95 60 → 96, brightest 173 → 255.

`camera.far_clip` had **no other consumer** — it was named as a clipping distance
and only ever used as the fog denominator, which is how it survived: a wrong
value for the fog looked like a right value for something else. Two call sites
had grown a `× 1.2` widening of it, compensating for a fog they had not
diagnosed; both are gone.

## Three defects found by *using* the feature, not by testing it

Each was invisible to the suite and obvious the moment a real command ran:

* **`label` stored the text and showed nothing.** PyMOL's `ExecutiveLabel`
  follows the text with `OMOP_VISI(cRepLabelBit, cVis_SHOW)`
  (`layer3/Executive.cpp`) — labelling *turns the representation on*. ChiMOL's
  did not, so `label name CA, resi` reported "Labelled 11 atoms" over an
  unchanged view and the fix was a `show labels` the user had to guess. A
  success message over a blank view is the worst shape a defect can take.
* **`ray` raised before casting a ray, whenever there was a window.** It set its
  progress display up with six `QProgressDialog` calls; `ChiSurfProgress` is a
  facade that carries most of that surface deliberately, so five worked and
  `setMinimumSize` raised. The headless path skips the display entirely — so the
  tests, which are headless, exercised the one path that worked. The caller now
  uses the facade's own spelling, and the facade grew the two members it was
  missing (`setMinimumSize`, `deleteLater`), because an incomplete compatibility
  shim is worse than none: it invites exactly this call site.
* **Seven scoped-representation masks were unclassified for `sort`.**
  `test_sort_mask::test_every_array_field_is_classified` — the guardrail written
  for precisely this — had been red since the masks landed. Six are atom-indexed;
  `trace_mask` is per *residue*, like `cartoon_mask`, because the trace is one
  point per CA.

# Capturing the GUI headlessly

Real constraints, verified:

* Offscreen clamps a `QMainWindow` to 640×603 whatever `resize` asks for, so
  **grab the widget you want rather than the window** — a child widget honours its
  own `resize`.
* `QOpenGLWidget` content never appears in a `QWidget.grab()`: that reads the
  backing store, so a window grab shows the panels over an empty viewport. Use
  `grabFramebuffer` for the 3D view and `grab()` for the surrounding layout —
  two images, not one.
* **Offscreen does not exercise GL.** Under `QT_QPA_PLATFORM=offscreen`
  `grabFramebuffer` returns black, so the ray tracer is the only headless
  capture — which is what `okf/workflows/testing.md` prescribes for visual
  tests, and it is enough for geometry. It is *not* enough for shading,
  representation flags or anything the scene builder decides: those need
  `QT_QPA_PLATFORM=cocoa` and a real window. Four defects listed below survived
  a full offscreen suite and were obvious in the first windowed render.
* `ray` driven through `MolViewPluginWindow` hands the trace to a worker and
  reports `ray: cancelled` in a script with no event loop of its own. Driving a
  bare `MolView` traces synchronously and works.
* `ObjectsDock.widget` is a **property**. Calling it (`widget()`) raises
  `TypeError: 'QWidget' object is not callable`.

:::{note}
A previous revision of this file claimed that grabbing the objects panel crashed,
and that grabbing the window crashed once the panel held two rows. **Both were
wrong.** The "crashes" were `TypeError` from calling that property, and the
tracebacks were hidden because the diagnostic scripts filtered stderr through
`grep`. Panel grabs work at any size and with any number of rows. The lesson is
the diagnostic one: a silent exit under a filtered pipe is not evidence of a
crash, and the filter has to come off before drawing a conclusion.
:::

# What only a real window showed

The capture notes above are about getting *an* image. Getting a **correct** one
needed a window with a GPU behind it: `QT_QPA_PLATFORM=cocoa`, a real
`grabFramebuffer`, and the PNG read back. Four defects were sitting in a tree
where every test passed, and none of them raised anything.

## Three representations drew nothing at all

`show spheres, all`, `show sticks, all` and `show cartoon, <sel>` produced zero
geometry. The selection branches set the per-atom *mask* and left the boolean
*flag* the scene builder also requires — so the mask said which atoms and
nothing said whether to draw them. `show lines` and an unqualified `show
cartoon` took different branches and worked, which is why it went unnoticed.

The general shape: **a representation is described by two pieces of state, and
writing one of them is a silent no-op.**

## Occlusion was counted twice, and swallowed half the picture

Ambient occlusion is multiplied into the vertex colour *and* handed to the
shader as `v_occ`. The fragment shader then damped ambient, rim, environment
and sun by `1.0 - v_occ`. A deeply occluded fragment therefore got a dark base
colour and near-zero ambient and came out solid black — whole helices vanished
into the background. Flooring the second term (`mix(0.35, 1.0, 1 - v_occ)`)
keeps occlusion reading as shape without extinguishing anything.

## `spectrum` never reached the cartoon

`spectrum count, rainbow` writes **per-atom** colours. The cartoon and the trace
read **per-residue** ones. So the command reported success, the atoms were
correctly coloured, and the ribbon went on showing the load-time blue-to-orange
gradient — a picture with no green, cyan or yellow in it. Measured on the mesh:
the green channel never exceeded 0.55 where a rainbow drives it to 1.0.

`_ca_rgba` now projects the per-atom override down to per-residue (each residue
takes its CA atom's colour, or the mean of its atoms), folded in at the single
place the per-residue array is finalised. The sequence strip was a *third* copy
of the same colouring, refreshed by `color` and not by `spectrum`.

That is the [working rule 5](#working-rules) failing for the third time, now in
its rendering form: **one colouring, three arrays, and a command that writes one
of them.**

## `nonbonded_size` is about bonds, not about polymers

PyMOL shrinks *nonbonded* atoms — ordered waters, free ions — so a shell of
full-size solvent does not bury the molecule. ChiMOL was shrinking everything
absent from the polymer colour map, which quartered every bonded ligand:
`show cartoon, polymer` plus `show spheres, organic` drew the ligand as a
scatter of dots. It now derives the mask from the inferred bond list, so it
agrees with the `nonbonded` selection keyword instead of being a second opinion
about what counts as solvent.

Worth recording as a testing lesson: at the bounding-box level, quartering every
ligand radius moves the measurement only from 0.998 to 0.892 of the van-der-Waals
envelope, because a bounding box is dominated by how far apart the atom *centres*
are. It is glaring on screen and easy to sleep through in an assertion — the
first threshold written for it (0.85) passed the bug.

## The default layout gave the viewport 40% of the window

The dock state asked for a 3:1 split by writing `"sizes": [3, 1]` among entries
that are otherwise pixel counts. QSplitter reads pixels, clamped the viewport to
its minimum width, and the 3D view ended up smaller than the side panels. The
sequence strip had the mirror problem in the other direction: 150 px allocated
for ~90 px of content, leaving a band of dead grey under the letters.

A guard test now rejects any `sizes` entry below 20, since a ratio and a very
small pixel count are indistinguishable by inspection.

# Rendering: the next front, and what it needs

The target ([specs/chimol](/specs/chimol.md)) puts rendering first, because it is
where "better than PyMOL" is actually won. ChimeraX's model is surveyed there.
This section is the *implementation* finding, so the next round starts from the
design rather than rediscovering it.

## Silhouettes — the algorithm, transcribed

From `graphics/src/fragmentShader.txt` (`USE_DEPTH_OUTLINE`) and
`opengl.py::Silhouette._draw_depth_outline`. A full-screen pass over the **depth
texture**:

1. sample this fragment's depth `d0`;
2. take `ds` = the **minimum** depth over a disc of radius `thickness` around it,
   excluding the centre;
3. discard unless
   `nf*(d0 - ds) >= jump * (1 - nf1*ds) * (1 - nf1*d0)`, where `nf` is the
   perspective near/far ratio and `nf1 = 1 - nf`;
4. otherwise write the silhouette colour.

The `(1 - nf1*ds)(1 - nf1*d0)` factor is the part that is not guessable: it
**linearises the non-linear depth buffer**, so `depth_jump` is a fraction of
*scene* depth rather than of buffer values. Without it the outline thickness
varies with distance and the setting means nothing consistent. Under an
orthographic projection `nf = 1`, the factor collapses to 1, and the test is a
plain depth difference — so a first implementation can be checked against the
simple case before trusting the general one.

Defaults: `thickness = 1` px, `color` black, `depth_jump = 0.03`.

## What chimol lacks

**Superseded — read the section above first.** The scaffolding described here as
missing exists (`renderer/postprocess.py`), and silhouettes are built on it. What
was missing was that switching it on broke the window; that is fixed. The
remaining items are multishadow occlusion and depth cue, which reuse the same
target. Kept for the design it records:

`qtgl.py` rendered straight to the default framebuffer: no
framebuffer-object scaffolding, no depth texture, no full-screen-quad pass and no
second shader program. Silhouettes, multishadow occlusion and depth cue all
need that scaffolding, so it was the first task and it is shared:

1. an FBO with a colour **and depth texture**, sized to the viewport and rebuilt
   on resize;
2. `paintGL` renders into it, then blits colour to the default framebuffer;
3. a texture-window helper — quad VAO plus a shader program taking the depth
   texture — for post-process passes to reuse.

Only then is the silhouette pass a small addition. Doing it the other way round —
bolting one pass into `paintGL` — is what makes the second and third effects
expensive.

**This must be verified in a real window.** Offscreen Qt creates no GL context, so
none of it is exercised by the offscreen suite; see the capture notes above.

## The viewport had no depth cue, and the settings for it were pointed at the tracer

`depth_cue`, `fog` and `fog_start` are **global** settings in PyMOL:
`SceneSetFog` (`layer1/Scene.cpp`) applies them to the *viewport*, and the ray
tracer follows unless `ray_trace_fog` / `ray_trace_fog_start` override — which
is why PyMOL has those two as separate names at all. chimol registered all three
against `ray.*` and applied them only to the tracer, so the interactive view had
**no depth cue at all** and the traced image disagreed with the viewport it was
supposed to reproduce.

The shader was already written for it. `fogDensity`, `fogColor`, the uniform
lookup and a `mix` in the fragment shader were all in place, and
`self._fog_density = 0.0` in `__init__` was **the only assignment anywhere in
the tree**. A complete feature held off by one initialiser — the fourth thing
this session that was built and unreachable, after the tracer's refusal, the
scaffolding, and the silhouette composite.

Two things had to be right, and both are transcribed rather than invented:

* **The shape.** PyMOL's fog is *linear between two planes*, not exponential in
  distance. `fog = (g_Fog_end + eye_pos.z) * g_Fog_scale` (`data/shaders/default.vs`)
  is a **visibility** — 1 unfogged — with `g_Fog_scale = 1/(end − start)`.
  chimol's shader had `1 − exp(−density · |viewPos|)`, which is a different
  curve and makes `fog_start` mean nothing.
* **The planes.** `FogStart = (back − front) · fog_start + front`, and
  `FogEnd = FogStart + (back − FogStart)/fog` when `fog` is in (0, 1), else
  `back`. Front and back are the planes fitted **around the scene** — camera
  distance either side of the target radius — not the camera's far plane. That
  is the identical distinction the tracer's fog fix turned on, and getting it
  wrong there had fogged every pixel 24–69 % with none left unfogged.

Measured on 148L as spheres, cue off against cue on: **91.6 % of lit pixels come
back unfogged** and the recessed ones fall to 0.48 of their brightness. The
guardrail asserts *both halves of that pair* — something fogged **and** something
not — because a dimmer passes either one alone. That is what the tracer's fog
failure looked like from inside a single-number check.

Defaults are PyMOL's: `depth_cue` **on**, `fog` 1.0, `fog_start` 0.45
(`SettingInfo.h` 84, 88, 192).

**One store, read where it is used.** `_fog_planes` reads the config on every
frame instead of caching onto the renderer, so `set depth_cue, off` cannot leave
a stale copy behind — which is exactly the failure the silhouette settings still
have, one section down.

Still open: the config path is `ray.depth_cue` / `ray.fog_start` /
`ray.fog_intensity`, which now reads wrong for settings that govern both
renderers. Moving them to a section of their own is a **key move**, and the
migration table only knows how to update a *default* — so it needs a small
extension to the loader rather than a table entry, and is worth doing with
`silhouette`'s two-store problem in the same change.

## The FBO scaffolding was built, and switching it on broke the window

The "what chimol lacks" list below said there was **no** render-to-texture
scaffolding and named it the next task. It has been there for some time, with
silhouettes on top of it — the entry was a claim with a shelf life, like the
tracer's refusal. What was true is that **nobody could have used it**: turning
silhouettes on took the sequence strip off the screen and jumped the molecule
half an inch up the window.

Three defects, all in how the offscreen pass meets the rest of the frame, and
all invisible to the suite because nothing rendered a *window* with an effect on.

* **The overlay was painted before the composite.** `_render_overlay` draws with
  QPainter, which targets the **widget's** framebuffer rather than the bound
  one, so the chrome went down first and the composite blit then erased it. The
  strip lost **53 %** of its ink. The two early-return paths in `paintGL`
  already ran `end()` first; only the path that draws a molecule did not.
* **The offscreen buffer was the window's full height** while the direct path
  reserves a band for the strip, so the scene was rendered centred in a taller
  frame than the one it is shown in and visibly shifted — and the blit, sized to
  that buffer, covered the band as well.
* **A window that has not been laid out built a 1-pixel-wide framebuffer.** The
  same `scene_width` floor that once told the camera the window was thirty times
  taller than wide: the scene renders into it, `end` blits a one-pixel column
  back, and **the molecule disappears**. The effect passes now decline below
  `_MIN_MEASURABLE_SCENE`, which is what they already do when no effect is on.

**The metric lied before the picture did, again.** The first measurement said
"10.28 % of pixels changed — the setting works". It did change the picture: it
was deleting the strip and moving the molecule. A real outline moves **0.15 %**.
That ratio is now the assertion, because *more* change is the failure here, not
less — and it is the same lesson the two-sided lighting work recorded one
section down, arrived at from the opposite direction.

Guardrails in `test_lighting.py`, which already renders real framebuffers. The
strip one asserts **ink coverage**, not pixel equality: painting after a
composite leaves QPainter different GL state and moves glyph antialiasing by up
to 12/255 (mean 0.38) with the two crops indistinguishable side by side, while
erasure takes the ink to nearly nothing. Both were checked against the old code
and do fail there.

The third defect also caught the *test* out before the code: a window restored
from a persisted dock layout handed the 3-D widget 109×350 — less than the
panel's own 220-pixel column — so the helper forces a viewport and **asserts**
it got one rather than skipping. A guardrail that quietly stands down is what
this file exists to avoid.

Still open here: `set silhouette, on` is not a registered setting, so the feature
is reachable only through the ChimeraX-style `lighting silhouette=on`. And
`set_lighting` writes `_post` directly while `_DISPLAY_CONFIG["silhouette"]` is
read only at construction — two stores for one state, so the config is a startup
default that a live change never reaches. Registering the name means fixing that
first, or it is one more setting that stores and does nothing.

## Every frame rebuilt the whole scene, through a colour query

Found while costing the impostor route below, and it made that route
unnecessary. `paintGL` → `_render_overlay` → `_refresh_gui_state` →
`get_residue_colors` → **`_build_scene_for_current_object`**. The sequence strip
has no signal telling it that `color`, `spectrum` or `ss` ran, so it re-reads the
residue colours every frame — reasonable — but the only way to get them ran the
whole scene builder. With a surface shown that is a density grid, marching
cubes, gradients and ambient occlusion, **sixty times a second**.

148L at 1280×860: surface **82.12 ms → 4.25 ms** (12 fps → 235 fps), cartoon
28.34 → 4.12, spheres 17.34 → 4.94, sticks 11.61 → 3.91. The colour computation
is split out as `_recompute_colors_per_ca`, which is all `get_residue_colors`
now calls.

**The measurement is the transferable part.** Frame time was *flat against pixel
count* — 8× the pixels, same milliseconds — which rules out fill and vertex work
together and says the cost is fixed CPU work per frame. That is what redirected
the search from the shaders to the profiler. **Ask a frame to scale before
assuming what it spends on.**

The call site carried the comment *"Reading them back is a cached array copy,
which costs nothing beside drawing the molecule itself."* It was the most
expensive thing in the frame. Same shape as the refusal that outlived its
limitation: **a comment asserting a cost is a claim with a shelf life**, and this
one was load-bearing — it is why nobody looked here.

One hazard the split introduced and the fix had to close: `get_residue_colors`
sized its array from `self._coords.shape[0]`, which on a **trajectory** is the
frame count, not the residue count. The old code got away with it because the
rebuild set the array correctly and a shape check then rejected the *return
value*; computing it directly would have stored a wrongly-sized array on the
viewer for the renderer to read. `_ca_coords_2d` is now the one definition of
what a per-residue array is sized by, and it is read-only, so a colour query
cannot advance a trajectory.

Guardrail in `test_trajectory_performance.py`, structural rather than timed like
everything else in that file: the scene builder must not be entered at all. It
was checked against the old code and does fail there.

## The WebGL viewer is read out — what it had, and where it went

Surveyed whole (not only the shaders) on 2026-08-05 to answer whether it was
worth keeping. **Verdict: read out, and the 1.0 GB checkout was removed the same
day.** This section is the record that survives it.

**To read it again**, which the shader notes below still assume is possible:

```
git clone https://github.com/nglviewer/ngl junk/ngl && git -C junk/ngl checkout 60be69b5
```

`60be69b5` is the commit everything here was read from. Paths below are relative
to that checkout. It is a clean upstream tree with nothing local in it, which is
why deleting it costs only the download.

**What it was consulted for is captured.** The shader set is the part of NGL that
has no counterpart in the two standing sources, and it is transcribed into the
next section — impostor cylinders, interior colouring, opaque back faces, SDF
glyphs, matrix scale. One of those five was **measured and rejected**: impostors
buy about a millisecond on an ordinary molecule (see the frame-cost finding), so
they stay a large-model technique. That is the shader budget spent.

**Almost everything else duplicates an authority chimol already has, and the
authority is better.** NGL's representations (`rocket`, `unitcell`, `slice`,
`hyperball`, `tube`, `rope`), its colour schemes (hydrophobicity, occupancy,
partial charge, B-factor) and its measurements (angle, dihedral) all exist in
PyMOL under names chimol is *required* to match — `cartoon_cylindrical_helices`,
`cell`, `slice`, `spectrum b`. Taking them from NGL would mean implementing the
right feature under the wrong name and defaults, which is the one thing the
compatibility contract forbids. **PyMOL stays the authority on behaviour and
ChimeraX on rendering quality; NGL was only ever the third opinion on shaders.**

**Two things it has that neither of the others does**, recorded here so dropping
the checkout does not lose them:

* `surface/edt-surface.ts` — a solvent-excluded surface by **Euclidean distance
  transform**, a different algorithm from the Gaussian density grid plus
  marching cubes chimol runs. Worth knowing it exists if surface build time ever
  becomes the complaint; it is not a parity item, because PyMOL's own surface is
  a third algorithm again and *that* is the one to match.
* `geometry/spatial-hash.ts` — a flat spatial hash, which is the structure
  `geometry/neighbors.py` already implements.

**Colour schemes are the one place a gap is real** — chimol has six colour modes
(`by_secondary_structure`, `by_residue`, `by_sequence`, `by_element`,
`by_chain`, `spectrum`) where PyMOL reaches the rest through `spectrum
<expression>`. That is a PyMOL-shaped gap with a PyMOL-shaped answer, and NGL is
not needed for it.

## Shader techniques worth taking, read from a WebGL viewer

Surveyed 2026-08-05 in `src/shader/` of that viewer — a small, complete and
readable set, the opposite of PyMOL's, and the reason to read it for *how* while
reading PyMOL for *what*. The checkout is gone; the section above says how to
fetch it back, and every path below is relative to it. Not started; listed by
what each would buy.

**1. Impostor sticks and cylinders — and the measurement says take it for
*quality*, not for speed.** `CylinderImpostor.vert` + `.frag` (130 + 356 lines)
ray-cast a cylinder in the fragment shader from one quad, which is exact at any
zoom where 148L's sticks are **33 216 triangles** approximating a few hundred
capped cylinders. `HyperballStickImpostor.frag` goes further and renders the
smooth hyperboloid join PyMOL cannot draw at all.

The speed argument was measured and **does not hold at this scale**. Once the
per-frame scene rebuild above was removed, 210 240 vertices (spheres) cost
0.9 ms more per frame than 5 536 (lines) — so trading vertices for fragment work
has about a millisecond to win on an ordinary molecule, against a ~3.9 ms floor
that is the sequence strip's text. Impostors stay the right answer above
`impostor_min_atoms` (20 000), which is what they were added for.

Where it would still pay is the **ray tracer**: a real cylinder primitive would
replace the tessellated 8-sided shafts `_sausages` builds, cutting the traced
primitive count and removing facets — the same trade `meta["spheres"]` already
makes for balls, and the tracer intersects analytic primitives exactly.

**2. `interior_fragment.glsl` — 8 lines, and it fixes clipping.** When a clip
plane cuts a surface, the shell reads as hollow because the camera sees the
*inside* of far-side triangles lit as if they were outside. NGL colours any
back-facing fragment with an interior colour and darkens it, so a cut surface
reads as solid material. This is the same `gl_FrontFacing` test the
`two_sided_lighting` work already put in the shader, so the hook exists. Related
to the interior-cull item in the integrative-model notes.

**3. `opaque_back_fragment.glsl` — the cheap half of order-independent
transparency.** Forcing back faces opaque makes a translucent closed surface
depth-sort correctly without sorting anything, which is the defect that makes
GL transparency disagree with the (now correct) traced transparency.

**4. `SDFFont.vert`/`.frag` — labels that stay crisp.** Signed-distance-field
glyphs scale to any zoom from one small atlas, where rasterised glyphs blur.
Worth noting this does *not* help `ray`, which has no glyph and says so.

**5. `matrix_scale.glsl` — four lines.** Recovers the scale from a model matrix
so an impostor's radius survives a scaled transform. Cheap insurance the moment
item 1 lands, and exactly the class of bug the two-coordinate-array finding was.

# The window, not the commands

Measured 2026-08-03 by photographing the window in a realistic state and reading
PyMOL's layout rules from its source rather than from memory. The *panel* was a
faithful PyMOL clone — object list with A/S/H/L/C, mouse-mode block, sequence
strip. The window around it was not, in three ways that a construction test
cannot see and a screenshot shows immediately.

| | PyMOL | ChiMOL, before |
| --- | --- | --- |
| Movie panel | zero height until a movie exists | full-width scrubber + nine buttons for `State 1/1` |
| Command prompt | always on screen (`internal_prompt`, default 1) | a background tab in a side stack |
| Side panels | none — the object list is *in* the viewport | a third of the window, holding a filter box and white space |

**The movie rule is exact and worth quoting**: `MovieGetPanelHeight`
(`layer1/Movie.cpp`) returns zero unless `MovieGetLength()` or
`SceneGetNFrame(G) > 1`. In chimol `mset` sets the frame count, so the two
conditions collapse to one. It was the loudest thing in the panel — a salmon bar
across the whole block — and it controlled a timeline of one.

**The prompt is not a nicety.** `internal_prompt` and `internal_feedback` are
both on by default and PyMOL draws them at the bottom of the viewport, because
typing commands *is* how the program is driven. Ours had a console with output,
history and completion, docked as the fifth tab of a stack whose first tab was
showing — so the first thing a PyMOL user reaches for was invisible until found.
It is now the row under the view, full width.

**An empty panel is worse than no panel**: it reads as a broken layout. The three
side panels have nothing until a file brings it — a hierarchy, an RMF, a map — so
they start hidden and *reveal themselves* when they have content
(`_reveal_panel_with_content`). Hidden, not removed: the View menu and a
right-click on a tab bring them back, and nothing else tells someone their
integrative model has a hierarchy to browse.

## The layout was authored and never applied

Chasing the above found a defect in the **shared** dock area, so every view in
ChiSurf is affected. `set_layout_state` applied the authored `sizes` at build
time, when the splitter is about 100×30 — `setSizes` clamps each share to the
children's minimums, and the resize that follows redistributes by rules of Qt's
own. Measured on the chimol default: an authored **700/170 came out 230/614**,
inverted, giving most of the window to the console it meant to give a strip to.

Two attempts failed before the third worked, and both failures are worth
recording. Re-applying once on the event loop lands *before* the window is
resized. Stretch factors do not survive either — `QSizePolicy`'s stretch is a
`uchar`, so an authored `700` silently becomes `255`, and even at the right
ratio the split still came out inverted. What works is to treat the numbers as
**proportions and re-apply them on every resize**, until the user drags that
divider — at which point their choice replaces the author's for good. That is
also the behaviour anyone expects from a divider they just moved.

## Two menu entries that did nothing

Both found by using the window rather than testing it, and both silent:

* **View ▸ Toggle Sequence** toggled a dock retired when the strip moved into
  the viewport. `_set_tab_visible` looped over every tab, matched the name
  against none, and returned; the entry ticked and unticked and the strip never
  moved. It writes the `seq_view` setting now — the same place `set` writes, so
  the menu and the command line cannot disagree.
* A **group name inside an atom selection** answered *emptily*: `group stuff,
  ligs 148l` then `show cartoon, stuff` did nothing and reported nothing, and
  `count_atoms stuff` said `0` rather than "unknown selection". Note this was
  *worse* than the "not accepted in a selection" this file used to record — it
  was accepted, and lied. **Fixed** by the multi-object resolver; see
  [One atom table, not one object](#one-atom-table-not-one-object) below.

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

## A frame carries more than coordinates

The one place chimol had to go **past** PyMOL rather than catch up with it, and
it came from a use PyMOL does not have: an agent simulation instead of a
molecular trajectory. An MD run moves the same atoms for the whole file. A
growing colony does not — cells **appear**, **grow**, and **change what they are
doing where they stand**.

RMF has always stored a radius and a colour **per frame**. chimol read neither:

* radii were read once, *after* the frame loop, so they came from whichever frame
  the walk happened to leave current — the last one. Nothing failed, because
  every file anyone had opened stated one radius;
* `ColoredConstFactory` was constructed in the loader and **never asked**. A file
  that states its own colours was drawn in the viewer's defaults.

Both are now read per frame and collapsed to a single array when they turn out
not to vary, so a static model grows no time axis and every consumer that does
not care about frames keeps asking for one array.

**A radius of zero is how "does not exist yet" is expressed**, because an RMF's
node set is fixed for the whole file. That needed a third visibility mask
(`absent_mask`), *not* a reuse of `hidden_mask`: one mask serving both questions
means stepping the movie silently un-hides whatever the hierarchy panel switched
off — the identical failure `representation_mask` was split out to avoid. All
three compose in `visible_row_mask`. Zero could not simply be passed through as a
radius either: the renderers substitute a default for a non-positive one, so
every unborn cell would have been drawn at full size from the first frame.

### Four traps, in order of how much time they cost

1. **`numpy` converting a SWIG object uses the iteration protocol.** Assigning an
   `RMF.Vector3` into an array row costs **20 us**; reading `v[0]`, `v[1]`, `v[2]`
   costs **1.4 us**. On 60 frames x 2600 beads that was **17 s of a 19.7 s load**,
   and the profile named `Vector3___getitem__` with 624 000 calls. The same
   spelling was in the coordinate fallback path and was fixed with it.
2. **`np.array_equal(frames, frames[:1])` does not broadcast.** It compares
   shapes first, so a series that never changes reads as one that always does,
   and every static file grew a full time axis. `np.all(frames == frames[0])`.
3. **`IMP.rmf` cannot write what RMF can store.** `save_frame` snapshots
   `IMP.display.Colored` when the hierarchy is added, so every frame comes back
   the colour the model started with. Writing through RMF directly gives per-frame
   colour and radius. This is worth knowing before designing around the
   limitation: the simulator had built an elaborate workaround — one particle per
   cell *per observed state*, with the unused ones parked at (-100, -100, -100) —
   for a constraint that belongs to the bridge, not to the format.
4. **An unborn particle still needs coordinates**, and they must be its nearest
   ancestor **alive in that frame**, not its parent — the parent is usually
   unborn too. Resolving one level put frame 0's invisible beads over the shape
   the colony only reached at the end, 17 um up, where the film was 1.1 um tall.
   Invisible and therefore harmless, until something frames the file.

### The camera was following the frame, and nobody had noticed

`_select_state_frame` recomputed the object's centre and radius from the frame
being shown, so the camera chased the current frame's centroid. On a molecule
the extent barely changes and the drift reads as a gentle wander — which is why
it survived — but on a structure that *grows* it is unmissable: playing the
biofilm swung the scene centre from 0 to −21 to +52 scene units and the radius
from 174 to 88 to 137, so the substratum slid about beneath a film that was
supposed to be growing off it. It was also **hiding half of what the trajectory
demo exists to teach**, since silently following the centroid removes exactly the
translational drift `intra_fit` is there to remove.

Not simply deleted: for a molecule wandering across a box, following it is the
useful behaviour, and that was the user's call. It is `movie_recenter`
(`camera.recenter_on_frame`), **on by default** because the molecular case is the
common one, read from the config *where it is used* so a live `set` reaches an
open viewer — the `_fog_planes` pattern, and the reason there is no second store
to leave stale.

Two things worth carrying:

* `set` is **global** in chimol as in PyMOL, so a demo that changes a setting
  leaks it into the next one. Each demo that cares now states the value it
  wants — a demo is a scene, not an increment;
* the centre is computed over **all rows**, not the visible ones, so a fixture
  whose particles never move cannot exercise this at all. The first version of
  the test asserted the camera *did* follow and passed vacuously against a
  fixture with fixed coordinates; it needed a drift term to mean anything.

### The demo is generated, not shipped

`Demo > Biofilm growth` has no file to fetch: the agent simulator beside ChiSurf
is run on first use (~3 s, 2600 cells over 60 frames) and cached under the
settings directory. That keeps the demo a *result* rather than a picture of one,
and it is what exercises the whole path end to end. `resolve_structure` builds it;
the failure is **raised**, not swallowed, because a path that is not there
surfaces as "cannot read file" and sends whoever hit it looking for a download.

## Clicking a residue did not work, in four ways at once

The most-used thing in a viewer, and nothing exercised it. Each defect on its
own is enough to make selection impossible, and they had accumulated:

1. **The picker was pyqtgraph's.** `_project_points_to_screen` built a camera
   basis from `view.cameraPosition()` and a `view.opts` dictionary — the
   `GLViewWidget` API, left behind when the renderer was replaced. The renderer
   kept an `opts` shim *"for compatibility with picking helpers"* whose `center`
   is a `QVector3D`; the helper passed it to `numpy.asarray`, which raises. So
   **every click raised**.
2. **The raise was swallowed** by `except Exception: pass` at the call site, so
   there was no message, no traceback, nothing in the log.
3. **The block could not run anyway**: it was gated on
   `getattr(self, "_gl_enabled", False)`, and *no code anywhere sets
   `_gl_enabled`*. A dead attribute name, defaulting to False, in front of the
   whole feature.
4. **A picked atom mapped to no residue.** `set_coordinates` — which is what
   `apply_payload`, "the single route from a file into the viewer", calls —
   cleared `_all_atom_res_ids` and never refilled it, though `set_structure`
   fills it from the same field. So for RMF, mmCIF and every bead model the
   pick succeeded and then had nothing to select.

**Why the tests passed throughout, which is the finding worth keeping.**
`test_mouse_selection.py` existed and was green. It stubbed the picking module,
set `viewer._gl_enabled = True` *itself* — supplying by hand the gate the
product never sets — and replaced `viewer.view` with a bare `object()`. Every
one of those substitutions replaced a thing that was broken with one that was
not. **A fixture is an assertion too**, and these asserted the broken
environment into existence. The tests now send real `QMouseEvent`s through the
real widget and read the selection that comes out; the merge-logic tests that
legitimately stub are kept, below a divider that says which is which.

**The projection lives on the renderer now** (`project_to_screen`), through the
same matrices `paintGL` uses, because a picker that computes its own projection
picks where the molecule is not. Two things a from-scratch version keeps getting
wrong and this one asserts: the viewport is the **scene column**, not the widget
(the panel takes a strip), and it sits **below the sequence strip**.

## The mouse block promised more than the mouse did

With picking working, the remaining gaps were in the routing, and they are all
the same shape: the *button* decided the gesture instead of the **action the
table resolves**.

* the **middle button** was turned into a pan before the table was consulted, so
  its three modified cells — `-Box`, `PkAt`, `Orig` — were unreachable. The
  block on screen drew a subtract-box that panned the camera;
* `Ctrl L` is `Move` in PyMOL, and it rotated, because the *drag* handler keyed
  on `LeftButton` rather than on what the press had decided;
* a **ctrl-shift click** — how anyone coming from PyMOL picks a residue — did
  nothing: the press correctly claimed `Sele` for a rubber band, and a band that
  is never dragged fell through a zero-size rectangle. Each box action now
  degenerates to the same operation on the atom under the cursor;
* `Orig` was in the table and wired to nothing.

`mouseReleaseEvent` was **defined twice**, and Python keeps the last, so the
earlier one — which ended the middle-button pan — never ran: after one
middle-drag the molecule followed the cursor for the rest of the session. There
was a comment saying the duplicate existed. A note that code is dead leaves the
dead code there; it is merged now.

The guardrail worth having is the one that walks **every cell of the block** and
asserts the press starts the gesture the cell names, because the block is
reference material — someone reads it to find out what ctrl-shift-middle does.

## The mates were all in the same place

`symexp` builds the crystallographic mates around a molecule. Every command
reported success, the objects appeared in the panel, the atom coordinates were
right -- and the picture was **one molecule**, because every mate was drawn at
the render origin.

Each object is drawn centred on its own centroid, so a new object built from a
mate's coordinates is re-centred onto itself and lands exactly where the
original is. Measured: six mates with six distinct centroids in Angstrom
(`[-26.2 29.8 62.2]`, `[17.9 15.4 29.9]`, ...), all drawn at `(0, 0, 0)`.
`symexp` exists to show how molecules pack, so this removed the feature
entirely while looking like it worked.

`create`/`extract` had already solved it -- `_reframe_to` moves the *render*
arrays into the parent's frame and leaves the stored coordinates alone -- and
the mates simply never got it. One call.

**Why it went unnoticed, and what to take from it:** the symmetry work was
verified through the *operators* (closure modulo lattice translations, det ±1,
one identity, 7658 of them) and through the mates' **coordinates**, both of
which were correct. Nothing looked at where they were **drawn**. A test that
asserts a transform is right does not assert that the result is *visible in the
right place*, and the two are different claims -- which is the same lesson as
the camera-framing and mouse-picking defects in this file. The guard here
compares the distances as drawn with the distances in Angstrom.

It surfaced only because `cell` gave the scene something with an absolute
position to disagree with.

## The measurement suite, and testing a number with no reference to check it against

ChimeraX is the authority on functionality, and its `measure_*` family was the
largest thing it had that ChiMOL had nothing of. Three landed:
`measure_buriedarea`, `measure_center`, `measure_inertia`.

**Buried area** is the one worth having. Transcribed from
`measure_buriedarea.py`: the SAS area of each set alone, minus the area of the
two together, **halved** — each set carries surface at the interface, so the
interface is half of what is buried. Two details that a from-scratch version
gets wrong:

* each set's own area is computed with **only that set present**, not by masking
  a crowded surface. An atom in neither set must not occlude, or the number is a
  difference of two other numbers rather than an interface;
* it is always the **solvent-accessible** surface, whatever `dot_solvent` says.
  A buried van der Waals area is not what anyone means, and silently answering a
  different question because a global flag was off is this file's most repeated
  failure.

`measure_inertia` transcribes `moments_of_inertia`: second moments over the
weight, the parallel-axis shift to the centre, `eigh`, eigenvalues ascending,
and the third axis flipped if the frame came out left-handed. It is
**mass-weighted**, as ChimeraX's is, since the table landed.

**The atomic masses came from PyMOL, with a generator, because that is the
rule.** `chempy.atomic_mass` is PyMOL's own IUPAC table, transcribed by
`analysis/make_elements.py` into `analysis/elements.py` — never hand-entered and
never a new dependency, the same arrangement as the 547 space groups. Three
things it turned on:

* PyMOL lists every symbol **twice**, cased and upper (`He` and `HE`), and that
  duplication is the useful part: a PDB element column is written both ways, and
  a table knowing one spelling drops every metal in half the files there are —
  to *nothing*, not to an error. The lookup is case-insensitive;
* an unknown symbol returns `None` and is **counted**, never defaulted. A weight
  quietly missing a metal is the kind of wrong number that gets published, so
  both commands say how many atoms they could not weigh;
* the table is verified by **properties plus its size**. A truncated extraction
  is self-consistent and passes every spot check that falls inside it, so
  `test_elements.py` asserts the count, the IUPAC values for the elements that
  decide a protein's weight, *and* that masses rise across a period — which is
  what catches a dropped row pairing symbols with their neighbours' masses.

Checked by hand where a reader can follow it: residue 1 of 148L is a methionine,
whose eight heavy atoms (N + 5 C + O + S) come to **122.13 Da**, and the whole
polymer to **17.3 kDa** — the hydrogen-less weight an X-ray structure should
have, against ~18.7 kDa with hydrogens.

**How to test a quantity with nothing to compare it against.** There is no
reference value here, so each test pins a *property*: buried area is symmetric
under swapping the sets, is zero for two residues at opposite ends of the fold,
grows with the probe radius, is refused for overlapping selections, and does not
move when `dot_solvent` changes. That is a stronger check than one hand-computed
number, which can be matched by an implementation that is wrong everywhere else.

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
