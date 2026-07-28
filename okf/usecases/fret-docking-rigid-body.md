---
type: Reference
title: Use case — FRET-restrained rigid-body docking (Structure Tools → Docking & Screening)
description: Take a two-body complex and a set of measured FRET distances and dock the bodies against them — load the docking project, score the reference pose, minimise or Monte-Carlo the mobile body, repeat the run for a score spread, and rank a structure library. Currently blocked end to end by an IMP.bff API that the plugin cannot reach.
tags: [usecase, structure, fret, docking, modelling, imp, gui]
timestamp: '2026-07-28T00:00:00Z'
---

# Use case: FRET-restrained rigid-body docking

**Goal:** the step *after*
[FPS JSON Editor](/usecases/fps-labelling-positions.md). The user has an
`fps.json` — labelling positions with linker geometry plus a table of measured
donor–acceptor distances with their asymmetric errors — and two (or more) rigid
structures whose relative arrangement is unknown. The tool places the mobile
body against the fixed one so that the accessible-volume distances it predicts
match the measured ones, reports the χ²-like restraint score of the docked pose,
and writes the docked PDBs, the score trace and (optionally) the `P(R_DA)`
distributions. This is ChiSurf's replacement for the C# **FPS** docking and the
C++ **OLGA** screening tools.

Four operations live behind one **Op** combo:

| Op | what it does |
| --- | --- |
| `dock` | rigid-body docking from a random start (`minimize` = IMP conjugate gradients, `mc` = PMI replica-exchange Monte-Carlo) |
| `refine` | local CG minimisation of the pose the PDBs already hold |
| `score` | evaluate one arrangement against the restraints, no sampling |
| `screen` | score a library of structures and rank them into a CSV |

**Data:** the plugin's own shipped example
`chisurf/plugins/modelling/fret/examples/fps_hiv_rt/` — **HIV-1 Reverse
Transcriptase** (`protein_1R0A.pdb`, 8 016 non-water atoms, chains A/B = p66/p51)
plus its **DNA** duplex (`dna.pdb`), 11 labelling positions and **20** measured
distances in `hiv_rt.fps.json`, and a ready-made `docking_project.json`
(2 bodies, `minimize`, 500 iterations, σ_DA = 6 Å). This is the canonical
protein + DNA test system. The screening/pair-selection half uses
`examples/olga_t4l/` — a 894-frame T4-Lysozyme NMSim trajectory
(`3GUN_NMSim_cl-rep_894.dcd`) with `pair_selection_tutorial.fps.json`.

**Tool:** `chisurf.plugins.modelling.fret` (`FretDockingTool`), display name
*Structure:FRET:Docking & Screening*; `menu_hidden`, so the way in is the
**Structure Tools** hub (`modelling/structure_tools`) → panel **2. Docking &
Screening**. CLI `fret`, RPC `fret.dock` / `fret.refine` / `fret.score` /
`fret.screen` / `fret.estimate_errors`.

## Steps

1. Open **Structure Tools** (🧬). The left navigation lists
   *1. FPS JSON Editor · 2. Docking & Screening · 3. Kappa2 Distribution ·
   QuEst · HydroPro · Trajectory Tools*. Click **2. Docking & Screening** — the
   panel builds in ~1.5 s (hub itself ~6 s).
2. The panel is a toolbar (**📂 Project · 💾 Save · 🏷️ fps.json · 📁 Output ·
   ▶️ Run · 🧹 Clear**), a **PDB rigid bodies (one per body)** path list
   (*+ Files · Database · − Remove · Clear*; order = `body_id` 0, 1, 2 …, the
   same file twice = homodimer), an AutoForm with two panels — *Inputs*
   (fps.json, Output, Op, Method, Score set) and *Docking* (Runs, Iterations,
   Clash k, Refine, Fixed body, σ_DA, AV backend, P(R_DA), Movie, Resume) plus a
   collapsed *Monte-Carlo (mc method only)* panel — and a dock area with
   **📊 Results · 📈 Score · 🧬 Structure** tabs over a status bar.
3. Press **📂 Project** and pick `fps_hiv_rt/docking_project.json`. Both PDBs
   appear in the rigid-body list as absolute paths, `fps.json`, `Output`
   (`…/dock_out`), Op = `dock`, Method = `minimize`, Iterations = 500,
   σ_DA = 6.0 Å are filled in. *(The status bar stays blank — RF-775.)*
