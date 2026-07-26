---
type: Reference
title: Use case — time-resolved anisotropy (Wizards hub → linked VV/VH global fit)
description: Open the Wizards hub, walk the Anisotropy wizard — polarised IRF/decay files, IRF background region, g-factor and l1/l2, lifetime and rotation spectra — and let it build the VV, VH and global fits with every shared parameter linked.
tags: [usecase, wizard, anisotropy, tcspc, vv-vh, global-fit, gui]
timestamp: '2026-07-26T00:00:00Z'
---

# Use case: anisotropy wizard → linked VV/VH global fit

**Goal:** measure how fast a fluorophore tumbles. The user has a
polarisation-resolved TCSPC measurement (VV and VH decays plus the matching
polarised IRF) and wants the rotational correlation time(s) ρ and their
amplitudes β, fitted *globally* over both polarisation channels so that the
lifetimes, the rotation spectrum, the photon count and the instrument
corrections are one shared set of numbers rather than two independent fits.
Building that by hand means creating two fits, setting two polarisation types,
assigning two IRFs and then wiring ~14 parameter links in the right order — the
wizard exists so the user does not have to.

**Data:** `test/data/tcspc/Jordi/02_18-577+7.5uM(577)UP_8ps.dat` (sample decay)
and `test/data/tcspc/Jordi/H2O_8-0 ps_2048 ch.dat` (water-scatter IRF). Both are
**VV/VH-stacked** text files: 4096 rows = 2048 VV channels followed by 2048 VH
channels, `dt = 0.032` ns/ch (65.5 ns window), 25 MHz repetition. In VV/VH mode
one file holds both polarisations, so the *same* path goes into both the VV and
the VH field.

**Tool:** the **Wizards** hub (`chisurf/plugins/core/wizards`, display name
*Main:Tools:Wizards*, `WizardHub`) — a two-panel launcher listing the guided
wizards (**Anisotropy**, **Batch analysis**) and embedding the selected one. The
Anisotropy wizard itself is
`chisurf/plugins/fluorescence_decay/tr_anisotropy` (`AnisotropyWizard`,
`menu_hidden`), an AutoForm wizard driven by `anisotropy.view.json` with a
Qt-free `core/` (IRF correction, spectrum I/O, the VV↔VH link plan) and a
`csc anisotropy` CLI.

## Steps

1. Start ChiSurf. In the **Read data** dock set **Experiment** = `TCSPC` and
   **File type** = `TXT/CSV` (the TCSPC readers are TXT/CSV, TTTR-file,
   Becker-SDT, Simulator).
2. In *File parameters*, configure the reader for this file family: header off,
   `Skiprows = 0`, CSV routine, `dt = 0.032` ns/ch, `rep. = 25` MHz, and — the
   step that matters — in *Anisotropy (VV/VH)* set **pol. = VV,VH**. Without it
   the stacked file is read as one 4096-channel curve.
3. Open **Main → Tools → Wizards** on the ribbon. The hub opens with
   *Anisotropy* already selected; the wizard's own six-step rail (**Welcome**,
   **Data**, **Normalize IRF**, **Corrections**, **Components**, **Finish**) sits
   to the right of the hub's wizard list.
4. **Welcome** — read the five-line summary, click **Next ›**.
5. **Data** — fill the four file fields. With a VV/VH-stacked file, put the same
   IRF path in *IRF VV* and *IRF VH*, and the same decay path in *Data VV* and
   *Data VH*; the loader reads each file twice with the polarisation set
   accordingly. (The checklist below the fields is dead — see RF-126.)
6. **Normalize IRF** — click **🔄 Load / reload data**. The four curves are read
   through the current TCSPC reader and plotted on a log axis: VV/VH raw and
   VV/VH background-corrected, with a draggable blue region for the background
   window. The region opens at 30 %–80 % of the channel range (**614 … 1638**
   here). Drag it, or type into **BG from / to**, onto a signal-free stretch —
   `1500 … 2000` for this IRF. Each change re-subtracts the per-channel mean
   background and rescales both channels to a common integral.
7. **Corrections** — set the detection **g-factor** and the channel-mixing
   **l1** / **l2**. These persist to
   `<user_settings>/anisotropy_corrections.json` and are *not* the same fields as
   the *Anisotropy (VV/VH)* box in the Read-data dock.
8. **Components** — the two tables hold the starting **lifetime spectrum**
   (amplitude, τ/ns) and **rotation spectrum** (amplitude, ρ/ns); they open from
   the packaged `wizard.spk.json` at `[[0.3, 1.8], [0.7, 4.1]]` and
   `[[0.28, 0.15], [0.1, 10.0]]`. Type into a cell to edit, or set the `a` / `l`
   (`ρ`) spin boxes below and click **➕** to append a component. **💾 Save
   spectrum** / **📂 Load spectrum** round-trip both tables as `*.spk.json`.
