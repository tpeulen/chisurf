---
type: Reference
title: Use case — QuEst, a fluorescence decay predicted from the structure alone
description: Simulate a tethered dye diffusing in its accessible volume on a PDB structure, quenched on contact with aromatic residues (PET) and optionally transferring to an acceptor, and read the predicted quantum yield, mean lifetime, FRET efficiency and decay curve.
tags: [usecase, structure, modelling, quenching, pet, fret, decay, quest, gui]
timestamp: '2026-07-28T00:00:00Z'
---

# Use case: QuEst — the decay a structure predicts, before any measurement

**Goal:** answer *"what decay should this labelling site give?"* from the
structure alone. Every other TCSPC workflow in ChiSurf goes the other way — a
measured decay in, lifetimes out
([TCSPC lifetime fit](/usecases/tcspc-lifetime-fit.md),
[MaxEnt](/usecases/decay-analysis-maxent.md)) — and each of them silently assumes
the donor's unquenched lifetime is the one the dye actually has at *that* site.
It usually is not: a dye on a 21 Å linker spends part of its time in contact with
the protein, and tryptophan, tyrosine, histidine, methionine and cysteine quench
it by photo-induced electron transfer. QuEst simulates that: it builds the dye's
accessible volume, diffuses the dye inside it, integrates the quenching rate
frame by frame, and — with an acceptor — the FRET rate as well.

The practical uses are (a) choosing between candidate labelling positions before
ordering a mutant, (b) explaining why a donor-only reference is multi-exponential
when the dye is one species, and (c) supplying the τ₀ that
[FPS labelling positions](/usecases/fps-labelling-positions.md) and the
[FRET calculators](/usecases/fret-calculators.md) take as given. It is the
structural counterpart of
[FRET observables from an MD trajectory](/usecases/md-trajectory-fret.md), which
reads the dye positions off a trajectory instead of simulating them.

Method: Peulen, Opanasyuk & Seidel, *J. Phys. Chem. B* **121**, 8211–8241 (2017).

**Data used this run:**

* `examples/projects/t4l_proteinmc/data/3GUN.pdb` — T4 Lysozyme, the T4L
  structure the repo ships (the [testing](/workflows/testing.md) canonical PDB is
  148L; 3GUN is the same protein and is in the tree). Donor at chain **A**,
  residue **132**, atom **CB**; acceptor at **A/55/CB** — a pair spanning the
  hinge, roughly R₀ apart.
* No measured file is needed. QuEst also accepts a four-character RCSB id in the
  *Structure file* box and fetches it.

**Tool:** *Structure Tools → QuEst*
(`chisurf/plugins/quenching_estimator`, `QuEstWindow`, wrapping
`quest.gui.dye_widget.TransientDecayGenerator` from the companion **quest**
repository). The plugin is `menu_hidden`; it is reached as the fourth entry of
the **Structure Tools** hub, below the separator. The form is an `AutoForm` over
`quest/gui/quest.view.json`, whose state *is* the QuEst project dict — so the
GUI, the `quest` CLI and the web backend all consume the same JSON, and there is
no hand-written conversion between them.

## Steps

1. Open **Structure Tools** (`StructureToolsTool`). The left navigation lists
   *1. FPS JSON Editor*, *2. Docking & Screening*, *3. Kappa2 Distribution*, then
   after a separator **QuEst**, *HydroPro*, then *Trajectory Tools*.
2. Click **💡 QuEst**. The panel loads in ~0.4 s into three columns: **Project**
   (the form), **Structure** (the 3-D view of the structure with the dye's
   accessible volume and trajectory), **Results** (state line, decay plot,
   trajectory plot, autocorrelation plot).
3. In *Structure*, set **Structure file** — either type/paste a path, press the
   **…** browse button, or use the window's **Load PDB…** toolbar button. Set
   **Attachment chain** `A`, **Attachment residue** `132`, **Attachment atom**
   `CB`.
4. In *Dye*, leave the linker geometry at the measured defaults —
   **Linker length** 21.5 Å, **Linker width** 0.5 Å, **Dye radius** 3.5 Å,
   **Grid resolution** 0.5 Å. These are the same three numbers an
   [FPS labelling position](/usecases/fps-labelling-positions.md) carries.
