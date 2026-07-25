---
type: Reference
title: Use case — FRET calculators (distance from efficiency, kappa2 error, FRET line)
description: Open the Calculators hub, convert a measured FRET efficiency into a donor-acceptor distance, bound the kappa2 orientation error, and generate a static FRET line to overlay on an smFRET histogram.
tags: [usecase, calculator, fret, kappa2, fret-line, phasor, gui]
timestamp: '2026-07-25T00:00:00Z'
---

# Use case: FRET calculators

**Goal:** the everyday "back of the envelope" FRET task, before or after any
fitting. The user has a measured transfer efficiency `E` (or a donor lifetime
`τ_DA`) and wants (a) the corresponding donor–acceptor distance `R_DA`, (b) how
badly the unknown orientation factor κ² could bias that distance, and (c) a
**FRET line** to draw over an smFRET `E`-vs-`τ` histogram so static and dynamic
populations can be told apart.

**Data:** *none* — this is the one core workflow that needs no data file. Every
calculator in the hub is analytic and works from typed numbers, which makes it
the natural smoke test for a fresh install. Defaults are a Förster radius
`R0 = 52 Å` and a donor lifetime `τ_D0 = 4 ns` (an Alexa488/Alexa647-like pair).

## Steps

1. Start ChiSurf and open **Tools → Calculators**. The hub is a two-panel
   launcher: the calculator list on the left, the selected calculator embedded on
   the right. It is the only calculator entry that is not `menu_hidden`, so it is
   the intended way in — `FRET-Calculator`, `Kappa2 Distribution`,
   `FRET Line Generator` and `Phasor-Calculator` are all reachable only through it.
2. Six calculators are offered: **FRET / homoFRET**, **FRET line**,
   **FCS diffusion**, **Phasor plot**, **κ² distribution**, **F-test / χ²-max**.
   The first is selected on open.
3. In **FRET / homoFRET → HeteroFRET**, set *Förster R0* and *Lifetime D0* for
   your dye pair, then type your measured **Efficiency** and press Enter (all
   fields commit on `editingFinished`, so the value must be committed).
   *Distance DA*, *Lifetime DA* and *kFRET* update together — the panel is
   bidirectional, so typing into any one of the five re-derives the other four.
4. Set **Sigma** to the width of the distance distribution you expect
   (default 6 Å) and tick **chi distribution** to compare a Gaussian `p(R)`
   against a χ (3D-Gaussian-chain) distribution. The two *Distributions* plots
   show `p(R)` and the induced `p(k_FRET)`.
5. Switch to the **HomoFRET** tab for the homo-transfer case: it converts an
   anisotropy relaxation time `t_RM` and rotational correlation time `rho` into a
   homo-FRET rate `k_homo` and an effective `R_DA`, and back.
6. Select **κ² distribution** on the left. Choose the model — **WIC (Cone)**,
   **DWT (Diffusion)** or **Isotropic** — and enter the measured residual
   anisotropies (`r_0`, `r_D∞`, `r_A∞`, `r_AD∞`) and your `true κ²` / `FRET E`.
7. Click **Compute**. Read *Mean κ²*, *SD κ²* and — the number that matters —
   *Mean R_app/R_DA* and *SD R_app/R_DA*, the systematic and random distance
   error incurred by assuming κ² = 2/3. Click **Save** to export `p(κ²)`.
8. Select **FRET line**. On the **Components** tab pick the model
   (`FRET: FD (Gaussian)`, `FD (Worm-like chain)`, `FD (Discrete)` or `Lifetime`)
   and set its parameters in the *Editor* panel on the right.
9. On the **Sweep** tab choose the parameter to sweep. **Set *Min* to a physical
   value — it defaults to 0, which is invalid for lifetime parameters (RF-071) —
   and pick a parameter that actually moves the line, e.g. `R(G,1)`, not the
   default `xL1` (RF-072).** For a static line: `R(G,1)`, Min 20, Max 90, 100
   points, `τ_D0 = 4 ns`.
10. Click **+ Add FRET line**. The line appears in the *FRET lines* list and is
    overlaid on the `E_FRET` vs `τ_F` plot and the `τ_X(τ_F)` plot. Repeat with a
    different parameter or model to overlay several lines.