4. Sanity-check the starting point first: set **Op = `score`** and press
   **▶️ Run**. Expected: the restraint score of the reference arrangement and
   the number of distances actually used, in the status bar and as one row in
   *Results*.
5. Set **Op = `dock`**, **Method = `minimize`**, **Iterations = 200**, tick
   **Movie**, press **▶️ Run**. A progress dialog with ETA and *best score so
   far* tracks `convergence.csv`; the *Score* tab plots total score vs CG step
   live; when it finishes the docked PDB is written to the output directory, the
   pose vectors are kept on the model, and the *Structure* tab steps through the
   docking trajectory with the frame slider.
6. Estimate the spread: set **Runs = 3** and press **▶️ Run** again. The three
   independent trials run in parallel, each gets its own curve in *Score* and
   its own row in *Results* (best score highlighted, sortable), and the status
   line reports `3 trials, Nx parallel: mean … ± …` plus the mobile-body RMSF
   precision in Å.
7. Press **💾 Save** to store the docked state as a project — the pose vectors
   go into the JSON, and re-loading it arms **Resume** so the next run continues
   from the docked poses instead of a fresh random start.
8. Rank a library instead: put a folder (or a list of PDBs) in the rigid-body
   list, set **Op = `screen`** and **▶️ Run**. Expected: a ranked
   `filename, score` table, best first, in *Results* and in
   `<Output>/screen.csv`.

## Expected

- `score` on the reference complex: a finite restraint score and `20`
  distances used.
- `dock`: a monotonically descending score trace, a docked PDB, a lower score
  than the random start, and a pose whose predicted AV distances sit inside the
  experimental error bars.
- `screen`: finite scores for every readable structure, `nan` only for the ones
  that genuinely failed, and a visible ranking.

## Observed (last run: 2026-07-28)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env, IMP 2.24.0) through
the Structure Tools hub with the shipped HIV-RT example copied to a scratch
directory. Screenshots at every step.

**The tool does not work at all. Every one of the four operations fails on the
same line.** `dock`, `score`, `refine`, `screen` and the repeated-run error
estimation all end in

```
AttributeError: module 'IMP.bff.restraints' has no attribute
'AVNetworkRestraintWrapper'
        core/imp_engine.py:551, build_assembly
```

after 1.4–2.3 s. The class *does* exist in the installed IMP.bff — as
`IMP.bff.restraints.AVNetworkRestraint.AVNetworkRestraintWrapper`, in a
`restraints/` directory that ships **without an `__init__.py`** and so
re-exports nothing; and with `modules/imp-tricks/src` on `PYTHONPATH` (the
documented way to run this tree) imp-tricks' own
`IMP/bff/restraints/__init__.py` replaces that namespace portion entirely, so
the submodule cannot even be imported. Verified both with and without imp-tricks
on the path — **RF-771**. The plugin's own capability probe still reports
`{"has_imp_bff": true}` because it only checks `hasattr(IMP.bff, "AV")`.

Everything around the broken seam is in good shape, which is what makes the
failure worth fixing rather than working around:

- **The GUI itself is clean.** Project load resolves the relative paths in
  `docking_project.json` against the project file, fills the rigid-body list in
  order, and populates all 18 form fields; every label carries a tooltip; the
  results table sorts numerically and highlights the best row; **💾 Save**
  round-trips the project. Layout is uncluttered at 1160×890 (screenshots
  `02_docking_panel`, `04_project_loaded`).
- **The accessible-volume machinery underneath is healthy.** Driven directly on
  the same fps.json: 8 016 atoms read in 0.02 s, **8 AVs in 0.64 s**
  (3 105–4 749 grid points each), and a pair statistic that is physically
  sensible — `p66_Q6C–p66_T27C`: `R_mp = 54.89 Å`, `⟨R_DA⟩ = 57.25 Å`,
  `⟨R_DA⟩_E = 56.24 Å`, `σ = 7.52 Å`. One position (`p66_K287C`) returns a
  **zero-volume AV with no warning** — the silent-zero-AV behaviour already
  filed as RF-478.
- **The pair-selection wizard works and is unreachable.**
  `FRETPairSelectionWindow` runs the full OLGA greedy selection on the shipped
  T4L trajectory and returns a sensible decreasing ⟨RMSD⟩ curve —
  `A48_A119 3.94 → A37_A86 3.24 → A48_A89 3.15 → A37_A116 2.98 → A37_A85 2.42 Å`
  — but it has **no entry point anywhere in the application** (RF-778), it
  **blocks the GUI thread for 53 s** with only a wait cursor (RF-777), and its
  plot's y-axis label is HTML-eaten down to `∧ (Å)` (RF-776).

