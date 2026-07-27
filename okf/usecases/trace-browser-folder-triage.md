---
type: Reference
title: Use case — Trace Browser (triaging a folder of single-molecule measurements)
description: Point the Trace Browser at a folder of TTTR measurements, preview each intensity trace, star-rate and annotate the good ones, filter to the keepers and export them (raw, CSV or DOCX) or hand one off to the time-window / HMM tools.
tags: [usecase, tttr, single-molecule, trace, browser, triage, gui]
timestamp: '2026-07-27T00:00:00Z'
---

# Use case: Trace Browser — triaging a folder of measurements

**Goal:** the *first* thing a user does after a measurement session, before any of
the analysis workflows: walk a folder of raw TTTR files, look at each intensity
trace, decide which measurements are worth analysing, record that judgement
(0–3 stars plus a free-text note that persists in the folder), and pass the
keepers on — as copied raw files, as binned CSV traces, as a DOCX report, or
straight into the [time-window](/usecases/burst-selection-fret.md),
intensity-trace HMM or [ndXplorer](/architecture/plugins.md) tools.

This is the "Correlation / TTTR tools" coverage entry for **file triage**; it sits
upstream of [micro-time histograms](/usecases/tttr-microtime-histogram.md),
[FCS correlation](/usecases/fcs-correlate-tttr.md) and
[burst selection](/usecases/burst-selection-fret.md).

**Data:** two sets were driven this run.

- Shipped: `test/data/tttr/BH/132/BH_SPC132.spc` and
  `test/data/tttr/BH/630_256/BH_SPC630_256.spc` (Becker & Hickl SPC-130,
  183 657 photons on routing channels 0/1/8/9, 61 s) — copied into a scratch
  folder first, because selecting a row writes `.trace_browser_meta.json` next to
  the data.
- Confocal spot survey: twelve `.ptu` point measurements
  (`junk/Seidel/Demo/20211202/allOverview_Pos_*_spot_*.ptu`, ~0.4 MB / 51 k
  photons / 16 s each, C-LR origami, arXiv:2108.00024) — the "many small files in
  one folder" shape the tool is built for.

**Tool:** `chisurf.plugins.tttr.trace_browser` (`TraceBrowserTool` wrapping the
`TraceBrowser` workspace), display name
*Spectroscopy:Single-Molecule:Trace Browser*; CLI `trace-browser`, RPC service
`trace_browser.*`.

## Steps

1. Open the tool. It comes up **directly on the browser page** — the detector-setup
   page is built, silently accepted (`_on_continue()` runs in `__init__`) and
   hidden. A toolbar runs across the top: **📂 Open · 🧹 Clear · ♻️ Caches ·
   📤 Export · CSV · DOCX · 🧠 HMM · ⏱️ TW · 📊 NDX · ☐ Subfolders · ❔ Help**.
2. Press **← Select setup** to see which detector setup is in force. The page
   shows the *Setup:* combo (last-used setup, `BS` here), the *TTTR Reading
   routine* box (*File Type* `SPC-130`, macro-time 13.5 ns, micro-time
   3.2959 ps) and the *Detectors* table (`green` = 8,0,3 µT 0:4095;
   `red` = 9,1,2 µT 0:2048; `yellow` = 9,1,2 µT 2048:4095). The setup's **file
   type decides which extensions the browser will list** and its detector names
   become the trace panel titles and CSV columns. Set *File Type* to `Auto` for a
   mixed folder. Press **Continue**.
3. Press **📂 Open** and pick the folder (or drag the folder onto the file table —
   `dropEvent` accepts a dropped directory). Tick **Subfolders** first to recurse.
4. The table fills with **File / Rating / Size (MB)**. Selecting a row computes and
   plots that file's trace; on opening, every listed file is pre-computed into a
   per-folder `.tttr_trace_cache` behind a cancellable *"Precomputing traces…"*
   progress dialog (12 × 0.4 MB PTU ≈ 0.1 s; 2 × 1.1 MB SPC ≈ 0.9 s).
5. Read the preview. Four stacked panels — one per detector of the setup
   (`green`, `red`, `yellow`) plus **Sum** — each with the binned trace against
   *Time (s)* on the left and its counts histogram on *Counts (log)* on the
   right. Set the bin width in the **`ms bin`** spin box (0.001–10000 ms; a
   re-bin takes ~0.08 s per file) and the vertical range with **Ymin/Ymax**.