11. Click **Save CSV** to export, or **Push to ndxplorer** to overlay the line on
    a live smFRET 2D histogram. Both buttons are disabled until a line exists.
12. Optionally select **Phasor plot** and open its second tab to see the universal
    semicircle with the reference-lifetime ticks, and **F-test / χ²-max** to turn
    a confidence level into a χ² threshold for two nested fits.

## Expected

- Step 1 opens instantly; each calculator is built lazily on first selection.
- Step 3: with `R0 = 52 Å`, `τ_D0 = 4 ns` and `E = 0.5`, `R_DA` = `R0` = 52.00 Å,
  `τ_DA` = 2.0000 ns and `k_FRET` = 0.2501 ns⁻¹. Typing a distance back should
  return the efficiency it came from.
- Step 7: for the shipped anisotropies the three models give distinct, plausible
  distributions — WIC `⟨κ²⟩ = 0.744 ± 0.189`, DWT `0.684 ± 0.218`, Isotropic
  `0.710 ± 0.719` — with `⟨R_app/R_DA⟩` within a few percent of 1 and
  `δ = 57.66°`. The isotropic model's much larger SD is the point of the exercise.
- Step 10: a static FRET line falls monotonically from `E ≈ 1` at `τ_F → 0` to
  `E = 0` at `τ_F = τ_D0 = 4 ns`, with 100 distinct points.

## Observed (last run: 2026-07-25)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) by constructing
`CalculatorHub` and walking its list row by row, then driving `FretCalculatorTool`,
`Kappa2Dist` and `FRETLineTool` directly — typing into the spin boxes and emitting
`editingFinished`, clicking **Compute** / **+ Add FRET line**, switching tabs and
radio buttons. Screenshots were taken at every step and inspected, list-item
pixels were sampled to confirm a text-rendering bug, and modal dialogs were
captured with a polling `QTimer` (they block an offscreen driver forever
otherwise).

**All six calculators build and the numbers that come out are right.** No
calculator failed to load, the FCS-diffusion panel is a model of good labelling
(every field carries a unit: `τ (µs)`, `D (µm²/s)`, `Veff (fL)`, `Conc (nM)`) and
its occupancy is internally consistent (`N = 0.628` for 1 nM in 1.0436 fL is
exactly `c·N_A·V`). The phasor plot is correct — at 80 MHz the 2 ns tick sits at
the apex `(0.5, 0.5)` of the universal semicircle, as it must. The κ² models give
three visibly different distributions and `Compute` is fast. The F-test panel
computes `χ²_max = 1.03936` for `χ²_min = 1`, ν = 100, 1 parameter at 95 %.

**The Calculators hub hides the name of whichever calculator you have selected.**
This is the first thing a user sees and it is wrong on every row. The list
stylesheet (`hub/gui/tool.py:71-86`) restyles `QListWidget::item` but sets no
`:selected` background, so the item keeps the white `Base` while Qt still paints
its text in `HighlightedText` — white on white. Sampling the selected row's text
area returns *no* black pixels while every unselected row returns hundreds; only
the emoji survives, so the selected entry reads as a bare "🎯" (RF-075).
Screenshots `01_calc_*.png`.

**The FRET calculator silently keeps stale numbers when a conversion fails.**
The three inverse paths (`_on_E_changed`, `_on_kFRET_changed`, `_on_tau_changed`)
guard on `if r.get("ok")` and do nothing at all on failure — no dialog, no status,
no reset. The backend returns `ok: False` for exactly the inputs a user types
when they see no transfer: `E = 0` → `division by zero`, `k_FRET = 0` →
`0.0 cannot be raised to a negative power`, `τ_DA = τ_D0` → `division by zero`.
The panel is then left displaying a physically contradictory set: **Efficiency
0.000000 next to Distance DA 0.10 Å, Lifetime DA 0.0000 ns and kFRET
9999.000000** — E = 0 shown together with maximum FRET (RF-073). The spin-box
ranges (`E ∈ [0, 1]`, `k_FRET ∈ [0, 9999]`) actively invite the input the backend
rejects. Screenshot `10_fret_da.png`.

