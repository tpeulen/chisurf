# emtk port report — `trace_browser` (final plugin report, cards T0 to T4)

Written by the implementing agent (Sonnet) for cards T0-T4; the agent could not write this file, so the reviewer saved the
essentials and appended the review. Per-card reports with their reviews stay beside it: [T0 model](REPORT-T0.md), [T1 Setup
stage](REPORT-T1.md), [T2 Browser stage](REPORT-T2.md), [T3a Qt-free binner](REPORT-T3a.md), [T3b plot, annotation,
precompute](REPORT-T3b.md).

## Header

| Field | Value |
|---|---|
| Plugin | `trace_browser` / `chisurf/plugins/tttr/trace_browser` |
| Port type | B (Qt only): no emtk app existed; model, spec and app written in cards T0-T4 |
| Commits | T0 `0e11d4c08`, `f37e4b392`; T1 `73c12c9e5`; T2 `afb048248`, `3584ced70`, `60716e89b`; T3a `2b37e2f91`; T3b `fd040fd96`, `2714a2274`; T4 `14b2474c2` (export, delete, hand-offs, help, guide), `12ead5009` (docs), `adcb725e3` (manifest entry + preview gate), `740ed5f66` (evidence); reviewer fixes `2ed20903b`, `3e65cdcc9` |
| Status | `entrypoints.emtk` declared; `trace_browser` is in `emtk_preview.json`: **the Qt tool stays the default** (see Review) |

## What the emtk window does (all cards)

Setup page (shared channel-definition editor, Continue / Back) -> Browser page: folder open and drop, include-subfolders (really
rescans), rating filter, bin window, y range, file table (`data_table`: File, Rating 0..3, Size, Notes; multi-selection with Select
all), the binned trace plot with Sum and a log-counts histogram (Qt-free binner, display-only decimation), the annotation box synced
with the Notes column, precompute as a visible job with Stop, Export (equal-bytes copies, no overwrites), CSV (identical bytes to the
Qt tool), DOCX (button disabled when `python-docx` is missing), Delete with an in-app confirmation to `.trash`, HMM / TW / NDX
hand-offs, Help window and a 13-step guided tour, settings persistence. Docs page 22, its figure and a README describe it.

## Evidence and tests (T4, manifest entry in place)

```
$ python -m pytest chisurf/plugins/tttr/trace_browser -q -p no:cacheprovider
167 passed, 6 warnings in 77.76s        (re-run by the reviewer; 129 before T4 + 38 new)
after: 39 controls, 0 without tooltip, qt-free      compare: lost [] / stale_explanations [] / explained 96 / exit 0
test/core/test_emtk_preview_gate.py + test/gui/test_emtk_port_parity.py: 20 passed
```

Deliberate breakage (export copying every row; delete without the "inside the open folder" guard): five tests failed, restored.
Screenshots (empty, populated, multi-selection, delete confirmation, export dialog, help window, guide steps, 800x600, no-host) were
read at full size; two defects found that way (a confirmation window without title, a clipped guide hint) are fixed.

## Deliberate differences of the whole port (summary; the full table is in `T4/deliberate.json` and the card reports)

Rating is an integer 0..3 cell (the Qt star widget has 3 stars; `data_table` has no choice cell); the Subfolders checkbox works;
stacked series rows are one overlaid plot with a legend and a Sum series; equal y limits mean "fit the data"; precompute and delete
confirmation are in-app, not modal dialogs; Export, CSV and DOCX act on the selection and Export never overwrites a same-name file;
the DOCX picture is a matplotlib plot of the loaded trace; the shared setup editor has ten fewer tttrlib container names; remembered
state is larger than Qt's (dock geometry only).

## Open items

1. **HMM / TW / NDX hand-offs do nothing in the real app**: they record a request and call `make_app(on_request=...)`, which no host
   supplies yet; without a host the three buttons are greyed. The Qt tool opened an Intensity Trace window, the Time Windows tool and
   ndX from the main window. This is a functional regression against the Qt tool.
2. `api/io.py:export_csv` labels the first column `time_ms` but holds seconds (one-word fix, pinned by a test).
3. `python-docx` is not installed on the test machine: DOCX ran only against a stand-in module.
4. emtk request: `DataTable` Ctrl/Shift-click and Ctrl+A.

## Review (reviewer, 2026-10-01)

Verified, not taken from the hand-over: 167 tests pass; `compare` exit 0 with `lost` `[]`; no Qt imports in `gui/app.py` /
`gui/model.py`; the real MMFDB file is untouched by the runs; the preview gate and parity tests pass. **The port is accepted as
complete except open item 1. The swap is NOT made**: the owner's rule is to swap only a fully functional emtk plugin, and three
of the Qt tool's features (HMM, time window, ndX) cannot be used from the emtk window in ChiSurf until a host fulfils the requests.
Card T5 (host adapter, Qt allowed because it only *hosts*) closes this; `trace_browser` leaves `emtk_preview.json` after T5 is
accepted.
