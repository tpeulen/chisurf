---
type: Reference
title: Use case — the Converter hub (raw stream → time-window BIDs → analysis folder)
description: The three-step file-preparation pipeline in one window — transcode/split a TTTR container, cut it into fixed-duration time-window BID (.bst) files, and turn those BIDs into a burstwise analysis folder with a .bur table.
tags: [usecase, tttr, converter, time-windows, bid, bur, burst, gui]
timestamp: '2026-07-29T00:00:00Z'
---

# Use case: the Converter hub — raw stream → time-window BIDs → analysis folder

**Goal:** produce a **burstwise analysis folder** from a raw photon file without
running a burst search. Instead of letting a burst-search find molecules, the
user cuts the measurement into **fixed-duration time windows** (the Seidel-style
"time-window BID" preparation) and lets every window become a row in a `.bur`
table. This is what feeds a time-window PDA fit, a per-window count-rate/FRET
series, or a quality check on a measurement whose bursts are not the point.

The whole pipeline is one window — *Tools → 🔁 Converter*
(`chisurf/plugins/tttr/converter`), a `NavigationPanelTool` whose left list
lazily embeds three existing tools declared in
`chisurf/plugins/tttr/converter/gui/panels.json`:

1. **✂️ TTTR Split / Convert** — `tttr_splitter` (transcode container, split into chunks)
2. **⏱️ TTTR → Time Windows** — `tttr_time_windows` (write `.bst` BID files)
3. **📦 BID → Analysis** — `burst/bid_to_analysis` (write `bi4_bur/<stem>.bur` + `Info/`)

It sits beside [TTTR file preparation](/usecases/tttr-file-preparation.md) (the
per-file toolbox) and before [the PDA distance fit](/usecases/pda-distance-fit.md)
and [burst selection](/usecases/burst-selection-fret.md), which consume the
folder this produces. The output must satisfy the
[burst-companion contract](/subsystems/burst-companions.md) — one row per burst,
merged column-wise by position — which is exactly where this run found its worst
defects.

**Data:**

- `test/data/tttr/BH/132/BH_SPC132.spc` — Becker & Hickl SPC-130, **183 657
  photons**, routing channels `0, 1, 8, 9`, 62.328 s, 4096 micro-time channels
  (3.30 ps), macro-time resolution 13.5 ns.
- Copied to a scratch folder and transcoded to PTU by step 1, then renamed
  `sample_01.ptu` so the pipeline runs on a realistic "measurement folder".

## Steps

1. Open **Tools → 🔁 Converter**. The left list shows the three steps; the shell
   has a shared status bar and a `◀ Back` / `⏭` / `Next ▶` stepper bottom-right.
2. Select **✂️ TTTR Split / Convert**. On *Input / Output*, drop (or type) the
   `.spc` path into **Input file** — the file loads and **Output folder**
   auto-fills with the source folder. Set **Output folder** to the target
   folder; leave **Input format** on `Auto` and **Output format** on `PTU`.
3. On *Split options* leave the defaults (`Photons/file 300 k`, `µ-time binning 1`,
   *Split into files* / *Reset macro times* / *Keep original* all on).
4. Press **✂️ Convert / Split**. The file is written to
   `<output folder>/<stem>/<stem>_00000.ptu`.
5. Select **⏱️ TTTR → Time Windows**. On the *📁 Files* tab add the converted
   `.ptu` (drag-drop, ➕ Files, 📁 Folder or 🗄️ Database).
6. On *⚙️ Settings* set **Time window** (default `10.000 ms`) and leave
   **Output folder** empty to let it derive one from the first file.
7. On *👁️ Preview* check the intensity trace with its window boundaries, then
   press **🕐 Process**. Read the result on the *📋 Summary* tab.
8. Select **📦 BID → Analysis**. On the *Setup* tab pick or define the detector
   setup (file type, macro/micro-time resolution, PIE windows, detectors — a
   green / red / yellow polarization-resolved default is pre-filled); on the
   *Files* tab drop the `.bst`, check that the **TTTR file** column resolved,
   and press **Process**.
9. Open the produced `<measurement>/<stem>/bi4_bur/<stem>.bur` and check that it
   has one row per time window with the expected photon counts and count rates.

## Expected

- Step 4 writes a PTU that reads back with the same photon count, routing
  channels and micro-times as the source.