**And the displayed Sigma is ignored by every inverse path, so the panel does not
round-trip.** Going *forward* (`_compute`, from `R`) passes `sigma` and
`distribution` and returns the distribution-averaged `⟨E⟩`; going *backward* from
`E`, `τ_DA` or `k_FRET` calls a single-distance Förster inverse and the result
echoes `sigma: 0.0`. Typing `R = 60 Å` at the default σ = 6 Å gives
`E = 0.309307`; typing that same efficiency straight back gives **R = 59.450 Å** —
the distance moves 0.55 Å with nothing changed and no hint why. At σ = 0.1 Å the
drift collapses to 0.010 Å (pure rounding), confirming σ as the cause (RF-074).

**The FRET Line Generator cannot draw a usable line from its shipped defaults.**
Two independent defaults are wrong. *Min* (`_min_spin`, `tool.py:282`) is never
given a value, so it starts at **0**, and the sweep evaluates the model at exactly
0: for `t0` and `tL1` that is a zero lifetime, which raises and aborts the whole
line — surfaced as a message box with an **empty title** whose entire body is the
raw exception text `division by zero`, and no line is added (RF-071). Both work
perfectly with Min = 1 (100 distinct points, `E` 0.15–0.82). Separately, the
sweep target defaults to the *first* entry, `xL1` — the amplitude of the only
lifetime component — which is scale-invariant, so it cannot change anything: all
100 points come back identical (`E = 0.5799`, `τ_F = 1.92613 ns`), the plot
auto-ranges onto a zero-length line and looks **blank** while the list and legend
confidently show "Line 1" (RF-072). `x(G,1)` is degenerate the same way. So the
one action the tool exists for, clicked with everything as shipped, produces an
empty-looking plot and no error. Screenshot `30_fretline_after_add.png`; with
`R(G,1)`, Min 20, Max 90 it produces a textbook static line falling from E ≈ 1 to
0 at τ_F = 4 ns (`60_fretline_working.png`).

**Adding a FRET line silently rewrites the user's model.** The sweep leaves the
swept parameter parked at the last value it visited and never restores it: with a
fresh tool `R(G,1)` reads 50.0 Å, and after one **+ Add FRET line** over 20→90 Å
the *Editor* panel reads **90.0 Å** (RF-070). Every later line is therefore
computed from the mutated model, which is how a sequential walk of all nine sweep
targets turned into eight consecutive "division by zero" dialogs while each target
tested from a fresh widget was fine — the failures cascade from the first sweep.

**Timing was not a problem.** Constructing `FRETLineTool` takes 6.4 s (the heaviest
of the six), but **+ Add FRET line** is 0.03–0.04 s and κ² **Compute** is
sub-second, so no progress indication is needed.

## UX / UI suggestions

- **Give the hub list a selected style.** Adding `QListWidget::item:selected`
  (background + `color: palette(highlighted-text)`) to the stylesheet fixes
  RF-075 and is where the missing selection affordance belongs anyway — right now
  the only cue is a faint focus rectangle.
- **Make the units `Å`, not `A`.** The FRET calculator's spin-box suffixes read
  `52.00 A` / `50.00 A` / `6.00 A` while the plot axis directly beneath them is
  correctly labelled `R (Å)`. The same panel gives `kFRET` **no** unit at all
  though its own plot says `k_FRET (1/ns)`.
- **Round the outputs.** `Efficiency 0.560037` and `kFRET 0.318230` are shown to
  six decimals, and the FCS panel shows `1/N 1.591209087` to nine — far past any
  experiment's precision, and it makes the fields hard to scan. Three or four
  decimals matches the inputs.
- **Say which fields are outputs.** In the HeteroFRET tab all five of *Distance
  DA*, *Lifetime DA*, *Efficiency*, *kFRET* and *Sigma* look identical, yet four
  of them are simultaneously inputs and outputs and re-derive each other. The
  homoFRET tab already marks `k_homo` read-only; the hetero tab gives no cue that
  typing in one box will rewrite the other four.
- **State the σ convention next to Sigma.** Given RF-074 the user cannot tell
  whether `E` is `E(⟨R⟩)` or `⟨E(R)⟩` — and it is currently *both*, depending on
  which box was typed into last. Whichever is chosen, the label should say so.