6. Rate the file: click the ☆☆☆ widget in the *Rating* column (1–3 stars; the
   click position picks the star, and ← → / 0–3 work when it has focus). Type a
   note into the **Annotation** box at the bottom; it is committed when the
   selection changes and debounce-saved to `.trace_browser_meta.json` in the
   folder, keyed by path relative to the folder.
7. Narrow the list with **Filter:** (`All`, `≥ 1★`, `≥ 2★★`, `≥ 3★★★`,
   `Only 0★`); click the *File*, *Rating* or *Size* header to sort. Both work
   (ratings stay attached to their file across a re-sort).
8. Export: **📤 Export** copies raw files to a chosen folder, **CSV** writes one
   `<stem>_trace.csv` per file (`time_ms,green,red,yellow`), **DOCX** writes a
   report of traces plus annotations.
9. Hand off the selected trace: **⏱️ TW** opens it in *TTTR→Time-Window BIDs* at
   the current bin width, **🧠 HMM** in *Intensity Trace Analysis*, **📊 NDX**
   computes burst IDs from the current time window and opens ndXplorer.

## Expected

- Every TTTR file in the folder that the reader can open is listed, with its size
  and its stored rating.
- Selecting a file draws its intensity trace within a second; re-binning redraws.
- Ratings and annotations survive closing and re-opening the folder.
- **Filter and selection are honoured by the exports** — what the user sees is
  what gets written.
- The three hand-off buttons open the target tool preloaded with the selected file.

## Observed (last run: 2026-07-27)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) against both data sets,
screenshots inspected at each step.

**The tool lists nothing at all.** Point the browser at *any* folder of
single-molecule TTTR files and the table stays empty — no message, no count, no
hint; the only thing that changes is the folder path in the label
(`03_folder_open`, `40_bh_empty`). Two independent filters each suffice to empty
it:

- `_is_image_tttr()` classifies **every** file as a CLSM image, because
  `_is_clsm_compatible()` treats "a `CLSMImage` could be constructed" as proof —
  and the reader happily salvages frames from a point measurement
  (`WARNING: no complete frames; salvaging 61 frame(s) with 200 line(s)`).
  Verified `True` for all 12 confocal-spot `.ptu` files **and** for the shipped
  `.spc` files. → **RF-349**.
- `_allowed_exts_for_setup()` narrows the listing to the extensions of the
  silently adopted last-used setup — `BS` → `SPC-130` → `{'.spc'}` — so a folder
  of `.ptu` is empty for a second reason, and the user never saw the setup page
  that decided it. → **RF-350**.

The RPC/CLI half of the same plugin answers differently:
`trace_browser.files.list` returns **12 files** for the folder the GUI shows as
empty (and `0` for the `.spc` folder, since its hardcoded extension set has no
`.spc`). → **RF-355**.

With the image heuristic bypassed the rest of the workflow works, and works well:

- 12 rows listed in 0.1 s including pre-computation; row selection plots in
  ~0.1 s; re-binning to 1 ms / 100 ms takes 0.08 s (`20_listed`, `22_bin_*`).
- Star rating, annotation, per-folder `.trace_browser_meta.json`, the rating
  filter (11 of 12 rows hidden at `≥ 3★`) and header sorting all behave — after a
  sort by size the 2-star widget was still on the file that was rated
  (`24_rated`, `27_sorted`).
- CSV export is correct: 1647 rows, header `time_ms,green,red,yellow`, values
  matching the plotted trace.
- Drag-and-drop of a folder onto the table opens it exactly like **📂 Open**.
- **♻️ Caches** removes the 14-file `.tttr_trace_cache` and confirms it;
  **🧹 Clear** empties the table.

What is broken or misleading once the list is populated:

- **📤 Export and CSV ignore both the selection and the filter.** With 11 of 12
  rows hidden by the `≥ 3★` filter and exactly one row selected, both wrote **all
  12 files**, silently. The button says *"Export selected…"*. → **RF-351**.
- **⏱️ TW is dead**: `'PathListWidget' object has no attribute 'addItem'` →
  *Transfer Failed* dialog. The time-window tool's file list was migrated to the
  unified AutoForm `path_list`; this call site was not. → **RF-354**.