- Step 7 writes `<stem>_TW_<n>ms/<stem>.bst`, one `start<TAB>stop` pair per
  window, `⌈duration / window⌉` rows.
- Step 8 writes `bi4_bur/<stem>.bur` (tab-separated, header + one row per
  window, zero-interleaved per the .bur convention), `Info/*.mti`,
  `Info/photon_selection_parameters.json` and `Info/datetime.txt`.
- The `.bur` carries **exactly as many real rows as the `.bst` has windows**, and
  its `Count Rate (KHz)` agrees with `Number of Photons / Duration (ms)`.

## Observed (last run: 2026-07-29)

**The physics and the file plumbing are sound; the row-level bookkeeping is not.**

Step 2–4 (Split / Convert) — **correct**. `BH_SPC132.spc → PTU` reproduced all
183 657 photons, routing channels `[0 1 8 9]`, `micro_times` **bit-identical**
(`np.array_equal` → True), 4096 micro-time channels at 3.2959 ps, 62.328 s;
*Reset macro times* shifted the first macro time to 0 while leaving every
`np.diff` unchanged. `do_split` itself takes **0.02 s**. Output lands in a
**sub-folder named after the input stem** (`out/BH_SPC132/BH_SPC132_00000.ptu`)
which nothing in the UI says.

Step 5–7 (Time Windows) — **correct output, unusable preview at the default
setting**. A 62.328 s file at the default 10 ms gave **6233 windows**; at 100 ms,
**624 windows**, auto-output `measurement/sample_01_TW_100ms/sample_01.bst`
(7 947 B, 624 lines of `start<TAB>stop`). But the preview draws **one dashed
white vertical line per window**: at the default the plot is a solid white
blanket with the yellow intensity trace invisible underneath
(`06_tw_preview.png`), and each redraw takes **1.79 s** versus 0.01 s at a 1 s
window. All four dock tabs (`⚙️ Settings`, `📁 Files`, `👁️ Preview`,
`📋 Summary`) carry a **✗ close button that does nothing**.

Step 8–9 (BID → Analysis) — **it runs, and it silently mis-counts every row.**
The `.bst` is written half-open (`compute_bids_from_tttr` documents
`[start_idx, stop_idx)`), while `generate_burst_dataframe` treats `stop` as the
**inclusive last photon**. Two consequences, both verified on disk:

- Window 1 is `[0, 663)` = 663 photons; the `.bur` reports **664**, and photon
  663 is counted again as the first photon of window 2. Every window is +1.
- The last window `(183604, 183657)` hits `stop >= n_ph` and is `continue`-d, so
  **624 BID windows produced 623 `.bur` rows** — a missing row, not a sentinel
  row, in a format the rest of ChiSurf merges *column-wise by position*.

And the total count rate is off by a factor of 1000: window 1 has 664 photons
over 100.035567 ms = **6.6376 kHz**, written as `0.006637639190868984` — while
the *per-detector* `Green Count Rate (KHz)` on the same row (594 photons over
99.5528 ms → `5.96668177774029`) is correct. The two columns of the same file
disagree by 1000×.

Everything else the panel produces is right: `Info/sample_01.mti`
(`sample_01.ptu<TAB>62.328036`), `photon_selection_parameters.json` with the
six channels and three micro-time ranges, and the interleaved zero rows the .bur
format expects.