- **Don't put the plot behind a tab in a tool called "Phasor plot".** The phasor
  calculator opens on **Controls** and the semicircle — its entire reason to
  exist — is on a second tab the user must find. A side-by-side split (controls
  left, plot right) matches every other calculator in the hub.
- **The phasor `s` axis is scaled as if it had units.** It reads `s (x0.001)`
  with ticks 0…600, so the apex of the universal semicircle displays as "500".
  `s` is dimensionless and bounded by 0.5 by construction; the `g` axis next to it
  is correctly 0…1.0 (RF-077). The FRET calculator's `p(R) (x0.001)` /
  `p(k) (x0.` axes have the same auto-multiplier, and the second one is clipped.
- **The κ² panel opens with an empty collapsible bar.** The first section of
  `k2dist.view.json` has `title: ""`, so AutoForm renders a grey header with a
  `▼` and no text above the *Model* radio row (RF-076).
- **Name the sweep parameters in physical terms.** The FRET-line sweep combo
  offers `xL1`, `tL1`, `t0`, `R0`, `k2`, `R(G,1)`, `s(G,1)`, `k(G,1)`, `x(G,1)` —
  a user cannot tell that `R(G,1)` is the mean donor–acceptor distance of Gaussian
  component 1 and `s(G,1)` its width, nor which of them will move the line. The
  combo has one shared tooltip for the whole list.
- **Give the sweep Min/Max sensible bounds and units.** Both accept ±1e9 with no
  unit, for a parameter whose meaning changes with the combo above them. Seeding
  Min/Max from the selected parameter's own range would fix RF-071 and RF-072 at
  once.
- **Two buttons labelled "+ Add" and two labelled "− Remove".** The Components
  tab and the FRET-lines list each have their own pair; only one of each is
  qualified ("+ Add FRET line"). Scripted and manual users alike hit the wrong one.
- **The embedded model *Editor* is unusable at hub width.** Inside the hub at
  1280 px the FRET-line tool's editor dock is squeezed to ~180 px: "IRF" reads
  `Click on button t`, the radio row is cut to `curve  ex`, and a horizontal
  scrollbar appears under a column of unlabelled checkboxes. It needs a minimum
  width, or the hub's splitter needs to give it more room.
- **Overlapping lines are indistinguishable.** Two FRET lines computed over the
  same parameter coincide exactly and the earlier one vanishes under the later
  one; only the legend hints that both exist. Dashing or offsetting duplicates
  would help.
- **A "no transfer" preset would pay for itself.** `E = 0`, `k_FRET = 0` and
  `τ_DA = τ_D0` are the three ways a user says "I measured no FRET", and all three
  are exactly the inputs that fail (RF-073). Even after the crash is fixed the
  honest answer is `R = ∞`, which the `R` box (max 9999 Å) cannot show.

## Bugs filed

- RF-070 — FRET Line Generator: a sweep leaves the swept parameter at its last
  value and never restores the model; later lines are computed from the mutated
  state.
- RF-071 — FRET Line Generator: the sweep *Min* box defaults to 0; sweeping `t0`
  or `tL1` raises `ZeroDivisionError`, shown as an untitled message box reading
  only "division by zero", and no line is added.
- RF-072 — FRET Line Generator: the default sweep target `xL1` is a
  scale-invariant amplitude, so the shipped defaults always produce a constant,
  invisible "FRET line" with no warning.
- RF-073 — FRET calculator: the `E` / `k_FRET` / `τ_DA` inverse paths ignore
  backend failures and leave contradictory stale values on screen (E = 0 beside
  k_FRET = 9999).
- RF-074 — FRET calculator: `Sigma` is ignored by every inverse path, so
  R → E → R does not round-trip (60.000 → 59.450 Å at σ = 6 Å).
- RF-075 — Calculators hub: the selected list item's label is painted white on
  white and is invisible.
- RF-076 — κ² calculator: the first section of `k2dist.view.json` has an empty
  title and renders as a blank collapsible header bar.
- RF-077 — Phasor calculator: the `s` axis gets an SI auto-multiplier
  (`s (x0.001)`, ticks 0…600) although `s` is dimensionless and ≤ 0.5.
