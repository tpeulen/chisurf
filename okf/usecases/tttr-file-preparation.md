---
type: Reference
title: Use case — TTTR Tools (prepare raw photon files before any analysis)
description: The unified TTTR toolbox — inspect and edit a file header, split a long measurement into chunks, convert the container, check the count rate per detector over a whole folder, shift micro-times and create ALEX micro-times.
tags: [usecase, tttr, toolbox, header, splitter, count-rate, alex, quality-control, gui]
timestamp: '2026-07-28T00:00:00Z'
---

# Use case: TTTR file preparation (the TTTR Tools toolbox)

**Goal:** everything a user does to a raw photon file **before** an analysis
window is ever opened. A measurement comes off the instrument as one long TTTR
file; before correlating, histogramming or burst-searching it the user wants to
(a) see what the file actually claims about itself and correct a wrong header
tag, (b) cut the long acquisition into equal chunks and/or convert the container
so the rest of the pipeline can read it, (c) check the count rate on every
detector across all of today's files to spot a dead detector, a bleached sample
or a mis-set laser power, and (d) apply the stream-level corrections —
micro-time shift, ALEX→micro-time — the downstream tools assume are already done.

All of that lives in **one window**: *Tools → TTTR Tools*, a
`NavigationPanelTool` whose left-hand list lazily embeds six existing tools
(declared in `chisurf/plugins/tttr/tttr_toolbox/gui/panels.json` — adding a tool
is one JSON entry).

This is the "Correlation / TTTR tools" coverage entry for **file preparation and
per-file quality control**; it sits *before*
[the micro-time histogram](/usecases/tttr-microtime-histogram.md),
[FCS correlation](/usecases/fcs-correlate-tttr.md) and
[burst selection](/usecases/burst-selection-fret.md), and beside
[the LUT calibration](/usecases/tttr-lut-calibration.md).

**Data:**

- `test/data/clsm/PQ_Olympus_MFIS.ht3` — a PicoQuant HydraHarp confocal-scan
  stream, 15 604 430 events (15 583 897 photons + 20 533 scan markers: 41 frame,
  10 246 line-start, 10 246 line-stop), 61 header tags, 32 768 micro-time
  channels, 75.1 s of acquisition, ≈208 kHz total.
- `test/data/tttr/BH/132/BH_SPC132.spc` — Becker & Hickl SPC-130, 183 657
  photons, 62.3 s.
- `test/data/tttr/BH/630_256/BH_SPC630_256.spc` — Becker & Hickl SPC-600/256,
  294 884 photons (used to test the reading-routine selector).

**Tool:** `chisurf.plugins.tttr.tttr_toolbox` → `TttrToolboxTool`, display name
*Tools:TTTR Tools*. Panels (each also a stand-alone, `menu_hidden` plugin):
ALEX Creator · Micro-time Shifter · TTTR Header Editor — Split / Convert —
Count Rate Analysis · Audifier.

## Steps

1. Open **Tools → TTTR Tools**. The window shows the navigation list on the left
   with a search box; the first panel is instantiated eagerly, the rest on first
   click. The panel selected last session is restored.
2. **TTTR Header Editor** — press **📂 Open** (or drop the file on the table) and
   pick `PQ_Olympus_MFIS.ht3`. The status line above the table reports the file,
   the detected container, the tag count and the fixed output format; the table
   fills with one row per tag (*Name* · *Type* combo · *Value* · *Idx*), and the
   collapsed **JSON** tab mirrors the whole header live.
3. Correct a tag: click into the *Value* cell of `Comment` and type the new text.
   Use **➕ Add** / **➖ Remove** to add or delete a tag (Add asks for name, value
   and idx in three successive input dialogs). Press **💾 Save as PTU** and pick
   an output path — the photon data of the source is copied verbatim and the
   edited tags are written into a PTU (the only container that persists arbitrary
   tags).