5. In *Simulation*, set **Unquenched lifetime** 4.2 ns, **Donor diffusion
   coefficient** 7.5 Å²/ns, **Simulation time** and **Time step** (0.032 ns
   resolves the fastest motion), **Simulated photons** and **Decay bins** 4096.
6. In *Quenching*, review the 20-row amino-acid table — one row per residue with
   **kQ (1/ns)**, **Radius (Å)**, **Atoms** and **Slow factor**. The defaults
   quench on CYS (0.8 ns⁻¹, 7.0 Å), HIS (1.0, 8.2), MET, TRP and TYR; every other
   residue is listed with kQ 0, which is the point — a zero is a modelling
   statement, not an omission. Any cell is editable.
7. In *FRET*, tick **FRET enabled**, set **Förster radius** 52 Å (Ångström, like
   every length in a project — a value in nm makes FRET vanish silently),
   **Orientation factor κ²** 0.667, and the acceptor site **A / 55 / CB** with its
   own linker geometry, diffusion coefficient and **Acceptor dynamics**
   (`trajectory` = the acceptor diffuses too, `averaged` = its accessible volume
   is averaged over).
8. Open **▶ Advanced** for **Parallel trajectories**, **Slowing radius**, **Save
   AV files**, **Output file prefix**, **Trajectory skip frames** and **Random
   seed**.
9. Click **▶ Simulate** in the footer. Then — see *Observed* — **re-render the
   panel** (switch away in the navigation and back, or resize the window), because
   the button does not refresh the form by itself.
10. Read the **State** line: `QY = … ⟨τ⟩ = … ns E = …`, the decay plot (Donor and
    D–A curves), the trajectory plot (|r − ⟨r⟩| against time) and the ACF (how
    fast the dye forgets where it was).
11. **💾 Save project…** writes the project JSON that `quest` CLI / RPC accepts;
    **📂 Load project…** reads one back.

## Expected

* An accessible volume around the attachment atom, and a dye trajectory inside it.
* A donor quantum yield below 1 — the site's quenching, relative to the unquenched
  dye — and a mean lifetime consistent with it.
* With FRET on, a transfer efficiency from the two simulated yields
  (E = 1 − QY_DA/QY_D) and two decay curves: donor-only and donor-in-presence-of-
  acceptor, the second both faster **and smaller in area** by the factor (1 − E).
* Numbers reproducible for a given random seed, and a stated uncertainty (or at
  least a reported precision no finer than the run-to-run scatter) without one.
* A way to get the predicted decay out, to compare against a measured one.

## Observed (last run: 2026-07-28)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) through
`StructureToolsTool` and through the standalone `QuEstWindow`, with screenshots
read at every step.