- The *Size (MB)* column prints the raw sort key (`0.387741`,
  `1.14441`) instead of the `0.4 MB` the same plugin's API returns, and the
  *Rating* column shows a bare `0` / `2` next to the stars. → **RF-352**.
- The *Include subfolders* checkbox is never added to a layout: it is parked at
  (0,0) under the *← Select setup* button, clipped to "Include su", and duplicates
  the toolbar's own **Subfolders** box. → **RF-353**.
- **🧠 HMM** opened without error. **DOCX** stopped at *"python-docx is not
  installed"* — that dependency **is** declared in `pixi.toml` and
  `pyproject.toml`, so this is a gap in the local arm64 conda env, not a product
  defect; noted so the next run does not re-file it.

## UX / UI suggestions

- **Say how many files were found.** The single most damaging thing about the
  empty-list bugs is that the window looks identical to "this folder is empty".
  A status line — *"12 files found, 12 skipped (image data), 0 listed"* — with the
  reason and the active extension filter would have turned two silent failures
  into a one-line diagnosis. The same line should name the setup in force
  (`BS · SPC-130 · green, red, yellow`), which today is only visible if the user
  thinks to press *← Select setup*.
- **The four panels need per-panel autoscale.** All four share one fixed
  `Ymin/Ymax` (default 0–1000) although their count rates differ ~10×: for
  `BH_SPC132.spc` (10 ms bins) `green` averages 22 counts/bin with bursts to
  ~900, `red` 5.3, `yellow` 2.5 — so `yellow` is an indistinguishable flat line
  at the default (`41_bh_default_yrange`). On the confocal-spot `.ptu` files
  (0–5 counts per 10 ms bin) *all four* panels are flat lines and the preview is
  useless until `Ymax` is hand-set to 60 (`20_listed` vs `23_yrange`) — with
  nothing on screen suggesting that is what is wrong. An autoscale button, or a
  per-panel range, or simply defaulting to the data's own range would fix it.
- **The rotated y-axis titles collide.** Four titles (`green Counts / 10 ms`,
  `red …`, `yellow …`, `Sum …`) are stacked in one narrow column and read as one
  run-on string (`… / 10 msyellow Counts / 10 ms`), and the panels' tick labels
  overlap across panel boundaries. Put the detector name in a panel caption or
  legend instead of the axis title.
- **The folder path runs into the next control** — `…/qa_tracebrowser/tracesFilter:`
  — the control row is built with `setSpacing(0)`. Add spacing, and elide the path
  from the left so the folder name stays visible.
- **Filtering everything out leaves the last trace on screen.** After `≥ 3★`
  emptied the table, the previously selected file's trace was still plotted with
  an empty annotation box, as if it were still selected (`26_filter_3stars`).
  Clear the plot (or show an empty-state message) when nothing is visible.
- **CSV export drops a `.tttr_trace_cache` folder into the user's chosen output
  directory.** Keep the cache next to the data (or in the app cache), not in an
  export target.
- **Selecting a row writes an empty annotation record.** Just clicking through the
  list creates `{"<file>": {"annotation": ""}}` entries in
  `.trace_browser_meta.json`, so a browse session dirties the data folder even
  when nothing was rated or annotated. Only write records that carry content.
- **`📤 Export` / `CSV` / `DOCX` should say what they did.** Twelve files were
  copied with no confirmation, no count and no error summary; the only trace is a
  log line.

## Bugs filed

- RF-349 — the image heuristic classifies every point-measurement TTTR as a CLSM
  image, so the file list is always empty.
- RF-350 — the silently adopted last-used detector setup restricts the listed
  extensions (and names the trace channels) without ever being shown.
- RF-351 — `📤 Export` and `CSV` write every row in the table, ignoring the
  selection and the rating filter.
- RF-352 — the *Size (MB)* and *Rating* columns display their numeric sort keys.
- RF-353 — the *Include subfolders* checkbox is not in any layout and overlaps the
  *← Select setup* button.
- RF-354 — the `⏱️ TW` hand-off calls `addItem` on the time-window tool's
  `PathListWidget`.
- RF-355 — the RPC/CLI file listing and the GUI listing use different, and both
  incomplete, file-type rules.