4. **Split / Convert** — on the *Input / Output* tab, drop the raw file onto
   *Input file* (a staged-loading progress bar runs) and set *Output folder*
   (it is pre-filled with the source file's own folder). Choose *Input format*
   (`Auto`) and *Output format* (`PTU`).
5. On *Split options*, set *Photons/file* (in units of 1000 — `2000` = 2 M photons
   per chunk), *µ-time binning*, and the three toggles *Split into files*,
   *Reset macro times*, *Keep original*. Press **✂ Convert / Split**: the chunks
   are written into a new sub-folder named after the input file
   (`<output folder>/<stem>/<stem>_00000.ptu` …).
6. The *Batch* tab does the same for a list of files: drop files/folders into the
   list, tick *Use file's parent as output folder*, press **▶ Start batch**.
7. **Count Rate Analysis** — on the *Channel Definition* tab pick a detector setup
   (or edit the *Detectors* table directly: name, routing channels, micro-time
   range, G-factor). *Polarization resolved* and the *PIE Windows* box combine
   into the channel list the count rates are reported for
   (`prompt_green`, `delayed_red`, …).
8. On the *Files* tab drop the folder of chunks from step 5 (**➕ Files** /
   **📁 Folder** / **🗄 Database**), then press **📈 Calculate**.
9. Read the result on the *Count Rates* tab (count rate in kHz per channel
   against file index, one coloured trace per channel, legend) and the *Results*
   tab (per-channel *Mean (kHz)* · *Std (kHz)* · *#Photons* · *Time (s)*).
   Press **💾 Save** to export the table as tab-separated text.
10. **ALEX Creator** — drop a file, set *Period* and *Shift* of the alternating
    excitation, check the *ALEX micro-time histogram* tab, press **💾 Save** to
    write a file whose micro-time is the ALEX phase. The *Batch* tab converts or
    merges many files.
11. **Micro-time Shifter** — drop files, apply a global and per-channel micro-time
    shift (with **⚡ Auto Align** against a trigger channel), watch the
    *Histogram* dock, **💾 Save**.
12. **Audifier** — the last panel; converts the photon stream to audio with a
    live micro-time/lifetime waterfall.

## Expected

- Step 2: 61 rows for the HT3, every *Type* combo showing the real tag type, the
  *Value* column wide enough to read the values.
- Step 3: the saved PTU is a **faithful** copy — same photon count, same macro
  times, micro times and routing channels, all header tags carried over (only
  the edited one changed), and the file still usable by every reader that could
  read the original (for a scan file: still reconstructable as a CLSM image).
- Step 5: chunks that together hold exactly the source photons, and clear
  feedback that the run finished and where the files went.
- Step 9: count rates that are internally consistent — `#Photons / Time` must
  agree with the reported `Mean`, and the numbers must be physically possible
  (a TCSPC detector cannot exceed a few MHz). The reading routine chosen in
  *Channel Definition* must be the routine the count rates are computed with.
- Step 10: a converted file whose micro-time is the ALEX phase — with a warning
  when the input already carries a real TCSPC micro-time that is about to be
  overwritten.

## Observed (last run: 2026-07-28)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env,
`CHISURF_SETTINGS_DIR` pointed at a scratch folder so the layout is the shipped
default), screenshots inspected at every step.

**The shell works well.** The window opens in 3.4 s and every one of the six
panels loads lazily without an error panel (0.97–1.80 s each). The navigation
list, the search box and the per-panel dock layouts are all sane at 1300×820, and
the toolbox remembers the panel you were on. The three *heavy* operations are
fast and, where they are correct, they are exactly correct:

| step | measured |
|---|---|
| header read (55 MB HT3, 61 tags) | 0.69 s |
| header save as PTU (15.6 M photons) | 0.77 s → 71.8 MB |
| split into 8 × 2 M-photon PTU chunks | 1.2 s, **15 604 430 / 15 604 430 photons preserved** |
| count rates, 8 files × 6 channels | 1.2 s |
| ALEX histogram + convert (2 M photons) | 0.9 s + 0.09 s |

The header round-trip is bit-exact on the photon data (`macro_times`,
`micro_times`, `routing_channels` all compare equal), the edited `Comment` tag
comes back verbatim, and the split chunks account for every photon.

**What is wrong.** Everything below was measured this run.

- **A header edit destroys a scan file.** Saving the edited HT3 as PTU drops the
  `ImgHdr` tag — `tttrlib` prints `ERROR: writing of tyBinaryBlob currently not
  supported` to *stderr*, which no user sees, while the GUI reports
  "Edited header saved as PTU." The saved file then reconstructs as
  `CLSMImage(1, 10246, 256)` — one salvaged frame — instead of the source's
  `(40, 256, 256)`. Photons and markers are all intact (41 / 10 246 / 10 246
  markers survive, and passing the markers explicitly *does* give
  `(40, 256, 256)`), so this is purely the lost header blob. Splitting the same
  file emits the identical error once per chunk. (RF-596)
- **A tag you add is written empty.** The *Add* button creates the row with the
  type combo left on its first entry, `Empty` (`0xFFFF0008`). Adding
  `User_Sample = "HeLa cells, 37 C"` and saving produces a tag whose value reads
  back as `None`. The same coercion hits the shipped start-up sample header:
  three of its six tags carry type codes that are not in the editor's 11-entry
  map, display as `Empty`, and are rewritten to `0xFFFF0008` the moment *any*
  cell in the table is edited. (RF-597)
- **The reading-routine combo does nothing.** *Channel Definition → File Type* is
  ignored by the count-rate computation, which hard-codes container
  auto-detection. Switching `SPC-130` → `SPC-600_256` on
  `BH_SPC630_256.spc` returns byte-identical results (110 597 photons,
  246.00 / 243.29 / 18453.18 / 18429.19 kHz) although `tttrlib` reads the file
  completely differently under the two routines (micro-time max 4095 vs 246;
  routing channels `0…15` vs `0, 2, 4, 6`). (RF-598)
- **Impossible count rates are reported as fact.** For that same shipped file the
  tool reports **18 453 kHz on a single detector** (99 644 kHz over the file) —
  the derived measurement time is `macro_times[-1] × macro_time_resolution` =
  2.96 ms for a file that holds 294 884 photons. Nothing warns, and **💾 Save**
  writes the number into the exported table. (RF-599)
- **The results table contradicts itself.** In the very same row, `Mean (kHz)`
  and `#Photons / Time (s)` disagree — `prompt_green` 21.40 vs 20.47,
  `prompt_red` 53.52 vs 51.20 — because `Mean` is the unweighted mean of the
  per-file rates while `Time (s)` is the *sum* over all files (75.143 s, repeated
  identically on every row). (RF-600)
- **A finished split looks like nothing happened.** After a run that really did
  write the files, the progress bar reads **0 %**, the status line reads
  **"Parsing …"** (still, 3.4 s later — the text is set by
  `staged_loading.load_with_progress` when the *input* was loaded and is never
  cleared), and there is no success message and no mention that the output went
  into a newly created sub-folder. (RF-601)
- **The header table gives the value column 100 px and the index column 604 px.**
  `setStretchLastSection(True)` is on *Idx* — one or two characters — so
  `CreatorName`, `FileTime`, `Comment` and `File_GUID` all render elided
  (`SymPhoTi…`, `Created o…`) in the one column the user came to edit.
  (RF-602)
- **ALEX conversion silently overwrites a real micro-time axis.** Loading a PTU
  that carries a 32 768-channel TCSPC micro-time and pressing *Save* writes a
  file whose maximum micro-time is 7 999 — the TCSPC axis is gone, with no
  warning and nothing on the panel that says the input already had one.
  (RF-603)

**Layout notes.** The *Results* pane clips its 6th row into a scrollbar while
leaving ~550 px of empty grey below it. In the *Detectors* table the headers
truncate to `icro Time Range` and `-Factor Channe`. A stale persisted dock layout
(from an earlier session, `sizes: [954, 0]`) rendered the whole right-hand column
of Count Rate Analysis at zero width — plot axis labels overprinted as
`0.2.4.6.8`, table headers as `an n (| (k ot ne` — with no visible way to reset
the layout; deleting `~/.chisurf/plugin_tttr_count_rate_analysis_settings.ini`
restored the (good) default.

## UX / UI suggestions

- **Say what happened.** Every write action in this window ends in silence:
  the splitter's bar returns to 0 %, the count-rate *Calculate* leaves the view on
  the *Channel Definition* tab. A one-line result banner — "8 files written to
  …/PQ_Olympus_MFIS" , "6 channels over 8 files" — plus switching to the tab that
  holds the new result would remove all of it.
- **Show what is loaded.** Neither the splitter nor the ALEX panel says anything
  about the file it just read. A single line (`15 604 430 photons · 75.1 s ·
  32 768 µT channels · 4 routing channels`) is what the user needs to choose a
  chunk size or an ALEX period at all, and it fills the ~550 px of empty space
  those two panels currently show.
- **Put the ALEX histogram next to the ALEX controls.** *Period* and *Shift* are
  tuned by eye against the histogram, but the histogram is on a different tab, so
  every trial value costs two clicks. Same for the splitter: the *Input / Output*
  and *Split options* tabs together hold seven controls and would fit in one pane.
- **Units and idioms.** *Period* / *Shift* carry no unit (macro-time ticks?);
  *Photons/file* is in units of 1000 but reads `300 k` in a spin box whose arrows
  step by 1; the batch list of the splitter is labelled "PTU files (drop files or
  folders)" although the tool reads and writes every container `tttrlib` supports.
