---
type: Reference
title: Use case — global analysis (two fits, one shared donor spectrum)
description: Fit a donor-only and a donor–acceptor decay side by side, link the donor lifetime spectrum across the two fits in the Global View graph, and run one global fit over both datasets.
tags: [usecase, global-fit, tcspc, fret, linking, globalview, gui]
timestamp: '2026-07-26T00:00:00Z'
---

# Use case: global analysis — two fits, one shared donor spectrum

**Goal:** the feature ChiSurf is named for. A donor-only (D0) and a
donor–acceptor (DA) decay of the same construct are measured. Fitted separately,
the DA fit has to re-determine the donor lifetimes from a quenched decay, and the
distance it reports is only as good as that. In a global analysis the donor
spectrum is **determined once by the D0 dataset and imposed on the DA fit**, so
the DA data pay only for the distance — the classical FRET global fit.

**Data:** `test/data/tcspc/EasyTau300/` — `215-268 D0.dat` + `215-268 D0 irf.dat`
and `215-268 DA.dat` + `215-268 DA irf.dat`. Two-column tab-separated text,
**6376 channels**, column 0 = time in **ns** (0 … 51.0, 0.008 ns/ch), column 1 =
counts. Each measurement carries its own IRF.

## Steps

1. Start ChiSurf. In **Read data**, set **Experiment** = `TCSPC`,
   **File type** = `TXT/CSV`.
2. In *File parameters* set **Skiprows = 0** and — **required, see RF-278** —
   set the **y-values** column spin box to **1**. Leave *Header* off and the
   format on *Auto*.
3. In *Timing* set **dt [ns/ch] = 1.0**. This file already carries a time column
   and the reader computes `x = column0 · dt`; leaving the default 0.016 scales
   the time axis by another factor of 0.016.
4. Click **+ Data** four times (or drop the files) and load the D0 decay, the D0
   IRF, the DA decay and the DA IRF. All four appear in the **Data** tab.
5. Select `215-268 D0.dat`, pick model **`Lifetime`**, press **Analysis**
   (the *Add fit* button). In the analysis dock's *Convolve* section press the
   **…** next to **IRF** and choose `215-268 D0 irf.dat`.
6. Select `215-268 DA.dat`, pick model **`FRET: FD (Discrete)`**, press
   **Analysis**, and assign `215-268 DA irf.dat` as its IRF.
7. In each fit window press the green **add** button in the *Lifetimes* section
   once, so both models carry a **bi-exponential donor**. Press **Fit** in both
   windows and check that each converges on its own.
8. Open **Tools ▸ Global View**. The graph shows one hub per fit with its free
   parameters as leaves. Drag the DA fit's **`tL1`** node onto the D0 fit's
   `tL1` node — the DA parameter becomes the slave, the D0 parameter the master.
   Repeat for **`tL2`**, **`xL1`**, **`xL2`**: the whole donor spectrum is now
   shared. (Do **not** use the parameter widget's own *Link…* menu — RF-279 /
   RF-280.)
9. Select the auto-created **`Global Dataset`** row, pick the model
   **`Global fit`** and press **Analysis**. A *Global fit* window opens with an
   empty *Used fits* table.
10. In that window press **update** (the fit chooser is empty until you do,
    RF-283), leave **all** ticked and press **add** — both fits appear in the
    *Used fits* table.
11. Press **Fit** in the global fit window. Read χ²ᵣ from its *Info* tab and the
    per-dataset χ²ᵣ from the two member windows; the linked lifetimes must now
    be identical in both.

## Expected

- Step 4 gives four 6376-point curves; the D0 decay peaks at channel 627 with
  10⁵ counts. Steps 5–6 auto-detect the fit ranges **605 … 5429** (D0) and
  **605 … 4267** (DA).
- Step 7: with one donor lifetime the D0 fit is clearly inadequate
  (χ²ᵣ ≈ 12.8, τ ≈ 3.94 ns); with two it reaches **χ²ᵣ ≈ 1.37**
  (τ₁ 1.16 ns, τ₂ 4.12 ns, x₂ 0.84). The DA FRET fit reaches **χ²ᵣ ≈ 1.14**
  with `R(G,1) ≈ 36.9 Å`, `E ≈ 0.21`, `xDOnly ≈ 0.74`.
- Step 8 removes `tL1`, `tL2`, `xL1`, `xL2` from the DA fit's free-parameter
  list and draws four edges between the two hubs in the graph.
- Step 11: **13** free parameters over **8486** points, ≈ 11 s,
  **χ²ᵣ = 3.55** (D0 member 2.71, DA member 4.64), shared donor lifetimes
  **0.569 / 4.073 ns**, and the DA fit now reports `R(G,1) = 52.4 Å`,
  `E = 0.370`, `xDOnly = 0.229`. Both member χ²ᵣ rise relative to their free
  local fits — that is the point: the shared spectrum is a real constraint and
  the residual mismatch is the evidence a single distance is too simple.

## Observed (last run: 2026-07-26)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env, private RPC port)
through the real main window: the *Read data* panel's own spin boxes, the
dataset selector, the model combo and the **Analysis** button, the `ConvolveWidget`
IRF picker, the green **add** lifetime button, `FittingControllerWidget.onRunFit`,
the Global View graph's link gesture (`on_link_requested`, what a drag between two
nodes emits) and the `GlobalFitModelWidget`'s *update* / *add* buttons.
Screenshots inspected at every step.

**The analysis itself works and the numbers are right.** All the values in
*Expected* above are from this run. The linked fit converged in 11.2 s, both
members ended with genuinely identical donor lifetimes (0.5690 / 4.0733 ns to
four decimals in both models), and the Global View graph rendered the four link
edges between the two fit hubs — a genuinely good picture of what a global fit
is. The per-member fit windows show the model over the data with flat residuals,
the shaded fit range and the correct time axis in ns.