9. **Finish** — click **✅ Create fits**. Two `Lifetime` fits (VV and VH) and one
   `Global fit` are added to ChiSurf, the corrected IRFs and the two sample
   decays are appended as datasets, and the VV↔VH link plan is replayed.
10. In the main window, run the **Global fit** and read ρ, β, the lifetimes and
    χ²ᵣ from its *Info* tab; the two child fit windows show the per-channel
    residuals.

## Expected

- Step 6 loads four 2048-channel curves in ~1.7 s and plots VV/VH raw and
  corrected on a log axis; the IRF peaks near channel 350 and the region sits on
  the flat tail.
- Step 9 takes ~5 s and creates exactly three fits and four new datasets, and
  applies **14 links** on the VH fit: `rho(1)`, `rho(2)`, `b(1)`, `b(2)`, `g`,
  `l1`, `l2`, `xL1..xL3`, `tL1..tL3`, `n0`. `g`/`l1`/`l2` carry the values typed
  in step 7 and are fixed; `n0` is shared but released.
- Step 10 converges in ~2.5 s. The wizard's *starting* state is far off (χ²ᵣ
  ≈ 570 / 641); after the global run χ²ᵣ = **4.58** (VV 4.67, VH 4.50) with
  ρ₁ ≈ 4.1 ns, ρ₂ ≈ 38.9 ns, β₁ = 0.078, β₂ = 0.302 (β₁+β₂ = r₀ = 0.38).

## Observed (last run: 2026-07-26)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, `arm64` env) through the real
widgets — the Read-data combo boxes, `WizardHub`, the AutoForm `WizardWidget`
Next/Back buttons, the bound file-path line edits, the embedded
`IrfNormalizationWidget` and `ComponentsWidget`, and the **Create fits** button —
with screenshots at every step, inspected.

**The science works, and the wizard earns its keep.** All four polarised curves
loaded (2048 channels each), the IRF plot with the draggable background region
renders correctly, all 14 links were applied on the VH fit, `g = 1.15`,
`l1 = 0.12`, `l2 = 0.44` arrived on both channels fixed, `n0` was shared and
released, and the global fit converged to χ²ᵣ = 4.582 in 2.5 s with
ρ₁ = 4.10 ns, ρ₂ = 38.87 ns, β₁ = 0.0784, β₂ = 0.3016, τ = 1.54 / 11.61 /
0.0015 ns and steady-state anisotropies `r_ss_l = 0.257`, `r_ss_i = 0.182`. The
VV fit window (residuals, autocorrelation, shaded range, IRF overlay) looks
professional.

**Three things a user would notice as broken.**

*The Data step gives no feedback at all.* The checklist under the four file
fields is the one place that says whether the paths were accepted, and it prints
`—` for all four rows for the whole session — before loading, after loading, and
after navigating away and back — while `data_ready` is already `True`
(`05_data_step_filled.png`, `05b_data_step_revisited.png`). The nav ✓ on **Data**
is also one navigation behind: it only appears after leaving the step and
returning. RF-126.

*The Finish step reports success unconditionally.* Two of this run's three
attempts had every link/constraint RPC fail (`fit not found`, ~40 tracebacks in
the log) and the wizard still printed the green *"Created VV, VH and global
anisotropy fits."* — with `g = 1`, `l1 = l2 = 0`, `n0` fixed and an empty *Link*
column in the global fit's *Info* tab. The links are the entire point of the
wizard. RF-127.

*Those failures are RF-012 again.* The two bad attempts ran while the user's own
`python -m chisurf` held 127.0.0.1:8765; the wizard's fitting client adopted that
foreign server, so `fit.range.auto`, `fit.set_fit_range`, `parameter.link` and
`parameter.set_*` all returned *"fit not found"*. The fit windows showed
*"Range 0, 0 / chi2r=-0.0000"*. Re-run with `mmfdb.cmd_port` pinned to a private
port, the identical script produces the numbers above — which isolates the cause
and confirms RF-012 is still open and still silent. Note `CHISURF_RPC_CMD_PORT`
is *not* read by the GUI (only by `server/services/agent.py`); the port comes
from `cs_settings["mmfdb"]`.