- **Default the split output away from the source folder.** *Output folder*
  pre-fills with the raw data's own directory, so the default action of the tool
  writes into the user's measurement folder.
- **Reconsider `Reset macro times` as a default-on.** Every chunk starts again at
  macro time 0 (verified: chunk 1 begins at 0), which destroys the absolute time
  axis and with it any chance to stitch the chunks or timestamp them against the
  experiment log.
- **Let the results table breathe** — expanding the table (or the plot) into the
  pane's spare vertical space, and dropping the repeated `Time (s)` column into
  the pane caption, would show all six channels without a scrollbar.
- **Offer a "reset layout" action** on the dock area's context menu: a persisted
  layout can restore panes at zero width and the tool then looks broken.
- **Give the count-rate plot the file names.** The x-axis is a bare *File index*;
  a QC sweep over 40 files cannot be acted on until you can tell which file is
  the outlier.

## Bugs filed

- RF-596 — header save drops `tyBinaryBlob` tags, breaking CLSM reconstruction
  (also hits Split / Convert).
- RF-597 — *Add* creates a tag typed `Empty`, whose value is lost on save;
  unmapped tag types are coerced on the first edit.
- RF-598 — the Count Rate Analysis reading-routine (*File Type*) combo has no
  effect on the computation.
- RF-599 — no plausibility guard on the derived measurement time; 18 453 kHz per
  detector reported and exported for a shipped file.
- RF-600 — `Mean (kHz)` and `#Photons / Time (s)` disagree in the same table row.
- RF-601 — after a successful split the progress bar reads 0 % and the status
  line is stuck on "Parsing …"; no success feedback.
- RF-602 — the header table stretches *Idx* (604 px) and elides *Value* (100 px).
- RF-603 — ALEX conversion overwrites an existing TCSPC micro-time axis without
  warning.