Two failure-reporting defects are worse than the crash, because they do not look
like failures:

- **`screen` reports success over an all-`nan` ranking.** `imp_engine.screen`
  catches the per-structure exception and appends `nan`, so with the engine dead
  the status bar reads **"ranked 2 structures"**, `screen.csv` contains
  `protein_1R0A.pdb,nan` / `dna.pdb,nan`, and nothing anywhere says the scoring
  never ran (RF-772). The same status message is what a *successful* screen
  produces.
- **A screen's ranking never reaches the Results table at all** — the `ranked`
  branch of `_on_finished` only sets a status string, so even when scoring works
  the only output is a CSV the user has to go find (RF-773).

And two smaller ones seen on the way: pressing **▶️ Run** on a fresh, empty
panel opens a progress dialog, silently defaults the output directory to
`<current working directory>/dock_out` and **creates that directory** (verified:
a `dock_out/` appeared in the repository root) before failing with a raw
traceback dialog *"At least one PDB file is required."* (RF-774); and a
successful **📂 Project** load produces no visible feedback because the outcome
is written to a model field that no view section renders (RF-775).

**Headless limitation:** the *Structure* tab's ChiMol viewer cannot render under
the offscreen platform (`QOpenGLWidget: Failed to create context`), so the 3-D
preview and its frame slider were exercised for wiring (`preview_models` is set,
the slider reads `1 / 1`) but not judged visually.

## UX / UI suggestions

- **Say which backend is actually usable, before the run.** The panel offers an
  *AV backend* combo (`auto / labellib / imp-bff`) and `fret.info_backends`
  already exists, but nothing is shown. A one-line capability banner —
  "IMP 2.24.0 · IMP.bff AV ✓ · AV network restraint ✗" — would have turned this
  entire session's dead end into a message the user could act on.
- **Grey out what the chosen Op ignores.** With `Op = screen` the whole
  *Docking* panel (Runs, Iterations, Clash k, Refine, Fixed body, σ_DA, Movie,
  Resume) stays enabled and inviting, and none of it is read; `score` ignores
  all but σ_DA. The *Monte-Carlo* panel already carries "(mc method only)" in
  its title — apply the same idea by enabling/disabling.
- **Validate before opening a progress dialog.** Missing PDBs, a missing
  fps.json and an empty output directory are all knowable at click time; the
  tool currently starts a run, creates directories and then shows a Python
  traceback.
- **The progress dialog is labelled "Docking…" for every operation**, including
  `score`, `refine` and `screen`, and for those it has no trace file so it sits
  at "running…" and jumps to 100 %. Use the operation's own name and an
  indeterminate bar when there is nothing to count.
- **Show the load/save outcome where the user is looking.** `📂 Project` and
  `💾 Save` should both land in the status bar (Save already does); better
  still, show the loaded project's name and body count next to the rigid-body
  list.
- **Give the pair-selection wizard a home.** It is a working OLGA-parity feature
  with no way in — either a fifth `Op` in this tool, or its own entry in the
  Structure Tools navigation next to the FPS JSON Editor that produces the
  fps.json it consumes.
- **Long-running structure work needs the shared progress handle.** The docking
  tool uses `ChiSurfProgress` with an ETA and Cancel and is the model to copy;
  the pair-selection wizard freezes the window for a minute with a wait cursor.
- Left navigation labels in the Structure Tools hub are elided
  ("2. Docking & Screen…", "3. Kappa2 Distributio…") at the default split — size
  the nav column to its contents.

## Bugs filed

- **RF-771** — every docking/scoring operation raises `AttributeError:
  module 'IMP.bff.restraints' has no attribute 'AVNetworkRestraintWrapper'`;
  the whole plugin is non-functional.
- **RF-772** — `screen` turns a total scoring failure into a successful ranking
  of `nan` scores.
- **RF-773** — a screen's ranked list never reaches the Results table.
- **RF-774** — Run with no inputs creates `<cwd>/dock_out` and then fails with a
  raw traceback instead of validating first.
- **RF-775** — a successful project load gives no visible feedback.
- **RF-776** — the pair-selection plot's y-axis label is HTML-eaten to `∧ (Å)`.
- **RF-777** — the pair-selection run blocks the GUI thread (53 s, no progress,
  no cancel).
- **RF-778** — the pair-selection wizard has no entry point in the application.