**Getting the data in is the fragile part.** Setting *Skiprows* — the one control
every text file needs — silently rewrites the y-column to 0, so the loaded
"decay" is the time axis; the fit then reports **χ²ᵣ = 0.0000** with parameters
like `R(G,1) = −22.1 Å` and `τ = 55 ns` and no warning anywhere (RF-278). The
first run of this workflow died there, and nothing on screen said why. The panel
also opens showing *Skiprows 7* while the reader is on 8 — panel and reader are
never synchronised in that direction.

**Cross-fit linking is only possible from Global View.** The obvious route — the
**Link…** button on the parameter itself — is broken twice over. Its menu lists
every parameter of every fit *except* those sharing the source's name, so the
canonical global-analysis link (`tL1` ↔ `tL1`) is simply not offered (RF-280).
And when a differently-named target is picked, the link lands on the **wrong
fit**: asking for *DA `sc` → D0 `bg`* linked **D0's own `sc` to D0's `bg`**,
took `sc` out of the D0 fit, left the DA parameter untouched, and reported
nothing (RF-279). The Global View path passes source and target fits correctly
and is the one that works.

**The global fit's result table hides half the result.** `Fit.__str__` keys the
parameter table by name, so with two members the shared names (`bg`, `sc`, `ts`,
`dt`, `rep`, …) collapse to one row each and only the last member's values
survive: the *Info* tab of the converged global fit showed `bg = −16.973` and
`sc = 0.05901` (both DA's) while the D0 member's `bg = 1.0486` appears nowhere
(RF-281). The linked rows do carry a `→tL1` marker in the *Link* column, which is
good; the likelihood-interval block is all `nan / no estimate`.

**Smaller things seen while driving:** the global fit panel's fit chooser is
empty until *update* is pressed (RF-283); its *add* button is connected twice, so
one click runs `onAddToLocalFitList` twice and prints four raw `print()` lines to
the console; the `GlobalFitModel` "global variable" feature has no widgets at all
and `onAddGlobalVariable()` raises `AttributeError: … has no attribute 'lineEdit'`
(RF-282); the Global View *Parameters* tab reports "77 rows × 11 columns" but
renders only seven of them in a fixed-height table with ~500 px of empty panel
below it (RF-284); the CSV panel's four column **combo boxes are never populated
by any code** and the *x-values* checkbox only enables one of them (RF-285).

## Bugs filed

- **RF-278** — S1: touching any *File parameters* control pushes the panel's own
  defaults onto the reader, setting `col_y = 0`; the decay loads as its own time
  axis and the fit reports χ²ᵣ = 0.0000.
- **RF-279** — S1: the parameter *Link…* menu links inside the **target** fit, so
  the wrong parameter in the wrong fit is linked.
- **RF-280** — S2: the same menu filters out identically named parameters in
  other fits, i.e. exactly the link a global analysis needs.
- **RF-281** — S2: the global fit's *Info* report collapses same-named
  parameters across members and shows only one member's values.
- **RF-282** — S2: the global-variable feature of `GlobalFitModelWidget` has no
  UI and raises `AttributeError` when invoked.
- **RF-283** — S3: the global fit's fit chooser is empty until *update* is
  pressed, and *add* is double-connected and prints debug output.
- **RF-284** — S3: Global View *Parameters* tab renders 7 of 77 rows in a
  fixed-height table with a large empty area; its title is duplicated.
- **RF-285** — S3: the CSV reader panel's four column combo boxes are dead.

## UX / UI suggestions

- **Say which fit a parameter belongs to.** The global fit's *Info* tab, the
  Global View graph labels and the *Used fits* table all identify a fit by its
  full absolute path, which is elided everywhere it appears (three wrapped lines
  in the table, running off the right edge of the graph). Use the short dataset
  name + a fit index (`1:`/`2:`, which `GlobalFitModel.parameter_names` already
  produces) and keep the path in a tooltip.
- **`range=0..0` on the global fit's *Info* header is meaningless** — a global
  fit has no single range. Show the member ranges, or the total point count
  (8486 here), which is what the χ²ᵣ is actually normalised by.
- **Show link state on the parameter row.** A linked parameter is indistinguishable
  from a free one in the compact parameter row; the `→ target` label and *Unlink*
  button only exist inside the pop-up. A small chain glyph on the row (and hiding
  the value spin box, since it is no longer independently editable) would make a
  linked model readable at a glance.
- **Give the fit sub-windows room for their tab strip.** At the default sub-window
  width the first tab of every fit window renders as `it` — the *Fit* tab clipped
  to two letters — and the title-bar button reads `C…e`. The dock tab bar has the
  same problem (`Read …`, `Anal…`, `Con…`, `Log…`).
- **Global View group titles are clipped** ("Visualization", "Link" are cut in
  half), the *all* checkbox draws two checkbox glyphs (`☐ ☑ all`), and the
  parameter node labels overlap each other and the fit label. The graph is the
  best explanation of a global model in the app; it deserves collision-free
  labels and a legend for what an edge means.
- **A one-click "link by name" would collapse this whole workflow.** Global
  analysis nearly always links parameters that share a name across fits. An
  action like *link all matching parameters to fit N* (or a checkbox column in
  Global View's parameter table) would replace four drag gestures and would not
  need the user to know that the drag direction picks the master.
- **The status bar shows developer text.** After the global fit it read
  `Parameter 'l2' has no controller to finalize.` — that message belongs in the
  log, not on the user's status line.