**Feedback across the hub is close to absent.** The Time-Window tool writes its
only success line ("Processed 1 file(s), 6233 windows") to its **own** status
bar, which `embed_mainwindow` leaves behind when it flattens the window — the
bar is `isVisible() == False` and the shell's bar reads `Ready` throughout; the
user has to click the *Summary* tab to learn anything. The splitter's single-file
run reports nothing at all on success (the *batch* run does pop "Batch complete
— processed N file(s)"), leaves its progress bar reading **0 %** after a
completed conversion, and leaves the shell status bar stuck on the internal word
**"Parsing …"** from the load two steps earlier (`04_split_done.png`).

Two more things a user will hit. The **⏭ fast-forward** walks all three panels,
runs **nothing** (no panel exposes the `toolAction_run` the shell looks for —
`process_current_step()` returns `False` on all three) and then announces
*"Fast-forward finished — the pipeline is done"*. And one unreadable BID
**aborts the whole batch**: `BidToAnalysisGUI.process_all` has its `try/except`
commented out, so a `ValueError` escapes the slot, the bad row is left reading
`Processing` forever, and the good file queued behind it is never touched.

Layout: the navigation pane is fixed at 220 px but needs 232, so a horizontal
scroll bar is permanently visible and *"TTTR → Time Windows"* is clipped mid-word
in every screenshot. The BID→Analysis *Files* table gives its three informative
columns (BID file / TTTR file / Output folder) so little width that all three
elide to `/tmp/qa-...`, while **Status** takes 55 % of the table to show the word
`Done` (`11_bid_done.png`).

Screenshots: `01_hub`, `02_panel0..2`, `04_split_done`, `05_tw_files`,
`06_tw_preview`, `07_tw_summary`, `10_bid_files`, `11_bid_done`.

## UX / UI suggestions

- **Cap the preview's window markers.** Below ~200 windows draw the dashed
  boundaries; above it, shade alternating windows (or draw nothing) and put
  "6233 windows — boundaries hidden" in the plot title. The trace is the point of
  the preview and at the *default* setting it is completely hidden.
- **Say how many windows the setting will produce, before Process.** The Settings
  tab knows the file duration as soon as a file is added; "10.000 ms → 6233
  windows" beside the spin box turns an abstract number into a decision.
- **Give the hub one visible completion line per step.** Every embedded tool
  should report through `find_status_reporter(...).report_status(...)` (the
  shell's shared bar) rather than its own `QMainWindow` status bar, which
  `embed_mainwindow` discards. "Wrote 624 windows → …/sample_01.bst" belongs on
  the shell bar, not only in a tab the user has to find.
- **Name the output path in the UI after a run.** Both step 1 (writes to a
  `<stem>/` sub-folder the user never asked for) and step 3 (writes to
  `<tttr parent>/<bid stem>/bi4_bur/`) invent a directory layout and never say
  so. A clickable "Open output folder" beside the run button would close it.
- **Reset the shell status bar to a terminal message.** "Parsing …" surviving a
  successful conversion reads like the app is stuck. `_deactivate_task`
  deliberately keeps the last message, so the *callers* need to set a final one.
- **Widen the BID→Analysis Files table sensibly** — `setStretchLastSection(True)`
  on a `Status` column that holds one word is exactly backwards; stretch the
  path columns and give Status a fixed width, or elide from the left so the file
  name survives.
- **The static hint "Select a file to preview its intensity trace." lives on the
  *Settings* tab**, never updates, and is still there once files are loaded and
  the preview is drawn. It belongs on the empty Preview tab.
- **Make the ✗ on the Time-Window dock tabs mean something** — either wire it to
  a hide-with-a-way-back (the tool's only menu is *File → Exit* / *Help → About*,
  and `embed_mainwindow` drops the menu bar entirely in the hub, so a genuinely
  closed tab would be unrecoverable), or turn `setTabsClosable` off.
- **Reflect the SPC micro-time-binning clamp in the widget.** `micro_time_binning`
  silently promotes the user's `1` to `8` for SPC containers while the combo keeps
  showing `1` — and, as filed below, neither value is used at all.
- **Widen the navigation pane to its size hint** (or elide the labels) — a
  permanent horizontal scroll bar under three items reads as a broken layout.

## Bugs filed

- RF-896 — `.bur` `Count Rate (KHz)` is 1000× too small (shared burst core).
- RF-897 — BID `[start, stop)` read as inclusive: every window +1 photon, last
  window silently dropped (624 windows → 623 rows).
- RF-898 — the ⏭ fast-forward reports the pipeline done after running nothing.
- RF-899 — the splitter's "µ-time binning" combo is never read.
- RF-900 — the time-window preview draws one vline per window (6233 at the
  default), hiding the trace and costing 1.79 s per redraw.
- RF-901 — the ✗ close button on every Time-Window dock tab does nothing.
- RF-902 — `BidToAnalysisGUI`'s window title contains a raw U+0012 control byte.
- RF-903 — `convert_many`, the documented programmatic API, always raises
  `TypeError`.
- RF-904 — one unreadable BID aborts the whole batch with an unhandled exception
  (the `try/except` is commented out).
- RF-905 — the Converter navigation pane is narrower than its size hint, so a
  scroll bar is always visible and a step label is clipped.
- RF-906 — the BID→Analysis Files table hides its three path columns behind a
  one-word Status column.