**What works, and works well.** The physics runs, and it is fast: a full
simulation on T4L with the **shipped defaults** (500,000 photons, 16 µs
trajectory, 0.5 Å grid) takes **6.9 s**, and a 20,000-photon QA run 1.7–3 s. The
AV is built, the trajectory diffuses, quenching is integrated per frame and the
FRET rate is computed against the acceptor's cloud. The parameter form is the
best-labelled in the tree: **every** control names its unit (`Linker length (Å)`,
`Donor diffusion coefficient (Å²/ns)`, `kQ (1/ns)`), each carries a real tooltip
(the *Coarse-grained structure* tooltip is a six-line explanation that it is *"a
modelling choice, not a speed optimisation"*), and the **?** help modal is a
genuinely good page — what the method does, what to set, what comes out. The
project round-trips: **Save project…** then **Load project…** returns the same
state, and the file is byte-for-byte what the CLI consumes. Setting a **Random
seed** makes a run exactly reproducible (QY 0.88325 / τ 4.10007 / E 0.84591 twice
over). Screenshot `21_after_explicit_refresh.png`.

**The result plot is dominated by photons that were never emitted.** The decay
histograms count *every* simulated photon, including the ones that were quenched
or transferred: `_photon_rate_walk` returns `dt = 0.0` for a photon that lost the
race, and `get_histogram`/`get_histogram_fret` histogram all of `dts` without
filtering on the emitted flag. So all the non-emitted photons pile into bin 0.
Measured (seed 7, 20,000 photons, A/132 → A/55): `fret_counts[0] = 14479`, i.e.
**72.4 %** of the D–A curve's counts sit in the first 12 ps bin — exactly
1 − QY_DA = 0.721; `donor_counts[0] = 685` = 3.4 % = 1 − QY_D. Both curves
therefore total ~20,000 counts whatever the transfer efficiency, so the plot
carries **no amplitude information at all**, and on the log axis the D–A curve
opens with a 300× spike (visible in every screenshot). Excluding bin 0 the sums
are right (5516 vs QY_DA·N = 5580; 19308 vs 19372) and 1 − ⟨τ_DA⟩/⟨τ_D⟩ = 0.574 —
so the curve *is* correct once the spike is removed. RF-689.

**Clicking ▶ Simulate appears to do nothing.** The run happens — 3–7 s of frozen
UI, no progress indication, no cursor change — and then the form still shows the
previous state: the **State** line still read `Not simulated yet.` while the model
held `QY = 0.969 ⟨τ⟩ = 4.15 ns E = 0.712`, and all three plots were still empty
(`20_after_simulate_click.png`). A subsequent `refresh()` populates everything
(`21_…`). The seam is general: `ButtonRowSection._call` runs the action and
returns, and no AutoForm section calls `sync_fields()`/`refresh_plots()` after it
— so this hits *every* plugin whose `button_row` action mutates the model. The
failure path is worse: clicking **▶ Simulate** with the shipped default project
(whose `pdb` is the placeholder `structure.pdb`) raises a `FileNotFoundError` that
reaches the console as a traceback, opens **no dialog**, and leaves only a
read-only line that is too narrow for its own text. RF-690, RF-693.

**The trajectory plot's time axis is the core count times the simulation time.**
With the shipped `parallel_trajectories = -1`, `trajectory_time_ns` ran to
**31,999.97 ns** for a stated *Simulation time* of **4000 ns** on this 8-core
machine, and to **128,000 ns** for the default 16,000 ns. With
`parallel_trajectories = 1` it ends at 3999.97 ns, exactly as asked. The eight
independent trajectories are concatenated onto one continuous "Time (ns)" axis, so
the seven joins read as instantaneous 10 Å jumps in |r − ⟨r⟩| — and the
autocorrelation, the one plot whose whole content is *"how fast does the dye
forget"*, is computed across those joins. The same project also produces a
different-looking trajectory on a machine with a different core count. RF-691.

**Without a seed the reported precision is an order of magnitude finer than the
reproducibility.** The default *Random seed* is empty (and lives in the collapsed
**Advanced** group). Three identical runs on the same site gave QY = 0.857 /
0.744 / 0.859 and E = 0.771 / 0.816 / 0.822 — a spread of 0.11 in QY and 0.05 in
E — while the State line quotes three decimals and no uncertainty of any kind.
Nothing in the UI suggests a repeat, an error bar or a warning. *Simulation time*
matters too, and in the same silent way: 500 ns gave E = 0.906 against 0.685 at
4000 ns, well outside the run-to-run scatter — a short trajectory under-samples
the accessible volume. See *UX* below; not filed as a bug, since a sensible fix
(repeat runs, or a seeded default) is a design decision.

**A saved project contradicts itself about where the donor is.** The form's
*Attachment* fields are bound to the project's top-level `attachment`, which is
what the simulation reads. The template's `fret.dyes[0]` (the donor) carries its
*own* `attachment`, which no control touches. After setting residue 132 in the
form and saving, the file says `attachment: {chain A, residue 132, atom CB}` and
`fret.dyes[0].attachment: {chain A, residue 1, atom CB}`. The run is correct; the
saved file is not self-consistent, and anything reading the dye list gets residue
1. RF-692.

**Both decay curves are drawn in the same colour.** The legend reads `— Donor`
and `— FRET` with two identical yellow swatches, and the two traces are the same
yellow in the plot — the one plot in the tool with more than one series is the one
where you cannot tell the series apart. RF-694.

**The predicted decay cannot leave the tool.** The GUI runs with
`save_outputs=False` (deliberately, so a click does not litter `jobs/`), and the
only export in the window is *Save project…* — the **inputs**. There is no "export
decay", no CSV, and no push into a ChiSurf dataset, so the predicted decay cannot
be plotted next to the measured one, which is the entire reason to predict it.
The `quest` CLI writes `decay.csv`; the GUI does not. RF-695.

**Environment limitation (not a defect):** the middle **Structure** column stayed
empty in this run — offscreen Qt has no OpenGL context
(`QOpenGLWidget: Failed to create context`), so the 3-D view of the structure, the
AV cloud and the trajectory could not be judged. The frame counter did advance
from `0 / 0` to `1 / 1` when the structure was set, so the data reached the
viewer. The empty column is ~1/3 of the window and says nothing about why.

## UX / UI suggestions

* **Say which average `⟨τ⟩` is.** The state line's `⟨τ⟩` is the mean arrival time
  of the *emitted* photons — the fluorescence-weighted average (4.15 ns here) —
  while `τ₀ × QY` is the species-weighted one (3.81 ns). A user checking the two
  against each other finds a 9 % discrepancy and no hint that both are right.
  Label it `⟨τ⟩_f`, and consider showing `⟨τ⟩_x` beside it.
* **Say which quantum yield `QY` is.** `QY = 0.907` is the *donor-only* yield
  (quenching, no transfer); with FRET on there is a second one, `QY_DA = 0.279`,
  which is in the result object but not on screen even though E is derived from
  it. Show `QY_D`, `QY_DA`, `E`.
* **Report the run-to-run scatter, or seed by default.** Either default *Random
  seed* to a value (reproducible, with a "reroll" button), or run N repeats and
  print `E = 0.80 ± 0.03`. Three decimals on a number that moves by 0.05 between
  clicks is the single most misleading thing in the window.
* **Warn when the trajectory is short.** *Simulation time* changes E by more than
  the noise; a rule of thumb against the ACF (e.g. "the trajectory is only 12×
  the correlation time of the dye position") would turn a silent bias into a
  visible one — the ACF needed for it is already computed and plotted.
* **Give the run a progress indication.** 7 s at the shipped defaults with a
  frozen window and an unchanged State line is indistinguishable from a hang; a
  larger structure or a finer grid is much longer. The AutoForm `progress` section
  and `ChiSurfProgress` already exist for exactly this
  ([gui-autoform](/subsystems/gui-autoform.md)); the model itself already notes
  the synchronous run as `LAY-07`.
* **Drop the duplicate buttons.** Embedded in Structure Tools the panel shows a
  toolbar *Load PDB… / Save project… / Load project… / Close* **and** a footer
  *▶ Simulate / 📂 Load project… / 💾 Save project…* — the same two actions twice,
  in different styles, 700 px apart. Keep the footer row (it has the primary
  action) and reduce the toolbar to *Load PDB…*.
* **The quencher table needs room.** At the Structure Tools default size
  (1200×750) the 20-row table is clipped to its header plus one part-row inside a
  scroll area that is itself scrolling — two nested scrollbars, ~1 usable row. It
  becomes readable around 1150 px of window height. Give it a fixed sensible
  height with its own scrollbar, or move the chemistry to its own tab.
* **Say why the 3-D column is empty.** When no structure is loaded (or no GL
  context exists) the column shows a bold "Structure" and a dead frame slider.
  A one-line placeholder — *"load a structure to see the accessible volume"* —
  costs nothing.
* **Offer the FRET-quenched donor decay as a fittable curve.** Once RF-689 and
  RF-695 are addressed, the natural next click is *"add these two decays to
  ChiSurf as a donor-only / donor–acceptor pair"*, which lands the user directly
  in the [global analysis](/usecases/global-analysis-linked-fits.md) workflow with
  a simulated reference.

## Bugs filed

- **RF-689** — decay histograms include the non-emitted photons at t = 0; 72 % of
  the D–A curve is a spike in the first bin and both curves carry the same area.
- **RF-690** — an AutoForm `button_row` action never refreshes the form, so
  **▶ Simulate** leaves the previous state and empty plots on screen.
- **RF-691** — the trajectory time axis (and the ACF) run over all parallel
  trajectories concatenated, so the axis is `parallel_trajectories × t_max` and
  depends on the machine's core count.
- **RF-692** — a saved project's donor dye keeps the template's attachment site,
  contradicting the top-level `attachment` the form edits and the run uses.
- **RF-693** — a failed run reports only through a read-only line that is too
  narrow for its own text; the traceback goes to the console and no dialog opens.
- **RF-694** — the Donor and D–A decays are drawn in the same colour, with
  identical legend swatches.
- **RF-695** — the simulated decay cannot be exported or pushed into ChiSurf; the
  window can only save its inputs.