**Smaller defects seen in the good run:** the corrected IRFs are registered as
datasets under `/Users/…/H2O_8-0 ps_2048 ch_vv_vv` — absolute path, polarisation
suffix twice (RF-128); the VV and VH fits get *different* auto fit ranges
(328…1809 vs 343…1827) although they are two channels of one measurement, and
both stops reach into the rising edge of the next excitation pulse, which is
what the +20 σ residual spike at 58 ns is (RF-129); and the anisotropy model's
`vv_bg_int` / `vh_bg_int` outputs are `nan` in both wizard-built fits (RF-130).

**Not a bug:** the Wizards hub is absent from the classic menu bar — the whole
plugin tree lives on the ribbon (*Main → Tools → Wizards*), which is the shipped
UI. A menu-bar-only walk finds 29 leaf actions, none of them plugins.

## UX / UI suggestions

- **Make the Data checklist live, and say what was read.** Even fixed, `IRF VV ✓`
  is thin. After **Load**, show channels, total counts and the peak channel per
  curve — that is what tells a user they picked the IRF and the decay the right
  way round. Today a swapped IRF/decay pair is only visible three steps later.
- **Say the VV/VH rule on the Data step.** With a stacked file the same path goes
  in both VV and VH fields; nothing in the UI says so (it is in the plugin
  README). A "this setup is VV/VH-stacked — one file holds both" hint, or
  auto-mirroring VV→VH when `is_vv_vh` is set, would remove a guess a new user
  cannot make.
- **Pre-tick nothing.** Steps with no `complete_when` render with a ✓ from the
  start, so the rail shows five of six steps "done" before the user has done
  anything, and the one real ✓ (Data) is the one that lags. Use ✓ only for
  genuinely satisfied steps and leave the rest blank.
- **Label the IRF plot axes** — x is channel index, y is counts, neither is
  labelled; and the legend's *"VV (corrected)" / "VH (corrected)"* entries are
  clipped by the legend box.
- **Show what the background region is doing.** The region is picked blind: print
  the subtracted background level per channel and the VV/VH intensity ratio for
  the current region, so the user can tell a good region from a bad one instead
  of eyeballing a log plot.
- **Corrections: three numbers, three 900-px-wide spin boxes**, laid out two per
  row so the `l1` box runs off the panel edge and loses its spinner arrows. Also
  offer a link to the **VV/VH G-Factor Calculator** plugin — "where do I get the
  g-factor" is the obvious next question, and ChiSurf ships the answer.
- **One home for g / l1 / l2.** The Read-data dock's *Anisotropy (VV/VH)* box has
  its own g-factor / l1 / l2 fields; after the wizard set 1.15 / 0.12 / 0.44 that
  box still read 1.000 / 0.000000 / 0.000000. Two disconnected editors for one
  instrument constant is a wrong-number trap.
- **Components: the amplitude/value spin-box labels are `a` and `l`.** `l` (the
  first letter of "Lifetime (ns)") reads as a `1` and collides with the `l1`
  correction one step earlier — use `τ` and `ρ`, with units. The `ρ (ns)` column
  header is also clipped along its top edge.
- **No feedback during **Create fits**.** Five seconds pass with the button live,
  no busy cursor and no progress text; the only sign anything happened is the
  status line at the end.
- **Name the fit windows by polarisation.** Both child windows open titled with
  the same truncated absolute path (`…/02_18-577+7.5uM(577)UP_8ps_U`), so the
  user cannot tell VV from VH. Title them `Anisotropy VV` / `Anisotropy VH`, and
  give the datasets short names instead of full paths.
- **`range=0..0` on the global fit's *Info* tab** is meaningless — a global fit
  has no range of its own; print the children's ranges or omit the field.
- **The *Info* tab's `Link` column wraps onto the next line** (`b(1) … cov` then
  `→b(1)`), which makes a 14-link table hard to scan.
- **Offer to run the fit.** The wizard stops at "fits created", in a state whose
  χ²ᵣ is ~570; the user must find the global fit window and press Fit. A
  *Create and fit* button would finish the job the wizard started.

## Bugs filed

- RF-126 — the Data-step checklist never refreshes; all four rows stay `—`, and
  the nav ✓ lags one navigation behind.
- RF-127 — `create_fits` reports success even when every link/constraint call
  failed.
- RF-128 — corrected-IRF datasets are named with the absolute path and a doubled
  polarisation suffix (`…_vv_vv`).
- RF-129 — VV and VH get different auto fit ranges, both reaching into the next
  excitation pulse; the wizard offers no common range.
- RF-130 — `vv_bg_int` / `vh_bg_int` are `nan` in every wizard-built fit.
- RF-012 (still open) — a second ChiSurf instance is adopted and the whole
  Finish step silently no-ops.
